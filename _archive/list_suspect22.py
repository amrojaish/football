#!/usr/bin/env python3
"""
تفاصيل المباريات المشكوك فيها — العراقي 2022
================================================
يعرض كل مباريات الأزواج الأربعة (النجف، النفط، نفط ميسان،
نفط البصرة، الديوانية) بتواريخها ونتائجها، لتسهيل البحث عن
المباراة الصحيحة من مصدر خارجي.

السياق: 6 أزواج شاذة (find_missing22.py) بنمط واحد — 3 "زائدة"
تقابلها 3 "ناقصة"، ومجموع الفرق صفر. يُرجَّح أن 3 مباريات
حقيقية نُسبت لفريق خطأ بسبب تشابه الأسماء عند المزوّد.
"""
import sqlite3, sys
from config import DB_FILE

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row

TEAMS = {
    "النجف": 11066, "النفط": 11071, "نفط ميسان": 11074,
    "نفط البصرة": 11072, "الديوانية": 15543,
}
ids = list(TEAMS.values())

print("\n=== كل مباريات الخمسة أندية المشتبه بها — IRQ 2022 ===\n")
rows = conn.execute(f"""
    SELECT m.match_id, m.date, h.short_name_ar hm, a.short_name_ar aw,
           m.home_goals hg, m.away_goals ag, m.home_id, m.away_id
    FROM matches m
    JOIN teams h ON h.team_id = m.home_id
    JOIN teams a ON a.team_id = m.away_id
    WHERE m.league_code='IRQ' AND m.season=2022
      AND (m.home_id IN ({",".join("?"*len(ids))})
        OR m.away_id IN ({",".join("?"*len(ids))}))
    ORDER BY m.date
""", ids + ids).fetchall()

for r in rows:
    hi = " ⭐" if r["home_id"] in ids and r["away_id"] in ids else ""
    print(f"  match_id={r['match_id']:>8}  {r['date'][:10]}  "
          f"{r['hm']} {r['hg']}-{r['ag']} {r['aw']}{hi}")

print(f"\n  ⭐ = مباراة بين اثنين من الخمسة (الأكثر ترجيحاً للخطأ)")
print(f"\n=== الأزواج الثلاثة الزائدة — بالتفصيل ===")
pairs = [("النجف", "النفط"), ("النجف", "نفط البصرة"), ("النفط", "الديوانية")]
for a, b in pairs:
    print(f"\n  {a} × {b}:")
    for r in rows:
        if {r["hm"], r["aw"]} == {a, b}:
            print(f"     match_id={r['match_id']}  {r['date'][:10]}  "
                  f"{r['hm']} {r['hg']}-{r['ag']} {r['aw']}")

print(f"\n=== الأزواج الثلاثة الناقصة — يُفترض أن إحدى المباريات أعلاه تخصها ===")
missing = [("النجف", "نفط ميسان"), ("النفط", "نفط البصرة"), ("نفط ميسان", "الديوانية")]
for a, b in missing:
    n = sum(1 for r in rows if {r["hm"], r["aw"]} == {a, b})
    print(f"  {a} × {b}  —  موجودة حالياً: {n} (يجب أن تكون 2)")
