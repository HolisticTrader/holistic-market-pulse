"""Save the latest Yahoo Finance quote for every pair in board/symbols.txt to board/prices.json.
Read by the Holistic live board (claude.ai artifact) through the board price sync task."""
import json, urllib.request, urllib.parse, datetime, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}

def quote(sym):
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1d&interval=1d"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
                m = json.load(r)["chart"]["result"][0]["meta"]
            return m["regularMarketPrice"], datetime.datetime.fromtimestamp(m["regularMarketTime"], datetime.timezone.utc).isoformat()
        except Exception:
            time.sleep(2)
    return None, None

rows = []
for line in open(os.path.join(HERE, "symbols.txt"), encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "|" not in line:
        continue
    pair, sym = [x.strip() for x in line.split("|", 1)]
    price, at = quote(sym)
    if price is not None:
        rows.append({"pair": pair, "symbol": sym, "price": price, "at": at})

out = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "source": "Yahoo Finance (may be delayed)", "prices": rows}
with open(os.path.join(HERE, "prices.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
print(f"{len(rows)} quotes saved")
