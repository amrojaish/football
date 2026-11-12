#!/usr/bin/env python3
"""
Manual-row guard (12 Nov 2026): fetch_matches2 skips a provider fixture (AWD or any) when manual_matches.csv has a row
for the same league, season and team pair (either order) within +-3 days or the same round — else it is counted twice.
Temp DB (real schema, empty) + temp manual_matches.csv next to it, fake API, no network.
Run: python C:\\Users\\User\\Projects\\Football\\test_manual_guard.py
"""
import copy
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\User\Projects\Football")
from _test_tmp import make_tmp  # noqa: E402
from config import DB_FILE  # noqa: E402
import fetch_matches2 as FM  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    fails += 0 if cond else 1


def fx(mid, h, a, date, status="AWD", rnd="Regular Season - 8", g=(3, 0)):
    return {"fixture": {"id": mid, "referee": None, "date": date + "T15:00:00+00:00", "venue": {"id": None, "name": None, "city": None},
                        "status": {"short": status}},
            "league": {"id": 542, "season": 2025, "round": rnd},
            "teams": {"home": {"id": h, "name": f"T{h}"}, "away": {"id": a, "name": f"T{a}"}},
            "goals": {"home": g[0], "away": g[1]},
            "score": {"halftime": {"home": None, "away": None}, "fulltime": {"home": g[0], "away": g[1]},
                      "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}}}


TMP = make_tmp("mguard_")
DB = TMP / "football.db"
src = sqlite3.connect(f"file:///{str(DB_FILE).replace(chr(92), '/')}?mode=ro", uri=True)
con = sqlite3.connect(DB)
for (sql,) in src.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"):
    con.execute(sql)
src.close()
# manual rows, as they sit in matches (ids from manual_matches.csv)
con.executemany("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round) "
                "VALUES (?, 'IRQ', 2025, ?, ?, ?, ?, ?, 'FT', ?)",
                [(9000005, "2025-12-23", 11064, 15546, 3, 0, None),               # date match
                 (9000008, "2026-01-30", 11069, 15547, 3, 0, "Regular Season - 20")])  # round match
con.commit()
con.close()
(TMP / "manual_matches.csv").write_text(
    "match_id,league_code,season,date,home_name,away_name,home_goals,away_goals,note,source\n"
    "9000005,IRQ,2025,2025-12-23,a,b,3,0,x,y\n"
    "9000008,IRQ,2025,2026-01-30,c,d,3,0,x,y\n"
    "9000099,IRQ,2025,2026-01-01,e,f,3,0,not in DB,y\n", encoding="utf-8")

FIX = [fx(1493255, 11064, 15546, "2025-12-25"),                                   # same pair, +2 days -> skip
       fx(1600001, 15547, 11069, "2026-02-20", rnd="Regular Season - 20"),          # reversed pair, same round -> skip
       fx(1546308, 15546, 11064, "2026-01-05", rnd="Regular Season - 38"),          # AWD, reversed, 13 days, other round -> skip
       fx(1600002, 15546, 11064, "2026-04-01", status="FT", rnd="Regular Season - 27", g=(2, 2)),  # non-AWD, far date -> import
       fx(1600003, 11064, 11066, "2025-12-23", status="FT", g=(1, 0))]              # other pair, same date -> import
calls = []


def fake_get(endpoint, params, label=""):
    calls.append((endpoint, dict(params)))
    return (True, copy.deepcopy(FIX), "") if endpoint == "fixtures" else (True, [], "")


FM.get, FM.DB_FILE, FM.DELAY, FM.check_key = fake_get, DB, 0, (lambda: True)
argv0 = sys.argv
sys.argv = ["fetch_matches2.py", "IRQ", "--season", "2025", "--budget", "20"]
try:
    FM.main()
finally:
    sys.argv = argv0

con = sqlite3.connect(DB)
got = {r[0] for r in con.execute("SELECT match_id FROM matches WHERE match_id < 9000000")}
check("1 AWD with a manual row for the same pair within 3 days is skipped", 1493255 not in got, got)
check("2 reversed pair + same round as a manual row is skipped", 1600001 not in got, got)
check("3 non-AWD: same pair, far date, different round is imported", 1600002 in got, got)
check("3b AWD: same pair reversed, 13 days apart, different round is skipped", 1546308 not in got, got)
check("4 other pair on the same date is imported (FT, events fetched)", 1600003 in got
      and [p.get("fixture") for e, p in calls if e == "fixtures/events"] == [1600002, 1600003], calls)
check("5 manual rows untouched", con.execute("SELECT COUNT(*) FROM matches WHERE match_id >= 9000000").fetchone()[0] == 2)
con.close()
check("6 other league/season: manual rows not used", FM.manual_rows(sqlite3.connect(DB), "TUN", 2025) == [])

print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
