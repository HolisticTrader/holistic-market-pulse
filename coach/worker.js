// Holistic Coach: Discord slash-command AI for Holistic Traders.
// Runs on Cloudflare Workers. Secrets (set in Cloudflare, never in code):
//   DISCORD_PUBLIC_KEY, DISCORD_APP_ID, ANTHROPIC_API_KEY
// Optional var: MODEL (default below), DAILY_LIMIT (per member, default 15)
//
// Commands: /analyze /journal /risk /coach /style /ask-mentor /lesson
//           /study-plan /challenge /quiz /battle /tournament
// /risk is plain math (no AI). The others call Claude with a strict
// "educate, quantify risk, never predict" system prompt.

const DEFAULT_MODEL = "claude-sonnet-5";

const SYSTEM = `You are Holistic Coach, the trading mentor bot for the Holistic Traders Discord.
House method: swing trading supply and demand. Buy wholesale (demand), sell retail (supply). Every trade needs an entry zone, a target, and an invalidation level, judged on weekly closes. Small risk per trade (usually 0.5-2%), wide stops, patience. Many members are working prop-firm challenges, so daily-loss and max-drawdown rules matter. The course pages are links, not an indexed lesson library: never claim that a specific rule or Fib anchor came from a course unless the member supplies that lesson text.

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

const COURSE = {
  udemy: "https://www.udemy.com/course/holistictraders/?referralcode=0facd4fc29218d594d31",
  ebook: "https://holistictrader.gumroad.com/l/holistictraders",
  substack: "https://immaculatetonyeth.substack.com/",
};

const QUIZZES = [
  { q: "A trader risks 1% of a $10,000 account on one idea. What is the planned loss at the stop?", a: "b", choices: "A) $10   B) $100   C) $1,000", explain: "$10,000 × 1% = $100." },
  { q: "Price closes below the weekly swing low used to frame a bullish setup. What is the disciplined next step?", a: "c", choices: "A) Add to the position   B) Move the stop lower   C) Reassess or invalidate the idea", explain: "A weekly close through the chosen invalidation level means the original thesis needs reassessment." },
  { q: "Which is the safest basis for a chart quiz in this arena?", a: "a", choices: "A) Historical or simulated data   B) Guessing the next live candle   C) Copying another member's live entry", explain: "The arena is for education on historical or simulated examples, never live next-candle betting." },
  { q: "A prop account has a daily loss limit. What belongs in the plan before a trade?", a: "b", choices: "A) Only the profit target   B) The trade risk plus existing daily loss and exposure   C) The largest available lot size", explain: "The remaining daily loss buffer includes realized losses and open risk under that firm's rules." },
];

const LESSONS = [
  "📘 [Holistic Trader's Blueprint ebook](" + COURSE.ebook + ")",
  "🎓 [Holistic Trading Plan course on Udemy](" + COURSE.udemy + ")",
  "📰 [Holistic Trader Newsletter / Substack](" + COURSE.substack + ")",
];

const sub = (data) => (data.options || []).find((x) => x.type === 1);
const subOpt = (data, name) => (sub(data)?.options || []).find((x) => x.name === name)?.value;
const escapeText = (s) => String(s ?? "").replace(/[<>]/g, "");

async function getRecord(env, key) {
  if (!env.LIMITS) return null;
  try { return await env.LIMITS.get(key, "json"); } catch { return null; }
}
async function putRecord(env, key, value, ttl = 15552000) {
  if (!env.LIMITS) return false;
  await env.LIMITS.put(key, JSON.stringify(value), { expirationTtl: ttl });
  return true;
}

function challengeText(c, current, todayPnl) {
  const equity = Number(current);
  if (!(equity > 0)) return "Enter a positive current balance/equity to see your progress.";
  const start = Number(c.start_balance), size = Number(c.account_size || c.start_balance);
  const target = start * Number(c.target_pct) / 100;
  const dailyLimit = size * Number(c.daily_loss_pct) / 100;
  const overallLimit = size * Number(c.max_loss_pct) / 100;
  const todayLoss = Math.max(0, -Number(todayPnl || 0));
  const remaining = Math.max(0, dailyLimit - todayLoss);
  const profit = equity - start;
  const passed = profit >= target && Number(c.days_done || 0) >= Number(c.min_days || 0);
  const phase = escapeText(c.phase || "Phase 1");
  return `🏦 **${escapeText(c.firm)} · ${escapeText(c.program)} · ${phase}**\n` +
    `Progress: ${profit >= 0 ? "+" : ""}$${profit.toFixed(2)} / $${target.toFixed(2)} target (${Number(c.target_pct)}%). ${passed ? "✅ Target and configured day count reached." : "Target/day requirements not yet met."}\n` +
    `Current balance: $${equity.toFixed(2)} · Daily loss room: $${remaining.toFixed(2)} of $${dailyLimit.toFixed(2)} · Max loss: $${overallLimit.toFixed(2)} from the configured starting balance.\n` +
    `Trading days: ${Number(c.days_done || 0)} / ${Number(c.min_days || 0)} · Markets: ${escapeText(c.markets || "confirm for program")} · Swing holding: ${c.swing ? "selected as allowed" : "not confirmed"}\n` +
    `Rules: ${c.rules_url ? `<${c.rules_url}>` : "use your program's current official rule page"}. Values are member-entered tracking settings. Confirm equity, reset times, drawdown method, and all rules with the firm before trading.`;
}

async function handleChallenge(env, data, userId) {
  const action = sub(data)?.name;
  const key = `challenge:${userId}`;
  if (action === "start") {
    const c = {
      firm: subOpt(data, "firm"), program: subOpt(data, "program"), phase: subOpt(data, "phase"),
      account_size: subOpt(data, "account_size"), start_balance: subOpt(data, "start_balance"),
      target_pct: subOpt(data, "target_pct"), daily_loss_pct: subOpt(data, "daily_loss_pct"),
      max_loss_pct: subOpt(data, "max_loss_pct"), min_days: subOpt(data, "min_days"),
      days_done: subOpt(data, "days_done"), markets: subOpt(data, "markets"),
      swing: subOpt(data, "swing"), rules_url: subOpt(data, "rules_url"), updated_at: new Date().toISOString(),
    };
    if (!await putRecord(env, key, c)) return "Challenge tracking needs the Cloudflare KV binding named `LIMITS`. Ask an admin to finish the setup before starting.";
    return `✅ Challenge tracker started. Set every field from your exact account dashboard/rulebook; programs change.\n${challengeText(c, c.start_balance, 0)}\n\nOfficial rule references: [FTMO objectives](https://ftmo.com/en/trading-objectives/) · [FTMO Swing](https://ftmo.com/en/faq/ftmo-swing-account-type/) · [The5ers High Stakes](https://the5ers.com/high-stakes/)`;
  }
  if (action === "status") {
    const c = await getRecord(env, key);
    if (!c) return "No saved challenge yet. Use `/challenge start` and enter the exact program rules and baseline.";
    return challengeText(c, subOpt(data, "current_balance"), subOpt(data, "today_pnl"));
  }
  return "Use `/challenge start` to configure a tracker or `/challenge status` to update your balance and today's P&L.";
}

