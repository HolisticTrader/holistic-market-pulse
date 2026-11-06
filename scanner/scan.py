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
  MIN_GAP% away (stocks 5, forex 1.5, crypto 8); T1 = nearest OPPOSING zone (supply for buys,
  demand for sells) at least MIN_GAP% away; T2 = the next opposing zone. 50-week SMA is context only.
  R:R from the close to the near edge of the zone.
Output: scanner/out/<mode>/results.json  (education only)
"""
import json, os, sys, time, csv, io, datetime, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

ATR_LEN, MA_LEN, PIV, PEAK_WEEKS = 15, 50, 2, 8
ZPIV = 5  # target zones come from MAJOR swings: 5 weekly bars each side (stops use 2)
TH = {"stock": 1.5, "forex": 1.5, "crypto": 3.0}
MIN_GAP = {"stock": 5.0, "forex": 1.5, "crypto": 8.0}
UA = {"User-Agent": "Mozilla/5.0"}
SERIES = {}
RAW = "https://raw.githubusercontent.com/HolisticTrader/holistic-market-pulse/scanner/scanner/"
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


def week_monday(ts):
    start = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    monday = (start - datetime.timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if start.weekday() == 6 and start.hour >= 20:  # forex week opens Sunday evening UTC -> belongs to next Monday's week
        monday += datetime.timedelta(days=7)
    return monday


def week_complete(ts, cls):
    monday = week_monday(ts)
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


def levels(side, close, sma, o, h, l, c, piv_lo, piv_hi, g, zlo, zhi):
    """Mechanical stop and targets for a BUY or SELL at the weekly close (Tony: targets are the opposing zones).
    BUY : stop = nearest weekly swing low at least g below; supply zones = MAJOR pivot-high candles (ZPIV bars each side) [body top, high];
          T1 = near edge of the nearest supply zone at least g above, T2 = the next supply zone above that.
    SELL: mirror with demand zones = pivot-low candles [low, body bottom]."""
    r = {"stop": None, "t1": None, "t1_far": None, "t2": None, "t2_far": None, "rr_t1": None, "rr_t2": None, "note": ""}

    def merge(zones, up):
        zones = sorted(zones, key=lambda z: z[0] if up else -z[1])
        out = []
        for z in zones:
            if out and ((up and z[0] <= out[-1][1]) or (not up and z[1] >= out[-1][0])):
                out[-1] = (min(out[-1][0], z[0]), max(out[-1][1], z[1]))
            else:
                out.append(z)
        return out

    if side == "BUY":
        lows = [l[i] for i in reversed(piv_lo) if l[i] < close * (1 - g)]
        zones = merge([(max(o[i], c[i]), h[i]) for i in zhi if max(o[i], c[i]) > close * (1 + g)], True)
        if not lows:
            r["note"] = "no swing low below the min gap (price discovery down)"
            return r
        r["stop"] = lows[0]; risk = close - r["stop"]
        if not zones:
            r["note"] = "no supply zone above (price discovery up)"
            return r
        r["t1"], r["t1_far"] = zones[0]
        r["rr_t1"] = round((r["t1"] - close) / risk, 2)
        if len(zones) > 1:
            r["t2"], r["t2_far"] = zones[1]
            r["rr_t2"] = round((r["t2"] - close) / risk, 2)
    else:
        highs = [h[i] for i in reversed(piv_hi) if h[i] > close * (1 + g)]
        zones = merge([(l[i], min(o[i], c[i])) for i in zlo if min(o[i], c[i]) < close * (1 - g)], False)
        if not highs:
            r["note"] = "no swing high above the min gap (price discovery up)"
            return r
        r["stop"] = highs[0]; risk = r["stop"] - close
        if not zones:
            r["note"] = "no demand zone below (price discovery down)"
            return r
        r["t1_far"], r["t1"] = zones[0]
        r["rr_t1"] = round((close - r["t1"]) / risk, 2)
        if len(zones) > 1:
            r["t2_far"], r["t2"] = zones[1]
            r["rr_t2"] = round((close - r["t2"]) / risk, 2)
    return r


def yahoo_alias(sym):
    """Yahoo lists many coins under a numbered symbol (UNI7083-USD). Look it up."""
    base = sym.split("-")[0]
    b = get(f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(base + ' USD')}&quotesCount=10&newsCount=0", 2)
    if not b:
        return None
    try:
        for q in json.loads(b).get("quotes", []):
            s = q.get("symbol", "")
            if q.get("quoteType") == "CRYPTOCURRENCY" and s.endswith("-USD") and s.split("-")[0].rstrip("0123456789") == base:
                return s
    except Exception:
        pass
    return None


def analyze(sym, name, cls):
    bars = weekly(sym, cls)
    if cls == "crypto" and (not bars or len(bars) < MA_LEN + ATR_LEN + PEAK_WEEKS):
        alt = yahoo_alias(sym)
        if alt and alt != sym:
            alt_bars = weekly(alt, cls)
            if alt_bars and len(alt_bars) > len(bars or []):
                sym, bars = alt, alt_bars
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
    zlo = [i for i in range(ZPIV, len(c) - ZPIV) if all(l[i] <= l[j] for j in range(i - ZPIV, i + ZPIV + 1))]
    zhi = [i for i in range(ZPIV, len(c) - ZPIV) if all(h[i] >= h[j] for j in range(i - ZPIV, i + ZPIV + 1))]

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
           "week_of": week_monday(ts[-1]).strftime("%Y-%m-%d"),
           "close": close, "multiple": round(m, 2), "multiple_prev": round(mprev, 2),
           "peak_8w": round(min(window) if side == "BUY" else max(window), 2) if side else None,
           "pct_from_sma": round(pct, 2), "atr_pct": round(atrp, 2), "sma50": sma, "state": state, "side": side}
    if side:
        k = min(80, n - MA_LEN - ATR_LEN)
        idx = list(range(n - k + 1, n + 1))
        SERIES[sym] = {"ts": [ts[i] for i in idx], "o": [o[i] for i in idx], "h": [h[i] for i in idx],
                       "l": [l[i] for i in idx], "c": [c[i] for i in idx],
                       "sma": [mult(i)[2] for i in idx], "m": [mult(i)[0] for i in idx]}
        row.update(levels(side, close, sma, o, h, l, c, piv_lo, piv_hi, g, zlo, zhi))
        row["passes_3to1"] = bool(row["rr_t1"] is not None and row["rr_t1"] >= 3)
        row["a_grade"] = bool(row["rr_t1"] is not None and row["rr_t1"] >= 5)
    return row


def chart(r, path):
    """Weekly candles, 50-week SMA, dots while the multiple is past the threshold, stop and T1 lines."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = SERIES.get(r["symbol"])
    if not d:
        return False
    G, R, W, BG = "#39FF14", "#FF3131", "#FFFFFF", "#000000"
    th = TH[r["class"]]
    x = list(range(len(d["c"])))
    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=110)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    for i in x:
        up = d["c"][i] >= d["o"][i]
        col = G if up else R
        ax.vlines(i, d["l"][i], d["h"][i], color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((i - 0.3, min(d["o"][i], d["c"][i])), 0.6,
                                   max(abs(d["c"][i] - d["o"][i]), 1e-12), color=col))
    ax.plot(x, d["sma"], color="#BBBBBB", linewidth=1.1, linestyle="--", label="50-week SMA")
    rng = max(d["h"]) - min(d["l"])
    for i in x:
        if d["m"][i] <= -th:
            ax.scatter(i, d["l"][i] - rng * 0.04, s=10, color=G, zorder=3)
        elif d["m"][i] >= th:
            ax.scatter(i, d["h"][i] + rng * 0.04, s=10, color=R, zorder=3)
    if r.get("stop"):
        ax.axhline(r["stop"], color=R, linewidth=0.9, linestyle=":")
        ax.text(x[0], r["stop"], " stop", color=R, fontsize=7, va="bottom")
    tcol = G if r["side"] == "BUY" else R
    for lab, a, b in (("T1", r.get("t1"), r.get("t1_far")), ("T2", r.get("t2"), r.get("t2_far"))):
        if a is not None and b is not None:
            ax.axhspan(min(a, b), max(a, b), color=tcol, alpha=0.18, linewidth=0)
            ax.text(x[0], a, f" {lab} zone", color=tcol, fontsize=7, va="bottom")
    ys = d["l"] + d["h"] + [v for v in (r.get("stop"), r.get("t1"), r.get("t1_far")) if v is not None]
    span = max(ys) - min(ys)
    for v in (r.get("t2"), r.get("t2_far")):
        if v is not None and min(ys) - span * 0.5 <= v <= max(ys) + span * 0.5:
            ys.append(v)
    pad = (max(ys) - min(ys)) * 0.06
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    if r["state"].endswith("ENDED"):
        ax.axvline(x[-1], color=W, linewidth=0.6, alpha=0.4)
    tick = r["symbol"].replace("=X", "").replace("-USD", "")
    status = "dot ended" if r["state"].endswith("ENDED") else "dot printing"
    ax.set_title(f"{tick}  ·  weekly  ·  {r['side']} {status}  ·  multiple {r['multiple']}", color=W, fontsize=10, loc="left")
    ax.text(0.99, 0.02, "Holistic Trader", transform=ax.transAxes, color="#666666", fontsize=7, ha="right")
    ax.tick_params(colors="#888888", labelsize=7)
    ax.set_xticks([])
    for sp in ax.spines.values():
        sp.set_color("#333333")
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return True


