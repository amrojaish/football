"""Unit test of refresh_goal_names.py + fix_goals ghost cleanup (17 Oct 2026). In-memory SQLite, no network.
Run from the repo root: python test_goal_refresh.py"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_backoff as BO  # noqa: E402
import fix_goals as FG  # noqa: E402
import refresh_goal_names as RG  # noqa: E402

RG.DELAY = 0
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


H = 3600
NOW = 1_800_000_000.0


def kick(hours_ago):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(NOW - hours_ago * H))


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                              home_goals INTEGER, away_goals INTEGER, status TEXT);
        CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, player_en TEXT, player_ar TEXT, detail TEXT);
        CREATE TABLE teams (team_id INTEGER PRIMARY KEY, short_name_ar TEXT);
        INSERT INTO teams VALUES (1, 'h'), (2, 'a');
    """)
    BO.ensure_table(c)
    return c


def match(c, mid, hours_ago, hg, ag, season=2026):
    c.execute("INSERT INTO matches VALUES (?, 'IRQ', ?, ?, 1, 2, ?, ?, 'FT')", (mid, season, kick(hours_ago), hg, ag))


def goal(c, mid, team, minute, name, detail="Normal Goal"):
    c.execute("INSERT INTO goals (match_id, team_id, minute, player_en, player_ar, detail) VALUES (?,?,?,?,'',?)", (mid, team, minute, name, detail))


def ev(team, minute, name, detail="Normal Goal"):
    return {"type": "Goal", "detail": detail, "team": {"id": team}, "time": {"elapsed": minute}, "player": {"id": 9, "name": name}}


def names(c, mid):
    return [(r["team_id"], r["minute"], r["player_en"], r["detail"]) for r in c.execute("SELECT * FROM goals WHERE match_id=? ORDER BY id", (mid,))]


def go(c, events_by_mid, now=NOW, budget=10, hit=None):
    def fetch(mid):
        if hit is not None:
            hit.append(mid)
        return True, events_by_mid.get(mid, []), ""
    return RG.run(c, 2026, budget, False, fetch=fetch, now=now)


# 1) counts match -> names, minutes and detail are filled
c = db(); match(c, 1, 5, 2, 1)
goal(c, 1, 1, 30, ""); goal(c, 1, 1, 61, ""); goal(c, 1, 2, 80, "")
rep = go(c, {1: [ev(1, 31, "A. One"), ev(1, 60, "B. Two", "Penalty"), ev(2, 80, "C. Three")]})
check("counts equal per team: blank rows get provider names, minutes and detail",
      names(c, 1) == [(1, 31, "A. One", "Normal Goal"), (1, 60, "B. Two", "Penalty"), (2, 80, "C. Three", "Normal Goal")], names(c, 1))
check("  report: 1 match updated, 3 goals filled", rep["updated_matches"] == 1 and rep["filled"] == 3, rep)

# 1b) provider "Missed Penalty" events are dropped before counting (same filter as fetch_matches2.py:222)
c = db(); match(c, 9, 5, 1, 0)
goal(c, 9, 1, 40, "")
rep = go(c, {9: [ev(1, 40, "Scorer Nine"), ev(1, 70, "Misser", "Missed Penalty")]})
check("Missed Penalty is not counted: counts still equal, blank row filled", names(c, 9) == [(1, 40, "Scorer Nine", "Normal Goal")], names(c, 9))

# 2) counts differ for one team -> nothing changes, reason logged
c = db(); match(c, 2, 5, 2, 1)
goal(c, 2, 1, 30, ""); goal(c, 2, 1, 61, ""); goal(c, 2, 2, 80, "")
before = names(c, 2)
rep = go(c, {2: [ev(1, 30, "A. One"), ev(2, 80, "C. Three"), ev(2, 85, "D. Four")]})
check("per-team count differs (even if the total equals): nothing changes", names(c, 2) == before, names(c, 2))
check("  and the reason is logged", bool(rep["skipped"]) and "count_differs" in rep["skipped"][0][1], rep["skipped"])

# 3) named goals are never touched or removed
c = db(); match(c, 3, 5, 2, 0)
goal(c, 3, 1, 10, "Named Player"); goal(c, 3, 1, 50, "")
rep = go(c, {3: [ev(1, 10, "named player"), ev(1, 51, "New Name")]})
check("named goal untouched (minute and spelling kept), blank one filled",
      names(c, 3) == [(1, 10, "Named Player", "Normal Goal"), (1, 51, "New Name", "Normal Goal")], names(c, 3))
c = db(); match(c, 4, 5, 2, 0)
goal(c, 4, 1, 10, "Named Player"); goal(c, 4, 1, 50, "")
before = names(c, 4)
rep = go(c, {4: [ev(1, 20, "Somebody Else"), ev(1, 70, "New Name")]})
check("named goal missing from the provider: nothing changes (never removed)", names(c, 4) == before and bool(rep["skipped"]), names(c, 4))
c = db(); match(c, 5, 5, 1, 0)
goal(c, 5, 1, 10, "")
rep = go(c, {5: [ev(1, 10, "")]})
check("provider name still blank: row unchanged, reason provider_names_blank",
      names(c, 5) == [(1, 10, "", "Normal Goal")] and rep["skipped"][0][1] == "provider_names_blank")
