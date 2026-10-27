#!/usr/bin/env python3
"""apply_scorer_aliases.py: ينظّف الرقم الملتصق فقط، لا يمسّ الاسم السليم، الاسم البديل على ناديه وحده، idempotent، ويرفض السلاسل.
التشغيل: python test_scorer_aliases.py"""
import sqlite3
import sys

import apply_scorer_aliases as m

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


def mk():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE goals (id INTEGER PRIMARY KEY, match_id INT, team_id INT, minute INT, player_en TEXT, player_ar TEXT, detail TEXT);
    CREATE TABLE events (id INTEGER PRIMARY KEY, match_id INT, team_id INT, minute INT, type TEXT, detail TEXT, player_en TEXT, player_ar TEXT, assist_en TEXT);
    CREATE TABLE lineup_players (match_id INT, team_id INT, player_id INT, player_en TEXT, player_ar TEXT, PRIMARY KEY (match_id, player_id));
    """)
    goals = [
        (1, 3535, 90, "Y. Amri                                  7"),
        (2, 3538, 90, "1                         C. Rivas"),
        (3, 3535, 90, "Fawaz Al Mubailish                                "),
        (4, 3535, 10, "Y. Amri"),
        (5, 3535, 20, "T. Y. Khenissi"),
        (6, 3535, 30, "T. Khenissi"),
        (7, 969, 40, "T. Y. Khenissi"),          # نفس النص بنادٍ آخر — لا يُمسّ
        (8, 3532, 50, "Ahmed 2nd Ali"),          # رقم بالوسط — لا يُمسّ
    ]
    for mid, t, mn, n in goals:
        c.execute("INSERT INTO goals (match_id, team_id, minute, player_en, detail) VALUES (?,?,?,?,'Normal Goal')", (mid, t, mn, n))
    c.execute("INSERT INTO events (match_id, team_id, minute, type, player_en) VALUES (5, 3535, 20, 'Goal', 'T. Y. Khenissi')")
    c.execute("INSERT INTO events (match_id, team_id, minute, type, player_en) VALUES (9, 3535, 70, 'Card', 'Abdellah Farah\t')")
    c.execute("INSERT INTO lineup_players VALUES (1, 980, 77, ' 4   B. Ghariani', '')")
    c.commit()
    return c


ALIASES = [{"team": 3535, "from": "T. Y. Khenissi", "to": "T. Khenissi"}]
quiet = lambda *_: None

# clean_name
check("junk trailing digit", m.clean_name("Y. Amri                                  7") == "Y. Amri")
check("junk leading digit", m.clean_name("1                         C. Rivas") == "C. Rivas")
check("trailing spaces", m.clean_name("Fawaz Al Mubailish                                ") == "Fawaz Al Mubailish")
check("tab stripped", m.clean_name("Abdellah Farah\t") == "Abdellah Farah")
check("normal name unchanged", m.clean_name("Alex Lima") == "Alex Lima")
check("inner digit unchanged", m.clean_name("Ahmed 2nd Ali") == "Ahmed 2nd Ali")

c = mk()
r = m.apply(c, ALIASES, out=quiet)
names = {mid: n for mid, n in c.execute("SELECT match_id, player_en FROM goals")}
check("goals cleaned", names[1] == "Y. Amri" and names[2] == "C. Rivas" and names[3] == "Fawaz Al Mubailish", names)
check("goals clean count", r["clean"]["goals"] == 3, r)
check("events cleaned", c.execute("SELECT player_en FROM events WHERE match_id=9").fetchone()[0] == "Abdellah Farah")
check("lineup cleaned", c.execute("SELECT player_en FROM lineup_players").fetchone()[0] == "B. Ghariani")
check("alias on its team (goals)", names[5] == "T. Khenissi", names)
check("alias on its team (events)", c.execute("SELECT player_en FROM events WHERE match_id=5").fetchone()[0] == "T. Khenissi")
check("alias NOT on another team", names[7] == "T. Y. Khenissi", names)
check("normal names untouched", names[4] == "Y. Amri" and names[6] == "T. Khenissi" and names[8] == "Ahmed 2nd Ali", names)

r2 = m.apply(c, ALIASES, out=quiet)
check("idempotent: second run 0 changes", sum(r2["clean"].values()) == 0 and sum(r2["alias"].values()) == 0, r2)

for bad, label in (([{"team": 1, "from": "A", "to": "A"}], "from=to"),
                   ([{"team": 1, "from": "A", "to": "B"}, {"team": 1, "from": "B", "to": "C"}], "chain"),
                   ([{"team": 1, "from": "A", "to": "B"}, {"team": 1, "from": "A", "to": "C"}], "two targets")):
    try:
        m.validate(bad)
        check(f"validate rejects {label}", False)
    except ValueError:
        check(f"validate rejects {label}", True)
check("validate: same from on two teams ok", m.validate([{"team": 1, "from": "A", "to": "B"}, {"team": 2, "from": "A", "to": "C"}]) is None)

real = m.load_aliases()
try:
    m.validate(real)
    check(f"scorer_name_aliases.csv valid ({len(real)} rows)", len(real) > 0)
except ValueError as e:
    check("scorer_name_aliases.csv valid", False, e)

print(f"\n{'OK' if not fail else f'{fail} FAILED'}")
sys.exit(1 if fail else 0)