async function handleQuiz(env, data, userId, command) {
  if (!env.LIMITS) return "The learning game needs the Cloudflare KV binding named `LIMITS` for questions and scores. Ask an admin to finish setup.";
  if (command === "tournament") {
    const score = Number((await env.LIMITS.get(`score:${userId}`)) || 0);
    return `🏆 **Weekly practice standings**\nYour completed quiz points: **${score}**. Tournaments are practice-only; there are no live-market predictions or financial prizes configured. Members can use `/quiz` for the next historical/simulated question.`;
  }
  const answer = String(opt(data, "answer") || "").trim().toLowerCase();
  const pendingKey = `quiz:${userId}`;
  if (answer) {
    const p = await getRecord(env, pendingKey);
    if (!p) return "Start a fresh historical/simulated question with `/quiz` or `/battle` first.";
    await env.LIMITS.delete(pendingKey);
    const correct = answer === p.answer;
    if (correct) {
      const key = `score:${userId}`;
      await env.LIMITS.put(key, String(Number((await env.LIMITS.get(key)) || 0) + 1));
    }
    return `${correct ? "✅ Correct" : "❌ Not quite"}. ${p.explain}\n${command === "battle" ? "Practice point: " + (correct ? "1" : "0") + ". " : ""}Education only; this question uses a simulated example, not live prices.`;
  }
  const q = QUIZZES[Math.floor(Math.random() * QUIZZES.length)];
  await putRecord(env, pendingKey, { answer: q.a, explain: q.explain }, 600);
  return `${command === "battle" ? "⚔️ **Battle Arena · simulated round**" : "🧠 **Practice quiz · historical/simulated**"}\n${q.q}\n${q.choices}\nReply with `/quiz answer:a` (or b/c) to check. This is a learning game, not a live-market call.`;
}

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
  const span = hi - lo;
  const fib = [0, .236, .382, .5, .618, .786, 1].map((r) => `${(r * 100).toFixed(r === 0 || r === 1 ? 0 : 1)}% ${(hi - span * r).toPrecision(6)}`).join(" · ");
  const rangeNote = `\nWeekly Fib reference (mechanical 52-week low ${lo.toPrecision(6)} to high ${hi.toPrecision(6)}; retracement from high): ${fib}. Midpoint ${((hi + lo) / 2).toPrecision(6)}. Approximate wholesale/discount area: 50-61.8% retracement; approximate retail/premium area: above the midpoint. The 52-week extremes are context, not verified course-selected swing anchors or confirmed supply/demand zones.`;
  const last8 = rows.slice(-8).map((x) => `${x.d}: H ${x.h.toPrecision(6)} L ${x.l.toPrecision(6)} C ${x.c.toPrecision(6)}`).join("\n");
  return `Symbol ${sym} (${y}). Price now ${p}. Change: 4w ${pct(4)}, 13w ${pct(13)}, 26w ${pct(26)}, 52w ${pct(52)}. 52-week high ${hi.toPrecision(6)}, low ${lo.toPrecision(6)}.${rangeNote}\nLast 8 weekly candles:\n${last8}\n(Data: Yahoo Finance, may be delayed.)`;
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
  if (name === "ask-mentor") {
    const excerpt = opt(data, "lesson_excerpt");
    if (!excerpt) return [{ type: "text", text: `The course links are available, but their lesson content is not indexed in this bot yet. I won't guess what the course says. Paste the relevant passage into the optional lesson_excerpt field and ask again.\n\n${LESSONS.join("\n")}` }];
    return [{ type: "text", text: `Answer only from the member-supplied approved lesson excerpt below. If it does not answer the question, say so and give the relevant course link. Do not add unsourced trading rules. Explain it simply and cite the excerpt topic if given.\nQuestion: ${opt(data, "question")}\nLesson excerpt: ${excerpt}\n\nCourse links:\n${LESSONS.join("\n")}` }];
  }
  if (name === "study-plan") return [{ type: "text", text: `Build a practical 7-day swing-trading study plan for these goals: ${opt(data, "goals")}. Link each day to one of the approved resources below. Do not invent specific lesson titles, page numbers, or claim the materials were reviewed. Cover weekly structure, supply/demand, Fib practice with disclosed anchors, risk, journaling, and review. Include a short task each day.\n${LESSONS.join("\n")}` }];
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
    if (["challenge"].includes(name)) return json({ type: 4, data: { content: await handleChallenge(env, i.data, userId), flags: 64, allowed_mentions: { parse: [] } } });
    if (["quiz", "battle", "tournament"].includes(name)) return json({ type: 4, data: { content: await handleQuiz(env, i.data, userId, name), flags: name === "quiz" ? 64 : 0, allowed_mentions: { parse: [] } } });
    if (name === "lesson") return json({ type: 4, data: { content: `📚 **Holistic Trader learning links**\nTopic requested: ${escapeText(opt(i.data, "topic") || "swing trading, supply and demand, weekly charts")}\n${LESSONS.join("\n")}\n\nThe bot does not have lesson-by-lesson indexing yet. Open the course or paste a lesson excerpt into `/ask-mentor` for a source-grounded explanation.`, flags: 64, allowed_mentions: { parse: [] } } });
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
