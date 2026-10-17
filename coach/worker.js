// Holistic Coach: Discord slash-command AI for Holistic Traders.
// Runs on Cloudflare Workers. Secrets (set in Cloudflare, never in code):
//   DISCORD_PUBLIC_KEY, DISCORD_APP_ID, ANTHROPIC_API_KEY
// Optional var: MODEL (default below), DAILY_LIMIT (per member, default 15)
//
// Commands: /analyze  /journal  /risk  /coach
// /risk is plain math (no AI). The others call Claude with a strict
// "educate, quantify risk, never predict" system prompt.

const DEFAULT_MODEL = "claude-sonnet-5-5";

const SYSTEM = `You are Holistic Coach, the trading mentor bot for the Holistic Traders Discord.
House method: swing trading supply and demand. Buy wholesale (demand), sell retail (supply). Every trade needs an entry zone, a target, and an invalidation level, judged on weekly closes. Small risk per trade (usually 0.5-2%), wide stops, patience. Many members are working prop-firm challenges, so daily-loss and max-drawdown rules matter.

Rules you never break:
- You do not predict where price will go and you never say a trade "will" work. Talk in scenarios: "if X holds... if Y breaks...".
- Always state uncertainty plainly and name what would make the idea wrong.
- Never tell someone to buy or sell. Explain structure, risk, and process so they decide.
- If data is missing (no chart, no levels), say what you'd need instead of guessing.
- Numbers you are given (prices, % changes) are the only market data you have. Do not invent prices, news, or levels.
- Be direct, warm, and concise. Discord format, under 1800 characters. Short headers or bullets are fine.
- End every reply with: "Education only, not financial advice."`;

const STYLES = {
  risk: { label: "🛡️ The Risk Manager", prompt: "Coaching style: THE RISK MANAGER. Lead with position size, % risked, total exposure, correlated positions, and drawdown math. Challenge anything above 2% risk or stacked exposure in the same currency. Ask: 'What happens to the account if this and your other open trades all stop out?'" },
  technical: { label: "📐 The Technical Analyst", prompt: "Coaching style: THE TECHNICAL ANALYST. Lead with structure: trend on the weekly, wholesale (demand) and retail (supply) zones, prior highs and lows, where invalidation sits on the chart. Teach how to read it, not what will happen." },
  psych: { label: "🧠 The Psychologist", prompt: "Coaching style: THE PSYCHOLOGIST. Lead with behavior and emotion. Ask about impulsive entries, revenge trading after losses, FOMO, boredom trades, moving stops, and how they felt before clicking. Be curious and non-judgmental, and ask one or two reflective questions." },
  prop: { label: "🏦 The Prop Firm Coach", prompt: "Coaching style: THE PROP FIRM COACH. Lead with challenge rules: daily loss limit, max drawdown, consistency rules, minimum trading days, news restrictions, and weekend holding. Translate every idea into 'does this keep the account alive and passing?'. Rules differ by firm, so tell them to confirm with their firm's own rulebook." },
};
const DEFAULT_STYLE = "technical";

async function getStyle(env, userId, override) {
  if (override && STYLES[override]) return override;
  if (env.LIMITS) { const s = await env.LIMITS.get(`style:${userId}`); if (s && STYLES[s]) return s; }
  return DEFAULT_STYLE;
}

const enc = new TextEncoder();
const hex = (h) => new Uint8Array(h.match(/.{2}/g).map((b) => parseInt(b, 16)));

async function verify(req, body, env) {
  const sig = req.headers.get("x-signature-ed25519");
  const ts = req.headers.get("x-signature-timestamp");
  if (!sig || !ts) return false;
  const key = await crypto.subtle.importKey("raw", hex(env.DISCORD_PUBLIC_KEY), { name: "Ed25519" }, false, ["verify"]);
  return crypto.subtle.verify("Ed25519", key, hex(sig), enc.encode(ts + body));
}

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });
const opt = (data, name) => (data.options || []).find((o) => o.name === name)?.value;

