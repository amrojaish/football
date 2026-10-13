"""Unit test of fetch_backoff (13 Oct 2026): schedule after FT (first try, +1h, +6h, +24h, +72h, stop), empty-only recording, legacy-exhausted matches, MAR player-stats skip.
In-memory SQLite, no network. Run from the repo root: python test_stats_backoff.py"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_backoff as BO  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
BO.ensure_table(c)
NOW = 1_800_000_000.0
H = 3600


def row(mid, league, hours_since_kickoff):
    ts = NOW - hours_since_kickoff * H
    d = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
    return {"match_id": mid, "league_code": league, "date": d}


class R(dict):
    def __getitem__(self, k):
        return dict.__getitem__(self, k)


def due(kind, rows, now=NOW):
    d, s = BO.filter_due(c, kind, [R(r) for r in rows], now)
    return [r["match_id"] for r in d], s


# 1) a match that just got its result is due at once (no wait for the FT estimate)
check("fresh result (1 h after kickoff): first attempt is due immediately", due("stats", [row(1, "EGY", 1)])[0] == [1])
# 2) after an EMPTY answer the next attempt waits: +1h after FT (FT = kickoff + 2h)
BO.record_empty(c, "stats", 1, NOW - 2 * H)   # the empty try happened 2 h ago
check("after 1 empty try at kickoff+1h: not due again until FT+1h (kickoff+3h)", due("stats", [row(1, "EGY", 1)], NOW)[0] == [] and due("stats", [row(1, "EGY", 2.9)], NOW)[0] == [])
check("  at kickoff+3h the 2nd attempt is due", due("stats", [row(1, "EGY", 3.01)], NOW)[0] == [1])
# 3) full schedule on a single match
sched = []
BO.ensure_table(c); c.execute("DELETE FROM stats_attempts")
t_kick = NOW - 80 * H            # kicked off 80 h ago: all steps would be reachable
for step, ft_plus in enumerate(BO.SCHEDULE_HOURS):
    # simulate: tries = step; the attempt becomes due at FT + SCHEDULE_HOURS[step]
    c.execute("DELETE FROM stats_attempts")
    if step:
        c.execute("INSERT INTO stats_attempts VALUES (1, 'stats', ?, 0)", (step,))
    ft = t_kick + 2 * H
    just_before = ft + ft_plus * H - 60
    just_after = ft + ft_plus * H + 60
    before = BO.filter_due(c, "stats", [R({"match_id": 1, "league_code": "EGY", "date": time.strftime("%Y-%m-%d %H:%M", time.gmtime(t_kick))})], just_before)[0]
    after = BO.filter_due(c, "stats", [R({"match_id": 1, "league_code": "EGY", "date": time.strftime("%Y-%m-%d %H:%M", time.gmtime(t_kick))})], just_after)[0]
    if step == 0:
        # no record yet and older than the whole schedule -> exhausted (legacy), so check the schedule on a recent kickoff instead
        pass
    else:
        sched.append((step, bool(before), bool(after)))
check("tries 1..4: not due 1 minute before FT+{1,6,24,72}h, due 1 minute after", sched == [(1, False, True), (2, False, True), (3, False, True), (4, False, True)], sched)
c.execute("DELETE FROM stats_attempts"); c.execute("INSERT INTO stats_attempts VALUES (7, 'stats', 5, 0)")
check("5 empty tries = stopped for good (never due, however old)", due("stats", [row(7, "EGY", 500)])[0] == [] and due("stats", [row(7, "EGY", 5000)])[1]["exhausted"] == 1)
# 3b) minimum gap: a match that is already past all its slots still gets only one attempt per hour (spread, not back-to-back runs)
c.execute("DELETE FROM stats_attempts")
BO.record_empty(c, "stats", 30, NOW)
check("late match (kicked off 60 h ago, 1 empty try just now): the next attempt waits MIN_GAP_H, then becomes due", due("stats", [row(30, "MAR", 60)], NOW + 600)[0] == [] and due("stats", [row(30, "MAR", 60)], NOW + 3700)[0] == [30])
# 4) failures are not recorded: no row -> still due on the next run
c.execute("DELETE FROM stats_attempts")
check("a FAILED request records nothing -> due again next run", due("stats", [row(3, "SAU", 5)])[0] == [3])
# 5) legacy: finished > 72 h ago with no record at all = exhausted (was retried hundreds of times before this table existed)
check("old match (200 h) with no record: skipped as exhausted; recent (50 h) still due", due("stats", [row(4, "UAE", 200), row(5, "UAE", 50)])[0] == [5])
# 6) kinds are independent
c.execute("INSERT INTO stats_attempts VALUES (9, 'stats', 5, 0)")
check("stats exhausted does not exhaust player-stats for the same match", due("pstats", [row(9, "EGY", 50)])[0] == [9] and due("stats", [row(9, "EGY", 50)])[0] == [])
# 7) MAR player-stats skipped entirely; MAR stats still tried
check("MAR player-stats: never requested (provider has none for any season); MAR stats still follow the schedule",
      due("pstats", [row(11, "MAR", 5)])[0] == [] and due("pstats", [row(11, "MAR", 5)])[1]["league_skip"] == 1 and due("stats", [row(11, "MAR", 5)])[0] == [11])
# 8) unreadable date: never blocked
check("unparseable date -> due (we never hide a match we cannot date)", BO.filter_due(c, "stats", [R({"match_id": 12, "league_code": "EGY", "date": "?"})], NOW)[0] != [])
# 9) record_empty counts up
c.execute("DELETE FROM stats_attempts")
for _ in range(3):
    BO.record_empty(c, "pstats", 20, NOW)
check("record_empty increments tries per (match, kind)", c.execute("SELECT tries FROM stats_attempts WHERE match_id=20 AND kind='pstats'").fetchone()[0] == 3)
print("FAILS:", fails)
raise SystemExit(1 if fails else 0)
