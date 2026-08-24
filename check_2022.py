#!/usr/bin/env python3
"""
فحص أندية موسم قديم بعد سحبه
================================
يكشف الأندية التي لها مباريات لكن **لا وجود لها في جدول
`teams`** — فمبارياتها لن تُولَّد لها صفحات، وجدول الترتيب
سيكون ناقصاً.

⚠️ **لماذا سكربت منفصل عن `check_season.py`؟** ذاك لا يحلّل
   وسائط سطر الأوامر، فيفحص 2026 دائماً مهما مرّرت (نمط درس 76).
   هذا يقرأ الموسم من الوسيط فعلياً.

    python check_2022.py            # يفحص 2022
    python check_2022.py 2023       # أو أي موسم
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

season = 2022
for a in sys.argv[1:]:
    if a.isdigit():
        season = int(a)

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

print()
print("=" * 62)
print(f"  فحص أندية موسم {season}")
print("=" * 62)

total_missing = 0
for code, info in LEAGUES.items():
    n = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE league_code=? AND season=?",
        (code, season)).fetchone()[0]
    print(f"\n  {info['name_ar']}  —  {n} مباراة")
    print("  " + "-" * 56)
    if not n:
        print("     (لم يُسحب بعد)")
        continue

    rows = conn.execute("""
        SELECT x.tid, t.short_name_ar nm, COUNT(*) c
        FROM (
            SELECT home_id tid FROM matches
              WHERE league_code=? AND season=?
            UNION ALL
            SELECT away_id FROM matches
              WHERE league_code=? AND season=?
        ) x
        LEFT JOIN teams t ON t.team_id = x.tid
        GROUP BY x.tid ORDER BY t.short_name_ar
    """, (code, season, code, season)).fetchall()

    missing = [r for r in rows if not (r["nm"] or "").strip()]
    ok = [r for r in rows if (r["nm"] or "").strip()]

    print(f"     أندية: {len(rows)}   بأسماء عربية: {len(ok)}"
          f"   مفقودة: {len(missing)}")

    if ok:
        print("     " + " · ".join(r["nm"] for r in ok))

    if missing:
        total_missing += len(missing)
        print(f"\n     ⚠️ بلا اسم عربي — أضفها لـteams_arabic.csv:")
        for r in missing:
            print(f"        team_id={r['tid']}   ({r['c']} مباراة)")

print()
print("=" * 62)
if total_missing:
    print(f"  ⚠️ {total_missing} نادياً مفقوداً — أضفها ثم:")
    print("      python sync_teams.py")
else:
    print("  ✅ لا نادي مفقود — الموسم جاهز للتوليد")
print("=" * 62)
