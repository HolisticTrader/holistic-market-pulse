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
  # name, symbol, direction, entry (None until recorded), target areas, invalidation
  # Target areas: a list, T1 first. Each is a zone (low, high) or a single level.
  # Long -> target is the RETAIL area. Short -> target is the WHOLESALE area.
  ("GBP/JPY","GBPJPY=X","short",None,[184.40],220.32),
  ("AUD/JPY","AUDJPY=X","short",None,[(100.0,110.0),(88.0,95.0)],113.0),
  ("CHF/JPY","CHFJPY=X","long",None,[204.0],None),
  ("USD/MXN","USDMXN=X","long",None,[18.80,21.00],17.50),
  ("USD/NOK","USDNOK=X","long",None,[10.62],9.07),
  ("AUD/USD","AUDUSD=X","short",None,[],0.7421),
  ("GBP/AUD","GBPAUD=X","long",None,[2.046],1.852),
  ("EUR/CHF","EURCHF=X","short",None,[],0.9445),
  ("NZD/JPY","NZDJPY=X","long",None,[94.99],86.50),
  ("USD/ZAR","USDZAR=X","long",None,[(17.00,17.80)],15.65),
]

UA = {"User-Agent": "Mozilla/5.0 (HolisticMarketPulse)"}

import functools
import netretry  # retries temporary network/Discord/X hiccups
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
CALL_LEDGER_PATH = "trade_calls_state.json"
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

def _entry_date(text, fallback_date=None):
    """Use a trade date printed in the call, otherwise the source post date."""
    m = re.search(r"(?i)\b(?:entry|trade)\s+date\s*[:\-]\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})", text)
    if m:
        raw = m.group(1)
        try:
            return (datetime.datetime.strptime(raw, "%Y-%m-%d") if "-" in raw
                    else datetime.datetime.strptime(raw, "%m/%d/%Y")).date().isoformat()
        except ValueError:
            pass
    if fallback_date:
        try:
            return datetime.date.fromisoformat(fallback_date[:10]).isoformat()
        except ValueError:
            pass
    return None

def parse_calls(text, fallback_date=None):
    """Find trade cards and close notices, keeping the trade entry date."""
    out = []
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    for m in re.finditer(r"(?i)\b(closed|close|exit(?:ed)?|out of|stopped out of|invalidated)\s*:?\s*\$([A-Za-z/]{3,10})", text):
        out.append(("close", m.group(2)))
    for chunk in re.split(r"(?=\$[A-Za-z][A-Za-z/]{2,9}\b)", text):
        m = re.match(r"\$([A-Za-z/]{3,10})", chunk)
        if not m: continue
        chunk = chunk[:600]
        d = re.search(r"(?i)\b(long|short|buy|sell|bullish|bearish)\b", chunk)
        en = re.search(r"(?i)\b(?:entry|entered|fill(?:ed)?)\b[^\n]{0,30}?(?<![A-Za-z\d.,])" + NUM + r"(?:\s*(?:-|–|—|to)\s*" + NUM + ")?", chunk)
        tg = re.search(r"(?i)\b(?:target|tp|t1)\b[^\n]{0,30}?(?<![A-Za-z\d.,])" + NUM + r"(?:\s*(?:-|–|—|to)\s*" + NUM + ")?", chunk)
        iv = re.search(r"(?i)\b(?:invalid(?:ation)?|stop(?:\s*loss)?|sl|wrong)\b[^\n]{0,40}?(?<![A-Za-z\d.,])" + NUM, chunk)
        if not d or not (tg or iv): continue
        side = "long" if d.group(1).lower() in ("long", "buy", "bullish") else "short"
        sym, name = yahoo_symbol(m.group(1))
        entry = None
        if en:
            first = _f(en.group(1))
            second = _f(en.group(2)) if en.group(2) else None
            entry = (min(first, second), max(first, second)) if second else first
        tgt = []
        if tg:
            a = _f(tg.group(1)); b = _f(tg.group(2)) if tg.group(2) else None
            tgt = [(min(a, b), max(a, b)) if b else a]
        out.append(("open", (name, sym, side, entry, tgt, _f(iv.group(1)) if iv else None,
                              _entry_date(chunk, fallback_date))))
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
    """Merge recent public posts into the persistent active-call ledger."""
    try:
        with open(CALL_LEDGER_PATH, encoding="utf-8") as f:
            state = json.load(f)
        initialized = bool(state.get("initialized"))
    except (OSError, ValueError):
        state, initialized = {}, False

    calls, dates = {}, {}
    if initialized:
        for sym, record in state.get("calls", {}).items():
            try:
                calls[sym] = tuple(record["call"])
                dates[sym] = record.get("entry_date")
            except (KeyError, TypeError):
                continue
    else:
        calls = {c[1]: c for c in CALLS}

    feed = sorted(substack_texts() + discord_alert_texts(), key=lambda x: x[0])
    for timestamp, text in feed:
        for action, val in parse_calls(text, timestamp[:10] if timestamp else None):
            if action == "close":
                sym = yahoo_symbol(val)[0]
                calls.pop(sym, None)
                dates.pop(sym, None)
            else:
                call = val[:6]
                calls[call[1]] = call
                dates[call[1]] = val[6]

    state = {
        "initialized": True,
        "calls": {
            sym: {"call": list(call), "entry_date": dates.get(sym)}
            for sym, call in calls.items()
        },
    }
    tmp = CALL_LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, CALL_LEDGER_PATH)
    return [(*call, dates.get(sym)) for sym, call in calls.items()]

