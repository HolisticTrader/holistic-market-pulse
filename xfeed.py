#!/usr/bin/env python3
"""Posts the "Hot on X" digest (top 5 X posts on Tony's open pairs) to Discord.
The Holistic X hot feed scheduled task writes the finished post into xfeed.txt and pushes it;
the push runs this through .github/workflows/xfeed.yml. Empty file = nothing to post."""
import json, os, re, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (HolisticMarketPulse)"}

def main():
    text = open("xfeed.txt", encoding="utf-8").read().strip() if os.path.exists("xfeed.txt") else ""
    if not text:
        print("xfeed.txt is empty: nothing to post.")
        return
    # Wrap X links in <> so Discord doesn't stack five big link previews under the post.
    text = re.sub(r"(?<!<)(https?://(?:x|twitter)\.com/\S+)", r"<\1>", text)
    payload = {"content": text[:2000], "username": "Hot on X", "allowed_mentions": {"parse": []}}
    hook = os.environ["DISCORD_WEBHOOK_URL"].rstrip("/")
    req = urllib.request.Request(hook + "?wait=true", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("posted message id:", json.load(r).get("id"))

if __name__ == "__main__":
    main()
