"""
Real UPCOMING matches picked at runtime (28 Oct 2026) for page tests that need a match the site still shows as not started
(match bell, star, kickoff). Replaces hard-coded ids that broke once the fixture was played (1612257: played 13 Oct).
Upcoming = status NS, no score, kickoff (matches.date, UTC) at least `lead_h` hours away, and its AR + EN pages built locally.
Read-only on football.db. Nothing upcoming -> the test prints SKIP with the reason and exits 0 (see skip()).
"""
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def amman_day(date_utc):
    """'YYYY-MM-DD HH:MM' (UTC) -> the Amman (UTC+3) calendar day the site files it under"""
    t = time.strptime(date_utc[:16], "%Y-%m-%d %H:%M")
    return time.strftime("%Y-%m-%d", time.gmtime(time.mktime(t) - time.timezone + 3 * 3600))


def upcoming_matches(n=1, league=None, lead_h=2, same_day=False):
    """-> up to n rows (match_id, date, home_id, away_id), soonest first; [] when fewer than n qualify.
    same_day: all n on the same Amman day (the first day that has n)."""
    db = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
    try:
        rows = db.execute("""SELECT match_id, date, home_id, away_id FROM matches
                             WHERE status = 'NS' AND home_goals IS NULL AND date > datetime('now', ?)
                               AND (? IS NULL OR league_code = ?) ORDER BY date, match_id""",
                          (f"+{int(lead_h)} hours", league, league)).fetchall()
    finally:
        db.close()
    rows = [r for r in rows if (ROOT / "matches" / f"{r[0]}.html").exists() and (ROOT / "en" / "matches" / f"{r[0]}.html").exists()]
    if not same_day:
        return rows[:n] if len(rows) >= n else []
    days = {}
    for r in rows:
        d = days.setdefault(amman_day(r[1]), [])
        d.append(r)
        if len(d) == n:
            return d
    return []


def skip(test, why):
    print(f"SKIP {test}: {why}")
    raise SystemExit(0)
