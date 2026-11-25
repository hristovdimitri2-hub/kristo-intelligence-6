# -*- coding: utf-8 -*-
"""Print the last N days of commits grouped by day, for docs/ROLLING_10_DAYS.md.

WHY A GENERATOR FOR A DOCUMENT THAT IS PROSE. The prose is curated and must stay
curated — a script cannot decide that "the audit" was the important thing on a
given day. What it can do is make the window checkable and cheap to move: any
claim in the rolling file can be verified against the commit list, and when a day
is added the same window can be re-printed instead of remembered.

    python scripts/rolling_10_days.py                 # last 10 days
    python scripts/rolling_10_days.py --days 14
    python scripts/rolling_10_days.py --warn          # non-zero if the doc is stale
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(REPO, "docs", "ROLLING_10_DAYS.md")


def git(*args):
    out = subprocess.run(["git", "-C", REPO] + list(args),
                         capture_output=True, text=True, check=True)
    return out.stdout


def commits_by_day(days):
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    raw = git("log", "--since=%s" % since, "--date=short",
              "--pretty=format:%ad|%s")
    grouped = {}
    for line in raw.splitlines():
        if "|" not in line:
            continue
        day, subject = line.split("|", 1)
        grouped.setdefault(day, []).append(subject)
    return grouped


def documented_window(path):
    """The 'Window: A – B' line, so the script can say whether it is current."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r"\*\*Window:\s*([0-9.]+)\s*[–-]\s*([0-9.]+)\*\*", text)
    return match.groups() if match else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--warn", action="store_true",
                    help="exit 1 if the document's window is not current")
    args = ap.parse_args()

    grouped = commits_by_day(args.days)
    total = sum(len(v) for v in grouped.values())
    today = dt.date.today()

    if args.warn:
        window = documented_window(DOC)
        if not window:
            print("x %s has no parsable '**Window: A - B**' line" % DOC)
            return 1
        end = dt.datetime.strptime(window[1], "%d.%m.%Y").date()
        age = (today - end).days
        if age > 1:
            print("x the rolling window ends %s, %d day(s) ago - move it"
                  % (window[1], age))
            return 1
        print("OK the rolling window ends %s" % window[1])
        return 0

    print("last %d days: %d commits across %d days\n"
          % (args.days, total, len(grouped)))
    for day in sorted(grouped, reverse=True):
        print("%s  (%d)" % (day, len(grouped[day])))
        for subject in grouped[day]:
            print("    %s" % subject[:100])
    print("\nwindow in %s: %s" % (os.path.relpath(DOC, REPO),
                                  documented_window(DOC)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
