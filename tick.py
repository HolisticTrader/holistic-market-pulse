#!/usr/bin/env python3
"""The post clock. GitHub's own cron runs this repo hours late, so timed posts used to get
skipped. tick.py runs often (hourly push from a cloud task + GitHub cron as a bonus) and fires
each timed job ONCE per day, as soon as it is due, as long as it isn't too stale.
Prints dispatch lines: "<workflow> <json inputs>" for every job due now.
State: state/tick.json {job_key: "YYYY-MM-DD" last day fired}."""
import json, os, sys, datetime
from zoneinfo import ZoneInfo

ALL = range(7)
WEEKDAYS = range(5)
# key, workflow file, inputs, target Central time, days (Mon=0), max minutes late before we skip today
JOBS = [
    ("brief",       "brief.yml",       {},                        "06:48", WEEKDAYS, 240),
    ("spark",       "spark.yml",       {},                        "07:33", ALL,      360),
    ("health",      "healthcheck.yml", {},                        "08:17", ALL,      720),
    ("halloffame",  "trivia.yml",      {"mode": "halloffame"},    "08:40", [4],      360),
    ("trivia",      "trivia.yml",      {"mode": "round"},         "12:00", ALL,      300),
    ("pulse",       "pulse.yml",       {"mode": "pulse"},         "15:15", WEEKDAYS, 180),
    ("leaderboard", "trivia.yml",      {"mode": "leaderboard"},   "21:30", ALL,      150),
]
EVERY_TICK = [("welcome.yml", {"mode": "new"})]
BOARD = ("pulse.yml", {"mode": "board"})          # live board refresh, Sun-Fri
STATE = "state/tick.json"


def main():
    now = datetime.datetime.now(ZoneInfo("America/Chicago"))
    today = now.date().isoformat()
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    out = []
    for key, wf, inputs, hm, days, max_late in JOBS:
        if now.weekday() not in days or st.get(key) == today:
            continue
        h, m = map(int, hm.split(":"))
        late = (now - now.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 60
        if 0 <= late <= max_late:
            out.append((wf, inputs, f"{key} ({hm} CT, {int(late)} min late)"))
            st[key] = today
        elif late > max_late and st.get(key) != today:
            print(f"# skip {key}: {int(late)} min past {hm}, too stale to post today", file=sys.stderr)
    for wf, inputs in EVERY_TICK:
        out.append((wf, inputs, wf))
    if now.weekday() != 5:   # no board refresh on Saturday (markets closed)
        out.append((BOARD[0], BOARD[1], "board refresh"))
    os.makedirs("state", exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)
    for wf, inputs, why in out:
        print(f"{wf}\t{json.dumps(inputs)}\t{why}")


if __name__ == "__main__":
    main()
