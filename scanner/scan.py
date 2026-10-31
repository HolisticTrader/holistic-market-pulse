"""Holistic ATR-multiple scanner (weekly) — "dots disappeared" + deep names.

Usage: python scanner/scan.py stocks_fx   (Friday: S&P 500 + forex)
       python scanner/scan.py crypto      (Sunday: top-100 crypto)

Indicator (Tony's TrendSpider "ATR multiple from MA"), WEEKLY bars, completed weeks only:
  ATR%     = Wilder ATR(15) / close * 100
  %fromSMA = (close - SMA50) / SMA50 * 100
  Multiple = %fromSMA / ATR%
Thresholds: stocks/forex 1.5, crypto 3.
  Dot printing: BUY multiple <= -th, SELL multiple >= +th.
  Dot DISAPPEARED (the trades): BUY last week <= -th and this week > -th;
                                SELL last week >= +th and this week < +th.

Mechanical levels (confirm on chart):
  entry = weekly close; stop = nearest weekly swing pivot (2 bars each side) at least
  MIN_GAP% away (stocks 5, forex 1.5, crypto 8); T1 = SMA50;
  T2 = nearest opposite pivot zone at least MIN_GAP% away. R:R from the close.
Output: scanner/out/<mode>/results.json  (education only)
"""
import json, os, sys, time, csv, io, datetime, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

ATR_LEN, MA_LEN, PIV, PEAK_WEEKS = 15, 50, 2, 8
TH = {"stock": 1.5, "forex": 1.5, "crypto": 3.0}
MIN_GAP = {"stock": 5.0, "forex": 1.5, "crypto": 8.0}
UA = {"User-Agent": "Mozilla/5.0"}
NOW = datetime.datetime.now(datetime.timezone.utc)

FX = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
      "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
      "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
      "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD", "NZDJPY", "NZDCHF", "NZDCAD",
      "CADJPY", "CADCHF", "CHFJPY",
      "USDMXN", "USDZAR", "USDNOK", "USDSEK", "USDTRY", "USDSGD", "ZARJPY", "MXNJPY"]
