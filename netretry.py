"""Makes every script's network calls survive temporary hiccups.

Import it once at the top of a script (`import netretry`). It wraps urllib's urlopen so that:
  - rate limits (429) and server errors (500/502/503/504) are retried with backoff,
    honoring Discord's/X's Retry-After header
  - dropped connections and timeouts on reads (GET) are retried
  - Discord bot calls always send the User-Agent Discord requires
Real problems (bad token 401, forbidden 403, not found 404, bad request 400) are NOT retried,
so they still surface immediately.
"""
import time, random, socket, urllib.request, urllib.error

_orig = urllib.request.urlopen
TRIES = 4
DISCORD_UA = "DiscordBot (https://github.com/HolisticTrader/holistic-market-pulse, 1.1)"
RETRY_CODES = {429, 500, 502, 503, 504}


def _wait(attempt, retry_after=None):
    try:
        s = float(retry_after) if retry_after else 0
    except ValueError:
        s = 0
    time.sleep(min(max(s, 2 ** attempt + random.random()), 30))


def urlopen(url, *a, **kw):
    req = url if isinstance(url, urllib.request.Request) else None
    if req is not None:
        auth = req.get_header("Authorization") or ""
        if "discord.com" in req.full_url and auth.startswith("Bot "):
            req.add_header("User-agent", DISCORD_UA)
    method = req.get_method() if req is not None else "GET"
    for attempt in range(TRIES):
        last = attempt == TRIES - 1
        try:
            return _orig(url, *a, **kw)
        except urllib.error.HTTPError as e:
            # POSTs are only retried when the server clearly did not process them
            ok = e.code == 429 or (e.code in RETRY_CODES and (method == "GET" or e.code in (502, 503, 504)))
            if last or not ok:
                raise
            print(f"[netretry] HTTP {e.code} on {method}, retrying ({attempt + 1}/{TRIES - 1})")
            _wait(attempt, e.headers.get("Retry-After") if e.headers else None)
        except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
            refused = isinstance(getattr(e, "reason", e), (ConnectionRefusedError, socket.gaierror))
            if last or (method != "GET" and not refused):
                raise
            print(f"[netretry] network error on {method} ({type(e).__name__}), retrying ({attempt + 1}/{TRIES - 1})")
            _wait(attempt)


urllib.request.urlopen = urlopen
