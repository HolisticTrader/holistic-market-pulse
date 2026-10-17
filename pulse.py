#!/usr/bin/env python3
"""Holistic Market Pulse: posts market updates to Discord via webhook.

Modes:
  python pulse.py board   -> edits ONE live board message (create it once, then pin it)
  python pulse.py pulse   -> posts a fresh market update with a discussion question
Env:
  DISCORD_WEBHOOK_URL  (required, keep secret)
  BOARD_MESSAGE_ID     (optional; set after first `board` run prints it)
Standard library only. Data: Yahoo Finance chart API (may be delayed).
"""
import json, os, sys, urllib.request, urllib.error, urllib.parse, datetime, random

FX = [("EURUSD=X","EUR/USD",5),("GBPUSD=X","GBP/USD",5),("USDJPY=X","USD/JPY",3),("DX-Y.NYB","DXY",2),
      ("GBPJPY=X","GBP/JPY",3),("AUDJPY=X","AUD/JPY",3),("CHFJPY=X","CHF/JPY",3),("NZDJPY=X","NZD/JPY",3),
      ("ZARJPY=X","ZAR/JPY",3),("AUDUSD=X","AUD/USD",5),("GBPAUD=X","GBP/AUD",5),("EURCHF=X","EUR/CHF",5),
      ("USDMXN=X","USD/MXN",4),("USDZAR=X","USD/ZAR",4),("USDNOK=X","USD/NOK",4),("GC=F","Gold",1)]
CRYPTO = [("BTC-USD","BTC",0),("ETH-USD","ETH",1),("SOL-USD","SOL",2)]
STOCKS = [("^GSPC","S&P 500",1),("^IXIC","Nasdaq",1),("^DJI","Dow",0),("^VIX","VIX",2)]

# Tony's open calls. Edit this list when calls change. None = not published.
CALLS = [
  # name, symbol, direction, target, invalidation
  ("GBP/JPY","GBPJPY=X","short",184.40,220.32),
  ("AUD/JPY","AUDJPY=X","short",110.0,113.0),  # T1 zone 100-110; T2 88-95
  ("CHF/JPY","CHFJPY=X","long",204.0,None),
  ("USD/MXN","USDMXN=X","long",18.80,17.50),
  ("USD/NOK","USDNOK=X","long",10.62,9.07),
  ("AUD/USD","AUDUSD=X","short",None,0.7421),
  ("GBP/AUD","GBPAUD=X","long",2.046,1.852),
  ("EUR/CHF","EURCHF=X","short",None,0.9445),
  ("NZD/JPY","NZDJPY=X","long",94.99,86.50),
  ("USD/ZAR","USDZAR=X","long",17.00,15.65),
]

UA = {"User-Agent": "Mozilla/5.0 (HolisticMarketPulse)"}

import functools
PERIODS = [("30D", 30), ("90D", 90), ("6M", 182), ("1Y", 365), ("YTD", None)]

@functools.lru_cache(maxsize=None)
def history(sym):
    """Latest price plus daily closes for the past year: (price, [(date, close), ...])."""
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1y&interval=1d"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                res = json.load(r)["chart"]["result"][0]
                closes = res["indicators"]["quote"][0]["close"]
                pts = [(datetime.date.fromtimestamp(t), c) for t, c in zip(res["timestamp"], closes) if c]
                return res["meta"]["regularMarketPrice"], pts
        except Exception:
            continue
    return None, []

def quote(sym):
    """(price, 1-WEEK % change): vs the last close at least 7 days ago."""
    p, pts = history(sym)
    if p is None or len(pts) < 2: return p, 0.0 if p else None
    cutoff = datetime.date.today() - datetime.timedelta(days=7)
    base = None
    for d, c in pts:
        if d <= cutoff: base = c
        else: break
    base = base or pts[0][1]
    return p, (p / base - 1) * 100

def perf(sym):
    """% change over each period in PERIODS, using the last close on/before the start date."""
    p, pts = history(sym)
    if p is None or not pts: return None, {}
    today = datetime.date.today()
    out = {}
    for label, days in PERIODS:
        start = datetime.date(today.year, 1, 1) if days is None else today - datetime.timedelta(days=days)
        base = None
        for d, c in pts:
            if d <= start: base = c
            else: break
        if base is None and days is None: base = next((c for d, c in pts if d >= start), None)
        out[label] = (p / base - 1) * 100 if base else None
    return p, out

import urllib.parse

def _px(p):
    return f"{p:.0f}" if p >= 1000 else f"{p:.2f}" if p >= 100 else f"{p:.3f}" if p >= 10 else f"{p:.4f}"

def _pc(v):
    if v is None: return "-"
    return f"{v:+.0f}" if abs(v) >= 10 else f"{v:+.1f}"

def table(rows):
    """Compact (~39 chars/row) so it doesn't wrap on phones."""
    lines = [f"{'':<7}{'Price':>7}" + "".join(f"{l:>5}" for l, _ in PERIODS)]
    for sym, name, d in rows:
        p, ch = perf(sym)
        if p is None:
            lines.append(f"{name[:7]:<7}{'n/a':>7}"); continue
        lines.append(f"{name.replace('/', '')[:7]:<7}{_px(p):>7}" + "".join(f"{_pc(ch.get(l)):>5}" for l, _ in PERIODS))
    return "```\n" + "\n".join(lines) + "\n```"

