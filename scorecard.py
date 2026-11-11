#!/usr/bin/env python3
"""Trade Alert Scorecard: refresh prices and post an @everyone update to #general.

Runs on GitHub Actions (no computer needed). Reads and rewrites scorecard/trade_alerts.csv,
the same table that feeds the Trade Alert Scorecard dashboard on claude.ai.

Usage: python scorecard.py "Pre-market" | "Midday" | "Market close"   (any label works)
       add --dry-run to print the post without sending it.

Tony's rules (Nov 10, 2026):
- 1% ($1,000) risk per call on a $100K account.
- Stops and targets count on a TOUCH of the daily high/low since the post.
- Take-profit (fib drawn 0 = wholesale low, 1 = retail high): long T1 = 0.618 (start of retail),
  full TP = 1; short T1 = 0.382 (start of wholesale), full TP = 0. Runner may run to the 1.618.
  The t1 column holds that published 0.618 / 0.382 level.
- At T1: close half, move the runner's stop to entry. Runner touching entry closes the trade.
- Status: T1 hit / In profit / Flat (|R| < 0.15) / Under water / Stopped out.
- Closed trades ("Trade closed" in the note) stay frozen. Never move a published stop.
"""
import csv, datetime, json, os, sys, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

try:
    import netretry  # noqa: F401  (retries flaky network calls)
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "scorecard", "trade_alerts.csv")
STATE = os.path.join(HERE, "state", "scorecard.json")
DASH = "https://claude.ai/artifact/EnTHR6qGgprpY9ka38ogBn"
UA = {"User-Agent": "Mozilla/5.0 (HolisticScorecard)"}
START, RISK = 100000, 1000

# NYSE closed all day (no post). Early 1 PM closes still post.
HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
            "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}

SYMBOL = {"USD/MXN": "MXN=X", "USD/NOK": "NOK=X", "USD/CAD": "CAD=X", "USD/JPY": "JPY=X",
          "USD/CHF": "CHF=X", "USD/ZAR": "ZAR=X", "USD/SEK": "SEK=X", "SPX": "^GSPC",
          "NDX": "^NDX", "DJI": "^DJI", "XAU/USD": "GC=F", "BTC": "BTC-USD", "ETH": "ETH-USD"}


def ysym(pair):
    if pair in SYMBOL:
        return SYMBOL[pair]
    if "/" in pair and len(pair) == 7:
        return pair.replace("/", "") + "=X"
    return pair.lstrip("$")


def quote(pair):
    """Return (last, [(date, high, low), ...]) for the last few days, or None."""
    sym = urllib.parse.quote(ysym(pair))
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                res = json.load(r)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            days = []
            for t, h, l in zip(res["timestamp"], q["high"], q["low"]):
                if h is not None and l is not None:
                    days.append((datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat(), h, l))
            last = res["meta"].get("regularMarketPrice")
            if last is not None and days:
                return last, days
        except Exception as e:  # try the other host
            print(f"# quote {pair} via {host} failed: {e}", file=sys.stderr)
    return None


def dp(s):
    return len(s.split(".")[1]) if "." in s else 0


