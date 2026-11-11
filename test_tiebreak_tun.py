#!/usr/bin/env python3
"""
TUN tiebreak (11 Nov 2026, FTF rules via lapresse.tn 2026-05-04): H2H points, H2H goal difference, overall goal difference,
goals scored. 3+ teams tied = mini-league between ALL of them. No "H2H goals scored" step (tiebreak.H2H_SKIP_H2H_GOALS).
In-memory DB, no api_standings table (so provider_order() returns None and the tiebreak itself is tested).

Note: with exactly 2 teams, equal H2H points + equal H2H goal difference always means equal H2H goals (each side's goals
against are the other's goals for), so "different H2H goals" can only happen in a 3+ team mini-league; tests 1-2 use 3 teams.
Run: python C:\\Users\\User\\Projects\\Football\\test_tiebreak_tun.py
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\Users\User\Projects\Football")
import tiebreak as TB  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    fails += 0 if cond else 1


def db(matches, code):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE matches (match_id INTEGER, league_code TEXT, season INTEGER, home_id INTEGER, away_id INTEGER,"
              " home_goals INTEGER, away_goals INTEGER)")
    for i, (h, a, hg, ag) in enumerate(matches, 1):
        c.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?)", (90000000 + i, code, 2099, h, a, hg, ag))
    return c


def order(code, matches, rows):
    rows = [dict(team_id=t, points=p, diff=d, scored=s, played=10) for t, p, d, s in rows]
    return [r["team_id"] for r in TB.sort_table(db(matches, code), code, 2099, rows)]


A, B, C, D = 1, 2, 3, 4

# 1) A and B level on mini-league points (4) and goal difference (+1), A scored more in the mini-league (4 vs 2).
#    TUN: overall goal difference decides (B +5 over A 0). The SAU path keeps "H2H goals" and puts A first.
#    C has the best overall goal difference but 0 mini-league points: the mini-league is between ALL three tied teams.
mini = [(A, C, 3, 2), (B, C, 1, 0), (A, B, 1, 1)]
rows = [(A, 10, 0, 10), (B, 10, 5, 8), (C, 10, 9, 20), (D, 12, 1, 5)]
check("TUN: level on H2H pts + H2H GD, different H2H goals -> overall GD decides (B before A)", order("TUN", mini, rows) == [D, B, A, C],
      order("TUN", mini, rows))
check("SAU unchanged: same data keeps H2H goals as step 3 (A before B)", order("SAU", mini, rows) == [D, A, B, C], order("SAU", mini, rows))
check("TUN 3-team mini-league: C last on H2H points despite the best overall GD", order("TUN", mini, rows)[-1] == C)

# 2) 3-team mini-league all level (every game 1-1): overall goal difference, then goals scored
draws = [(A, B, 1, 1), (B, C, 1, 1), (C, A, 1, 1)]
rows2 = [(A, 7, 2, 9), (B, 7, 2, 11), (C, 7, 4, 6)]
check("TUN 3-team mini-league all level -> overall GD then goals scored (C, B, A)", order("TUN", draws, rows2) == [C, B, A], order("TUN", draws, rows2))

# 3) 2 teams: H2H points beat overall goal difference (2026: Monastir over Sakiet, Metlaoui over Zarzis)
rows3 = [(A, 12, 2, 8), (B, 12, 3, 5)]
check("TUN 2 teams: H2H winner first even with worse overall GD", order("TUN", [(A, B, 1, 0)], rows3) == [A, B], order("TUN", [(A, B, 1, 0)], rows3))

# 4) the option is TUN-only
check("H2H_SKIP_H2H_GOALS = {'TUN'} only", TB.H2H_SKIP_H2H_GOALS == {"TUN"} and TB.H2H_ENABLED["TUN"] is True)

print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
