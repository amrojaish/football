#!/usr/bin/env python3
"""
مساعد لـtest_live_table.mjs: يطبع JSON بلقطة الجدول لكل دوري (موسمه الحالي) من نفس مدخلات get_table + الترتيب المتوقع منها.
قراءة فقط من football.db. لا يُشغَّل لحاله.
"""
import json
import sqlite3
import sys

from config import DB_FILE, LEAGUES
from make_site3 import get_table
from tiebreak import H2H_ENABLED, H2H_TWO_TEAM_ONLY, STANDINGS_EXCLUDED

conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
out = {}
for code, info in LEAGUES.items():
    season = conn.execute("SELECT MAX(season) FROM matches WHERE league_code = ?", (code,)).fetchone()[0]
    table = get_table(conn, code, season)
    rows = [{k: r[k] for k in ("team_id", "played", "wins", "draws", "losses", "scored", "diff", "points")} for r in table]
    ms = [m for m in conn.execute(
        "SELECT match_id, home_id, away_id, home_goals, away_goals FROM matches WHERE league_code = ? AND season = ?",
        (code, season)) if m["home_goals"] is not None and m["away_goals"] is not None and m["match_id"] not in STANDINGS_EXCLUDED]
    out[code] = {
        "snapshot": {
            "league": code, "season": season,
            "rules": {"enabled": code != "JOR", "leagueId": info["id"], "h2h": bool(H2H_ENABLED.get(code, False)),
                      "twoOnly": code in H2H_TWO_TEAM_ONLY},
            "counted_ids": [m["match_id"] for m in ms], "rows": rows,
            "matches": [[m["match_id"], m["home_id"], m["away_id"], m["home_goals"], m["away_goals"]] for m in ms],
            "alias": {},
        },
        "expected": [r["team_id"] for r in table],
    }
sys.stdout.write(json.dumps(out))
