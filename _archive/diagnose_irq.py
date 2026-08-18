#!/usr/bin/env python3
"""
تشخيص الدوري العراقي
=====================
بيفحص:
  1. كل نادي وعدد مبارياته
  2. مباريات كربلاء (نادي هابط، ما لازم يكون موجود)
  3. توزيع المباريات على الشهور — يكشف خلط مواسم

صفر طلبات API — بيقرأ بس.

التشغيل:
    python diagnose_irq.py
    python diagnose_irq.py SAU 2025
"""

import sqlite3
import sys
from collections import Counter
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "IRQ"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2025

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

print(f"\n{'=' * 62}")
print(f"  تشخيص {CODE} — موسم {SEASON}")
print(f"{'=' * 62}")

# ---------------------------------------------------------------
# 1) كل نادي وعدد مبارياته
# ---------------------------------------------------------------
rows = conn.execute("""
    WITH g AS (
        SELECT home_id AS tid FROM matches
        WHERE league_code = ? AND season = ?
        UNION ALL
        SELECT away_id FROM matches
        WHERE league_code = ? AND season = ?
    )
    SELECT t.team_id, t.short_name_ar AS name, COUNT(*) AS n
    FROM g LEFT JOIN teams t ON t.team_id = g.tid
    GROUP BY g.tid
    ORDER BY n
""", (CODE, SEASON, CODE, SEASON)).fetchall()

print(f"\n[1] الأندية ({len(rows)} نادي) — مرتبة من الأقل مباريات:\n")
for r in rows:
    name = r["name"] or f"⚠️ ID {r['team_id']} غير موجود بجدول teams"
    flag = "   <-- مشبوه" if r["n"] < 20 else ""
    print(f"      {r['n']:>3} مباراة   {name}{flag}")

# ---------------------------------------------------------------
# 2) الأندية المشبوهة وتفاصيل مبارياتها
# ---------------------------------------------------------------
suspects = [r for r in rows if r["n"] < 20]

if suspects:
    print(f"\n[2] تفاصيل مباريات الأندية المشبوهة:")
    for s in suspects:
        print(f"\n  --- {s['name'] or s['team_id']} ---")
        ms = conn.execute("""
            SELECT m.match_id, m.date, m.home_goals hg, m.away_goals ag,
                   h.short_name_ar hn, a.short_name_ar an
            FROM matches m
            LEFT JOIN teams h ON h.team_id = m.home_id
            LEFT JOIN teams a ON a.team_id = m.away_id
            WHERE m.league_code = ? AND m.season = ?
              AND (m.home_id = ? OR m.away_id = ?)
            ORDER BY m.date
        """, (CODE, SEASON, s["team_id"], s["team_id"])).fetchall()
        for m in ms:
            print(f"      {m['date']}  {m['hn']} {m['hg']}-{m['ag']} {m['an']}"
                  f"   id={m['match_id']}")
else:
    print(f"\n[2] ما في أندية بأقل من 20 مباراة")

# ---------------------------------------------------------------
# 3) توزيع المباريات على الشهور — يكشف خلط مواسم
# ---------------------------------------------------------------
dates = conn.execute("""
    SELECT substr(date, 1, 7) AS ym FROM matches
    WHERE league_code = ? AND season = ?
""", (CODE, SEASON)).fetchall()

months = Counter(d["ym"] for d in dates)

print(f"\n[3] توزيع المباريات على الشهور:\n")
for ym in sorted(months):
    bar = "#" * min(months[ym], 40)
    print(f"      {ym}   {months[ym]:>3}  {bar}")

first, last = min(months), max(months)
print(f"\n      من {first} إلى {last}  ({len(months)} شهر)")
print("      (موسم واحد طبيعي = 9-11 شهر. أكثر من هيك = خلط مواسم)")

conn.close()
print(f"\n{'=' * 62}\n")
