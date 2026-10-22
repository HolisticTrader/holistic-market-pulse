#!/usr/bin/env python3
"""Posts one rotating Holistic Trader promo or insight to X (Twitter) via the official API v2.
Env (GitHub secrets): X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
State: state/xpost.json remembers recent picks so posts don't repeat back-to-back."""
import os, json, time, random, hmac, hashlib, base64, urllib.parse, urllib.request, uuid
import netretry  # retries temporary network/Discord/X hiccups

OFFERS = {
 "substack": "https://immaculatetonyeth.substack.com",
 "ebook": "https://holistictrader.gumroad.com/l/holistictraders",
 "udemy": "https://udemy.com/course/holistictraders/?referralcode=0facd4fc29218d594d31",
 "discord": "https://discord.gg/PYUKcPWdj8",
 "shop": "https://holistictrader.threadless.com/",
 "coffee": "https://buymeacoffee.com/ImmaculateTony.Eth",
}
POSTS = [
 ("substack", "Every call I make gets graded in public. Wins, losses, and what I changed.\n\nThe full breakdowns live on the Holistic Trader Substack 👇\n{u}"),
 ("substack", "Most traders post the entry. Few post the line where they're wrong.\n\nI post both, then grade it after. Free on Substack 👇\n{u}"),
 ("substack", "Levels before the move. Grades after.\n\nThat's the whole newsletter 👇\n{u}"),
 ("ebook", "Buy wholesale. Sell retail. Two levels, one rule, and a lot of patience.\n\nThe full swing-trading playbook is in the Holistic Trader's Blueprint 👇\n{u}"),
 ("ebook", "Supply and demand isn't a pattern. It's where inventory changes hands.\n\nLearn to read it: Holistic Trader's Blueprint 👇\n{u}"),
 ("udemy", "A trading plan isn't a vibe. It's entry, target, invalidation, and size, written down before you click.\n\nBuild yours step by step 👇\n{u}"),
 ("udemy", "Most blown accounts didn't lack a strategy. They lacked a plan.\n\nThe Holistic Trading Plan course 👇\n{u}"),
 ("discord", "Free Discord: live trade alerts, daily market pulse, and Holistic Trivia that earns you a belt from ⚪ to ⚫.\n\nPull up 👇\n{u}"),
 ("discord", "We grade our calls in public and quiz each other on market history for fun.\n\nHolistic Traders Discord 👇\n{u}"),
 ("shop", "Discipline you can wear.\n\nHolistic Traders shop 👇\n{u}"),
 ("coffee", "If my breakdowns have saved you a bad trade, a coffee keeps them coming ☕\n{u}"),
 (None, "The trade isn't over when you're right. It's over when your level breaks or your target hits. Everything in between is noise."),
 (None, "Patience isn't waiting. It's knowing exactly what you're waiting for."),
 (None, "A stop you move isn't a stop. It's a hope."),
 (None, "Weekly closes over intraday wicks. The higher timeframe is where the real decisions get made."),
]

def sign(method, url, params, ck, cs, tk, ts):
    oauth = {"oauth_consumer_key": ck, "oauth_nonce": uuid.uuid4().hex, "oauth_signature_method": "HMAC-SHA1",
             "oauth_timestamp": str(int(time.time())), "oauth_token": tk, "oauth_version": "1.0"}
    allp = {**params, **oauth}
    q = "&".join(f"{urllib.parse.quote(k, '~')}={urllib.parse.quote(v, '~')}" for k, v in sorted(allp.items()))
    base = "&".join(urllib.parse.quote(x, "~") for x in (method, url, q))
    key = f"{urllib.parse.quote(cs, '~')}&{urllib.parse.quote(ts, '~')}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v, "~")}"' for k, v in sorted(oauth.items()))

def main():
    env = [os.environ.get(k, "").strip() for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(env):
        print("X keys not set yet, skipping"); return
    try: st = json.load(open("state/xpost.json"))
    except Exception: st = {"recent": []}
    choices = [i for i in range(len(POSTS)) if i not in st["recent"]]
    i = random.choice(choices)
    key, tpl = POSTS[i]
    text = tpl.format(u=OFFERS.get(key, ""))
    url = "https://api.twitter.com/2/tweets"
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": sign("POST", url, {}, *env)})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("posted:", json.load(r).get("data", {}).get("id"))
    st["recent"] = (st["recent"] + [i])[-8:]
    os.makedirs("state", exist_ok=True); json.dump(st, open("state/xpost.json", "w"))

if __name__ == "__main__":
    main()
