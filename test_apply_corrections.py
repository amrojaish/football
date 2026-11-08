#!/usr/bin/env python3
"""apply_corrections.apply_rows (6 نوفمبر 2026، الموجة 2b): تفصيل ft/et الاختياري + exclude_goals يبقيان بعد إعادة السحب.
قاعدة بالذاكرة — بلا football.db. التشغيل: python test_apply_corrections.py"""
import sqlite3
import sys

import apply_corrections as AC

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


def db():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT,
                 home_id INTEGER, away_id INTEGER, home_goals INTEGER, away_goals INTEGER, status TEXT,
                 ft_home INTEGER, ft_away INTEGER, et_home INTEGER, et_away INTEGER, pen_home INTEGER, pen_away INTEGER)""")
    c.execute("CREATE TABLE teams (team_id INTEGER PRIMARY KEY, short_name_ar TEXT)")
    c.execute("""CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER,
                 player_en TEXT, player_ar TEXT, detail TEXT)""")
    c.executemany("INSERT INTO teams VALUES (?, ?)", [(1, "أ"), (2, "ب")])
    return c


def provider_write(c):
    """ما يكتبه السحب (save_finished + MS.save) بكل إعادة: نتيجة 90 د، extratime فارغ، أهداف الأحداث كلها"""
    c.execute("DELETE FROM matches")
    c.execute("DELETE FROM goals")
    c.execute("INSERT INTO matches VALUES (1528440,'TUN-C',2025,'2026-03-22',1,2,1,1,'PEN',1,1,NULL,NULL,5,4)")
    c.execute("INSERT INTO matches VALUES (1528446,'TUN-C',2025,'2026-03-22',1,2,0,0,'PEN',0,0,NULL,NULL,3,5)")
    c.executemany("INSERT INTO goals (match_id, team_id, minute, player_en, player_ar, detail) VALUES (?,?,?,?,'',?)", [
        (1528440, 2, 5, "O. Adejoh", "Normal Goal"), (1528440, 1, 82, "O. Ayinde", "Normal Goal"),
        (1528440, 2, 97, "Y. Dao", "Normal Goal"), (1528440, 1, 112, "O. Ayinde", "Normal Goal"),
        (1528446, 2, 120, "B. Hasni", "Normal Goal"), (1528446, 1, 120, "A. Hichri", "Normal Goal"),
    ])


ROWS = [
    {"match_id": "1528440", "correct_home": "2", "correct_away": "2", "note": "", "ft_home": "1", "ft_away": "1",
     "et_home": "1", "et_away": "1", "exclude_goals": ""},
    {"match_id": "1528446", "correct_home": "0", "correct_away": "0", "note": "", "ft_home": "", "ft_away": "",
     "et_home": "", "et_away": "", "exclude_goals": "120|B. Hasni;120|A. Hichri"},
    # صف قديم بلا الأعمدة الجديدة إطلاقاً (DictReader يعطي None)
    {"match_id": "999", "correct_home": "1", "correct_away": "0", "note": ""},
]

c = db()
provider_write(c)
res = AC.apply_rows(c, ROWS)
m = c.execute("SELECT home_goals, away_goals, ft_home, ft_away, et_home, et_away, pen_home, pen_away, status "
              "FROM matches WHERE match_id = 1528440").fetchone()
check("1528440 -> 2-2 · ft 1-1 · et 1-1 · pens 5-4 kept · PEN kept", tuple(m) == (2, 2, 1, 1, 1, 1, 5, 4, "PEN"), m)
check("1528440 keeps its 4 goals", c.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1528440").fetchone()[0] == 4)
m = c.execute("SELECT home_goals, away_goals, pen_home, pen_away, status FROM matches WHERE match_id = 1528446").fetchone()
check("1528446 stays 0-0 PEN 3-5", tuple(m) == (0, 0, 3, 5, "PEN"), m)
check("1528446 both 120' events excluded (score already 0-0 = old code skipped them)",
      c.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1528446").fetchone()[0] == 0)
check("counts: 2 applied, 0 already, 1 not found (old-format row tolerated)", res == (2, 0, 1), res)

res = AC.apply_rows(c, ROWS)
check("second run: idempotent (0 applied, 2 already)", res == (0, 2, 1), res)

# إعادة سحب تكتب فوق كل شيء ← التصحيح يعود بنفس الحالة
provider_write(c)
AC.apply_rows(c, ROWS)
m = c.execute("SELECT home_goals, away_goals, et_home, et_away FROM matches WHERE match_id = 1528440").fetchone()
check("after refetch: 1528440 back to 2-2 with et 1-1", tuple(m) == (2, 2, 1, 1), m)
check("after refetch: 1528446 goals excluded again", c.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1528446").fetchone()[0] == 0)

# الاستبعاد مقيَّد بالدقيقة + الاسم: هدف حقيقي لنفس اللاعب بدقيقة أخرى يبقى
c.execute("INSERT INTO goals (match_id, team_id, minute, player_en, player_ar, detail) VALUES (1528446, 2, 60, 'B. Hasni', '', 'Normal Goal')")
AC.apply_rows(c, [dict(ROWS[1], correct_home="0", correct_away="1")])
check("exclusion matches minute AND player only", c.execute("SELECT minute FROM goals WHERE match_id = 1528446").fetchall() == [(60,)])

# --check لا يكتب
provider_write(c)
res = AC.apply_rows(c, ROWS, check_only=True)
check("check_only: reports 2 to fix, writes nothing",
      res[0] == 2 and c.execute("SELECT home_goals, et_home FROM matches WHERE match_id = 1528440").fetchone() == (1, None)
      and c.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1528446").fetchone()[0] == 2, res)

# قبل هجرة match_score: أعمدة ft/et تُتجاهل بلا خطأ
c2 = sqlite3.connect(":memory:")
c2.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, date TEXT, home_id INTEGER, away_id INTEGER, home_goals INTEGER, away_goals INTEGER)")
c2.execute("CREATE TABLE teams (team_id INTEGER PRIMARY KEY, short_name_ar TEXT)")
c2.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, minute INTEGER, player_en TEXT)")
c2.execute("INSERT INTO matches VALUES (1528440, '2026-03-22', 1, 2, 1, 1)")
res = AC.apply_rows(c2, ROWS[:1])
check("pre-migration DB: score fixed, ft/et ignored", res[0] == 1 and c2.execute("SELECT home_goals FROM matches").fetchone()[0] == 2, res)

# صيغة خاطئة تفشل بصوت
try:
    AC.parse_excludes("120 B. Hasni")
    check("bad exclude_goals spec raises", False)
except ValueError:
    check("bad exclude_goals spec raises", True)

# (الموجة 5ب) هدف بلا اسم: بالدقيقة + الفريق فقط — «54||5400»
check("nameless spec parses to (minute, '', team), named stays a pair",
      AC.parse_excludes("54||5400;120|B. Hasni") == [(54, "", 5400), (120, "B. Hasni")])
for bad in ("54|", "54||", "54||abc", "54|B. Hasni|5400"):
    try:
        AC.parse_excludes(bad)
        check(f"bad spec {bad!r} raises", False)
    except ValueError:
        check(f"bad spec {bad!r} raises", True)


def nameless_db():
    c3 = db()
    c3.execute("INSERT INTO matches VALUES (7,'CAF-CL',2026,'2026-09-20',1,2,2,1,'FT',NULL,NULL,NULL,NULL,NULL,NULL)")
    c3.executemany("INSERT INTO goals (match_id, team_id, minute, player_en, player_ar, detail) VALUES (7,?,?,?,'','Normal Goal')", [
        (1, 54, ""), (1, 54, None), (2, 54, ""), (1, 54, "Named Scorer"), (1, 10, ""),
    ])
    return c3


NR = [{"match_id": "7", "correct_home": "2", "correct_away": "1", "note": "", "exclude_goals": "54||1"}]
c3 = nameless_db()
res = AC.apply_rows(c3, NR)
left = sorted(tuple(r) for r in c3.execute("SELECT team_id, minute, COALESCE(player_en, '') FROM goals WHERE match_id = 7"))
check("nameless exclude: only that team + minute + empty/NULL name is removed",
      left == [(1, 10, ""), (1, 54, "Named Scorer"), (2, 54, "")] and res == (1, 0, 0), (left, res))
check("nameless exclude: second run idempotent", AC.apply_rows(c3, NR) == (0, 1, 0))
c3 = nameless_db()
AC.apply_rows(c3, NR, check_only=True)
check("nameless exclude: check_only writes nothing", c3.execute("SELECT COUNT(*) FROM goals WHERE match_id = 7").fetchone()[0] == 5)

# الملف الحقيقي: الصفوف الخمسة للموجة 2b بالأعمدة الصحيحة
rows = {r["match_id"]: r for r in AC.load_rows()}
check("match_corrections.csv: 1619062 stays 0-0 with the 54' nameless Colombe goal excluded",
      rows["1619062"]["correct_home"] == "0" and rows["1619062"]["correct_away"] == "0"
      and AC.parse_excludes(rows["1619062"]["exclude_goals"]) == [(54, "", 5400)])
want = {"1528440": ("2", "2", "1", "1", "1", "1"), "1538419": ("1", "1", "0", "0", "1", "1"),
        "1488754": ("3", "3", "2", "2", "1", "1"), "1494076": ("3", "3", "2", "2", "1", "1")}
check("match_corrections.csv: 4 ET corrections as specified",
      all(tuple(rows[k][c] for c in ("correct_home", "correct_away", "ft_home", "ft_away", "et_home", "et_away")) == v
          for k, v in want.items()), {k: rows.get(k) for k in want})
check("match_corrections.csv: 1528446 0-0 + both 120' exclusions",
      rows["1528446"]["correct_home"] == "0" and AC.parse_excludes(rows["1528446"]["exclude_goals"]) == [(120, "B. Hasni"), (120, "A. Hichri")])

print(f"\n{'ALL PASS' if not fail else f'{fail} FAILED'}")
sys.exit(1 if fail else 0)
