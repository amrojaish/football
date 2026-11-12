#!/usr/bin/env python3
"""
AWD import (12 Nov 2026, TUN 2025: 3 awarded fixtures were never imported because fetch_matches2 asked FT/AET/PEN only).
fetch_matches2.main() now asks FT-AET-PEN-AWD; an AWD fixture is saved like fetch_overdue/import_cups
(save_finished(..., [], status="AWD")): score + ft + round + venue, 0 goal rows, and NO fixtures/events request.
fetch_events/stats/lineups/player_stats pending() skip AWD/WO rows (no request, no backoff row).
Temp DB with the real schema (empty), fake API, no network.
Run: python C:\\Users\\User\\Projects\\Football\\test_awd_import.py
"""
import copy
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\User\Projects\Football")
from _test_tmp import make_tmp  # noqa: E402
from config import DB_FILE  # noqa: E402
import fetch_matches2 as FM  # noqa: E402
import fetch_events as FE  # noqa: E402
import fetch_stats as FS  # noqa: E402
import fetch_lineups as FL  # noqa: E402
import fetch_player_stats as FP  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    fails += 0 if cond else 1


# provider response for TUN 1415801 (inspect_1111/tun2025_fixtures.json), trimmed
AWD = {"fixture": {"id": 1415801, "referee": None, "timezone": "UTC", "date": "2025-08-27T15:30:00+00:00",
                   "venue": {"id": None, "name": "Stade 15 Octobre", "city": "Bizerte"},
                   "status": {"long": "Technical loss", "short": "AWD", "elapsed": None}},
       "league": {"id": 202, "season": 2025, "round": "Regular Season - 4"},
       "teams": {"home": {"id": 981, "name": "CA Bizertin"}, "away": {"id": 988, "name": "Club Africain"}},
       "goals": {"home": 0, "away": 2},
       "score": {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": 0, "away": 2},
                 "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}}}
FT = copy.deepcopy(AWD)
FT["fixture"].update(id=1415999, status={"long": "Match Finished", "short": "FT", "elapsed": 90})
FT["goals"] = {"home": 1, "away": 0}
FT["score"]["fulltime"] = {"home": 1, "away": 0}
EV = [{"type": "Goal", "detail": "Normal Goal", "comments": None, "time": {"elapsed": 10, "extra": None},
       "team": {"id": 981}, "player": {"id": 1, "name": "A. Scorer"}}]

# empty DB with the real schema
TMP = make_tmp("awd_")
DB = TMP / "t.db"
src = sqlite3.connect(f"file:///{str(DB_FILE).replace(chr(92), '/')}?mode=ro", uri=True)
con = sqlite3.connect(DB)
for (sql,) in src.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"):
    con.execute(sql)
src.close()
con.execute("INSERT INTO teams (team_id, league_code, name_en) VALUES (981, 'TUN', 'CA Bizertin'), (988, 'TUN', 'Club Africain')")
con.commit()
con.close()

calls = []


def fake_get(endpoint, params, label=""):
    calls.append((endpoint, dict(params)))
    if endpoint == "fixtures":
        return True, [copy.deepcopy(AWD), copy.deepcopy(FT)], ""
    return True, EV, ""


FM.get, FM.DB_FILE, FM.DELAY, FM.check_key = fake_get, DB, 0, (lambda: True)
argv0 = sys.argv
sys.argv = ["fetch_matches2.py", "TUN", "--season", "2025", "--budget", "10"]
try:
    FM.main()
finally:
    sys.argv = argv0

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
check("1 list request asks FT-AET-PEN-AWD", calls[0] == ("fixtures", {"league": 202, "season": 2025, "status": "FT-AET-PEN-AWD"}), calls[:1])
ev_calls = [p.get("fixture") for e, p in calls if e == "fixtures/events"]
check("2 events requested for the FT fixture only (no follow-up fetch for AWD)", ev_calls == [1415999], ev_calls)
r = con.execute("SELECT * FROM matches WHERE match_id = 1415801").fetchone()
check("3 AWD row saved: status AWD, score 0-2, ft 0-2, round, venue",
      r is not None and (r["status"], r["home_goals"], r["away_goals"], r["ft_home"], r["ft_away"], r["round"], r["venue_name"])
      == ("AWD", 0, 2, 0, 2, "Regular Season - 4", "Stade 15 Octobre"), dict(r) if r else None)
check("4 AWD row: 0 goal rows", con.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1415801").fetchone()[0] == 0)
check("5 FT row still saved with its goal", con.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1415999").fetchone()[0] == 1)

# follow-up fetchers never pick an AWD/WO row (so no request and no fetch_backoff row)
con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status) "
            "VALUES (1415802, 'TUN', 2025, '2025-09-01 15:00', 981, 988, NULL, NULL, 'WO')")
con.commit()
for name, mod in (("events", FE), ("stats", FS), ("lineups", FL), ("player_stats", FP)):
    ids = {row["match_id"] for row in mod.pending(con, "TUN", 2025)}
    check(f"6 {name}.pending skips AWD/WO, keeps FT", 1415801 not in ids and 1415802 not in ids and 1415999 in ids, ids)
con.close()

print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
