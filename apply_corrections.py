#!/usr/bin/env python3
"""
تطبيق تصحيحات النتائج اليدوية
================================
بيقرأ match_corrections.csv وبيصحّح النتائج بالديتابيس.

ليش موجود:
الـAPI أحياناً بيحتفظ بنتيجة خاطئة (هدف ملغي، نتيجة محسومة إدارياً).
أي سحب جديد بيرجّع الغلط، فهالسكربت بينطبّق بعد كل سحب.

صفر طلبات API.

التشغيل:
    python apply_corrections.py --check    <- عرض بس
    python apply_corrections.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

CORRECTIONS_FILE = BASE_DIR / "match_corrections.csv"
CHECK_ONLY = "--check" in sys.argv


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not CORRECTIONS_FILE.exists():
        print(f"ما لقيت {CORRECTIONS_FILE.name}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    with open(CORRECTIONS_FILE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)
                if (r.get("match_id") or "").strip()]

    if not rows:
        print("ملف التصحيحات فاضي")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"  تصحيحات مسجّلة: {len(rows)}")
    print(f"{'=' * 60}")

    applied = already = notfound = 0

    for r in rows:
        mid = int(r["match_id"])
        new_h = int(r["correct_home"])
        new_a = int(r["correct_away"])
        note = (r.get("note") or "").strip()

        m = conn.execute("""
            SELECT m.home_goals, m.away_goals,
                   h.short_name_ar AS home, a.short_name_ar AS away, m.date
            FROM matches m
            LEFT JOIN teams h ON h.team_id = m.home_id
            LEFT JOIN teams a ON a.team_id = m.away_id
            WHERE m.match_id = ?
        """, (mid,)).fetchone()

        if m is None:
            print(f"\n  {mid} — مش موجودة بالديتابيس")
            notfound += 1
            continue

        cur_h, cur_a = m["home_goals"], m["away_goals"]
        label = f"{m['home']} × {m['away']} ({m['date']})"

        if (cur_h, cur_a) == (new_h, new_a):
            print(f"\n  ✅ {label}")
            print(f"     مصححة أصلاً: {new_h}-{new_a}")
            already += 1
            continue

        print(f"\n  🔧 {label}")
        print(f"     الـAPI:  {cur_h}-{cur_a}")
        print(f"     الصحيح: {new_h}-{new_a}")
        print(f"     السبب:  {note}")

        if CHECK_ONLY:
            continue

        conn.execute(
            "UPDATE matches SET home_goals = ?, away_goals = ? WHERE match_id = ?",
            (new_h, new_a, mid))

        # لو النتيجة الصحيحة 0-0، الأهداف المسجّلة كلها ملغاة
        if new_h == 0 and new_a == 0:
            n = conn.execute(
                "SELECT COUNT(*) FROM goals WHERE match_id = ?",
                (mid,)).fetchone()[0]
            if n:
                conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))
                print(f"     انحذف {n} هدف ملغي من جدول goals")

        applied += 1

    if not CHECK_ONLY:
        conn.commit()

    print(f"\n{'=' * 60}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انعدّل شي")
        print(f"  محتاجة تصحيح: {applied}  |  مصححة أصلاً: {already}"
              f"  |  مفقودة: {notfound}")
    else:
        print(f"  انصحح: {applied}  |  كانت مصححة: {already}"
              f"  |  مفقودة: {notfound}")
    print(f"{'=' * 60}")

    if applied and not CHECK_ONLY:
        print("\n  الخطوة الجاية:  python make_site3.py\n")

    conn.close()


if __name__ == "__main__":
    main()
