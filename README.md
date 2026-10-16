# Holistic Market Pulse (Discord)

Posts to your Discord #general through the "Holistic Market Pulse" webhook. Runs free on GitHub Actions. No AI, no computer needed.

- **Live board**: one message, edited every 15 minutes Sun–Fri (pin it).
- **Pulse posts**: 7:45 AM, 12:00 PM, 3:15 PM CT on weekdays, plus a Saturday 10 AM crypto check. Each ends with a discussion question.
- Order: Forex (incl. your 11 calls), then Crypto, then Stocks.

## Setup (about 5 minutes)
1. Create a free GitHub account (github.com) if you don't have one.
2. New repository → name it `holistic-market-pulse` → **Private** → Create.
3. "uploading an existing file" → drag in `pulse.py`, `README.md`, and the `.github` folder (keep the path `.github/workflows/pulse.yml`) → Commit.
4. Repo **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DISCORD_WEBHOOK_URL`  Value: your webhook link (Discord → #general settings → Integrations → Webhooks → Holistic Market Pulse → Copy Webhook URL).
5. **Actions** tab → enable workflows → "Holistic Market Pulse" → **Run workflow** with mode `board`. A board message appears in #general.
6. In Discord, right-click that message → **Pin**. Right-click again → **Copy Message ID** (turn on Developer Mode in Discord settings → Advanced if you don't see it).
7. Back in GitHub: **Settings → Secrets and variables → Actions → Variables → New variable** `BOARD_MESSAGE_ID` = that id.
8. Run workflow once more with mode `pulse` to test a post. Done — it runs on its own from here.

## Notes
- Cron times are UTC set for Central Daylight Time. After Nov 1 (Central Standard), posts land one hour earlier unless you add 1 to each hour in `pulse.yml`.
- GitHub's scheduler can run a few minutes late under load.
- Update your open calls in the `CALLS` list at the top of `pulse.py`.
- Keep the webhook link secret. To revoke, delete the webhook in Discord.

## Auto-tracking new calls
The board's "On our calls" section also reads new calls from **#trade-alert** (needs `DISCORD_BOT_TOKEN`) and from your **Substack feed** (no setup). Write calls in this format so the bot can read them:

```
$USDJPY (Weekly) — Long
Entry: 155.00–156.00
Target: T1 160.50
Invalid: weekly close below 153.40
```
Any ticker works: forex pairs ($USDJPY), gold ($XAUUSD), crypto ($BTC), stocks ($NVDA). Needs the ticker, long/short, and a target or invalidation.
To remove one: post `Closed $USDJPY`. A newer call on the same ticker replaces the old one. The board shows the newest 12.

### One-time bot setup (for #trade-alert)
1. discord.com/developers/applications → New Application → "Holistic Market Pulse".
2. Bot tab → Reset Token → copy it. On the same page, turn ON "Message Content Intent" → Save.
3. OAuth2 → URL Generator → scope `bot` → permissions `View Channels` + `Read Message History` → open the URL → add to Holistic Traders.
4. GitHub repo → Settings → Secrets and variables → Actions → New secret `DISCORD_BOT_TOKEN` = the token.

## Holistic Trivia + Dojo belts (#off-topic)
- A poll round every 2 hours, 8 AM to 8 PM CT, daily. Each poll is open 2 hours, and the answer and explanation drop with the next round.
- Market-legend quotes at 10 AM, 2 PM and 6 PM. The leaderboard posts at 9:30 PM CT.
- Points: correct answer 3, any vote 1, chat activity 1 per message (max 5/day), and +2/day once you're on a 3+ day streak.
- Belts (all-time points) are given as colored Discord roles: ⚪ White, 🟡 Yellow 10, 🟠 Orange 25, 🟢 Green 50, 🔵 Blue 100, 🟣 Purple 175, 🟤 Brown 275, ⚫ Black 400.
- Needs the secret `OFFTOPIC_WEBHOOK_URL`. Scoring and belt roles also need `DISCORD_BOT_TOKEN`, with the bot granted View Channels, Read Message History and **Manage Roles**.
- Questions and quotes live in `trivia_bank.py`. Edit them anytime.
- To relaunch the announcement, edit `launch.txt`.
