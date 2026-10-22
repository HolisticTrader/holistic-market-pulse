#!/usr/bin/env python3
"""Holistic Trivia + Holistic Traders Belts.
  python trivia.py round        reveal last answer, maybe a quote, post a new 2-hour poll
  python trivia.py leaderboard  score polls + server activity, post standings and belt promotions
  python trivia.py announce     launch announcement (@everyone in #general) + first round
Env: DISCORD_WEBHOOK_URL (#general: trivia, Dojo standings, Hall of Fame all post here),
     DISCORD_BOT_TOKEN (optional: scoring + activity points), GUILD_ID
State: state/trivia.json (committed back by the workflow)."""
import json, os, sys, random, datetime, urllib.request, urllib.error
from trivia_bank import QUESTIONS, QUOTES
import netretry  # retries temporary network/Discord/X hiccups

STATE = "state/trivia.json"
GUILD = os.environ.get("GUILD_ID", "1342649158187749457")
UA = {"User-Agent": "DiscordBot (https://github.com/HolisticTrader/holistic-market-pulse, 1.1)", "Content-Type": "application/json"}
L = "ABCD"
POLL_HOURS = 8   # one question a day: posts 12 PM CT, closes 8 PM, answer + standings 9:30 PM
PTS_CORRECT, PTS_VOTE, STREAK_BONUS = 3, 1, 2
# Chat points: a reply to Tony or to a setup in #trade-alert = 3, a reply to anyone else = 2,
# any other message = 1. Capped at ACT_CAP a day so spam can't farm belts.
PTS_MSG, PTS_REPLY, PTS_REPLY_TONY, ACT_CAP = 1, 2, 3, 10
TONY = os.environ.get("TRADER_NAME", "immaculatetony").lower()
SETUP_CHANNEL = os.environ.get("TRADE_ALERT_CHANNEL_ID", "1546270988100960297")
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

def tag(s, u):
    return f"<@{u}>" if not str(u).startswith("u:") else f"**{s['names'].get(u, 'trader')}**"

def pingable(ids):
    return [u for u in ids if not str(u).startswith("u:")]

def resolve_usernames(s, members):
    """Merge points stored by username ("u:name") into real Discord IDs once the bot can see members."""
    by_name = {m["user"]["username"].lower(): m["user"] for m in members if "user" in m}
    for key in [k for k in list(s["total"]) if k.startswith("u:")]:
        u = by_name.get(key[2:].lower())
        if not u: continue
        for bucket in ("total", "week_pts"):
            if key in s[bucket]:
                s[bucket][u["id"]] = s[bucket].get(u["id"], 0) + s[bucket].pop(key)
        s["names"][u["id"]] = s["names"].pop(key, None) or uname(u)

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
            pts = PTS_MSG
            ref = m.get("referenced_message")
            if ref:
                ra = ref.get("author", {})
                who = (ra.get("username", "") + " " + (ra.get("global_name") or "")).lower()
                if ra.get("id") == a.get("id"): pts = PTS_MSG                      # replying to yourself
                elif TONY in who or ref.get("channel_id") == SETUP_CHANNEL: pts = PTS_REPLY_TONY
                else: pts = PTS_REPLY
            per.setdefault(a["id"], [uname(a), 0])[1] += pts
    for uid, (name, n) in per.items():
        add(s, uid, name, min(n, ACT_CAP))
    s["last_scan"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

BELT_COLORS = {"White": 0xFFFFFF, "Yellow": 0xF1C40F, "Orange": 0xE67E22, "Green": 0x2ECC71,
               "Blue": 0x3498DB, "Purple": 0x9B59B6, "Brown": 0x8B5A2B, "Black": 0x5D6166}
# any role whose name ends in "Sensei" is staff: never given a belt, never touched by the sync

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
    sensei = next((rid for n, rid in by_name.items() if n.lower().endswith("sensei")), None)
    # every human member gets at least White Belt (new joiners included)
    try:
        members = req(f"https://discord.com/api/v10/guilds/{GUILD}/members?limit=1000", auth=auth)
        resolve_usernames(s, members)
        for m in members:
            u = m.get("user", {})
            if u.get("bot") or set(m.get("roles", [])) & (belt_ids | {sensei}): continue
            try: req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{u['id']}/roles/{ids['White']}", method="PUT", auth=auth)
            except Exception as e: print("white belt failed", u.get("id"), e)
    except Exception as e:
        print("member list failed", e)
    for uid, pts in s["total"].items():
        if str(uid).startswith("u:"): continue
        want = ids[belt(pts)[2]]
        try:
            mem = req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}", auth=auth)
        except Exception:
            continue
        have = set(mem.get("roles", []))
        if sensei and sensei in have: continue
        for rid in (have & belt_ids) - {want}:
            try: req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}/roles/{rid}", method="DELETE", auth=auth)
            except Exception as e: print("remove role failed", uid, e)
        if want not in have:
            try: req(f"https://discord.com/api/v10/guilds/{GUILD}/members/{uid}/roles/{want}", method="PUT", auth=auth)
            except Exception as e: print("add role failed", uid, e)

