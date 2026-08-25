#!/usr/bin/env python3
"""
فحص صفحات الأندية الجديدة (موسم 2022)
=========================================
يتحقق من: هل الأندية موجودة بالديتابيس؟ هل صفحاتها موجودة على
القرص (عربي وإنجليزي)؟ ويحسب عمر آخر تعديل لـclubs.html.

⚠️ سياق: الديتابيس اختفى وعاد بـgit checkout يوم 24 أغسطس
   (درس 83). إن كانت صفحات الأندية الجديدة مفقودة، فالسبب
   الأرجح: التوليد الأخير الناجح سبق استرجاع 2022، أو
   make_clubs.py لم يُعَد تشغيله بعد الاسترجاع.
"""
import sqlite3, os, sys
from pathlib import Path
from config import DB_FILE, BASE_DIR

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row

NEW = ["15543", "17792", "2926", "2950"]

print("\n=== وجود الأندية بالديتابيس ===")
for tid in NEW:
    r = conn.execute("SELECT short_name_ar, name_en FROM teams WHERE team_id=?",
                     (tid,)).fetchone()
    print(f"  {tid}: {dict(r) if r else '❌ غير موجود بـteams'}")

print("\n=== وجود صفحاتها على القرص ===")
for tid in NEW:
    ar = BASE_DIR / "clubs" / f"{tid}.html"
    en = BASE_DIR / "en" / "clubs" / f"{tid}.html"
    print(f"  {tid}: ar={'✅' if ar.exists() else '❌'}  en={'✅' if en.exists() else '❌'}")

print("\n=== كم صفحة بمجلد clubs/ الآن، وآخر تعديل ===")
p = BASE_DIR / "clubs"
files = list(p.glob("*.html"))
print(f"  عدد الملفات: {len(files)}")
if files:
    newest = max(files, key=lambda f: f.stat().st_mtime)
    import datetime
    print(f"  آخر تعديل: {newest.name} — "
          f"{datetime.datetime.fromtimestamp(newest.stat().st_mtime)}")

print("\n=== أندية 2022 كلها — موجودة كصفحة أم لا؟ ===")
rows = conn.execute("""
    SELECT DISTINCT x.tid, t.short_name_ar nm FROM (
        SELECT home_id tid FROM matches WHERE league_code='IRQ' AND season=2022
        UNION SELECT away_id FROM matches WHERE league_code='IRQ' AND season=2022
    ) x LEFT JOIN teams t ON t.team_id=x.tid ORDER BY t.short_name_ar
""").fetchall()
for r in rows:
    ar = (BASE_DIR / "clubs" / f"{r['tid']}.html").exists()
    print(f"  {r['nm'] or r['tid']:14}  {'✅' if ar else '❌ مفقودة'}")
