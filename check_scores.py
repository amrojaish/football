#!/usr/bin/env python3
"""
فحص تطابق النتيجة مع أحداث الأهداف
=====================================
يكشف المباريات التي لا يطابق فيها عدد الأهداف المسجّلة في
`goals` النتيجةَ المسجّلة في `matches`.

⚠️ **اصطلاح الهدف العكسي محقَّق بالداتا لا بالنقل:**
   في `goals`، حقل `team_id` للهدف العكسي هو **الفريق
   المستفيد** لا فريق اللاعب. الدليل: من 169 مباراة فيها هدف
   عكسي، **167 (99%)** يطابق مجموعُها النتيجةَ بهذا الافتراض.
   الافتراض المعاكس كان سيقلب 167 نتيجة.

الأنماط الثلاثة المتوقعة:
   1. **محسومة إدارياً** — النتيجة 3-0 أو 0-3 والأحداث مختلفة
      تماماً. طبيعي: الاتحاد يحسم المباراة والأحداث تبقى كما
      لُعبت. لا تُصحَّح.
   2. **أهداف ملغاة** — النتيجة 0-0 وفيها أحداث. عالجها
      `fix_goals.py` بالأرشفة.
   3. **حدث ناقص أو نتيجة خاطئة** — فرق هدف واحد عادةً.
      هذه وحدها تستحق `match_corrections.csv`.

صفر طلبات API. لا يكتب شيئاً.

    python check_scores.py
"""
import sqlite3
import sys
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT m.match_id, m.date, m.league_code lg, m.season s,
           h.short_name_ar home, a.short_name_ar away,
           m.home_goals hg, m.away_goals ag,
           (SELECT COUNT(*) FROM goals x
              WHERE x.match_id = m.match_id AND x.team_id = m.home_id) gh,
           (SELECT COUNT(*) FROM goals x
              WHERE x.match_id = m.match_id AND x.team_id = m.away_id) ga,
           (SELECT COUNT(*) FROM goals x WHERE x.match_id = m.match_id) tot
    FROM matches m
    JOIN teams h ON h.team_id = m.home_id
    JOIN teams a ON a.team_id = m.away_id
    WHERE m.home_goals IS NOT NULL
""").fetchall()

played = [r for r in rows if r["tot"] > 0]
bad = [r for r in played if r["gh"] != r["hg"] or r["ga"] != r["ag"]]

forfeit, cancelled, real = [], [], []
for r in bad:
    pair = {r["hg"], r["ag"]}
    if pair == {0, 3}:
        forfeit.append(r)
    elif r["hg"] == 0 and r["ag"] == 0:
        cancelled.append(r)
    else:
        real.append(r)

print()
print("=" * 66)
print(f"  مباريات فيها أهداف مسجّلة : {len(played)}")
print(f"  لا تطابق النتيجة          : {len(bad)}")
print("=" * 66)
print(f"  محسومة إدارياً (3-0)  : {len(forfeit)}   طبيعي — لا تُصحَّح")
print(f"  نتيجة 0-0 وفيها أحداث : {len(cancelled)}   شغّل fix_goals.py")
print(f"  ⚠️ تحتاج مراجعة       : {len(real)}")

def show(rs, title):
    if not rs:
        return
    print(f"\n{title}")
    for r in rs:
        print(f"  {r['date'][:10]} {r['lg']}{r['s']}  "
              f"{r['home']} {r['hg']}-{r['ag']} {r['away']}"
              f"   الأحداث: {r['gh']}-{r['ga']}   match={r['match_id']}")

show(real, "⚠️ للمراجعة — حدث ناقص أو نتيجة خاطئة:")
show(cancelled, "أهداف ملغاة (يعالجها fix_goals.py):")
show(forfeit, "محسومة إدارياً — للعلم فقط:")

print("""
  التصحيح يتم في match_corrections.csv ثم:
      python apply_corrections.py
""")
