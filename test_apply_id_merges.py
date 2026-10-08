#!/usr/bin/env python3
"""apply_id_merges.py: يدمج بالمعرّف فقط، يتخطّى من ظهرا معاً، يرفض السلاسل، idempotent، ولا يلمس غير player_id.
التشغيل: python test_apply_id_merges.py"""
import sqlite3
import sys

import apply_id_merges as m

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


def mk():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE lineup_players (match_id INT, team_id INT, player_id INT, player_en TEXT, player_ar TEXT, number INT, pos TEXT, grid TEXT, starter INT, PRIMARY KEY (match_id, team_id, player_id, player_en));
    CREATE TABLE player_stats (match_id INT, team_id INT, player_id INT, player_en TEXT, player_ar TEXT, minutes INT, PRIMARY KEY (match_id, team_id, player_id, player_en));
    CREATE TABLE goals (id INTEGER PRIMARY KEY, match_id INT, team_id INT, player_en TEXT);
    """)
    # 10 = keep (matches 1-4), 20 = drop (matches 5-6), 30 = keep2 (match 1), 40 = drop2 (match 1: same match -> two people)
    for mid in (1, 2, 3, 4):
        c.execute("INSERT INTO lineup_players VALUES (?,?,?,?,?,?,?,?,?)", (mid, 7, 10, "Ahmed Ali", "", 9, "F", "", 1))
        c.execute("INSERT INTO player_stats VALUES (?,?,?,?,?,?)", (mid, 7, 10, "Ahmed Ali", "", 90))
    for mid in (5, 6):
        c.execute("INSERT INTO lineup_players VALUES (?,?,?,?,?,?,?,?,?)", (mid, 7, 20, "A. Ali", "", 9, "F", "", 1))
        c.execute("INSERT INTO player_stats VALUES (?,?,?,?,?,?)", (mid, 7, 20, "A. Ali", "", 80))
    c.execute("INSERT INTO lineup_players VALUES (1,8,30,'K. One','',1,'G','',1)")
    c.execute("INSERT INTO lineup_players VALUES (1,8,40,'K. Two','',2,'G','',1)")
    # pid 0 group (name + team)
    c.execute("INSERT INTO player_stats VALUES (9,7,0,'Ahmed Ali',NULL,90)")
    c.execute("INSERT INTO player_stats VALUES (9,7,0,'Someone Else',NULL,90)")
    for mid in (1, 5):
        c.execute("INSERT INTO goals (match_id, team_id, player_en) VALUES (?,?,?)", (mid, 7, "Ahmed Ali"))
    c.commit()
    return c


def counts(c):
    return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("lineup_players", "player_stats", "goals")}


R = lambda **k: {"drop": 0, "keep": 0, "team": None, "en": "", "note": "", **k}

# 1) plain id merge: rows move, names untouched, goals untouched, apps = sum
c = mk(); before = counts(c); goals_before = c.execute("SELECT * FROM goals ORDER BY id").fetchall()
rows = [R(drop=20, keep=10, team=7)]
rep, done, skipped = m.apply(c, rows)
check("merge 20 -> 10: done=1 skipped=0", (done, skipped) == (1, 0), (done, skipped))
check("  keep appearances = 8 + 4 = 12 (before 8, drop 4)", rep[0]["keep_before"] == 8 and rep[0]["keep_after"] == 12, rep[0])
check("  row counts unchanged in every table", counts(c) == before, counts(c))
check("  names untouched (A. Ali stays A. Ali, now under id 10)", c.execute("SELECT COUNT(*) FROM lineup_players WHERE player_id=10 AND player_en='A. Ali'").fetchone()[0] == 2)
check("  goals table byte-identical", c.execute("SELECT * FROM goals ORDER BY id").fetchall() == goals_before)
check("  no row left under the dropped id", c.execute("SELECT COUNT(*) FROM lineup_players WHERE player_id=20").fetchone()[0] == 0)
rep2, d2, s2 = m.apply(c, rows)
check("  idempotent: second run does nothing", (d2, s2) == (0, 0) and rep2[0]["status"] == "nothing", rep2[0]["status"])

# 2) pid 0 group: only that (name, team); the other pid-0 name stays
c = mk()
rep, done, skipped = m.apply(c, [R(drop=0, keep=10, team=7, en="Ahmed Ali")])
check("pid-0 group by (name, team) -> 10: 1 row moved, the other pid-0 player untouched",
      done == 1 and c.execute("SELECT COUNT(*) FROM player_stats WHERE player_id=0").fetchone()[0] == 1
      and c.execute("SELECT player_en FROM player_stats WHERE player_id=0").fetchone()[0] == "Someone Else", rep[0])

# 3) two people in the same match: skipped, nothing written
c = mk(); before = c.execute("SELECT * FROM lineup_players ORDER BY 1,2,3").fetchall()
rep, done, skipped = m.apply(c, [R(drop=40, keep=30, team=8)], out=lambda *a: None)
check("both ids in match 1 -> skipped_shared_match, no write", (done, skipped) == (0, 1) and rep[0]["status"] == "skipped_shared_match"
      and c.execute("SELECT * FROM lineup_players ORDER BY 1,2,3").fetchall() == before, rep[0])

# 4) validation
for label, rows, ok in [
    ("chain 20->10, 10->5", [R(drop=20, keep=10), R(drop=10, keep=5)], False),
    ("cycle 1->2, 2->1", [R(drop=1, keep=2), R(drop=2, keep=1)], False),
    ("drop == keep", [R(drop=3, keep=3)], False),
    ("pid 0 without name/team", [R(drop=0, keep=10)], False),
    ("same source to two keeps", [R(drop=20, keep=10), R(drop=20, keep=11)], False),
    ("valid", [R(drop=20, keep=10), R(drop=21, keep=10)], True),
]:
    try:
        m.validate(rows); good = True
    except ValueError:
        good = False
    check(f"validate: {label} -> {'accepted' if ok else 'refused'}", good == ok)

sys.exit(1 if fail else 0)
