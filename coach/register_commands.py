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
 {"name": "ask-mentor", "description": "Ask about a course lesson; include an excerpt for source-grounded answers.",
  "options": [{"name": "question", "description": "What do you want explained?", "type": STR, "required": True},
              {"name": "lesson_excerpt", "description": "Paste the approved lesson text (up to 4000 characters)", "type": STR, "required": False}]},
 {"name": "lesson", "description": "Open the approved Holistic Trader learning links.",
  "options": [{"name": "topic", "description": "Topic you are studying", "type": STR, "required": False}]},
 {"name": "study-plan", "description": "Build a 7-day swing-trading study plan with course links.",
  "options": [{"name": "goals", "description": "What do you want to improve?", "type": STR, "required": True}]},
 {"name": "challenge", "description": "Track a prop-firm evaluation using your exact account rules.", "options": [
  {"name": "start", "description": "Set up a personal evaluation tracker", "type": 1, "options": [
   {"name": "firm", "description": "Firm", "type": STR, "required": True, "choices": [{"name":"FTMO","value":"FTMO"},{"name":"The5ers","value":"The5ers"},{"name":"Other / custom","value":"Custom"}]},
   {"name": "program", "description": "Exact program/account type", "type": STR, "required": True},
   {"name": "phase", "description": "Phase or account stage", "type": STR, "required": True},
   {"name": "account_size", "description": "Nominal account size in USD", "type": NUM, "required": True},
   {"name": "start_balance", "description": "Starting balance/equity in USD", "type": NUM, "required": True},
   {"name": "target_pct", "description": "Profit target percent from current rulebook", "type": NUM, "required": True},
   {"name": "daily_loss_pct", "description": "Daily loss limit percent", "type": NUM, "required": True},
   {"name": "max_loss_pct", "description": "Maximum overall loss percent", "type": NUM, "required": True},
   {"name": "min_days", "description": "Minimum required trading days", "type": 4, "required": True},
   {"name": "days_done", "description": "Trading days completed so far", "type": 4, "required": True},
   {"name": "markets", "description": "Allowed markets from your program rules", "type": STR, "required": True},
   {"name": "swing", "description": "Does your exact account type permit overnight/weekend holds?", "type": 5, "required": True},
   {"name": "rules_url", "description": "Official rules link for this exact program", "type": STR, "required": True}]},
  {"name": "status", "description": "Update balance and today's P&L", "type": 1, "options": [
   {"name": "current_balance", "description": "Current balance/equity in USD", "type": NUM, "required": True},
   {"name": "today_pnl", "description": "Today's realized plus open P&L in USD", "type": NUM, "required": False}]}]},
 {"name": "quiz", "description": "Historical/simulated trading-knowledge quiz.",
  "options": [{"name":"answer","description":"Submit your answer to the current question","type":STR,"required":False,"choices":[{"name":"A","value":"a"},{"name":"B","value":"b"},{"name":"C","value":"c"}]}]},
 {"name": "battle", "description": "Start or answer a simulated Forex Battle Arena round.",
  "options": [{"name":"answer","description":"Submit your answer to the current round","type":STR,"required":False,"choices":[{"name":"A","value":"a"},{"name":"B","value":"b"},{"name":"C","value":"c"}]}]},
 {"name": "tournament", "description": "View your practice tournament score and standings."},
]
req = urllib.request.Request(f"https://discord.com/api/v10/applications/{os.environ['DISCORD_APP_ID']}/guilds/{GUILD}/commands",
    data=json.dumps(CMDS).encode(), method="PUT",
    headers={"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}", "Content-Type": "application/json", "User-Agent": "HolisticCoach"})
print([c["name"] for c in json.load(urllib.request.urlopen(req))])
