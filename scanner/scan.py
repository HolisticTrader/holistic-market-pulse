"""Holistic ATR-multiple scanner (weekly) with R:R filter.

Settings (Tony's stocks/forex): ATR 15, SMA 50, threshold +/-1.5, weekly bars.
  ATR%      = Wilder ATR(15) / close * 100
  %fromSMA  = (close - SMA50) / SMA50 * 100
  Multiple  = %fromSMA / ATR%
  BUY  (wholesale) when Multiple <= -1.5
  SELL (retail)    when Multiple >= +1.5

Levels are MECHANICAL (weekly swing pivots, 2 bars each side), not hand-drawn zones:
  BUY : stop = low of nearest pivot-low below close (touch)
        T1   = SMA50 (mean reversion)
        T2   = bottom of nearest pivot-high supply above close
  SELL: mirror.
  R:R = reward / risk from the weekly close.
Writes scanner/out/results.json and results.csv. Education only.
"""
import json, os, sys, time, csv, io, datetime, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

ATR_LEN, MA_LEN, TH, PIV = 15, 50, 1.5, 2
UA = {"User-Agent": "Mozilla/5.0"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

FX = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
      "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
      "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
      "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD", "NZDJPY", "NZDCHF", "NZDCAD",
      "CADJPY", "CADCHF", "CHFJPY",
      "USDMXN", "USDZAR", "USDNOK", "USDSEK", "USDTRY", "USDSGD", "ZARJPY", "MXNJPY"]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read()
        except Exception:
            time.sleep(2 + 2 * i)
    return None


def sp500():
    raw = get("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv")
    if not raw:
        return []
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    return [(r["Symbol"].replace(".", "-"), r.get("Security", "")) for r in rows]


def weekly(sym):
    for host in ("query1", "query2"):
        b = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=5y&interval=1wk")
        if not b:
            continue
        try:
            res = json.loads(b)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            bars = [(t, o, h, l, c) for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                    if None not in (o, h, l, c)]
            return bars
        except Exception:
            continue
    return None


def analyze(sym, name, cls):
    bars = weekly(sym)
    if not bars or len(bars) < MA_LEN + ATR_LEN + 5:
        return {"symbol": sym, "name": name, "class": cls, "error": "no data"}
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
        return pct / (atrs[i] / c[i] * 100), pct, sma

    m, pct, sma = mult(len(c) - 1)
    mprev = mult(len(c) - 2)[0]
    close = c[-1]
    # pivots on completed structure (exclude last PIV bars)
    piv_lo = [i for i in range(PIV, len(c) - PIV) if all(l[i] <= l[j] for j in range(i - PIV, i + PIV + 1))]
    piv_hi = [i for i in range(PIV, len(c) - PIV) if all(h[i] >= h[j] for j in range(i - PIV, i + PIV + 1))]
    sig = "BUY" if m <= -TH else "SELL" if m >= TH else "-"
    row = {"symbol": sym, "name": name, "class": cls, "date": datetime.datetime.utcfromtimestamp(ts[-1]).strftime("%Y-%m-%d"),
           "close": close, "multiple": round(m, 2), "multiple_prev": round(mprev, 2), "pct_from_sma": round(pct, 2),
           "sma50": sma, "signal": sig, "stop": None, "t1": None, "t2": None, "rr_t1": None, "rr_t2": None, "note": ""}
    if sig == "BUY":
        lows = [l[i] for i in reversed(piv_lo) if l[i] < close]
        highs = [min(o[i], c[i]) for i in reversed(piv_hi) if min(o[i], c[i]) > close]
        if not lows:
            row["note"] = "no pivot low below price (price discovery down)"
            return row
        stop = lows[0]; risk = close - stop
        row["stop"] = stop; row["t1"] = sma
        row["rr_t1"] = round((sma - close) / risk, 2) if risk > 0 else None
        if highs:
            t2 = min(highs); row["t2"] = t2
            row["rr_t2"] = round((t2 - close) / risk, 2) if risk > 0 else None
    elif sig == "SELL":
        highs = [h[i] for i in reversed(piv_hi) if h[i] > close]
        lows = [max(o[i], c[i]) for i in reversed(piv_lo) if max(o[i], c[i]) < close]
        if not highs:
            row["note"] = "no pivot high above price (price discovery up)"
            return row
        stop = highs[0]; risk = stop - close
        row["stop"] = stop; row["t1"] = sma
        row["rr_t1"] = round((close - sma) / risk, 2) if risk > 0 else None
        if lows:
            t2 = max(lows); row["t2"] = t2
            row["rr_t2"] = round((close - t2) / risk, 2) if risk > 0 else None
    return row


def main():
    uni = [(s, n, "stock") for s, n in sp500()] + [(f"{p}=X", p, "forex") for p in FX]
    print(f"universe {len(uni)}", flush=True)
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda a: analyze(*a), uni))
    ok = [r for r in rows if "error" not in r]
    print(f"scanned {len(ok)} / {len(uni)}", flush=True)
    meta = {"run": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z", "universe": len(uni), "scanned": len(ok),
            "failed": [r["symbol"] for r in rows if "error" in r]}
    json.dump({"meta": meta, "rows": ok}, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    keys = list(ok[0].keys())
    with open(os.path.join(OUT, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(ok)
    for r in sorted([r for r in ok if r["signal"] != "-"], key=lambda r: r["multiple"]):
        print(r["class"], r["symbol"], r["signal"], r["multiple"], r["rr_t1"], r["rr_t2"])


if __name__ == "__main__":
    main()