// ---------- /risk: pure math ----------
function riskCalc(data) {
  const equity = Number(opt(data, "equity"));
  const riskPct = Number(opt(data, "risk_percent"));
  const entry = Number(opt(data, "entry"));
  const stop = Number(opt(data, "stop"));
  const sym = String(opt(data, "symbol") || "").toUpperCase().replace("/", "");
  if (!(equity > 0 && riskPct > 0 && entry > 0 && stop > 0) || entry === stop)
    return "I need a positive equity, risk %, entry and stop (and entry can't equal stop).";
  const riskUsd = (equity * riskPct) / 100;
  const dist = Math.abs(entry - stop);
  let units = riskUsd / dist; // correct when the instrument is quoted in USD
  let note = "";
  const isFx = /^[A-Z]{6}$/.test(sym);
  if (isFx && !sym.endsWith("USD")) {
    if (sym.startsWith("USD")) { units = (riskUsd * stop) / dist; note = `Converted at your stop price (${stop}) because ${sym} is quoted in ${sym.slice(3)}.`; }
    else note = `${sym} isn't quoted in USD, so treat this as approximate. Your platform's position calculator is the final word.`;
  }
  const lines = [
    `🧮 **Position size: ${sym || "your trade"}**`,
    `Account: $${equity.toLocaleString()} · Risk: ${riskPct}% = **$${riskUsd.toFixed(2)}**`,
    `Entry ${entry} · Stop ${stop} · Distance ${dist.toPrecision(4)}`,
  ];
  if (isFx) {
    const pip = sym.includes("JPY") ? 0.01 : 0.0001;
    lines.push(`Stop distance: **${(dist / pip).toFixed(1)} pips**`, `Size: **${units.toFixed(0)} units ≈ ${(units / 100000).toFixed(2)} standard lots** (${(units / 1000).toFixed(1)} micro lots)`);
  } else {
    lines.push(`Size: **${units < 10 ? units.toFixed(4) : units.toFixed(2)} units/shares/coins**`);
  }
  if (note) lines.push(`-# ${note}`);
  if (riskPct > 2) lines.push(`⚠️ ${riskPct}% per trade is aggressive. Ten losses in a row would cost about ${(100 - 100 * Math.pow(1 - riskPct / 100, 10)).toFixed(0)}% of the account.`);
  lines.push("-# Check against your prop firm's daily loss limit. Education only, not financial advice.");
  return lines.join("\n");
}

// ---------- market data for /analyze ----------
function yahooSymbol(s) {
  s = s.toUpperCase().replace("/", "").replace("$", "");
  const ccy = ["USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF","ZAR","MXN","NOK","SEK"];
  if (s === "XAUUSD" || s === "GOLD") return "GC=F";
  if (s.length === 6 && ccy.includes(s.slice(0, 3)) && ccy.includes(s.slice(3))) return s + "=X";
  if (["BTC","ETH","SOL","XRP","DOGE","ADA"].includes(s.replace(/USDT?$/, ""))) return s.replace(/USDT?$/, "") + "-USD";
  return s;
}

async function marketSnapshot(sym) {
  const y = yahooSymbol(sym);
  const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(y)}?range=1y&interval=1wk`, { headers: { "user-agent": "Mozilla/5.0" } });
  if (!r.ok) return null;
  const res = (await r.json())?.chart?.result?.[0];
  if (!res) return null;
  const q = res.indicators.quote[0];
  const rows = res.timestamp.map((t, i) => ({ d: new Date(t * 1000).toISOString().slice(0, 10), h: q.high[i], l: q.low[i], c: q.close[i] })).filter((x) => x.c);
  const p = res.meta.regularMarketPrice;
  const pct = (n) => { const b = rows[Math.max(0, rows.length - 1 - n)]?.c; return b ? (((p / b) - 1) * 100).toFixed(1) + "%" : "n/a"; };
  const hi = Math.max(...rows.map((x) => x.h)), lo = Math.min(...rows.map((x) => x.l));
  const last8 = rows.slice(-8).map((x) => `${x.d}: H ${x.h.toPrecision(6)} L ${x.l.toPrecision(6)} C ${x.c.toPrecision(6)}`).join("\n");
  return `Symbol ${sym} (${y}). Price now ${p}. Change: 4w ${pct(4)}, 13w ${pct(13)}, 26w ${pct(26)}, 52w ${pct(52)}. 52-week high ${hi.toPrecision(6)}, low ${lo.toPrecision(6)}.\nLast 8 weekly candles:\n${last8}\n(Data: Yahoo Finance, may be delayed.)`;
}

// ---------- Claude ----------
async function askClaude(env, userContent, style) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": env.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: env.MODEL || DEFAULT_MODEL, max_tokens: 900, system: SYSTEM + "\n\n" + STYLES[style].prompt, messages: [{ role: "user", content: userContent }] }),
  });
  if (!r.ok) throw new Error("AI error " + r.status);
  const out = await r.json();
  return out.content.filter((b) => b.type === "text").map((b) => b.text).join("\n").slice(0, 1950);
}

async function buildPrompt(name, data, resolved) {
  if (name === "analyze") {
    const sym = String(opt(data, "symbol") || "");
    const question = opt(data, "question") || "Walk me through the structure: where is wholesale, where is retail, and what would invalidate a long or a short?";
    const att = opt(data, "chart");
    const snap = sym ? await marketSnapshot(sym) : null;
    const parts = [{ type: "text", text: `Member asks for a chart/setup breakdown of ${sym}.\nQuestion: ${question}\n\nMarket data:\n${snap || "No data available for this symbol."}\n\nGive: 1) the structure in plain words, 2) likely demand (wholesale) and supply (retail) areas based ONLY on this data, 3) bullish and bearish scenarios with what invalidates each, 4) the main uncertainty. No predictions.` }];
    const url = att && resolved?.attachments?.[att]?.url;
    if (url) parts.push({ type: "image", source: { type: "url", url } });
    return parts;
  }
  if (name === "journal") return [{ type: "text", text: `Review this trade like a coach. Identify process mistakes (entry, stop placement, sizing, management, emotions) and what was done well. Be specific and kind. Trade:\n${opt(data, "trade")}` }];
  if (name === "coach") return [{ type: "text", text: `Give feedback on these trading rules. What's clear, what's vague, what's missing (entry, target, invalidation, size, daily loss limit, when to stop trading), and one concrete improvement. Rules:\n${opt(data, "rules")}` }];
  return null;
}

