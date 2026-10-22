#!/usr/bin/env python3
"""Daily check that every credential the bots depend on still works.
Fails (one email per day) only when something is actually broken, and says exactly what to fix.
Read-only: it never posts anything."""
import json, os, sys, urllib.request, urllib.error
import netretry  # noqa: F401  (retries temporary hiccups so only real breakage fails)
from xpost import sign

GUILD = os.environ.get("GUILD_ID", "1342649158187749457")
problems, notes = [], []


def get(url, auth=None, ua="DiscordBot (https://github.com/HolisticTrader/holistic-market-pulse, 1.1)"):
    h = {"User-Agent": ua}
    if auth:
        h["Authorization"] = auth
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
        return json.load(r)


def check(name, fn, fix):
    try:
        notes.append(f"OK    {name}: {fn()}")
    except urllib.error.HTTPError as e:
        problems.append(f"FAIL  {name}: HTTP {e.code} -> {fix}")
    except Exception as e:
        problems.append(f"FAIL  {name}: {type(e).__name__} {e} -> {fix}")


hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

if hook:
    check("Discord webhook (#general posts)", lambda: get(hook)["name"],
          "webhook was deleted; make a new one in Discord channel settings > Integrations and update the DISCORD_WEBHOOK_URL secret")
else:
    problems.append("FAIL  DISCORD_WEBHOOK_URL secret is empty")

if tok:
    auth = f"Bot {tok}"
    check("Discord bot token", lambda: get("https://discord.com/api/v10/users/@me", auth)["username"],
          "token was reset/revoked; Discord Developer Portal > Holistic Dojo > Bot > Reset Token, then update the DISCORD_BOT_TOKEN secret")
    check("Bot can read server members", lambda: f"{len(get(f'https://discord.com/api/v10/guilds/{GUILD}/members?limit=5', auth))} sampled",
          "bot was removed from the server or Server Members Intent was turned off")
    check("Bot can see channels", lambda: f"{len(get(f'https://discord.com/api/v10/guilds/{GUILD}/channels', auth))} channels",
          "bot lost access to the server")
else:
    problems.append("FAIL  DISCORD_BOT_TOKEN secret is empty")

xenv = [os.environ.get(k, "").strip() for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
if all(xenv):
    url = "https://api.twitter.com/2/users/me"
    check("X (Twitter) keys", lambda: get(url, sign("GET", url, {}, *xenv), ua="HolisticHealth")["data"]["username"],
          "X keys were regenerated/revoked; get new ones at developer.x.com and update the X_* secrets")
else:
    notes.append("SKIP  X keys not set")

print("\n".join(notes + problems))
if problems:
    print(f"::error::{len(problems)} credential problem(s). See the lines marked FAIL above for the exact fix.")
    sys.exit(1)
print("All credentials healthy.")
