#!/usr/bin/env python3
"""Holistic Trivia + Holistic Traders Belts.
  python trivia.py round        reveal last answer, maybe a quote, post a new 2-hour poll
  python trivia.py leaderboard  score polls + server activity, post standings and belt promotions
  python trivia.py announce     launch announcement (@everyone in #general) + first round
Env: OFFTOPIC_WEBHOOK_URL (required), DISCORD_WEBHOOK_URL (#general, for announce),
     DISCORD_BOT_TOKEN (optional: scoring + activity points), GUILD_ID
State: state/trivia.json (committed back by the workflow)."""
import json, os, sys, random, datetime, urllib.request, urllib.error
from trivia_bank import QUESTIONS, QUOTES

STATE = "state/trivia.json"
GUILD = os.environ.get("GUILD_ID", "1342649158187749457")
UA = {"User-Agent": "Mozilla/5.0 (HolisticTrivia)", "Content-Type": "application/json"}
L = "ABCD"
POLL_HOURS = 2
PTS_CORRECT, PTS_VOTE, PTS_MSG, MSG_CAP, STREAK_BONUS = 3, 1, 1, 5, 2
BELTS = [(0, "⚪", "White"), (10, "🟡", "Yellow"), (25, "🟠", "Orange"), (50, "🟢", "Green"),
         (100, "🔵", "Blue"), (175, "🟣", "Purple"), (275, "🟤", "Brown"), (400, "⚫", "Black")]

def load():
    d = {"asked": [], "last": None, "polls": [], "week": "", "week_pts": {}, "total": {}, "names": {},
         "streak": {}, "last_day": {}, "quote_i": 0, "last_scan": None}
    try: d.update(json.load(open(STATE)))
    except Exception: pass
    return d

def save(s):
    os.makedirs("state", exist_ok=True); json.dump(s, open(STATE, "w"), indent=1)

def req(url, payload=None, method=None, auth=None):
    h = dict(UA)
    if auth: h["Authorization"] = auth
    data = json.dumps(payload).encode() if payload is not None else (b"" if method in ("PUT",) else None)
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"), headers=h)
    with urllib.request.urlopen(r, timeout=20) as resp:
        b = resp.read(); return json.loads(b) if b else {}

def ct():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/Chicago"))

def belt(p):
    b = BELTS[0]
    for x in BELTS:
        if p >= x[0]: b = x
    return b

def say(hook, text, ping_everyone=False, users=()):
    am = {"parse": ["everyone"] if ping_everyone else [], "users": list(users)[:100]}
    return req(hook + "?wait=true", {"content": text[:1990], "username": "Holistic Trivia", "allowed_mentions": am})

# ---------------- rounds ----------------
def round_(hook, s):
    parts = []
    if s.get("last") is not None:
        q, o, a, why = QUESTIONS[s["last"]]
        parts.append(f"✅ **Answer time:** {q}\n**{L[a]}. {o[a]}**\n> {why}")
    if ct().hour in (10, 14, 18):
        qt, who = QUOTES[s["quote_i"] % len(QUOTES)]; s["quote_i"] += 1
        parts.append(f"📜 *\"{qt}\"*\n— {who}")
    if parts: say(hook, "\n\n".join(parts))
    pool = [i for i in range(len(QUESTIONS)) if i not in s["asked"]] or list(range(len(QUESTIONS)))
    if len(pool) == len(QUESTIONS): s["asked"] = []
    i = random.choice(pool); s["asked"].append(i)
    q, o, a, why = QUESTIONS[i]
    poll = {"question": {"text": f"🧠 {q}"[:300]},
            "answers": [{"poll_media": {"text": f"{L[k]}. {x}"[:55]}} for k, x in enumerate(o)],
            "duration": POLL_HOURS, "allow_multiselect": False}
    try:
        m = req(hook + "?wait=true", {"content": f"🥋 **Holistic Trivia** · {POLL_HOURS} hours to lock in. Right answer = {PTS_CORRECT} pts, any vote = {PTS_VOTE}. Points earn your belt.",
                                      "poll": poll, "username": "Holistic Trivia", "allowed_mentions": {"parse": []}})
        s["polls"].append({"id": m["id"], "ch": m["channel_id"], "ans": a + 1, "n": len(o), "scored": False,
                           "day": ct().strftime("%Y-%m-%d")})
    except urllib.error.HTTPError as e:
        print("poll failed, text fallback:", e.code, e.read()[:200])
        opts = "\n".join(f"{L[k]}. {x}" for k, x in enumerate(o))
        say(hook, f"🧠 **Holistic Trivia**\n{q}\n{opts}\n\nAnswer: ||{L[a]}. {o[a]}||")
    s["last"] = i; s["polls"] = s["polls"][-60:]

