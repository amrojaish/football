#!/usr/bin/env python3
"""
تحديد المباريات المفقودة — العراقي 2022
==========================================
كل نادٍ يجب أن يلاقي كل نادٍ آخر مرتين (ذهاب وإياب).
هذا يكشف أي زوج لم يلتقِ العدد الصحيح.

⚠️ التشخيص السابق أثبت أن الخلل ليس من الدمج: نوروز 38
   بالضبط، صفر تكرار، والمجموع 760 صحيح. المشكلة أن قائمة
   مباريات المزوّد تناقض جدول ترتيبه هو.
"""
import sqlite3, sys
from collections import defaultdict
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
LG, S = "IRQ", 2022

names = {r["team_id"]: r["short_name_ar"] for r in
         conn.execute("SELECT team_id, short_name_ar FROM teams")}

teams = set()
pair = defaultdict(int)
for r in conn.execute("""SELECT home_id h, away_id a FROM matches
    WHERE league_code=? AND season=?""", (LG, S)):
    teams.add(r["h"]); teams.add(r["a"])
    pair[frozenset((r["h"], r["a"]))] += 1

teams = sorted(teams)
print(f"\n=== أزواج لم تلتقِ مرتين — {LG} {S} ===")
bad = 0
for i, x in enumerate(teams):
    for y in teams[i+1:]:
        n = pair.get(frozenset((x, y)), 0)
        if n != 2:
            bad += 1
            print(f"  {names.get(x,x):14} × {names.get(y,y):14}  "
                  f"التقيا {n} مرة" + ("   ⚠️ ناقص" if n < 2 else "   ⚠️ زائد"))
print(f"\n  عدد الأزواج الشاذة: {bad}")
print(f"  (الأزواج الكلية المتوقعة: {len(teams)*(len(teams)-1)//2})")