def movers(rows):
    out = []
    for sym, name, d in rows:
        p, c = quote(sym)
        if p is not None:
            out.append((name, c))
    return sorted(out, key=lambda x: abs(x[1]), reverse=True)


# ---------- Auto-tracked calls from #trade-alert and Substack ----------
import re, html
TRADE_ALERT_CHANNEL = os.environ.get("TRADE_ALERT_CHANNEL_ID", "1546270988100960297")
SUBSTACK_FEED = os.environ.get("SUBSTACK_FEED", "https://immaculatetonyeth.substack.com/feed")
TRADER_NAME = os.environ.get("TRADER_NAME", "immaculatetony").lower()
CCY = {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF","ZAR","MXN","NOK","SEK","DKK","SGD","HKD","TRY","PLN","CNH","HUF","CZK"}
CRYPTO_SYMS = {"BTC","ETH","SOL","XRP","ADA","DOGE","AVAX","LINK","DOT","LTC","BNB","MATIC","SUI"}
NUM = r"(\d+(?:,\d{3})*(?:\.\d+)?)"

def yahoo_symbol(t):
    t = t.upper().replace("/", "")
    if t in ("XAUUSD", "GOLD"): return "GC=F", "Gold"
    if t in ("XAGUSD", "SILVER"): return "SI=F", "Silver"
    if t in ("DXY",): return "DX-Y.NYB", "DXY"
    if len(t) == 6 and t[:3] in CCY and t[3:] in CCY: return t + "=X", t[:3] + "/" + t[3:]
    base = t[:-3] if t.endswith("USD") and t[:-3] in CRYPTO_SYMS else t[:-4] if t.endswith("USDT") else t
    if base in CRYPTO_SYMS: return base + "-USD", base
    return t, t

def _f(x): return float(x.replace(",", ""))

def parse_calls(text):
    """Find trade cards like:
    $USDJPY (Weekly) - Long | Entry: 155-156 | Target: T1 160 | Invalid: weekly close below 153.5
    Also 'Closed $USDJPY' removes a call. Returns list of (action, tuple)."""
    out = []
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    for m in re.finditer(r"(?i)\b(closed|close|exit(?:ed)?|out of|stopped out of|invalidated)\s*:?\s*\$([A-Za-z/]{3,10})", text):
        out.append(("close", m.group(2)))
    # split into chunks starting at each $TICKER
    for chunk in re.split(r"(?=\$[A-Za-z][A-Za-z/]{2,9}\b)", text):
        m = re.match(r"\$([A-Za-z/]{3,10})", chunk)
        if not m: continue
        chunk = chunk[:600]
        d = re.search(r"(?i)\b(long|short|buy|sell|bullish|bearish)\b", chunk)
        tg = re.search(r"(?i)\b(?:target|tp|t1)\b[^\n]{0,30}?(?<![A-Za-z\d.,])" + NUM, chunk)
        iv = re.search(r"(?i)\b(?:invalid(?:ation)?|stop(?:\s*loss)?|sl|wrong)\b[^\n]{0,40}?(?<![A-Za-z\d.,])" + NUM, chunk)
        if not d or not (tg or iv): continue
        side = "long" if d.group(1).lower() in ("long", "buy", "bullish") else "short"
        sym, name = yahoo_symbol(m.group(1))
        out.append(("open", (name, sym, side, _f(tg.group(1)) if tg else None, _f(iv.group(1)) if iv else None)))
    return out

def _get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")

def discord_alert_texts():
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not tok: return []
    try:
        msgs = json.loads(_get(f"https://discord.com/api/v10/channels/{TRADE_ALERT_CHANNEL}/messages?limit=100",
                               {"Authorization": f"Bot {tok}"}))
    except Exception as e:
        print("discord read failed:", e); return []
    texts = []
    for m in reversed(msgs):  # oldest first, so newer posts override
        a = m.get("author", {})
        who = (a.get("username", "") + " " + (a.get("global_name") or "")).lower()
        if a.get("bot") or TRADER_NAME not in who: continue
        body = m.get("content", "") + "\n" + "\n".join((e.get("description") or "") for e in m.get("embeds", []))
        texts.append((m.get("timestamp", ""), body))
    return texts

def substack_texts():
    try:
        xml = _get(SUBSTACK_FEED)
    except Exception as e:
        print("substack read failed:", e); return []
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)[:15]
    out = []
    for it in items:
        date = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
        body = (re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", it, re.S) or [None, ""])[1]
        try:
            ts = datetime.datetime.strptime(date.strip(), "%a, %d %b %Y %H:%M:%S %Z").isoformat()
        except Exception:
            ts = ""
        out.append((ts, body[:20000]))
    return out

def all_calls():
    calls = {c[1]: c for c in CALLS}
    feed = sorted(substack_texts() + discord_alert_texts(), key=lambda x: x[0])
    for _, text in feed:
        for action, val in parse_calls(text):
            if action == "close":
                calls.pop(yahoo_symbol(val)[0], None)
            else:
                calls[val[1]] = val
    return list(calls.values())

def calls_block():
    lines = []
    for name, sym, side, tgt, inv in all_calls()[-12:]:  # newest 12 to stay under Discord's 2000-char limit
        p, _ = quote(sym)
        if p is None:
            continue
        bits = [f"{name} {side} @ {p:.4g}"]
        if tgt is not None:
            dist = (tgt - p) / p * 100 * (1 if side == "long" else -1)
            bits.append("T1 hit ✅" if dist <= 0 else f"{dist:.1f}% to T1 ({tgt:g})")
        if inv is not None:
            room = (p - inv) / p * 100 * (1 if side == "long" else -1)
            bits.append("INVALIDATED ❌" if room <= 0 else f"{room:.1f}% from stop ({inv:g})")
        lines.append("• " + " | ".join(bits))
    return "\n".join(lines)

def now_ct():
    # Central Time label without external tz libs: use zoneinfo when available.
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Chicago")).strftime("%a %b %d, %I:%M %p CT").replace(" 0", " ")
    except Exception:
        return datetime.datetime.utcnow().strftime("%a %b %d, %H:%M UTC")

QUESTIONS = [
    "On the weekly chart, does {a}'s {ac:+.2f}% move align with its monthly structure? What would invalidate your swing view?",
    "Is {a}'s {ac:+.2f}% weekly move meaningful against its 30D/90D trend, or just short-term volatility? What evidence supports your swing read?",
    "Compare {a} ({ac:+.2f}% this week) with {b} ({bc:+.2f}%): how do their weekly/monthly structures differ, and what would change your view?",
    "Which open idea has the clearest weekly/monthly structure and defined invalidation? What would make you stand aside?",
    "Which pair's weekly structure is strongest relative to its monthly trend, and what evidence would confirm or invalidate that assessment?",
]

def build(kind):
    """Returns (content, embeds). Tables go in embeds so the multi-period columns fit Discord's limits."""
    head = f"**📡 Holistic Market Pulse | {now_ct()}**" if kind == "pulse" else f"**📊 LIVE BOARD** · updated {now_ct()}"
    embeds = [
        {"title": "💱 FOREX · % change", "description": table(FX)[:4000], "color": 0x2ECC71},
        {"title": "🎯 On our calls", "description": (calls_block() or "No open calls.")[:4000], "color": 0xD4AF37},
        {"title": "🪙 CRYPTO · % change", "description": table(CRYPTO)[:4000], "color": 0xF39C12},
        {"title": "📈 STOCKS · % change", "description": table(STOCKS)[:4000], "color": 0x3498DB},
    ]
    if kind == "crypto":
        head = f"**🪙 Weekend Crypto Pulse | {now_ct()}**"
        embeds = [embeds[2]]
        m = movers(CRYPTO)
        a, ac = m[0] if m else ("BTC", 0.0)
        content = head + "\n💬 **Your read:** " + random.choice([
            "{a} is {ac:+.2f}% on the week. Real flow or thin-liquidity noise?",
            "Weekend crypto: {a} {ac:+.2f}% this week. Are you trading it or waiting for Monday?",
            "Does {a}'s weekly move align with the monthly trend, or is it countertrend? What weekly evidence would confirm or invalidate a swing thesis?"]).format(a=a, ac=ac)
        embeds[-1]["footer"] = {"text": "30D · 90D · 6M · 1Y · YTD % change. Data: Yahoo Finance. Not financial advice."}
        return content, embeds
    content = head
    if kind == "pulse":
        m = movers(FX + CRYPTO + STOCKS)
        q = random.choice(QUESTIONS)
        a, ac = m[0] if m else ("Gold", 0.0)
        b, bc = m[1] if len(m) > 1 else ("DXY", 0.0)
        content += "\n💬 **Your read:** " + q.format(a=a, ac=ac, b=b, bc=bc)
    embeds[-1]["footer"] = {"text": "30D · 90D · 6M · 1Y · YTD % change. Data: Yahoo Finance, may be delayed. Not financial advice."}
    return content, embeds

def send(url, payload, method="POST"):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method,
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r) if r.status != 204 else {}

def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "pulse"
    hook = os.environ["DISCORD_WEBHOOK_URL"].rstrip("/")
    content, embeds = build(kind)
    payload = {"content": content, "embeds": embeds, "username": "Holistic Market Pulse", "allowed_mentions": {"parse": []}}
    mid = os.environ.get("BOARD_MESSAGE_ID", "").strip()
    if kind == "board" and not mid and os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        print("No BOARD_MESSAGE_ID yet: skipping scheduled board run (run 'board' manually once to create it).")
        return
    if kind == "board" and mid:
        send(f"{hook}/messages/{mid}", payload, method="PATCH")
        print("board updated", mid)
    else:
        res = send(hook + "?wait=true", payload)
        print("posted message id:", res.get("id"))
        if kind == "board":
            print(">>> Pin this message in Discord, then save this id as the BOARD_MESSAGE_ID variable.")

if __name__ == "__main__":
    main()
