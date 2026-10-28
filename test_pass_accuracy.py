#!/usr/bin/env python3
"""
Pass accuracy (28 Oct 2026): `player_stats.passes_pct` is the COUNT of accurate passes (lineup_view.py), not a percentage.
The player page used to show AVG(passes_pct) as "Pass %". Now: sum(accurate) / sum(total) * 100 over the matches where
both exist and total > 0; nothing usable -> "—". Offline: synthetic in-memory DB, no football.db, no network. Run:
    python C:\\Users\\User\\Projects\\Football\\test_pass_accuracy.py
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_players as MP  # noqa: E402
from lineup_view import ratio_pct, _stat_rows  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER)")
c.execute("CREATE TABLE player_stats (match_id INTEGER, team_id INTEGER, player_id INTEGER, player_en TEXT, player_ar TEXT, "
          "minutes INTEGER, rating REAL, captain INTEGER, substitute INTEGER, pos TEXT, shots_total INTEGER, shots_on INTEGER, "
          "goals INTEGER, conceded INTEGER, assists INTEGER, saves INTEGER, passes_total INTEGER, passes_key INTEGER, "
          "passes_pct INTEGER, tackles INTEGER, blocks INTEGER, interceptions INTEGER, duels_total INTEGER, duels_won INTEGER, "
          "dribbles_try INTEGER, dribbles_ok INTEGER, fouls_drawn INTEGER, fouls_made INTEGER, yellow INTEGER, red INTEGER, "
          "pen_scored INTEGER, pen_missed INTEGER, pen_saved INTEGER)")   # = the real table before player_stats_extra.migrate
c.executemany("INSERT INTO matches VALUES (?, 'EGY', 2026)", [(i,) for i in range(1, 10)])
c.execute("INSERT INTO matches VALUES (10, 'EGY', 2025)")
# (match, player, passes_total, passes_pct = accurate count)
rows = [
    (1, 10, 40, 30),      # counted
    (2, 10, 10, 9),       # counted
    (3, 10, 0, 0),        # total 0 -> excluded
    (4, 10, None, 5),     # no total -> excluded
    (5, 10, 20, None),    # no accurate count -> excluded (its 20 passes must not dilute the %)
    (6, 20, None, None),  # player 20: nothing usable at all
    (7, 30, 10, 0),       # player 30: 0 of 10 -> a real 0%
    (8, 40, 3, 2),        # player 40: 2/3 = 66.7 -> 67
    (9, 50, 20, 15),      # player 50, 2026: 15/20 = 75%
    (10, 50, None, None), # player 50, 2025: no pass data that season -> "—" in that row
]
c.executemany("INSERT INTO player_stats (match_id, player_id, minutes, passes_total, passes_pct, pos) VALUES (?, ?, 90, ?, ?, 'M')", rows)

s = MP.season_stats_rows(c)
p10 = s[10][0]
# hand-computed: (30 + 9) / (40 + 10) = 39 / 50 = 78 %  (the old AVG(passes_pct) over 30, 9, 0, 5 gave "11%")
check("player 10: accurate 30+9 over total 40+10 -> 78% (matches 3/4/5 excluded)",
      (p10["pacc"], p10["ptot"], p10["pct"]) == (39, 50, 78), p10)
check("player 20: no match with both values -> pct None", s[20][0]["pct"] is None, s[20][0])
check("player 30: 0 accurate of 10 -> 0% (a real zero, not hidden)", s[30][0]["pct"] == 0, s[30][0])
check("player 40: 2/3 -> 67% (rounded)", s[40][0]["pct"] == 67, s[40][0])

for lang in ("ar", "en"):
    t = MP.T[lang]
    h10, h20, h30, h50 = (MP.season_stats_table(s[p], lang, t) for p in (10, 20, 30, 50))
    check(f"{lang}: table shows 78% (not the old 11%)", "<td>78%</td>" in h10 and "11%" not in h10, h10[-400:])
    check(f"{lang}: no usable passes in any season -> no Pass % column at all (never 0%)",
          t["ps_pct"] not in h20 and "%</td>" not in h20, h20[-400:])
    check(f"{lang}: two seasons, one without pass data -> 75% in 2026 and '—' (not 0%) in 2025",
          t["ps_pct"] in h50 and "<td>75%</td>" in h50 and h50.count("<td>—</td>") >= 1 and "<td>0%</td>" not in h50, h50[-500:])
    check(f"{lang}: real 0% is shown as 0%", "<td>0%</td>" in h30, h30[-400:])

check("ratio_pct: 39/50 -> 78, 2/3 -> 67, 0/10 -> 0, total 0 / None and part None -> None",
      [ratio_pct(39, 50), ratio_pct(2, 3), ratio_pct(0, 10), ratio_pct(5, 0), ratio_pct(5, None), ratio_pct(None, 10)]
      == [78, 67, 0, None, None, None])
ov = _stat_rows({"pos": "M", "minutes": 90, "passes_total": 40, "passes_pct": 30}, "en")
check("match overlay uses the same rule: 30/40 (75%)", "30/40 (75%)" in ov, ov)

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