def num(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def refresh(rows, today, since):
    """Update every open call in place. Returns change lines for the post."""
    changes, missing = [], []
    for r in rows:
        if "Trade closed" in (r.get("note") or ""):
            continue
        try:
            e, s = float(r["entry"]), float(r["stop"])
        except ValueError:
            missing.append(r["pair"])
            continue
        q = quote(r["pair"])
        if not q:
            missing.append(r["pair"])
            continue
        last, days = q
        short = r["direction"].lower() == "short"
        sg = -1 if short else 1
        risk = abs(e - s)
        hi = max([num(r["high_since"], -1e18)] + [h for d, h, l in days if d >= r["alert_date"]])
        lo = min([num(r["low_since"], 1e18)] + [l for d, h, l in days if d >= r["alert_date"]])
        side = r["direction"].lower()
        t1 = num(r["t1"], None) if r.get("t1") else None

        if r["status"] == "T1 hit":
            # runner: stop sits at entry
            recent = [(h, l) for d, h, l in days if d >= since]
            touched = any((short and h >= e) or (not short and l <= e) for h, l in recent)
            if touched or (short and last >= e) or (not short and last <= e):
                r["open_r"] = "0"
                r["risk_on"] = "0"
                r["r_now"] = f"{num(r['banked_r']):.2f}"
                r["note"] = (r["note"] + f" Runner stop at entry hit {today}. Trade closed.").strip()
                changes.append(f"🔒 RUNNER CLOSED AT ENTRY: {r['pair']} {side}")
            else:
                o = 0.5 * sg * (last - e) / risk
                r["open_r"] = f"{o:.2f}"
                r["r_now"] = f"{num(r['banked_r']) + o:.2f}"
        else:
            stop_hit = (short and hi >= s) or (not short and lo <= s)
            t1_hit = t1 is not None and ((short and lo <= t1) or (not short and hi >= t1))
            if stop_hit and not t1_hit:
                r.update(status="Stopped out", banked_r="-1", open_r="0", r_now="-1.00", risk_on="0",
                         note=(r["note"] + f" Stopped {today}. Trade closed.").strip())
                changes.append(f"❌ STOP HIT: {r['pair']} {side}")
            elif t1_hit:
                banked = 0.5 * abs(t1 - e) / risk
                o = 0.5 * sg * (last - e) / risk
                r.update(status="T1 hit", banked_r=f"{banked:.2f}", open_r=f"{o:.2f}",
                         r_now=f"{banked + o:.2f}", risk_on="0",
                         note=(r["note"] + f" Half closed at T1 {r['t1']} on {today}; runner stop moved to entry.").strip())
                changes.append(f"🎯 T1 HIT: {r['pair']} {side} ({banked:+.2f}R banked)")
            else:
                R = sg * (last - e) / risk
                r["r_now"] = r["open_r"] = f"{R:.2f}"
                r["status"] = "Flat" if abs(R) < 0.15 else ("In profit" if R > 0 else "Under water")

        r["price_now"] = f"{last:.{max(dp(r['price_now']), 2)}f}"
        r["high_since"] = f"{hi:.{max(dp(r['high_since']), 2)}f}"
        r["low_since"] = f"{lo:.{max(dp(r['low_since']), 2)}f}"
        r["move_pct"] = f"{sg * (last - e) / e * 100:.2f}"
    return changes, missing


def build(rows, label, now, extra):
    equity = START + sum((num(r["banked_r"]) + num(r["open_r"])) * RISK for r in rows)
    pct = (equity - START) / START * 100
    c = {k: sum(1 for r in rows if r["status"] == k) for k in ("T1 hit", "In profit", "Flat", "Under water", "Stopped out")}
    live = [r for r in rows if "Trade closed" not in (r.get("note") or "")] or rows
    best = max(live, key=lambda r: num(r["r_now"]))
    worst = min(live, key=lambda r: num(r["r_now"]))
    fr = lambda v: ("+" if num(v) > 0 else "") + f"{num(v):.2f}R"
    sign = "+" if pct >= 0 else "−"
    lines = [
        "@everyone",
        f"📊 SCORECARD UPDATE | {label} | {now.strftime('%b')} {now.day}",
        f"💰 $100K account (1% risk/call): ${equity:,.0f} ({sign}{abs(pct):.2f}%)",
        f"🎯 T1 hit {c['T1 hit']} | 🐂 In profit {c['In profit']} | 😐 Flat {c['Flat']} | 🐻 Under water {c['Under water']} | ❌ Stopped {c['Stopped out']}",
        f"🔥 Best: {best['pair']} {fr(best['r_now'])} | 🧊 Worst: {worst['pair']} {fr(worst['r_now'])}",
        *extra,
        f"Live scorecard 👉 {DASH}",
        "Education only. Not financial advice.",
    ]
    return "\n".join(lines)[:1990]


PUBLIC_COLS = ["alert_date", "pair", "direction", "status", "r_now", "banked_r", "open_r", "risk_on", "card", "note"]
PUBLIC_PATH = os.path.join(HERE, "scorecard", "public.csv")


def public_note(r):
    """A note with no price levels (entry, stop and targets stay behind the Substack paywall)."""
    closed = "Trade closed" in (r.get("note") or "")
    if r["status"] == "T1 hit":
        head = f"Half closed at T1 ({num(r['banked_r']):+.2f}R banked); "
        return head + ("runner stopped out at entry. Trade closed." if closed else "runner still open with its stop at entry.")
    if r["status"] == "Stopped out":
        return "Stopped out. Trade closed."
    if (r.get("stop_basis") or "").lower().startswith("assumed"):
        return "No stop was published; the scorecard uses the prior weekly candle."
    return ""


def write_public(rows):
    """The dashboard's public copy: results only, no levels."""
    with open(PUBLIC_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PUBLIC_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r.get(k, "") for k in PUBLIC_COLS}, "note": public_note(r)})


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    label = args[0] if args else "Update"
    now = datetime.datetime.now(ZoneInfo("America/New_York"))
    today = now.date().isoformat()
    if now.weekday() >= 5 or today in HOLIDAYS:
        print(f"Market closed today ({today}): no scorecard post.")
        return

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols, rows = rd.fieldnames, list(rd)

    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    known = set(st.get("posted_pairs", []))

    changes, missing = refresh(rows, today, (st.get('last_post') or today)[:10])
    new = [f"🆕 NEW CALL: {r['pair']} {r['direction'].lower()}" for r in rows
           if known and f"{r['alert_date']}|{r['pair']}" not in known]
    text = build(rows, label, now, new + changes)
    print(text)
    if missing:
        print("# no fresh price for: " + ", ".join(missing), file=sys.stderr)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    write_public(rows)

    if dry:
        return
    hook = os.environ["DISCORD_WEBHOOK_URL"].rstrip("/")
    payload = {"content": text, "username": "Holistic Market Pulse", "allowed_mentions": {"parse": ["everyone"]}}
    req = urllib.request.Request(hook + "?wait=true", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("posted", r.status)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    st["posted_pairs"] = [f"{r['alert_date']}|{r['pair']}" for r in rows]
    st["last_post"] = now.isoformat(timespec="minutes")
    st["last_label"] = label
    json.dump(st, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    main()
