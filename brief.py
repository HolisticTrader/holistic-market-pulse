#!/usr/bin/env python3
"""Holistic Morning Brief (trading days): economic calendar, currency headlines, watchlist,
and rule-conflict warnings, every item with a source link and timestamp.
Sources: ForexFactory calendar feed (faireconomy.media), Google News RSS, Yahoo Finance.
Env: DISCORD_WEBHOOK_URL (#general)."""
import json, os, re, datetime, urllib.request, urllib.parse, html
from zoneinfo import ZoneInfo
import pulse  # reuse prices + call list

CT = ZoneInfo("America/Chicago")
UA = {"User-Agent": "Mozilla/5.0 (HolisticBrief)"}
CAL_URLS = ["https://nfs.faireconomy.media/ff_calendar_thisweek.json", "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"]
CCYS = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
NEWS_Q = {"USD": "Federal Reserve OR US dollar", "EUR": "ECB OR euro currency", "GBP": "Bank of England OR pound sterling",
          "JPY": "Bank of Japan OR yen", "Other": "forex market currencies"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read().decode("utf-8", "replace")

def calendar(today):
    for u in CAL_URLS:
        try:
            ev = json.loads(get(u)); break
        except Exception as e:
            print("calendar fetch failed", u, e); ev = None
    if not ev: return None
    out = []
    for e in ev:
        try: t = datetime.datetime.fromisoformat(e["date"]).astimezone(CT)
        except Exception: continue
        if t.date() == today and e.get("impact") in ("High", "Medium") and e.get("country") in CCYS:
            out.append((t, e))
    return sorted(out, key=lambda x: x[0])

def ff_link(day):
    return f"https://www.forexfactory.com/calendar?day={day.strftime('%b').lower()}{day.day}.{day.year}"

def headlines(ccy, q, n=1):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"({q}) when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try: xml = get(url)
    except Exception as e:
        print("news failed", ccy, e); return []
    items = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S)[:n]:
        title = html.unescape(re.sub(r"<.*?>", "", (re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1]))
        link = (re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1].strip()
        pub = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
        try: ts = datetime.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc).astimezone(CT).strftime("%b %d %I:%M %p CT")
        except Exception: ts = "time n/a"
        items.append(f"• [{title[:110]}]({link}) · {ts}")
    return items

def trending():
    """Social pulse: StockTwits trending tickers + r/Forex hot posts. Both optional, fail quietly."""
    out = []
    try:
        d = json.loads(get("https://api.stocktwits.com/api/2/trending/symbols.json"))
        syms = d.get("symbols", [])[:10]
        if syms:
            out.append("**StockTwits trending:** " + " · ".join(f"[${x['symbol']}](https://stocktwits.com/symbol/{x['symbol']})" for x in syms))
    except Exception as e:
        print("stocktwits failed", e)
    try:
        xml = get("https://www.reddit.com/r/Forex/hot/.rss?limit=6")
        posts = []
        for en in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
            title = html.unescape((re.search(r"<title>(.*?)</title>", en, re.S) or [None, ""])[1])
            link = (re.search(r'<link href="(.*?)"', en) or [None, ""])[1]
            upd = (re.search(r"<updated>(.*?)</updated>", en) or [None, ""])[1]
            if not title or "Daily" in title or "Weekly" in title: continue
            try: ts = datetime.datetime.fromisoformat(upd).astimezone(CT).strftime("%b %d %I:%M %p CT")
            except Exception: ts = ""
            posts.append(f"• [{title[:100]}]({link}) · {ts}")
            if len(posts) == 3: break
        if posts: out.append("**r/Forex hot:**\n" + "\n".join(posts))
    except Exception as e:
        print("reddit failed", e)
    return out

