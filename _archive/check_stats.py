#!/usr/bin/env python3
"""
فحص تغطية الإحصائيات
======================
بيقارن عدد المباريات المنتهية مع عدد اللي عندها إحصائيات،
مقسّماً حسب الدوري والموسم.

التشغيل:
    python check_stats.py
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

total = conn.execute(
    "SELECT COUNT(*) FROM matches WHERE home_goals IS NOT NULL"
).fetchone()[0]

covered = conn.execute(
    "SELECT COUNT(DISTINCT match_id) FROM match_stats"
).fetchone()[0]

print(f"\n{'=' * 58}")
print("  تغطية إحصائيات المباريات")
print(f"{'=' * 58}")
print(f"  مباريات منتهية : {total}")
print(f"  عندها إحصائيات : {covered}")
print(f"  ناقصة          : {total - covered}")

print(f"\n{'=' * 58}")
print("  التفصيل حسب الدوري والموسم")
print(f"{'=' * 58}\n")

rows = conn.execute("""
    SELECT m.league_code lg, m.season s,
           COUNT(*) done,
           SUM(CASE WHEN EXISTS (
               SELECT 1 FROM match_stats st
               WHERE st.match_id = m.match_id
           ) THEN 1 ELSE 0 END) with_stats
    FROM matches m
    WHERE m.home_goals IS NOT NULL
    GROUP BY m.league_code, m.season
    ORDER BY m.season DESC, m.league_code
""").fetchall()

for r in rows:
    name = LEAGUES.get(r["lg"], {}).get("name_ar", r["lg"])
    pct = r["with_stats"] / r["done"] * 100 if r["done"] else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    print(f"  {name:<18} {r['s']}   "
          f"{r['with_stats']:>4}/{r['done']:<4}  [{bar}] {pct:.0f}%")

print(f"\n{'=' * 58}\n")
conn.close()
