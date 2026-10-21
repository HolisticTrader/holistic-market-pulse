#!/usr/bin/env python3
"""Holistic Traders welcomes.
  python welcome.py everyone   one-time @everyone welcome + intro thread prompt in #general (webhook only)
  python welcome.py new        greet members who joined since last run: public shout-out + personal DM
                               (needs DISCORD_BOT_TOKEN with Server Members Intent)
Env: DISCORD_WEBHOOK_URL (#general), DISCORD_BOT_TOKEN, GUILD_ID"""
import json, os, sys, datetime, random, urllib.request

GUILD = os.environ.get("GUILD_ID", "1342649158187749457")
STATE = "state/welcome.json"
UA = {"User-Agent": "Mozilla/5.0 (HolisticWelcome)", "Content-Type": "application/json"}
SUBSTACK = "https://immaculatetonyeth.substack.com"
TRADE_ALERT = "1546270988100960297"

def req(url, payload=None, method=None, auth=None):
    h = dict(UA)
    if auth: h["Authorization"] = auth
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"), headers=h)
    with urllib.request.urlopen(r, timeout=20) as resp:
        b = resp.read(); return json.loads(b) if b else {}

def post(hook, text, everyone=False, users=()):
    return req(hook + "?wait=true", {"content": text[:1990], "username": "Holistic Traders",
               "allowed_mentions": {"parse": ["everyone"] if everyone else [], "users": list(users)}})

EVERYONE = f"""@everyone 👋 **Welcome to Holistic Traders. Let's actually meet each other.**

**Who we are:** a community of swing traders who trade structure, not hype. We buy wholesale (demand), sell retail (supply), and every call comes with an entry, a target, and the line where we're wrong.

**What we focus on: getting funded.** 🏦
Prop trading is the core of what we do here, because it changes the math:
• You trade the firm's capital, not your savings. Your max loss is the challenge fee.
• The rules (daily loss, max drawdown) force the discipline most traders never build alone.
• Pass, stay consistent, and you get paid a split of the profits. Then you scale.
It's not easy money. Most people fail challenges by risking too much and rushing. That's exactly what we work on here: small risk, wide stops, patience.

**What you get in here:**
📈 Trade alerts with levels in <#{TRADE_ALERT}>
📊 A live market board pinned in this channel, updated every 15 min
🧠 Holistic Trivia + 🥋 belts you earn by showing up
📰 Full breakdowns + graded calls on the Substack: {SUBSTACK}

**Now your turn. Drop a quick intro below 👇**
1. Your name / where you're from
2. What you trade (forex, crypto, stocks, futures)
3. Are you funded, working a challenge, or planning to start?
4. One thing you want to get better at

**No question is a dumb question.** Prop rules, risk sizing, how to read a level: ask it here. Someone's got you."""

PUBLIC = [
    "🥋 Welcome to the dojo, <@{id}>! Tell us: what do you trade, and are you funded, in a challenge, or just getting started? Questions welcome anytime.",
    "👋 <@{id}> just pulled up. Welcome! Drop a quick intro: where you're from, what you trade, and your prop goals. No question is too basic in here.",
    "🔥 New White Belt in the building: <@{id}>! What's your market, and what's the one thing you want to get better at? We got you.",
]

DM = f"""Hey {{name}}, welcome to Holistic Traders! 🙏 This is Tony.

Quick rundown so you're not lost:
• **We're built around prop trading.** Trade a firm's capital, cap your risk at the challenge fee, get paid on consistency. Small risk, wide stops, patience.
• **Trade alerts** with entry, target and invalidation live in #trade-alert.
• **The live market board** is pinned in #general and updates every 15 minutes.
• **Points and belts** (⚪ White to ⚫ Black): replying to my setups pays the most, plus a daily trivia question at 12 PM CT.
• **Full breakdowns + graded calls:** {SUBSTACK}

Do me one favor: introduce yourself in #general. What you trade and where you're at with prop firms. And ask me anything, seriously. No question is a dumb one."""

def load():
    try: return json.load(open(STATE))
    except Exception: return {"since": None, "welcomed": []}

def save(s):
    os.makedirs("state", exist_ok=True); json.dump(s, open(STATE, "w"), indent=1)

def new_members(hook, s):
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not tok:
        print("no bot token yet, skipping new-member welcomes"); return
    auth = f"Bot {tok}"
    now = datetime.datetime.now(datetime.timezone.utc)
    since = datetime.datetime.fromisoformat(s["since"]) if s.get("since") else now  # first run: start fresh, don't spam old members
    members = req(f"https://discord.com/api/v10/guilds/{GUILD}/members?limit=1000", auth=auth)
    fresh = []
    for m in members:
        u = m.get("user", {})
        if u.get("bot") or u["id"] in s["welcomed"]: continue
        if datetime.datetime.fromisoformat(m["joined_at"]) > since:
            fresh.append(u)
    for u in fresh[:10]:
        try:
            post(hook, random.choice(PUBLIC).format(id=u["id"]), users=[u["id"]])
        except Exception as e:
            print("public welcome failed", u["id"], e)
        try:
            ch = req("https://discord.com/api/v10/users/@me/channels", {"recipient_id": u["id"]}, auth=auth)
            req(f"https://discord.com/api/v10/channels/{ch['id']}/messages",
                {"content": DM.format(name=u.get("global_name") or u.get("username"))}, auth=auth)
        except Exception as e:
            print("DM failed (member may have DMs closed)", u["id"], e)
        s["welcomed"].append(u["id"])
    s["welcomed"] = s["welcomed"][-500:]
    s["since"] = now.isoformat()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "new"
    hook = os.environ["DISCORD_WEBHOOK_URL"].rstrip("/")
    s = load()
    if mode == "everyone": post(hook, EVERYONE, everyone=True)
    else: new_members(hook, s)
    save(s)

if __name__ == "__main__":
    main()