WATCH_DEFAULT = ["SPY|SPY", "QQQ|QQQ", "DXY|DX-Y.NYB", "GOLD|GC=F"]


def watch_bars(out_dir):
    """Weekly OHLC for Tony's board calls + index/macro (scanner/watch.txt: LABEL|YAHOO per line).
    Uses the current week's bar even if incomplete, so Friday runs see this week's high/low."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch.txt")
    lines = list(WATCH_DEFAULT)
    if os.path.exists(path):
        lines += [ln.strip() for ln in open(path) if "|" in ln and not ln.strip().startswith("#")]
    seen, rows = set(), []
    for ln in lines:
        label, sym = [x.strip() for x in ln.split("|", 1)]
        if sym in seen:
            continue
        seen.add(sym)
        row = {"label": label, "symbol": sym}
        b = None
        for host in ("query1", "query2"):
            b = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1mo&interval=1d")
            if b:
                break
        try:
            res = json.loads(b)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            off = res["meta"].get("gmtoffset", 0) or 0
            days = [(t + off, o, h, l, c) for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                    if None not in (o, h, l, c)]
            weeks = {}
            for t, o, h, l, c in days:  # group daily bars by Monday-start week (exchange-local time)
                wk = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
                      - datetime.timedelta(days=datetime.datetime.fromtimestamp(t, datetime.timezone.utc).weekday()))
                w = weeks.setdefault(wk, [o, h, l, c])
                w[1], w[2], w[3] = max(w[1], h), min(w[2], l), c
            keys = sorted(weeks)
            wk = keys[-1]
            o, h, l, c = weeks[wk]
            prev = weeks[keys[-2]][3] if len(keys) > 1 else None
            row.update({"week_of": wk.isoformat(), "days_in_week": sum(
                1 for t, *_ in days if datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date() >= wk),
                "open": round(o, 5), "high": round(h, 5),
                        "low": round(l, 5), "close": round(c, 5), "prev_close": round(prev, 5) if prev else None,
                        "pct_vs_prev_close": round((c / prev - 1) * 100, 2) if prev else None,
                        "pct_open_to_close": round((c / o - 1) * 100, 2),
                        "last_price": res["meta"].get("regularMarketPrice")})
        except Exception as e:
            row["error"] = f"couldn't read Yahoo: {type(e).__name__}"
        rows.append(row)
    json.dump({"run_utc": NOW.isoformat(timespec="seconds"), "rows": rows},
              open(os.path.join(out_dir, "watch.json"), "w"), indent=1)
    print(f"watch {len(rows)} symbols, {sum('error' in r for r in rows)} failed", flush=True)


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
    week = max((r["week_of"] for r in ok), default="na")
    chart_dir = os.path.join(out_dir, "charts", week)
    os.makedirs(chart_dir, exist_ok=True)
    picks = list(ended)
    for v in deep.values():
        picks += v["buys"][:3] + v["sells"][:3]
    for r in picks:
        fn = r["symbol"].replace("=", "_").replace("/", "_") + ".png"
        try:
            if chart(r, os.path.join(chart_dir, fn)):
                r["chart_url"] = f"{RAW}out/{mode}/charts/{week}/{fn}"
        except Exception as e:
            print("chart failed", r["symbol"], e, flush=True)
    meta = {"mode": mode, "run_utc": NOW.isoformat(timespec="seconds"), "universe": len(uni), "scanned": len(ok),
            "failed": [r["symbol"] for r in rows if "error" in r],
            "week_of": max((r["week_of"] for r in ok), default=None),
            "thresholds": TH, "min_gap_pct": MIN_GAP,
            "counts": {"dots_ended": len(ended), "dots_ended_3to1": len(trades),
                       "buy_printing": sum(r["state"] == "BUY_DOT_PRINTING" for r in ok),
                       "sell_printing": sum(r["state"] == "SELL_DOT_PRINTING" for r in ok)}}
    json.dump({"meta": meta, "trades_3to1": trades, "dots_ended_all": ended, "deep_names": deep, "all": ok},
              open(os.path.join(out_dir, "results.json"), "w"), indent=1)
    try:
        watch_bars(out_dir)
    except Exception as e:
        print("watch failed", e, flush=True)
    print(json.dumps(meta["counts"]), flush=True)
    for r in trades:
        print("TRADE", r["class"], r["symbol"], r["side"], r["peak_8w"], r["rr_t1"], r["rr_t2"])


if __name__ == "__main__":
    main()
