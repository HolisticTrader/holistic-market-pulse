#!/usr/bin/env python3
"""Daylight-saving guard for GitHub's UTC-only cron.
Each scheduled job is listed at BOTH possible UTC hours (CDT and CST), one hour apart.
This lets through only the run that lands at the intended Central Time, allowing up to
45 minutes of GitHub lag. The other copy is 60 minutes off, so it is always skipped.
Usage: python gate.py HH:MM   -> prints go=true/false (append to $GITHUB_OUTPUT)"""
import sys, datetime
from zoneinfo import ZoneInfo
hh, mm = (int(x) for x in sys.argv[1].split(":"))
now = datetime.datetime.now(ZoneInfo("America/Chicago"))
want = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
late = (now - want).total_seconds() / 60
if late < -720: late += 1440   # target was "yesterday" relative to now (just past midnight)
ok = 0 <= late < 45
print(f"go={'true' if ok else 'false'}")
