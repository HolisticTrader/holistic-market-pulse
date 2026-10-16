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
import json, os, sys, urllib.request, urllib.error, datetime, random

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
@functools.lru_cache(maxsize=None)
def quote(sym):
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1d&interval=5m"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                m = json.load(r)["chart"]["result"][0]["meta"]
                p = m["regularMarketPrice"]; pc = m.get("chartPreviousClose") or m.get("previousClose")
                return p, (p / pc - 1) * 100 if pc else 0.0
        except Exception:
            continue
    return None, None

import urllib.parse

def table(rows):
    lines = []
    for sym, name, d in rows:
        p, c = quote(sym)
        if p is None:
            lines.append(f"{name:<9}{'n/a':>10}")
            continue
        arrow = "▲" if c > 0 else "▼" if c < 0 else "•"
        lines.append(f"{name:<9}{p:>10.{d}f}  {arrow} {c:+.2f}%")
    return "```\n" + "\n".join(lines) + "\n```"

def movers(rows):
    out = []
    for sym, name, d in rows:
        p, c = quote(sym)
        if p is not None:
            out.append((name, c))
    return sorted(out, key=lambda x: abs(x[1]), reverse=True)

def calls_block():
    lines = []
    for name, sym, side, tgt, inv in CALLS:
        p, _ = quote(sym)
        if p is None:
            continue
        bits = [f"{name} {side} @ {p:.4g}"]
        if tgt is not None:
            dist = (tgt - p) / p * 100 * (1 if side == "long" else -1)
            bits.append("T1 hit ✅" if dist <= 0 else f"{dist:.1f}% to T1 ({tgt:g})")
        if inv is not None:
            room = (p - inv) / p * 100 * (1 if side == "long" else -1)
            bits.append("INVALIDATED ❌" if room <= 0 else f"{room:.1f}% above stop line ({inv:g})" if side == "long" else f"{room:.1f}% below stop line ({inv:g})")
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
    "{a} is the biggest mover today ({ac:+.2f}%). Chasing it, fading it, or sitting on hands?",
    "Biggest move on the board: {a} {ac:+.2f}%. Real flow or noise? Drop your read 👇",
    "{a} {ac:+.2f}% and {b} {bc:+.2f}%. Same story or two different ones?",
    "Which call on our list are you watching closest this session, and why?",
    "Weekly close is what matters. Which pair do you think closes the week strongest?",
]

def build(kind):
    head = f"**📡 Holistic Market Pulse | {now_ct()}**" if kind == "pulse" else f"**📊 LIVE BOARD** · updated {now_ct()}"
    parts = [head, "", "**💱 FOREX**", table(FX), "**🎯 On our calls**", calls_block(), "",
             "**🪙 CRYPTO**", table(CRYPTO), "**📈 STOCKS**", table(STOCKS)]
    if kind == "pulse":
        m = movers(FX + CRYPTO + STOCKS)
        q = random.choice(QUESTIONS)
        a, ac = m[0] if m else ("Gold", 0.0)
        b, bc = m[1] if len(m) > 1 else ("DXY", 0.0)
        parts += [f"💬 **Your read:** " + q.format(a=a, ac=ac, b=b, bc=bc)]
    parts += ["", "-# Data: Yahoo Finance, may be delayed. Not financial advice."]
    msg = "\n".join(parts)
    return msg[:1990]

def send(url, payload, method="POST"):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method,
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r) if r.status != 204 else {}

def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "pulse"
    hook = os.environ["DISCORD_WEBHOOK_URL"].rstrip("/")
    payload = {"content": build(kind), "username": "Holistic Market Pulse", "allowed_mentions": {"parse": []}}
    mid = os.environ.get("BOARD_MESSAGE_ID", "").strip()
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
