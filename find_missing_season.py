#!/usr/bin/env python3
"""
كشف أزواج أندية لم تلتقِ مرتين — أي موسم
=============================================
كل نادٍ يجب أن يلاقي كل نادٍ آخر مرتين (ذهاب وإياب) بدوري
كامل. أي زوج بغير ذلك يعني مباراة نُسبت لفريق خطأ (كما حصل
بالعراقي 2022 — نمط تشابه أسماء "النفط"/"نفط ميسان"/"نفط
البصرة"، درس 85).

⚠️ نسخة معمَّمة عن find_missing22.py — تقبل الدوري والموسم
   كوسيطين، وتفحص كل المواسم المتاحة إن لم تُحدَّد.

    python find_missing_season.py IRQ           # كل مواسم العراقي
    python find_missing_season.py IRQ 2023       # موسم واحد فقط
    python find_missing_season.py                # كل الدوريات كل المواسم
"""

import sqlite3
import sys
from collections import defaultdict
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

args = sys.argv[1:]
league_filter = next((a for a in args if a in LEAGUES), None)
season_filter = next((int(a) for a in args if a.isdigit()), None)

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
names = {r["team_id"]: r["short_name_ar"]
         for r in conn.execute("SELECT team_id, short_name_ar FROM teams")}

combos = conn.execute("""
    SELECT DISTINCT league_code, season FROM matches
    ORDER BY league_code, season
""").fetchall()

total_issues = 0
checked = 0

for c in combos:
    lg, season = c["league_code"], c["season"]
    if league_filter and lg != league_filter:
        continue
    if season_filter and season != season_filter:
        continue

    teams = set()
    pair = defaultdict(int)
    for r in conn.execute("""
            SELECT home_id h, away_id a FROM matches
            WHERE league_code=? AND season=?""", (lg, season)):
        teams.add(r["h"]); teams.add(r["a"])
        pair[frozenset((r["h"], r["a"]))] += 1

    teams = sorted(teams)
    n = len(teams)
    # دوري ذهاب وإياب: كل زوج يلتقي مرتين
    expected = 2
    bad = []
    for i, x in enumerate(teams):
        for y in teams[i+1:]:
            k = pair.get(frozenset((x, y)), 0)
            if k != expected:
                bad.append((x, y, k))

    checked += 1
    if bad:
        total_issues += len(bad)
        print(f"\n⚠️ {lg} {season} — {len(bad)} زوج شاذ (من {n} نادياً):")
        for x, y, k in bad:
            tag = "ناقص" if k < expected else "زائد"
            print(f"    {names.get(x,x):14} × {names.get(y,y):14}"
                  f"  التقيا {k} مرة   {tag}")

print()
print("=" * 60)
print(f"  مواسم مفحوصة: {checked}")
print(f"  أزواج شاذة إجمالاً: {total_issues}")
if total_issues == 0:
    print("  ✅ لا شذوذ — كل الأزواج التقت العدد الصحيح")
print("=" * 60)