def reveal_last(hook, s):
    if s.get("last") is None: return
    q, o, a, why = QUESTIONS[s["last"]]
    say(hook, f"✅ **Tonight's last answer:** {q}\n**{L[a]}. {o[a]}**\n> {why}\n\nNext question tomorrow at 12 PM CT. 🥋")
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
        txt = "🥋 **Holistic Traders Dojo: daily wrap**\nBoard's empty. First points of the week are up for grabs. Today's question drops at 12 PM CT right here in #general."
        if not tok: txt += "\n-# Scoring switches on once the server bot is connected."
        say(hook, txt); return
    top = sorted(s["week_pts"].items(), key=lambda x: -x[1])[:10]
    med = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    rows = []
    for k, (u, p) in enumerate(top):
        _, e, nm = belt(s["total"].get(u, 0)); st = s["streak"].get(u, 0)
        rows.append(f"{med[k]} {tag(s, u)} · {p} pts {e} {nm} Belt" + (f" · 🔥{st}-day streak" if st >= 2 else ""))
    txt = f"🥋 **Holistic Traders Dojo · Week {wk[-2:]} standings**\n" + "\n".join(rows)
    at = sorted(s["total"].items(), key=lambda x: -x[1])[:5]
    if at:
        txt += "\n\n🏛️ **All-time Hall of Fame**\n" + "\n".join(
            f"{['👑','2.','3.','4.','5.'][k]} {tag(s, u)} · {p} pts {belt(p)[1]} {belt(p)[2]} Belt" for k, (u, p) in enumerate(at))
    if promos:
        txt += "\n\n🎖️ **Belt promotions:** " + ", ".join(f"<@{u}> → {belt(s['total'][u])[1]} {belt(s['total'][u])[2]}" for u in promos)
    txt += ("\n\n-# Points: correct answer 3 · any vote 1 · active in chat 1/msg (max 5/day) · 3+ day streak +2/day. "
            "Belts: ⚪→🟡10→🟠25→🟢50→🔵100→🟣175→🟤275→⚫400 (all-time). Weekly board resets Monday.")
    say(hook, txt, users=pingable(set(promos) | {u for u, _ in top} | {u for u, _ in at}))

def hall_of_fame(hook, s):
    """Friday-morning all-time leaderboard."""
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if tok:
        score_polls(s, tok); score_activity(s, tok); sync_belt_roles(s, tok)
    top = sorted(s["total"].items(), key=lambda x: -x[1])[:10]
    if not top:
        say(hook, "🏛️ **Holistic Traders Hall of Fame**\nNo all-time points on the board yet. Every trivia vote and every message counts. Be the first name up here. 🥋"
            + ("" if tok else "\n-# Scoring switches on once the server bot is connected."))
        return
    marks = ["👑", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    rows = "\n".join(f"{marks[k]} {tag(s, u)} · {p} pts · {belt(p)[1]} {belt(p)[2]} Belt"
                     + (f" · 🔥{s['streak'].get(u)}-day streak" if s["streak"].get(u, 0) >= 2 else "")
                     for k, (u, p) in enumerate(top))
    counts = {}
    for p in s["total"].values():
        counts[belt(p)[2]] = counts.get(belt(p)[2], 0) + 1
    dojo = " · ".join(f"{e} {counts[nm]}" for _, e, nm in BELTS if counts.get(nm) and nm != "White") + " · everyone else ⚪"
    leader = top[0]
    nxt = next(((need, e, nm) for need, e, nm in BELTS if need > leader[1]), None)
    tail = (f"\n\n{tag(s, leader[0])} is {nxt[0] - leader[1]} pts from {nxt[1]} {nxt[2]} Belt. Who's catching them? 👀"
            if nxt else f"\n\n{tag(s, leader[0])} is a ⚫ Black Belt. Respect. 🙏")
    intro = s.pop("hof_intro", "")
    say(hook, f"{intro}🏛️ **Holistic Traders Hall of Fame · all-time**\n{rows}\n\n**The dojo right now:** {dojo}{tail}\n"
              "-# Every Friday morning. Points never reset here. Belts: ⚪→🟡10→🟠25→🟢50→🔵100→🟣175→🟤275→⚫400",
        users=pingable(u for u, _ in top))

def announce(hook, s):
    general = clean_hook(os.environ["DISCORD_WEBHOOK_URL"]) if os.environ.get("DISCORD_WEBHOOK_URL") else ""
    try: ch = req(hook).get("channel_id")
    except Exception: ch = None
    where = f"<#{ch}>" if ch else "#general"
    txt = (f"@everyone 🥋 **The Holistic Traders Dojo is open.**\n\n"
           f"Starting today, {where} runs **Holistic Trivia** once a day: technical analysis, market history and forex questions, "
           f"plus quotes from the legends who built this game.\n\n"
           f"⏰ **One question a day at 12 PM CT.** Voting closes at 8 PM. The answer drops at 9:30 PM with the standings.\n"
           f"🎯 **Points:** right answer **3**, any vote **1**, **replying to my setups 3**, replying to another trader **2**, any other message **1** (up to 10 a day), and a 3-day streak adds **+2 a day**.\n"
           f"🏆 **Leaderboard every night at 9:30 PM CT.** Weekly board resets Monday.\n\n"
           f"🥋 **Earn your belt** (all-time points):\n"
           f"⚪ White → 🟡 Yellow (10) → 🟠 Orange (25) → 🟢 Green (50) → 🔵 Blue (100) → 🟣 Purple (175) → 🟤 Brown (275) → ⚫ **Black Belt (400)**\n\n"
           f"Black belts get recognized. First round is live now. 👇 {where}")
    say(general or hook, txt, ping_everyone=True)
    round_(hook, s)

import re as _re
def clean_hook(v):
    m = _re.search(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", v or "")
    if not m: raise SystemExit("Webhook setting doesn't contain a valid Discord webhook link")
    return m.group(0)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "round"
    hook = clean_hook(os.environ.get("DISCORD_WEBHOOK_URL"))
    s = load()
    {"round": round_, "leaderboard": leaderboard, "announce": announce, "halloffame": hall_of_fame}[mode](hook, s)
    save(s)

if __name__ == "__main__":
    main()
