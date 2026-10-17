# Holistic Coach (Discord slash-command AI)

Commands: `/analyze` (chart/setup breakdown, optional screenshot) · `/journal` (trade review) · `/risk` (position size, pure math, no AI) · `/coach` (rules feedback) · `/style` (pick your coach).
Styles: 🛡️ Risk Manager · 📐 Technical Analyst · 🧠 Psychologist · 🏦 Prop Firm Coach.
The AI is instructed never to predict price, always to state uncertainty and invalidation, and to end with "Education only, not financial advice."

## What you need (about 15 minutes, one time)
1. **Discord bot**: the same "Holistic Dojo" app from the belts setup. From its General Information page, copy the **Application ID** and **Public Key**.
2. **Anthropic API key**: console.anthropic.com → API Keys. This is pay-per-use. Set a monthly spend limit in the console.
3. **Cloudflare account** (free): dash.cloudflare.com → Workers & Pages → Create Worker → name it `holistic-coach` → Edit code → paste `worker.js` → Deploy.
   - Worker → Settings → Variables and Secrets: add secrets `DISCORD_PUBLIC_KEY`, `DISCORD_APP_ID`, `ANTHROPIC_API_KEY`.
   - Optional: create a KV namespace and bind it as `LIMITS`. That enables saved coaching styles and a 15-questions-per-member daily cap.
4. Copy the Worker URL (e.g. `https://holistic-coach.<you>.workers.dev`) → Discord Developer Portal → your app → General Information → **Interactions Endpoint URL** → paste → Save. Discord tests it right away.
5. GitHub repo → Settings → Variables → add `DISCORD_APP_ID`. Then edit `coach/register.txt` (any change) to register the commands. Needs the `DISCORD_BOT_TOKEN` secret.
