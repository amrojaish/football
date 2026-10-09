#!/usr/bin/env python3
"""apply_id_repoints.py: يصحّح player_id لصفوف محدّدة فقط (اسم+قميص)، idempotent، يتخطّى التكرار، ولا يلمس غير player_id.
التشغيل: python test_apply_id_repoints.py"""
import sqlite3
import sys

import apply_id_repoints as m

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
    """)
    for mid in range(1, 10):   # real owner 16858: 28 el wensh rows
        c.execute("INSERT INTO lineup_players VALUES (?,1040,16858,'Mahmoud Hamdi El Wensh','',28,'D','',1)", (mid,))
    for mid in (3, 4, 5):      # the wrong rows: 'M. I. Hassan' #52 under 16858
        c.execute("INSERT INTO lineup_players VALUES (?,1040,16858,'M. I. Hassan','',52,'','',0)", (mid,))
    for mid in (3, 4, 5, 6):   # real owner of #52 has stats rows only
        c.execute("INSERT INTO player_stats VALUES (?,1040,477137,'Mohamed Ibrahim Hassan','',45)", (mid,))
    c.execute("INSERT INTO lineup_players VALUES (20,1040,477137,'Mohamed Ibrahim Hassan','',52,'','',1)")
    c.commit()
    return c


R = lambda **k: {"table": "lineup_players", "from": 16858, "to": 477137, "number": 52, "en": "M. I. Hassan", "expect": 3, **k}

c = mk()
tot = c.execute("SELECT COUNT(*) FROM lineup_players").fetchone()[0]
rep = m.apply(c, [R()])
check("3 wrong rows re-pointed", rep[0]["matched"] == 3 and rep[0]["moved"] == 3, rep[0])
check("  El Wensh's 9 rows (#28) stay with 16858", c.execute("SELECT COUNT(*) FROM lineup_players WHERE player_id=16858").fetchone()[0] == 9)
check("  total rows unchanged; names/numbers untouched", c.execute("SELECT COUNT(*) FROM lineup_players").fetchone()[0] == tot
      and c.execute("SELECT COUNT(*) FROM lineup_players WHERE player_id=477137 AND player_en='M. I. Hassan' AND number=52").fetchone()[0] == 3)
rep2 = m.apply(c, [R()])
check("  idempotent: second run matches nothing", rep2[0]["matched"] == 0 and rep2[0]["moved"] == 0, rep2[0])
# a new wrong row appears later (CI re-fetch) -> fixed on the next run
c.execute("INSERT INTO lineup_players VALUES (7,1040,16858,'M. I. Hassan','',52,'','',0)")
rep3 = m.apply(c, [R()])
check("  a later wrong row of the same kind is fixed too", rep3[0]["moved"] == 1, rep3[0])

# same person already in that match/team under the right id -> skipped, no PK clash
c = mk()
c.execute("INSERT INTO lineup_players VALUES (3,1040,477137,'Mohamed Ibrahim Hassan','',52,'','',0)")
rep = m.apply(c, [R()], out=lambda *a: None)
check("match 3 already has 477137 -> that row skipped, other two moved", rep[0]["moved"] == 2 and rep[0]["skipped_dup"] == 1, rep[0])

# a different shirt or name under the same wrong id is not touched
c = mk()
c.execute("INSERT INTO lineup_players VALUES (8,1040,16858,'M. I. Hassan','',99,'','',0)")
rep = m.apply(c, [R()])
check("same name, other shirt number -> untouched", c.execute("SELECT COUNT(*) FROM lineup_players WHERE number=99 AND player_id=16858").fetchone()[0] == 1)

# target unknown -> nothing written
c = mk()
rep = m.apply(c, [R(to=999999)], out=lambda *a: None)
check("target id without any row -> skipped, no write", rep[0]["moved"] == 0 and c.execute("SELECT COUNT(*) FROM lineup_players WHERE player_id=999999").fetchone()[0] == 0, rep[0])

for label, rows, ok in [
    ("unknown table", [R(table="goals")], False),
    ("from == to", [R(to=16858)], False),
    ("missing name", [R(en="")], False),
    ("chain", [R(), R(from_=1) if False else R(**{"from": 477137, "to": 5})], False),
    ("valid", [R()], True),
]:
    try:
        m.validate(rows); good = True
    except ValueError:
        good = False
    check(f"validate: {label} -> {'accepted' if ok else 'refused'}", good == ok)

sys.exit(1 if fail else 0)
