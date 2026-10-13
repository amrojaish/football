"""Unit test of `fetch_lineups.py --refetch recent` candidate selection + attempt cap + duplicate-id handling + merge-apply (13 Oct 2026).
No network, no real DB: an in-memory SQLite with the minimal schema. Run: python C:\\Users\\User\\Projects\\Football\\test_lineups_recent.py"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_lineups as F  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.executescript("""
CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                      home_goals INTEGER, away_goals INTEGER, status TEXT);
CREATE TABLE lineups (match_id INTEGER, team_id INTEGER, formation TEXT, coach_en TEXT, coach_ar TEXT, PRIMARY KEY (match_id, team_id));
CREATE TABLE lineup_players (match_id INTEGER, team_id INTEGER, player_id INTEGER, player_en TEXT, player_ar TEXT, number INTEGER, pos TEXT,
                             grid TEXT, starter INTEGER, PRIMARY KEY (match_id, player_id));
""")
now = datetime.now(timezone.utc)
fmt = lambda h: (now - timedelta(hours=h)).strftime("%Y-%m-%d %H:%M")


def match(mid, hours_ago, status="FT", starters=10):
    c.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?)", (mid, "EGY", 2026, fmt(hours_ago), 1, 2, 1, 0, status))
    for team in (1, 2):
        c.execute("INSERT INTO lineups VALUES (?,?,?,?,?)", (mid, team, "4-4-2", "", ""))
        n = starters if team == 1 else 11
        for i in range(n):
            c.execute("INSERT INTO lineup_players VALUES (?,?,?,?,?,?,?,?,?)", (mid, team, mid * 100 + team * 20 + i, f"P{i}", "", i + 1, "M", "", 1))


match(1, 5)                      # recent, short -> candidate
match(2, 30)                     # older than 26 h -> not a candidate
match(3, 5, status="2H")         # not finished -> never
match(4, 5, starters=11)         # complete -> not short
match(5, 20)                     # recent, short -> candidate (older than #1)
check("recent candidates: finished + short + within 26 h, newest match_id first", F.recent_short_fixtures(c) == [5, 1], F.recent_short_fixtures(c))
check("auto candidates: finished + short, any age (never an unfinished match)", sorted(F.short_fixtures(c)) == [1, 2, 5], F.short_fixtures(c))
for i in range(F.RECENT_MAX_TRIES - 1):
    F.note_refetch_try(c, 1)
check(f"{F.RECENT_MAX_TRIES - 1} tries recorded -> still a candidate", 1 in F.recent_short_fixtures(c))
F.note_refetch_try(c, 1)
check(f"{F.RECENT_MAX_TRIES} tries -> dropped from the list (a real provider gap is not retried forever); other match unaffected",
      F.recent_short_fixtures(c) == [5], F.recent_short_fixtures(c))
row = c.execute("SELECT tries FROM lineup_refetch WHERE match_id = 1").fetchone()
check("attempt counter stored in lineup_refetch", row and row[0] == F.RECENT_MAX_TRIES, row and tuple(row))

# duplicate provider id inside one match: the real id stays with the known name, the other gets a synthetic negative id; nobody is lost
c.execute("INSERT INTO lineup_players VALUES (900,1,42302,'Amro Abdelfatah Ali Surag','',11,'M','',0)")   # known name for 42302 elsewhere
data = [{"team": {"id": 1}, "formation": "4-4-2", "coach": {"name": "C"},
         "startXI": [{"player": {"id": 42302, "name": "A. B. Khalifa", "number": 1, "pos": "G", "grid": "1:1"}},
                     {"player": {"id": 42302, "name": "A. Surag", "number": 11, "pos": "M", "grid": "2:2"}}],
         "substitutes": [{"player": {"id": None, "name": "No Id", "number": 7, "pos": "F"}}]}]
F.DUP_LOG.clear()
lines, players, n_null = F.build_rows(901, 1, 2, data, c)
by = {p[3]: p for p in players}
check("duplicate id: A. Surag (matches the id's known name) keeps 42302, A. B. Khalifa gets a negative id; no row lost",
      by["A. Surag"][2] == 42302 and by["A. B. Khalifa"][2] < 0 and len(players) == 3 and len({p[2] for p in players}) == 3, players)
check("  the duplicate is logged; the null-id player is counted (n_null = 1) and also negative", len(F.DUP_LOG) == 1 and n_null == 1 and by["No Id"][2] < 0, (F.DUP_LOG, n_null))

# merge-apply reconcile: matched stale row -> Arabic name carried over, stale deleted; unmatched with Arabic not in CSV -> kept; unmatched without Arabic -> deleted
c.execute("INSERT INTO lineup_players VALUES (950,1,111,'M. Ismail','محمد إسماعيل',9,'F','',1)")        # stale: same team+number+last name as the new row
c.execute("INSERT INTO lineup_players VALUES (950,1,112,'Gone Player','',30,'M','',0)")               # stale, no Arabic, no match -> deleted
c.execute("INSERT INTO lineup_players VALUES (950,1,113,'Zzz Unknownarabic','اسم غير موجود',31,'M','',0)")   # stale with an Arabic name not in players_ar.csv -> kept
new_players = [(950, 1, 999, "Mohamed Ismail", "", 9, "F", "", 1)]
c.execute("INSERT INTO lineup_players VALUES (950,1,999,'Mohamed Ismail','',9,'F','',1)")   # as if the upsert already ran
stored = [tuple(r) for r in c.execute("SELECT player_id, team_id, player_en, player_ar, number, starter FROM lineup_players WHERE match_id = 950 AND player_id != 999")]
m_, u_, d_ = F.reconcile_stale(c, 950, stored, new_players)
left = {r[0]: r[1] for r in c.execute("SELECT player_id, player_ar FROM lineup_players WHERE match_id = 950")}
check("reconcile: stale M. Ismail matched (same team + #9 + last name) -> deleted and its Arabic name moved to the new row", 111 not in left and left.get(999) == "محمد إسماعيل", left)
check("  unmatched stale without an Arabic name is deleted; unmatched stale whose Arabic name is NOT in players_ar.csv is kept",
      112 not in left and 113 in left and (m_, u_, d_) == (1, 1, 1), ((m_, u_, d_), left))

print("FAILS:", fails)
raise SystemExit(1 if fails else 0)
