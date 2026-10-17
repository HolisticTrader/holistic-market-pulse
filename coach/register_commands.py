#!/usr/bin/env python3
"""One-time: register Holistic Coach slash commands in your server.
Usage: DISCORD_BOT_TOKEN=... DISCORD_APP_ID=... python register_commands.py
(Run from GitHub Actions, see coach/README.md, so the token never touches your computer.)"""
import json, os, urllib.request
GUILD = os.environ.get("GUILD_ID", "1342649158187749457")
STR, NUM, ATT = 3, 10, 11
STYLE_OPT = {"name": "style", "description": "Override your coaching style for this question", "type": STR, "required": False,
             "choices": [{"name": "Risk Manager", "value": "risk"}, {"name": "Technical Analyst", "value": "technical"},
                         {"name": "Psychologist", "value": "psych"}, {"name": "Prop Firm Coach", "value": "prop"}]}
CMDS = [
 {"name": "analyze", "description": "Break down a chart or setup (structure, zones, scenarios, risk). No predictions.",
  "options": [{"name": "symbol", "description": "e.g. EURUSD, GBPJPY, BTC, NVDA", "type": STR, "required": True},
              {"name": "question", "description": "What do you want to know?", "type": STR, "required": False},
              {"name": "chart", "description": "Attach a chart screenshot", "type": ATT, "required": False}, STYLE_OPT]},
 {"name": "journal", "description": "Review a trade and find the mistakes (and what you did right).",
  "options": [{"name": "trade", "description": "Pair, direction, entry, stop, target, result, and what you were thinking", "type": STR, "required": True}, STYLE_OPT]},
 {"name": "risk", "description": "Position size from account equity, risk %, entry and stop.",
  "options": [{"name": "equity", "description": "Account size in USD", "type": NUM, "required": True},
              {"name": "risk_percent", "description": "Risk per trade, e.g. 1", "type": NUM, "required": True},
              {"name": "entry", "description": "Entry price", "type": NUM, "required": True},
              {"name": "stop", "description": "Stop-loss price", "type": NUM, "required": True},
              {"name": "symbol", "description": "e.g. EURUSD (helps with pips/lots)", "type": STR, "required": False}]},
 {"name": "coach", "description": "Get feedback on your trading rules.",
  "options": [{"name": "rules", "description": "Paste your rules", "type": STR, "required": True}, STYLE_OPT]},
 {"name": "style", "description": "Choose your default coaching style.",
  "options": [dict(STYLE_OPT, name="coach", description="Who do you want coaching you?", required=True)]},
]
req = urllib.request.Request(f"https://discord.com/api/v10/applications/{os.environ['DISCORD_APP_ID']}/guilds/{GUILD}/commands",
    data=json.dumps(CMDS).encode(), method="PUT",
    headers={"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}", "Content-Type": "application/json", "User-Agent": "HolisticCoach"})
print([c["name"] for c in json.load(urllib.request.urlopen(req))])