def build():
    now = datetime.datetime.now(CT); today = now.date()
    stamp = now.strftime("%a %b %d, %I:%M %p CT")
    embeds = []

    cal = calendar(today)
    if cal is None:
        cal_txt = f"Calendar feed unavailable this morning. Check it directly: [ForexFactory]({ff_link(today)})"
    elif not cal:
        cal_txt = f"No high or medium impact releases today for the majors. [Verify on ForexFactory]({ff_link(today)})"
    else:
        rows = []
        for t, e in cal:
            dot = "🔴" if e["impact"] == "High" else "🟠"
            fx = " · ".join(x for x in [f"F {e['forecast']}" if e.get("forecast") else "", f"P {e['previous']}" if e.get("previous") else ""] if x)
            rows.append(f"{dot} `{t.strftime('%I:%M %p')}` **{e['country']}** {e['title']}" + (f" ({fx})" if fx else ""))
        cal_txt = "\n".join(rows[:20]) + f"\n\n[Source: ForexFactory calendar]({ff_link(today)}) · times in CT · F = forecast, P = previous"
    embeds.append({"title": "🗓️ Economic releases today", "description": cal_txt[:4000], "color": 0xE74C3C})

    news = []
    for c, q in NEWS_Q.items():
        h = headlines(c, q)
        if h: news.append(f"**{c}** " + "\n".join(h).lstrip("• "))
    embeds.append({"title": "📰 Currency headlines (last 24h)", "description": ("\n".join(news) or "No headlines pulled this morning.")[:4000]
                   + "\n-# Headlines via Google News. Open the link to read the original source.", "color": 0x3498DB})

    hot = trending()
    if hot:
        embeds.append({"title": "🔥 What traders are talking about", "description": "\n\n".join(hot)[:4000]
                       + "\n-# Social chatter isn't analysis. Use it to see what the crowd is watching, not what to trade.", "color": 0xE67E22})

    calls = pulse.all_calls()
    watch = []
    for name, sym, side, tgt, inv in calls[:12]:
        p, chg = pulse.quote(sym)
        if p is None: continue
        watch.append(f"`{name:<7}` {p:.5g}  ({chg:+.2f}% 1W) · {side}" + (f" · T {tgt:g}" if tgt else "") + (f" · stop {inv:g}" if inv else ""))
    embeds.append({"title": "👀 Watchlist (our open calls)", "description": ("\n".join(watch) or "No open calls.") + "\n-# Prices: Yahoo Finance, may be delayed.", "color": 0x2ECC71})

    warn = []
    if cal:
        involved = {}
        for name, sym, *_ in calls:
            for c in CCYS:
                if c in name.replace("/", ""): involved.setdefault(c, []).append(name)
        for t, e in cal:
            if e["impact"] == "High" and e["country"] in involved:
                warn.append(f"⚠️ `{t.strftime('%I:%M %p')}` **{e['country']} {e['title']}** hits {', '.join(sorted(set(involved[e['country']])))}")
        if now.weekday() == 4:
            warn.append("⚠️ It's Friday. If your firm restricts weekend holding, plan exits before the close.")
    if warn:
        warn.append("Many prop firms restrict opening or closing trades in a window around high-impact news (often ±2–5 min). Rules vary, so check your firm's rulebook.")
    embeds.append({"title": "🚦 Rule check: events vs. open calls", "description": ("\n".join(warn) or "No high-impact events on currencies in our open calls today.")[:4000],
                   "color": 0xF1C40F, "footer": {"text": f"Generated {stamp}. Verify before trading. Education only, not financial advice."}})

    # Discord caps all embeds in one message at 6000 chars: trim the longest sections until it fits
    def total(): return sum(len(e.get("title", "")) + len(e.get("description", "")) + len(e.get("footer", {}).get("text", "")) for e in embeds)
    while total() > 5800:
        e = max(embeds, key=lambda x: len(x["description"]))
        lines = e["description"].split("\n")
        e["description"] = "\n".join(lines[:-2] + lines[-1:]) if len(lines) > 3 else e["description"][:len(e["description"]) - 300]
    return f"☀️ **Holistic Morning Brief · {now.strftime('%A %b %d')}**", embeds

def main():
    hook = os.environ["DISCORD_WEBHOOK_URL"].strip().rstrip("/")
    content, embeds = build()
    req = urllib.request.Request(hook + "?wait=true", data=json.dumps({"content": content, "embeds": embeds, "username": "Holistic Market Pulse", "allowed_mentions": {"parse": []}}).encode(),
                                 headers={"Content-Type": "application/json", **UA})
    urllib.request.urlopen(req, timeout=20).read(); print("brief posted")

if __name__ == "__main__":
    main()