# ---------------- scoring ----------------
def add(s, uid, name, pts):
    s["week_pts"][uid] = s["week_pts"].get(uid, 0) + pts
    s["total"][uid] = s["total"].get(uid, 0) + pts
    if name: s["names"][uid] = name

def uname(u): return u.get("global_name") or u.get("username") or "trader"

def score_polls(s, tok):
    now = datetime.datetime.now(datetime.timezone.utc)
    voters_by_day = {}
    for p in s["polls"]:
        if p["scored"]: continue
        # only score polls that have closed
        made = datetime.datetime.fromtimestamp(((int(p["id"]) >> 22) + 1420070400000) / 1000, datetime.timezone.utc)
        if now - made < datetime.timedelta(hours=POLL_HOURS): continue
        try:
            for k in range(1, p["n"] + 1):
                users = req(f"https://discord.com/api/v10/channels/{p['ch']}/polls/{p['id']}/answers/{k}?limit=100",
                            auth=f"Bot {tok}").get("users", [])
                for u in users:
                    if u.get("bot"): continue
                    add(s, u["id"], uname(u), PTS_CORRECT if k == p["ans"] else PTS_VOTE)
                    voters_by_day.setdefault(p["day"], set()).add(u["id"])
            p["scored"] = True
        except Exception as e:
            print("poll score failed", p["id"], e)
    # streaks
    for day, ids in sorted(voters_by_day.items()):
        for uid in ids:
            prev = s["last_day"].get(uid)
            if prev == day: continue
            yday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
            s["streak"][uid] = s["streak"].get(uid, 0) + 1 if prev == yday else 1
            s["last_day"][uid] = day
            if s["streak"][uid] >= 3: add(s, uid, None, STREAK_BONUS)

def score_activity(s, tok):
    since = s.get("last_scan")
    start = datetime.datetime.fromisoformat(since) if since else datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    try:
        chans = [c for c in req(f"https://discord.com/api/v10/guilds/{GUILD}/channels", auth=f"Bot {tok}") if c.get("type") == 0]
    except Exception as e:
        print("channel list failed", e); return
    per = {}
    for c in chans:
        try:
            msgs = req(f"https://discord.com/api/v10/channels/{c['id']}/messages?limit=100", auth=f"Bot {tok}")
        except Exception:
            continue
        for m in msgs:
            a = m.get("author", {})
            if a.get("bot") or m.get("webhook_id"): continue
            if datetime.datetime.fromisoformat(m["timestamp"]) <= start: continue
            per.setdefault(a["id"], [uname(a), 0])[1] += 1
    for uid, (name, n) in per.items():
        add(s, uid, name, min(n, MSG_CAP) * PTS_MSG)
    s["last_scan"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

BELT_COLORS = {"White": 0xF5F5F5, "Yellow": 0xF1C40F, "Orange": 0xE67E22, "Green": 0x2ECC71,
               "Blue": 0x3498DB, "Purple": 0x9B59B6, "Brown": 0x8B5A2B, "Black": 0x111111}

def sync_belt_roles(s, tok):
    """Create belt roles if missing, then give each scored member exactly one belt role.
    Needs the bot's Manage Roles permission; its own role must sit above the belt roles."""
    auth = f"Bot {tok}"
    try:
        roles = req(f"https://discord.com/api/v10/guilds/{GUILD}/roles", auth=auth)
    except Exception as e:
        print("role list failed", e); return
    by_name = {r["name"]: r["id"] for r in roles}
    ids = {}
    for need, emoji, nm in BELTS:
        rn = f"{emoji} {nm} Belt"
        if rn not in by_name:
            try:
                r = req(f"https://discord.com/api/v10/guilds/{GUILD}/roles",
                        {"name": rn, "color": BELT_COLORS[nm], "hoist": True, "mentionable": False}, auth=auth)
                by_name[rn] = r["id"]
            except Exception as e:
                print("role create failed", rn, e); return
        ids[nm] = by_name[rn]
    belt_ids = set(ids.values())
    for uid, pts in s["total"].items():
        want = ids[belt(pts)[2]]
        try:
            mem = req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}", auth=auth)
        except Exception:
            continue
        have = set(mem.get("roles", []))
        for rid in (have & belt_ids) - {want}:
            try: req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}/roles/{rid}", method="DELETE", auth=auth)
            except Exception as e: print("remove role failed", uid, e)
        if want not in have:
            try: req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}/roles/{want}", method="PUT", auth=auth)
            except Exception as e: print("add role failed", uid, e)