async function followUp(env, token, content) {
  await fetch(`https://discord.com/api/v10/webhooks/${env.DISCORD_APP_ID}/${token}/messages/@original`, {
    method: "PATCH", headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, allowed_mentions: { parse: [] } }),
  });
}

// simple per-member daily limit to control AI cost (uses Cloudflare KV if bound as LIMITS)
async function overLimit(env, userId) {
  if (!env.LIMITS) return false;
  const key = `${userId}:${new Date().toISOString().slice(0, 10)}`;
  const n = Number((await env.LIMITS.get(key)) || 0);
  if (n >= Number(env.DAILY_LIMIT || 15)) return true;
  await env.LIMITS.put(key, String(n + 1), { expirationTtl: 172800 });
  return false;
}

export default {
  async fetch(req, env, ctx) {
    if (req.method !== "POST") return new Response("Holistic Coach is running.");
    const body = await req.text();
    if (!(await verify(req, body, env))) return new Response("bad signature", { status: 401 });
    const i = JSON.parse(body);
    if (i.type === 1) return json({ type: 1 }); // Discord PING
    if (i.type !== 2) return json({ type: 4, data: { content: "Unsupported." } });

    const name = i.data.name;
    const userId = i.member?.user?.id || i.user?.id;
    if (name === "risk") return json({ type: 4, data: { content: riskCalc(i.data), flags: 0 } });
    if (name === "style") {
      const pick = opt(i.data, "coach");
      if (!STYLES[pick]) return json({ type: 4, data: { content: "Pick one of the four styles.", flags: 64 } });
      if (env.LIMITS) await env.LIMITS.put(`style:${userId}`, pick);
      return json({ type: 4, data: { content: `Your coach is now **${STYLES[pick].label}**. /analyze, /journal and /coach will answer in that style. You can still override it per question with the \`style\` option. 🥋`, flags: 64 } });
    }

    if (await overLimit(env, userId))
      return json({ type: 4, data: { content: "You've hit today's coach limit. Back tomorrow 🥋", flags: 64 } });

    ctx.waitUntil((async () => {
      try {
        const style = await getStyle(env, userId, opt(i.data, "style"));
        const prompt = await buildPrompt(name, i.data, i.data.resolved);
        const answer = prompt ? await askClaude(env, prompt, style) : "Unknown command.";
        await followUp(env, i.token, `-# ${STYLES[style].label}\n${answer}`);
      } catch (e) {
        await followUp(env, i.token, "Coach hit a snag answering that. Try again in a minute.");
      }
    })());
    return json({ type: 5 }); // "Holistic Coach is thinking..."
  },
};

export { riskCalc, yahooSymbol, STYLES }; // for local tests
