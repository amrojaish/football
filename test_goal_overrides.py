#!/usr/bin/env python3
"""
goal_player_overrides.csv (8 Nov 2026): one goal (match_id, minute, team_id, player_name) -> player_id, read by player_pages.build_plan.
Run: python C:\\Users\\User\\Projects\\Football\\test_goal_overrides.py
Reads football.db and player_url_history.json read-only (build_plan gets a copy of the history).
"""
import hashlib
import sqlite3
import sys
from pathlib import Path

from _test_tmp import make_tmp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import player_pages as pp  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + repr(extra)[:600]))
    if not cond:
        fails += 1


md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()  # noqa: E731
DB_MD5, H_MD5 = md5(ROOT / "football.db"), md5(pp.HISTORY_FILE)
tmp = make_tmp("goal_overrides_")

ok = tmp / "ok.csv"
ok.write_text("match_id,minute,team_id,player_name,player_id\n10,80,20,A Name,30\n,,,,\n", encoding="utf-8")
check("loader: row -> key and id, blank row ignored", pp.load_goal_overrides(ok) == {(10, 80, 20, "A Name"): 30}, pp.load_goal_overrides(ok))
check("loader: missing file = {}", pp.load_goal_overrides(tmp / "nope.csv") == {})
check("first row of the real file is the Musona goal", pp.load_goal_overrides().get((1639340, 80, 25735, "Knowledge Musona")) == 3081, pp.load_goal_overrides())

con = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
hist = pp.load_history()
merges, pins = pp.load_id_merges(), pp.load_pins()
KEY = (1639340, 80, 25735, "Knowledge Musona")
real = pp.build_plan(con, dict(hist), merges, pins)
none = pp.build_plan(con, dict(hist), merges, pins, goal_overrides={})
wrong = pp.build_plan(con, dict(hist), merges, pins, goal_overrides={(1639340, 81, 25735, "Knowledge Musona"): 3081})
by = lambda plan: {x["slug"]: x for x in plan["pages"]}  # noqa: E731
R, N, W = by(real), by(none), by(wrong)
has = lambda pg: any((g["match_id"], g["minute"], g["team_id"], g["en"]) == KEY for g in pg["goals"])  # noqa: E731

check("without the override the goal has its own page (the case being fixed)", "knowledge-musona-3" in N and has(N["knowledge-musona-3"]), sorted(s for s in N if "musona" in s))
check("override: knowledge-musona-3 does not exist (page or redirect)", "knowledge-musona-3" not in R and "knowledge-musona-3" not in real["stubs"], sorted(s for s in R if "musona" in s))
check("override: goal is on page 3081", R["knowledge-musona"]["pid"] == 3081 and has(R["knowledge-musona"]))
check("override: 3081 keeps URL and Arabic name", R["knowledge-musona"]["slug"] == N["knowledge-musona"]["slug"] and R["knowledge-musona"]["display_ar"] == N["knowledge-musona"]["display_ar"] and R["knowledge-musona"]["display_ar"] == "نوليدج موسونا", R["knowledge-musona"]["display_ar"])
check("override: league goals of 3081 unchanged, exactly one goal added", len(R["knowledge-musona"]["goals"]) == len(N["knowledge-musona"]["goals"]) + 1)
ids = lambda pg: (pg["slug"], pg["kind"], pg["pid"], pg["display_en"], pg["display_ar"], sorted(g["gid"] for g in pg["goals"]))  # noqa: E731
check("override: every other page identical", all(ids(R[s]) == ids(N[s]) for s in N if s not in ("knowledge-musona", "knowledge-musona-3")) and set(R) == set(N) - {"knowledge-musona-3"})
check("override: redirects of published links identical", all(real["stubs"].get(k) == v for k, v in none["stubs"].items() if k in hist))
check("a row with the wrong minute changes nothing", set(W) == set(N) and "knowledge-musona-3" in W)
con.close()
check("football.db and player_url_history.json untouched", md5(ROOT / "football.db") == DB_MD5 and md5(pp.HISTORY_FILE) == H_MD5)
print(f"\nTOTAL FAILS: {fails}")
sys.exit(1 if fails else 0)