def reveal_last(hook, s):
    if s.get("last") is None: return
    q, o, a, why = QUESTIONS[s["last"]]
    say(hook, f"✅ **Tonight's last answer:** {q}\n**{L[a]}. {o[a]}**\n> {why}\n\nNew rounds start 8 AM CT. 🥋")
    s["last"] = None

def leaderboard(hook, s):
    reveal_last(hook, s)
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    wk = ct().strftime("%G-W%V")
    if s["week"] != wk: s["week"], s["week_pts"] = wk, {}
    before = {u: belt(p)[2] for u, p in s["total"].items()}
    if tok:
        score_polls(s, tok); score_activity(s, tok); sync_belt_roles(s, tok)
    promos = [u for u, p in s["total"].items() if belt(p)[2] != before.get(u, "White") and p >= BELTS[1][0]]
    if not s["week_pts"]:
        txt = "🥋 **Holistic Traders Dojo: daily wrap**\nBoard's empty. First points of the week are up for grabs. Rounds start 8 AM CT in #off-topic."
        if not tok: txt += "\n-# Scoring switches on once the server bot is connected."
        say(hook, txt); return
    top = sorted(s["week_pts"].items(), key=lambda x: -x[1])[:10]
    med = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    rows = []
    for k, (u, p) in enumerate(top):
        e, _, nm = belt(s["total"].get(u, 0)); st = s["streak"].get(u, 0)
        rows.append(f"{med[k]} **{s['names'].get(u, 'trader')}** · {p} pts {e} {nm} Belt" + (f" · 🔥{st}-day streak" if st >= 2 else ""))
    txt = f"🥋 **Holistic Traders Dojo · Week {wk[-2:]} standings**\n" + "\n".join(rows)
    if promos:
        txt += "\n\n🎖️ **Belt promotions:** " + ", ".join(f"<@{u}> → {belt(s['total'][u])[0]} {belt(s['total'][u])[2]}" for u in promos)
    txt += ("\n\n-# Points: correct answer 3 · any vote 1 · active in chat 1/msg (max 5/day) · 3+ day streak +2/day. "
            "Belts: ⚪→🟡10→🟠25→🟢50→🔵100→🟣175→🟤275→⚫400 (all-time). Weekly board resets Monday.")
    say(hook, txt, users=promos)

def announce(hook, s):
    general = os.environ.get("DISCORD_WEBHOOK_URL", "").rstrip("/")
    try: ch = req(hook).get("channel_id")
    except Exception: ch = None
    where = f"<#{ch}>" if ch else "#off-topic"
    txt = (f"@everyone 🥋 **The Holistic Traders Dojo is open.**\n\n"
           f"Starting today, {where} runs **Holistic Trivia** all day: technical analysis, market history and forex questions, "
           f"plus quotes from the legends who built this game.\n\n"
           f"⏰ **New round every 2 hours, 8 AM to 8 PM CT, every day.** You get {POLL_HOURS} hours to vote. The answer drops with the next round.\n"
           f"🎯 **Points:** right answer **3**, any vote **1**, being active in the chat **1 per message** (up to 5 a day), and a 3-day streak adds **+2 a day**.\n"
           f"🏆 **Leaderboard every night at 9:30 PM CT.** Weekly board resets Monday.\n\n"
           f"🥋 **Earn your belt** (all-time points):\n"
           f"⚪ White → 🟡 Yellow (10) → 🟠 Orange (25) → 🟢 Green (50) → 🔵 Blue (100) → 🟣 Purple (175) → 🟤 Brown (275) → ⚫ **Black Belt (400)**\n\n"
           f"Black belts get recognized. First round is live now. 👇 {where}")
    say(general or hook, txt, ping_everyone=True)
    round_(hook, s)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "round"
    hook = os.environ["OFFTOPIC_WEBHOOK_URL"].rstrip("/")
    s = load()
    {"round": round_, "leaderboard": leaderboard, "announce": announce}[mode](hook, s)
    save(s)

if __name__ == "__main__":
    main()
