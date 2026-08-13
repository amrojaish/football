#!/usr/bin/env python3
"""
إضافة المباريات اليدوية
=========================
بيقرأ manual_matches.csv وبيضيف مباريات **غير موجودة عند المزوّد**
للديتابيس.

ليش موجود:
بعض المباريات تُحسم إدارياً بعد إلغائها أو عدم إقامتها، فالـAPI
ما بيسجّلها إطلاقاً — لا كنتيجة ولا كسجل. النتيجة: الجدول ناقص
مباريات ونقاط، والفرق بتظهر بأعداد مباريات مختلفة.

مثال: العراقي 2025 كان ناقص 7 مباريات كلها محسومة 3-0 إدارياً.

المعرّفات تبدأ من 9000001 لتمييزها عن معرّفات الـAPI.
إعادة التشغيل آمنة — بيتخطى الموجود.

صفر طلبات API.

التشغيل:
    python apply_manual.py --check    <- عرض بس
    python apply_manual.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

MANUAL_FILE = BASE_DIR / "manual_matches.csv"
CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not MANUAL_FILE.exists():
        print(f"ما لقيت {MANUAL_FILE.name}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # خريطة الأسماء → المعرّفات
    ids = {}
    for r in conn.execute("SELECT team_id, short_name_ar FROM teams"):
        nm = (r["short_name_ar"] or "").strip()
        if nm:
            ids[nm] = r["team_id"]

    with open(MANUAL_FILE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)
                if (r.get("match_id") or "").strip()]

    if not rows:
        print("ملف المباريات اليدوية فاضي")
        conn.close()
        return

    print(f"\n{'=' * 62}")
    print(f"  مباريات مسجّلة يدوياً: {len(rows)}")
    print(f"{'=' * 62}")

    added = exists = bad = 0

    for r in rows:
        mid = int(r["match_id"])
        code = (r.get("league_code") or "").strip()
        season = int(r["season"])
        date = (r.get("date") or "").strip()
        hn = (r.get("home_name") or "").strip()
        an = (r.get("away_name") or "").strip()
        hg = int(r["home_goals"])
        ag = int(r["away_goals"])
        note = (r.get("note") or "").strip()

        h_id = ids.get(hn)
        a_id = ids.get(an)

        if h_id is None or a_id is None:
            missing = hn if h_id is None else an
            print(f"\n  ❌ {hn} × {an}")
            print(f"     '{missing}' مش موجود بجدول teams")
            print(f"     (تأكد من short_name_ar بـteams_arabic.csv)")
            bad += 1
            continue

        found = conn.execute(
            "SELECT 1 FROM matches WHERE match_id = ?", (mid,)).fetchone()

        if found:
            print(f"\n  ✅ {hn} {hg}-{ag} {an}   ({date})")
            print(f"     مضافة أصلاً")
            exists += 1
            continue

        print(f"\n  ➕ {hn} {hg}-{ag} {an}   ({date})   id={mid}")
        print(f"     {note}")

        if CHECK_ONLY:
            continue

        conn.execute("""
            INSERT INTO matches
            (match_id, league_code, season, date,
             home_id, away_id, home_goals, away_goals, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'FT')
        """, (mid, code, season, date, h_id, a_id, hg, ag))
        added += 1

    if not CHECK_ONLY:
        conn.commit()

    print(f"\n{'=' * 62}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انضاف شي")
        print(f"  جاهزة للإضافة: {added}  |  موجودة: {exists}"
              f"  |  أسماء خاطئة: {bad}")
    else:
        print(f"  انضاف: {added}  |  كانت موجودة: {exists}"
              f"  |  أسماء خاطئة: {bad}")
    print(f"{'=' * 62}")

    if added and not CHECK_ONLY:
        print("""
  ⚠️ هذه المباريات بلا أحداث بجدول goals — وهذا صحيح،
     فهي لم تُلعب أو أُلغيت وحُسمت إدارياً.

  الخطوة الجاية:
      python apply_corrections.py
      python verify_standings.py IRQ 2025
        """)

    conn.close()


if __name__ == "__main__":
    main()
