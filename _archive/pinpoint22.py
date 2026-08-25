#!/usr/bin/env python3
"""
تحديد المباراة الأرجح للخطأ — بمطابقة تواريخ الجولات
=========================================================
لكل زوج "ناقص"، نجلب تاريخ مباراته الوحيدة الموجودة، ونقارنه
بتواريخ الثلاث "الزائدة" لنفس الفريقين تقريباً. المباراة التي
تاريخها الأقرب لتاريخ الجولة نفسها في الدوري (أي فريق آخر
لعب بنفس التاريخ تقريباً) هي الأرجح أن تكون الخطأ.
"""
import sqlite3, sys
from config import DB_FILE

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row

def team_id(name):
    return conn.execute(
        "SELECT team_id FROM teams WHERE short_name_ar=?", (name,)
    ).fetchone()[0]

pairs_missing = [("النجف", "نفط ميسان"), ("النفط", "نفط البصرة"),
                  ("نفط ميسان", "الديوانية")]

for a, b in pairs_missing:
    ta, tb = team_id(a), team_id(b)
    print(f"\n=== {a} × {b} — الموجودة حالياً ===")
    for r in conn.execute("""
        SELECT m.match_id, m.date, h.short_name_ar hm, a.short_name_ar aw,
               m.home_goals hg, m.away_goals ag
        FROM matches m JOIN teams h ON h.team_id=m.home_id
        JOIN teams a ON a.team_id=m.away_id
        WHERE m.league_code='IRQ' AND m.season=2022
          AND ((m.home_id=? AND m.away_id=?) OR (m.home_id=? AND m.away_id=?))
    """, (ta, tb, tb, ta)):
        print(f"   match_id={r['match_id']}  {r['date'][:10]}  "
              f"{r['hm']} {r['hg']}-{r['ag']} {r['aw']}")

    # ما الذي لعبه نفط ميسان (والفريق الآخر) بنفس تواريخ المباريات
    # الثلاث "الزائدة" ذات الصلة؟
    print(f"   بحث: هل {a} أو {b} لعب مباراة أخرى بأحد هذه التواريخ؟")
    for date in ("2023-02-11", "2023-05-23", "2023-07-05",
                 "2022-10-15", "2023-03-18", "2023-05-25",
                 "2022-10-29", "2023-04-18", "2023-07-20"):
        for team in (a, b):
            tid = team_id(team)
            r = conn.execute("""
                SELECT m.match_id, h.short_name_ar hm, a.short_name_ar aw,
                       m.home_goals hg, m.away_goals ag
                FROM matches m JOIN teams h ON h.team_id=m.home_id
                JOIN teams a ON a.team_id=m.away_id
                WHERE m.league_code='IRQ' AND m.season=2022 AND m.date LIKE ?
                  AND (m.home_id=? OR m.away_id=?)
            """, (date+'%', tid, tid)).fetchone()
            if r:
                print(f"      {date}: {team} لعب -> match_id={r['match_id']} "
                      f"{r['hm']} {r['hg']}-{r['ag']} {r['aw']}")