SKIP_COINS = {"USDT", "USDC", "DAI", "FDUSD", "USDE", "TUSD", "USDD", "PYUSD", "USDS", "USD1", "USDP", "GUSD",
              "FRAX", "LUSD", "USDX", "RLUSD", "USD0", "BUIDL", "USDTB", "USDF", "USDG", "SUSDE", "SUSDS",
              "WBTC", "WETH", "STETH", "WSTETH", "WEETH", "WBETH", "RETH", "CBBTC", "CBETH", "METH", "EZETH",
              "RSETH", "LBTC", "SOLVBTC", "JITOSOL", "MSOL", "BNSOL", "BSOL", "JUPSOL", "CLBTC", "TBTC",
              "XAUT", "PAXG", "BTCB", "OSETH", "LSETH", "SAVAX", "STKAAVE", "BFUSD", "SYRUPUSDC"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return r.read()
        except Exception:
            time.sleep(3 + 4 * i)
    return None


def sp500():
    raw = get("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv")
    if not raw:
        return []
    return [(r["Symbol"].replace(".", "-"), r.get("Security", ""))
            for r in csv.DictReader(io.StringIO(raw.decode("utf-8")))]


def top_crypto():
    raw = get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=120&page=1", 5)
    if not raw:
        return []
    out, seen = [], set()
    for c in json.loads(raw):
        s = c["symbol"].upper()
        price = c.get("current_price") or 0
        if s in SKIP_COINS or s in seen or ("USD" in s and 0.97 < price < 1.03):
            continue
        seen.add(s)
        out.append((f"{s}-USD", c["name"]))
        if len(out) >= 100:
            break
    return out


def week_complete(ts, cls):
    start = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    monday = (start - datetime.timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if start.weekday() >= 5:  # timestamp late Sunday UTC for some exchanges -> next Monday
        monday += datetime.timedelta(days=7)
    if cls == "crypto":
        return NOW >= monday + datetime.timedelta(days=7)
    return NOW >= monday + datetime.timedelta(days=4, hours=20)  # after Friday's US close


def weekly(sym, cls):
    for host in ("query1", "query2"):
        b = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=5y&interval=1wk")
        if not b:
            continue
        try:
            res = json.loads(b)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            bars = [(t, o, h, l, c) for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                    if None not in (o, h, l, c)]
            while bars and not week_complete(bars[-1][0], cls):
                bars.pop()
            return bars
        except Exception:
            continue
    return None


def levels(side, close, sma, o, h, l, c, piv_lo, piv_hi, g):
    """Mechanical stop/T1/T2 and R:R for a BUY or SELL at the weekly close."""
    r = {"stop": None, "t1": sma, "t2": None, "rr_t1": None, "rr_t2": None, "note": ""}
    if side == "BUY":
        lows = [l[i] for i in reversed(piv_lo) if l[i] < close * (1 - g)]
        tops = [min(o[i], c[i]) for i in reversed(piv_hi) if min(o[i], c[i]) > close * (1 + g)]
        if not lows:
            r["note"] = "no swing low below the min gap (price discovery down)"
            return r
        r["stop"] = lows[0]; risk = close - r["stop"]
        r["rr_t1"] = round((sma - close) / risk, 2) if sma > close else 0.0
        if tops:
            r["t2"] = min(tops); r["rr_t2"] = round((r["t2"] - close) / risk, 2)
    else:
        highs = [h[i] for i in reversed(piv_hi) if h[i] > close * (1 + g)]
        bots = [max(o[i], c[i]) for i in reversed(piv_lo) if max(o[i], c[i]) < close * (1 - g)]
        if not highs:
            r["note"] = "no swing high above the min gap (price discovery up)"
            return r
        r["stop"] = highs[0]; risk = r["stop"] - close
        r["rr_t1"] = round((close - sma) / risk, 2) if sma < close else 0.0
        if bots:
            r["t2"] = max(bots); r["rr_t2"] = round((close - r["t2"]) / risk, 2)
    return r


def analyze(sym, name, cls):
    bars = weekly(sym, cls)
    if not bars or len(bars) < MA_LEN + ATR_LEN + PEAK_WEEKS:
        return {"symbol": sym, "name": name, "class": cls, "error": "no data / too short"}
    ts = [b[0] for b in bars]; o = [b[1] for b in bars]; h = [b[2] for b in bars]
    l = [b[3] for b in bars]; c = [b[4] for b in bars]
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    atr = sum(tr[:ATR_LEN]) / ATR_LEN
    atrs = [None] * (ATR_LEN - 1) + [atr]
    for x in tr[ATR_LEN:]:
        atr = (atr * (ATR_LEN - 1) + x) / ATR_LEN
        atrs.append(atr)

    def mult(i):
        sma = sum(c[i - MA_LEN + 1:i + 1]) / MA_LEN
        pct = (c[i] - sma) / sma * 100
        return pct / (atrs[i] / c[i] * 100), pct, sma, atrs[i] / c[i] * 100

    n = len(c) - 1
    m, pct, sma, atrp = mult(n)
    mprev = mult(n - 1)[0]
    window = [mult(i)[0] for i in range(n - PEAK_WEEKS + 1, n + 1)]
    th, g = TH[cls], MIN_GAP[cls] / 100
    close = c[-1]
    piv_lo = [i for i in range(PIV, len(c) - PIV) if all(l[i] <= l[j] for j in range(i - PIV, i + PIV + 1))]
    piv_hi = [i for i in range(PIV, len(c) - PIV) if all(h[i] >= h[j] for j in range(i - PIV, i + PIV + 1))]

    if mprev <= -th and m > -th:
        state, side = "BUY_DOT_ENDED", "BUY"
    elif mprev >= th and m < th:
        state, side = "SELL_DOT_ENDED", "SELL"
    elif m <= -th:
        state, side = "BUY_DOT_PRINTING", "BUY"
    elif m >= th:
        state, side = "SELL_DOT_PRINTING", "SELL"
    else:
        state, side = "-", None

    row = {"symbol": sym, "name": name, "class": cls,
           "week_of": datetime.datetime.fromtimestamp(ts[-1], datetime.timezone.utc).strftime("%Y-%m-%d"),
           "close": close, "multiple": round(m, 2), "multiple_prev": round(mprev, 2),
           "peak_8w": round(min(window) if side == "BUY" else max(window), 2) if side else None,
           "pct_from_sma": round(pct, 2), "atr_pct": round(atrp, 2), "sma50": sma, "state": state, "side": side}
    if side:
        row.update(levels(side, close, sma, o, h, l, c, piv_lo, piv_hi, g))
        row["passes_3to1"] = bool(row["rr_t1"] is not None and row["rr_t1"] >= 3)
        row["a_grade"] = bool(row["passes_3to1"] and row["rr_t2"] is not None and row["rr_t2"] >= 3)
    return row


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "stocks_fx").strip()
    if mode == "crypto":
        uni = [(s, n, "crypto") for s, n in top_crypto()]
    else:
        mode = "stocks_fx"
        uni = [(s, n, "stock") for s, n in sp500()] + [(f"{p}=X", p, "forex") for p in FX]
    print(f"mode {mode} universe {len(uni)}", flush=True)
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda a: analyze(*a), uni))
    ok = [r for r in rows if "error" not in r]

    ended = [r for r in ok if r["state"].endswith("DOT_ENDED")]
    trades = sorted([r for r in ended if r["passes_3to1"]], key=lambda r: -abs(r["peak_8w"]))
    deep = {}
    for cls in sorted({r["class"] for r in ok}):
        p = [r for r in ok if r["class"] == cls]
        deep[cls] = {
            "buys": sorted([r for r in p if r["state"] == "BUY_DOT_PRINTING"], key=lambda r: r["multiple"])[:10],
            "sells": sorted([r for r in p if r["state"] == "SELL_DOT_PRINTING"], key=lambda r: -r["multiple"])[:10],
        }
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", mode)
    os.makedirs(out_dir, exist_ok=True)
    meta = {"mode": mode, "run_utc": NOW.isoformat(timespec="seconds"), "universe": len(uni), "scanned": len(ok),
            "failed": [r["symbol"] for r in rows if "error" in r],
            "week_of": max((r["week_of"] for r in ok), default=None),
            "thresholds": TH, "min_gap_pct": MIN_GAP,
            "counts": {"dots_ended": len(ended), "dots_ended_3to1": len(trades),
                       "buy_printing": sum(r["state"] == "BUY_DOT_PRINTING" for r in ok),
                       "sell_printing": sum(r["state"] == "SELL_DOT_PRINTING" for r in ok)}}
    json.dump({"meta": meta, "trades_3to1": trades, "dots_ended_all": ended, "deep_names": deep, "all": ok},
              open(os.path.join(out_dir, "results.json"), "w"), indent=1)
    print(json.dumps(meta["counts"]), flush=True)
    for r in trades:
        print("TRADE", r["class"], r["symbol"], r["side"], r["peak_8w"], r["rr_t1"], r["rr_t2"])


if __name__ == "__main__":
    main()
