#!/usr/bin/env python3
"""
تنظيف سجلات الأحداث الخاطئة
==============================
fetch_events.py كان يسجّل المباريات **القادمة** كـtype='none'
لأنه لم يكن يفلتر home_goals IS NOT NULL.

النتيجة: تلك المباريات ستُتخطّى للأبد حتى بعد أن تُلعب.

هذا السكربت يحذف تلك السجلات فقط — لا يلمس الأحداث الحقيقية
ولا سجلات 'none' للمباريات المنتهية (وهي صحيحة: مباراة لُعبت
فعلاً وبلا بطاقات).

التشغيل:
    python clean_ghost_events.py --check
    python clean_ghost_events.py
"""

import sqlite3
import sys
from config import DB_FILE

CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM events LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول events غير موجود")
        return

    rows = conn.execute("""
        SELECT e.match_id, m.league_code lg, m.season s, m.date
        FROM events e
        JOIN matches m ON m.match_id = e.match_id
        WHERE e.type = 'none' AND m.home_goals IS NULL
    """).fetchall()

    print(f"\n{'=' * 58}")
    print(f"  سجلات وهمية (مباريات قادمة): {len(rows)}")
    print(f"{'=' * 58}")

    if not rows:
        print("\n  ما في شي للحذف ✅\n")
        conn.close()
        return

    by = {}
    for r in rows:
        k = (r["lg"], r["s"])
        by[k] = by.get(k, 0) + 1
    for (lg, s), n in sorted(by.items()):
        print(f"      {lg}  موسم {s}   {n}")

    if CHECK_ONLY:
        print(f"\n  [وضع الفحص] — ما انحذف شي\n")
        conn.close()
        return

    n = conn.execute("""
        DELETE FROM events
        WHERE type = 'none' AND match_id IN (
            SELECT match_id FROM matches WHERE home_goals IS NULL
        )
    """).rowcount
    conn.commit()

    left = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    print(f"\n{'=' * 58}")
    print(f"  انحذف: {n} سجل   |   باقي بالجدول: {left}")
    print(f"{'=' * 58}")
    print("""
  ⚠️ لا تعد تشغيل fetch_events.py قبل إصلاحه — سيعيد
     تسجيل المباريات القادمة من جديد.
    """)

    conn.close()


if __name__ == "__main__":
    main()
