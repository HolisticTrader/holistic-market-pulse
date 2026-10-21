#!/usr/bin/env python3
"""Morning Spark: one insight, test, or question every morning in #general.
Env: DISCORD_WEBHOOK_URL (#general).
State: state/spark.json (no repeats until the bank is used up)."""
import json, os, random, urllib.request, urllib.error

SPARKS = [
 # ---------- insights ----------
 ("insight", "Losses and gains aren't symmetric. Drop 50% and you need +100% just to get back to even. Drop 10% and you need +11%.", "This is why prop firms cap drawdown. Small losses are recoverable, big ones are math problems."),
 ("insight", "Risk 1% per trade and lose 10 in a row: you're down about 9.6%. Risk 5% and the same streak takes about 40% of the account.", "Same strategy, same streak. Size alone decides whether you survive it."),
 ("insight", "A 40% win rate is profitable if your winners are 2R: 0.4 × 2 − 0.6 × 1 = +0.2R per trade.", "Win rate isn't the scoreboard. Expectancy is."),
 ("insight", "Break-even win rates by reward:risk: 1:1 needs 50%. 2:1 needs 33%. 3:1 needs 25%.", "Which one does your current strategy actually need?"),
 ("insight", "Kahneman and Tversky found that losses hit us psychologically about twice as hard as equal gains.", "That's why moving a stop feels better than taking it, even when it's worse."),
 ("insight", "The 'disposition effect' (Shefrin & Statman, 1985): people sell winners too early and hold losers too long.", "Look at your last 10 trades. Do you see it?"),
 ("insight", "Barber & Odean's study of household brokerage accounts ('Trading Is Hazardous to Your Wealth', 2000) found the most active traders earned the lowest returns.", "More trades isn't more opportunity. Often it's more cost and more mistakes."),
 ("insight", "Volatility clusters. Calm periods tend to follow calm periods, and wild ones follow wild ones.", "When the market goes quiet, it's usually not the time to size up and force it."),
 ("insight", "Compounding 1% a week works out to roughly +68% a year (1.01 to the 52nd power).", "Consistency beats home runs, and it's way easier on the nervous system."),
 ("insight", "Survivorship bias: funds and traders who blew up disappear from the stats, so the average 'looks' better than reality.", "Every highlight reel you see online is survivorship bias."),
 ("insight", "In the EU, CFD brokers have to publish the share of retail accounts that lose money. It's commonly 70% or more.", "The edge isn't a secret indicator. It's doing the boring things most people won't."),
 ("insight", "Forex trades around the clock from Sunday evening to Friday afternoon (US time), which is why it gaps on weekends.", "Holding over the weekend is a decision. Make it on purpose."),
 ("insight", "The gambler's fallacy: after five losses in a row, the next trade is not 'due' to win. Each one stands on its own.", "Your edge plays out over 100 trades, not the next one."),
 ("insight", "A stop isn't a prediction that you'll lose. It's the price at which your reason for the trade is no longer true.", "If you can't name that price, you don't have a trade yet."),
 ("insight", "Prop challenges usually aren't failed on the profit target. They're failed on the daily loss or max drawdown rule.", "Pass the risk test first. The profit takes care of itself."),
 # ---------- tests ----------
 ("test", "This week: write your invalidation level BEFORE every entry. No level, no trade.", "Report back Friday: did you take fewer trades? Better ones?"),
 ("test", "For 5 sessions, only take trades with at least 2R of room to your target.", "Track how many setups you skipped. That number says a lot."),
 ("test", "Set alerts at your stop and target, then close the chart. Don't watch P&L tick.", "Did you manage the trade better or worse than usual? Tell us Friday."),
 ("test", "Before every trade this week, rate your emotional state 1–10 in your journal.", "Friday: compare your scores to your results. Any pattern?"),
 ("test", "Before each entry, check the weekly chart first. If the weekly disagrees, pass.", "How many trades did the weekly save you from?"),
 ("test", "Cut your position size in half for one week.", "Did your decisions get calmer? Smaller size often shows you how much fear was driving them."),
 ("test", "Mark your levels on Sunday. All week, trade only those levels.", "Prediction: fewer trades, better entries. Prove it or disprove it."),
 ("test", "Count how many trades you take this week out of boredom, not setup.", "Be honest. Drop your number Friday."),
 ("test", "After every loss this week, wait 30 minutes before the next trade.", "Did it stop revenge trades? Report back."),
 ("test", "Write one sentence of 'why' before each trade. If you can't, don't click.", "Read the sentences back Friday. What do they say about you?"),
 # ---------- questions ----------
 ("question", "Would you rather have a 70% win rate at 0.5R, or a 35% win rate at 3R? Do the math and defend it.", None),
 ("question", "What's one rule you broke this month, and what did it cost you?", None),
 ("question", "If you could only trade ONE pair or coin for a full year, which one, and why?", None),
 ("question", "What's harder for you: getting in or getting out?", None),
 ("question", "You get funded tomorrow with $100k. What's the first thing you do differently?", None),
 ("question", "Do you trust your indicators or your price levels more? Why?", None),
 ("question", "What's the best trading lesson that cost you real money?", None),
 ("question", "Is patience a skill you can train, or a personality trait? Argue it.", None),
 ("question", "If your trading were a business, what's its biggest expense right now?", None),
 ("question", "What's one thing you'd tell yourself on day one of trading?", None),
 ("question", "Weekly close or daily close: which one actually decides your trades?", None),
 ("question", "What's the difference between a pullback and a reversal, in your own words?", None),
 ("question", "What would make you stop trading a strategy that's in a drawdown?", None),
 ("question", "Prop firm challenge or personal account first? Make your case.", None),
 ("question", "What's your non-negotiable rule, the one you never break?", None),
]
ICON = {"insight": "💡 **Insight**", "test": "🧪 **Test this**", "question": "🤔 **Question of the day**"}

import re as _re
def clean_hook(v):
    m = _re.search(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", v or "")
    if not m: raise SystemExit("Webhook setting doesn't contain a valid Discord webhook link")
    return m.group(0)

def main():
    hook = clean_hook(os.environ.get("DISCORD_WEBHOOK_URL"))
    try: s = json.load(open("state/spark.json"))
    except Exception: s = {"used": [], "last_type": ""}
    pool = [i for i in range(len(SPARKS)) if i not in s["used"]] or list(range(len(SPARKS)))
    if len(pool) == len(SPARKS): s["used"] = []
    varied = [i for i in pool if SPARKS[i][0] != s.get("last_type")] or pool  # rotate types
    i = random.choice(varied); kind, body, kicker = SPARKS[i]
    s["used"].append(i); s["last_type"] = kind
    text = f"☀️ **Morning Spark**\n{ICON[kind]}\n\n{body}"
    if kicker: text += f"\n\n*{kicker}*"
    text += "\n\n💬 Reply below. Good answers earn activity points toward your belt 🥋"
    req = urllib.request.Request(hook + "?wait=true", data=json.dumps({"content": text, "username": "Holistic Trivia", "allowed_mentions": {"parse": []}}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (HolisticSpark)"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except urllib.error.HTTPError as e:
        print("Discord rejected the post:", e.code, e.read()[:200]); raise
    except Exception as e:
        print("Could not reach the webhook (check the DISCORD_WEBHOOK_URL secret):", type(e).__name__); raise
    os.makedirs("state", exist_ok=True); json.dump(s, open("state/spark.json", "w"))
    print("posted spark", i, kind)

if __name__ == "__main__":
    main()