def _zone(t):
    """(low, high, label) for a target area or a single level."""
    if isinstance(t, (tuple, list)):
        lo, hi = min(t), max(t)
        return lo, hi, f"{_px(lo)}–{_px(hi)}"
    return t, t, _px(t)

def _target_status(side, p, t):
    """Returns (reached, text) for one target area."""
    lo, hi, label = _zone(t)
    if lo <= p <= hi and lo != hi:
        return True, f"{label} · price is **inside the area** ✅"
    if (side == "long" and p >= hi) or (side == "short" and p <= lo):
        return True, f"{label} · **reached** ✅"
    near = lo if side == "long" else hi  # the edge price reaches first
    return False, f"{label} · {abs(near - p) / p * 100:.1f}% to the area"

FTMO_BALANCE = 100000.0
RISK_PERCENT_LOW = 0.01
RISK_PERCENT_HIGH = 0.015
RISK_DOLLARS_LOW = FTMO_BALANCE * RISK_PERCENT_LOW
RISK_DOLLARS_HIGH = FTMO_BALANCE * RISK_PERCENT_HIGH

def calls_block():
    rows = []
    for name, sym, side, entry, tgts, inv, entry_date in all_calls()[-12:]:  # newest 12 to stay under Discord's limits
        p, _ = quote(sym)
        if p is None:
            continue
        if tgts is None: tgts = []
        elif not isinstance(tgts, list): tgts = [tgts]
        entry_value = (sum(entry) / 2) if isinstance(entry, (tuple, list)) else entry
        room = (p - inv) / p * 100 * (1 if side == "long" else -1) if inv is not None else None
        rows.append((name, side, entry, entry_value, tgts, inv, p, room))
    rows.sort(key=lambda r: r[7] if r[7] is not None else float("inf"))
    if not rows:
        return "", 0xD4AF37

    NEAR = 3.0  # % from stop that counts as "close to stop"
    groups = {"stop": [], "near": [], "hit": [], "profit": [], "below": [], "flat": [], "missing": []}
    total_pnl_low = total_pnl_high = 0.0
    scored_calls = missing_score_calls = 0
    for name, side, entry, entry_value, tgts, inv, p, room in rows:
        arrow = "📈 Long" if side == "long" else "📉 Short"
        area = "Retail" if side == "long" else "Wholesale"
        date_text = entry_date or "Not recorded"
        try:
            month_year = datetime.date.fromisoformat(date_text).strftime("%B / %Y")
        except ValueError:
            month_year = "Not recorded"
        lines = [f"**{name}** · {arrow} · current **{_px(p)}**",
                 f"🗓️ Entry date: **{date_text}** · Month / year: **{month_year}**"]
        if entry_value is None:
            missing_score_calls += 1
            lines.append("📍 Entry: **not on record** · P/L unavailable")
            status = "missing"
        else:
            if isinstance(entry, (tuple, list)) and entry[0] != entry[1]:
                entry_label = f"{_px(entry[0])}–{_px(entry[1])} (midpoint {_px(entry_value)})"
            else:
                entry_label = _px(entry_value)
            lines.append(f"📍 Entry: {entry_label}")
            move = (p - entry_value) * (1 if side == "long" else -1)
            pip_size = 0.01 if name.endswith("/JPY") else 0.0001 if "/" in name else None
            move_label = f"{abs(move) / pip_size:.1f} pips" if pip_size else f"{abs(move):.4g} price units"
            sign = "+" if move > 0 else "−" if move < 0 else ""
            if move > 0:
                label, icon, status = "IN PROFIT", "🟢", "profit"
            elif move < 0:
                label, icon, status = "BELOW ENTRY", "🔴", "below"
            else:
                label, icon, status = "AT ENTRY", "⚪", "flat"

            valid_stop = inv is not None and ((inv < entry_value) if side == "long" else (inv > entry_value))
            if valid_stop:
                stop_distance = abs(entry_value - inv)
                pnl_low = RISK_DOLLARS_LOW * move / stop_distance
                pnl_high = RISK_DOLLARS_HIGH * move / stop_distance
                total_pnl_low += pnl_low
                total_pnl_high += pnl_high
                scored_calls += 1
                if move > 0:
                    amount = f"+${pnl_low:,.0f} to +${pnl_high:,.0f}"
                elif move < 0:
                    amount = f"−${abs(pnl_high):,.0f} to −${abs(pnl_low):,.0f}"
                else:
                    amount = "$0"
                lines.append(f"{icon} **{label}** · {sign}{move_label} · est. **{amount}**")
                if isinstance(entry, (tuple, list)) and entry[0] != entry[1]:
                    lines.append(f"↳ Uses entry-zone midpoint. Risk range: ${RISK_DOLLARS_LOW:,.0f}–${RISK_DOLLARS_HIGH:,.0f} (1%–1.5% of ${FTMO_BALANCE:,.0f}); fees/swaps excluded.")
                else:
                    lines.append(f"↳ Risk range: ${RISK_DOLLARS_LOW:,.0f}–${RISK_DOLLARS_HIGH:,.0f} (1%–1.5% of ${FTMO_BALANCE:,.0f}); fees/swaps excluded.")
            else:
                missing_score_calls += 1
                lines.append(f"{icon} **{label}** · {sign}{move_label} · USD estimate needs a valid stop")
        t1_hit = False
        if not tgts:
            lines.append(f"🎯 {area} area (target): not posted yet")
        for i, t in enumerate(tgts):
            hit, txt = _target_status(side, p, t)
            if i == 0: t1_hit = hit
            tag = f"T{i+1} " if len(tgts) > 1 else ""
            lines.append(f"🎯 {tag}{area} area: {txt}")
        if inv is None:
            lines.append("🛑 Stop: not posted yet")
        elif room <= 0:
            lines.append(f"🛑 Stop {_px(inv)}: **hit** ❌ call closed")
        else:
            lines.append(f"🛑 Stop {_px(inv)}: {room:.1f}% away")
        entry_text = "\n".join(lines)
        if room is not None and room <= 0: groups["stop"].append(entry_text)
        elif room is not None and room < NEAR: groups["near"].append(entry_text)
        elif t1_hit: groups["hit"].append(entry_text)
        else: groups[status].append(entry_text)

    score_color = 0xD4AF37
    out = [
        f"*Example sizing: FTMO ${FTMO_BALANCE:,.0f} · {RISK_PERCENT_LOW:.0%}–{RISK_PERCENT_HIGH:.1%} risk per call (${RISK_DOLLARS_LOW:,.0f}–${RISK_DOLLARS_HIGH:,.0f} at the stop). "
        "P/L is estimated from entry, current price, and stop; quotes may be delayed.*"
    ]
    score_line = f"🟡 **OVERALL OPEN-CALL SCORE · unavailable** · no calls have both a recorded entry and valid stop ({missing_score_calls} unscored)"
    if scored_calls:
        net_low = min(total_pnl_low, total_pnl_high)
        net_high = max(total_pnl_low, total_pnl_high)
        low_pct, high_pct = net_low / FTMO_BALANCE * 100, net_high / FTMO_BALANCE * 100
        icon = "🐂" if net_low > 0 else "🐻" if net_high < 0 else "⚖️"
        score_color = 0x39FF14 if net_low > 0 else 0xFF1744 if net_high < 0 else 0xD4AF37
        fmt_dollars = lambda amount: f"+${amount:,.0f}" if amount > 0 else f"−${abs(amount):,.0f}" if amount < 0 else "$0"
        fmt_percent = lambda amount: f"+{amount:.2f}%" if amount > 0 else f"−{abs(amount):.2f}%" if amount < 0 else "0.00%"
        score_line = (f"{icon} **OVERALL OPEN-CALL SCORE · {fmt_percent(low_pct)} to {fmt_percent(high_pct)}** "
                      f"({fmt_dollars(net_low)} to {fmt_dollars(net_high)}) · {scored_calls} calls with valid entry/stop")
        if missing_score_calls:
            score_line += f" · {missing_score_calls} unscored (entry/stop missing)"
    for key, title in (("stop", "❌ STOPPED OUT"), ("near", f"⚠️ CLOSE TO STOP (under {NEAR:g}%)"),
                       ("hit", "✅ IN OR PAST THE TARGET AREA"), ("profit", "🟢 IN PROFIT"),
                       ("below", "🔴 BELOW ENTRY"), ("flat", "⚪ AT ENTRY"),
                       ("missing", "🟡 ENTRY NOT ON RECORD")):
        if groups[key]:
            out.append(f"\n__{title}__")
            out.append("\n\n".join(groups[key]))
    out.insert(1, score_line)
    return "\n".join(out), score_color

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
    # Forex / crypto / stocks % change tables removed (Tony, Oct 21). Only the open calls show.
    calls_text, calls_color = calls_block()
    embeds = [
        {"title": "🎯 OUR OPEN CALLS", "description": (calls_text or "No open calls.")[:4000], "color": calls_color},
    ]
    content = head
    if kind == "pulse":
        m = movers(FX + CRYPTO + STOCKS)
        q = random.choice(QUESTIONS)
        a, ac = m[0] if m else ("Gold", 0.0)
        b, bc = m[1] if len(m) > 1 else ("DXY", 0.0)
        content += "\n💬 **Your read:** " + q.format(a=a, ac=ac, b=b, bc=bc) + "\n-# Hit reply with your answer. Replies earn 2 Dojo points."
    embeds[-1]["footer"] = {"text": "Data: Yahoo Finance, may be delayed. Not financial advice."}
    return content, embeds

def send(url, payload, method="POST"):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method,
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r) if r.status != 204 else {}

def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "pulse"
    if kind == "crypto":
        print("Weekend crypto check retired with the % change tables: nothing to post.")
        return
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