check("only the current season and only FT matches with a blank goal are targets",
      RG.blank_matches(c, 2025) == [] and len(RG.blank_matches(c, 2026)) == 1)

# 4) backoff: first try at once, then FT+1h, +6h, +24h, +72h, then never again
c = db(); match(c, 6, 1, 1, 0)           # kicked off 1 h before NOW (FT = kickoff + 2h)
goal(c, 6, 1, 10, "")
hit = []
for hours_after_kickoff, expect in ((1, 1), (1.5, 0), (3.05, 1), (8.1, 1), (26.2, 1), (74.3, 1), (200, 0), (900, 0)):
    n0 = len(hit)
    go(c, {6: [ev(1, 10, "")]}, now=NOW + (hours_after_kickoff - 1) * H, hit=hit)
    check(f"  schedule: {hours_after_kickoff} h after kickoff -> {'call' if expect else 'no call'}", len(hit) - n0 == expect)
check("5 calls in total, then it stops forever", len(hit) == 5, hit)
check("  attempts recorded as kind 'goals' (5)", c.execute("SELECT tries FROM stats_attempts WHERE match_id=6 AND kind='goals'").fetchone()[0] == 5)

# 5) one-time list: an old blank match is tried once, then never
c = db(); match(c, 7, 500, 1, 0)
goal(c, 7, 1, 10, "")
hit = []
go(c, {7: [ev(1, 10, "")]}, hit=hit)
go(c, {7: [ev(1, 10, "")]}, hit=hit, now=NOW + 5 * H)
go(c, {7: [ev(1, 10, "")]}, hit=hit, now=NOW + 400 * H)
check("old (>72 h) blank match with no record: exactly one call ever", hit == [7], hit)
check("  recorded as 'goals_once'", c.execute("SELECT COUNT(*) FROM stats_attempts WHERE match_id=7 AND kind='goals_once'").fetchone()[0] == 1)
c = db(); match(c, 8, 500, 1, 0); goal(c, 8, 1, 10, "")
BO.record_empty(c, "goals", 8, NOW - 400 * H)
hit = []
go(c, {8: []}, hit=hit)
check("old match that already has a schedule record is NOT in the one-time list",
      c.execute("SELECT COUNT(*) FROM stats_attempts WHERE match_id=8 AND kind='goals_once'").fetchone()[0] == 0)

# 6) hard cap per run; failures are not recorded
c = db()
for m in range(20, 35):
    match(c, m, 500, 1, 0); goal(c, m, 1, 10, "")
hit = []
go(c, {}, hit=hit, budget=4)
check("budget caps the calls per run (4 of 15 one-time matches)", len(hit) == 4, hit)
c2 = db(); match(c2, 40, 3, 1, 0); goal(c2, 40, 1, 10, "")
r2 = RG.run(c2, 2026, 5, False, fetch=lambda m: (False, [], "HTTP 500"), now=NOW)
check("a failed fetch is not recorded (retried next run)",
      r2["calls"] == 1 and c2.execute("SELECT COUNT(*) FROM stats_attempts").fetchone()[0] == 0)

# 7) ghost cleanup: blank name in a 0-0 final only
c = db(); c.execute(FG.SCHEMA)
match(c, 50, 99, 0, 0); goal(c, 50, 1, 10, ""); goal(c, 50, 2, 20, "Disallowed Named")
match(c, 51, 99, 1, 0); goal(c, 51, 1, 10, "")
match(c, 52, 99, 2, 0); goal(c, 52, 1, 10, "Scorer"); goal(c, 52, 1, 80, "Scorer2")
ghost, named = FG.find_zero_goals(c)
check("ghost = only the blank goal in the 0-0 match; the named goal in a 0-0 is only listed",
      [g["match_id"] for g in ghost] == [50] and [g["match_id"] for g in named] == [50])
FG.archive_goals(c, ghost, "zero_zero_match"); c.commit()
check("  ghost archived to cancelled_goals and removed from goals",
      c.execute("SELECT COUNT(*) FROM goals WHERE match_id=50").fetchone()[0] == 1
      and c.execute("SELECT COUNT(*) FROM cancelled_goals WHERE match_id=50 AND reason='zero_zero_match'").fetchone()[0] == 1)
check("  blank goal in a non-0-0 match and named goals elsewhere are untouched",
      c.execute("SELECT COUNT(*) FROM goals WHERE match_id IN (51, 52)").fetchone()[0] == 3)

print("\n" + ("ALL PASS" if not fails else f"{fails} FAILED"))
sys.exit(1 if fails else 0)
