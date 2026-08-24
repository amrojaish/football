#!/usr/bin/env python3
"""
تشخيص فروق الترتيب — العراقي 2022
=====================================
يقارن عدد مباريات كل نادٍ بالعدد المتوقع، ويكشف أي نادٍ
له عدد شاذ (المتوقع: 38 لدوري من 20 نادياً، ذهاب وإياب).

⚠️ الفروق الظاهرة بالمقارنة كان مجموعها صفراً (−2 +1 +1)،
   أي أن مباريات نُسبت لأندية خاطئة لا أنها فُقدت.
"""
import sqlite3, sys
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
LG, S = "IRQ", 2022

print(f"\n=== عدد مباريات كل نادٍ — {LG} {S} ===")
rows = conn.execute("""
    SELECT t.short_name_ar nm, x.tid, COUNT(*) n
    FROM (
        SELECT home_id tid FROM matches WHERE league_code=? AND season=?
        UNION ALL
        SELECT away_id FROM matches WHERE league_code=? AND season=?
    ) x LEFT JOIN teams t ON t.team_id=x.tid
    GROUP BY x.tid ORDER BY n DESC, t.short_name_ar
""", (LG,S,LG,S)).fetchall()
for r in rows:
    flag = "" if r["n"] == 38 else f"   ⚠️ متوقع 38"
    print(f"  {r['nm'] or '(بلا اسم)':16} id={r['tid']:<7} {r['n']:3}{flag}")

print(f"\n  مجموع الظهور: {sum(r['n'] for r in rows)}  (المتوقع 760 = 380×2)")

print(f"\n=== مباريات نوروز (25062) بالتفصيل ===")
for r in conn.execute("""
    SELECT m.match_id, m.date, h.short_name_ar hm, a.short_name_ar aw,
           m.home_goals hg, m.away_goals ag
    FROM matches m
    JOIN teams h ON h.team_id=m.home_id JOIN teams a ON a.team_id=m.away_id
    WHERE m.league_code=? AND m.season=? AND (m.home_id=25062 OR m.away_id=25062)
    ORDER BY m.date""", (LG,S)):
    print(f"   {r['date'][:10]}  {r['hm']} {r['hg']}-{r['ag']} {r['aw']}")

print("\n=== هل بقيت مباريات على المعرّف القديم 6689؟ ===")
n = conn.execute("""SELECT COUNT(*) FROM matches
    WHERE home_id=6689 OR away_id=6689""").fetchone()[0]
print(f"   {n}  (يجب أن يكون صفراً بعد الدمج)")

print("\n=== مباريات مكرّرة (نفس التاريخ ونفس الفريقين)؟ ===")
d = conn.execute("""
    SELECT m.date, m.home_id, m.away_id, COUNT(*) c, GROUP_CONCAT(m.match_id) ids
    FROM matches m WHERE m.league_code=? AND m.season=?
    GROUP BY m.date, m.home_id, m.away_id HAVING c > 1""", (LG,S)).fetchall()
print(f"   حالات: {len(d)}")
for r in d[:10]:
    print(f"     {r['date'][:10]}  {r['home_id']} × {r['away_id']}  ({r['ids']})")
