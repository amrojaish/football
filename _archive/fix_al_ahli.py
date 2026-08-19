#!/usr/bin/env python3
"""
تصحيح: "Al Ahli" في عمود اللاعب — كان بنالتي وهدفاً عكسياً
=============================================================
`probe_al_ahli.py` كشف سببين واضحين، وتحقّق المستخدم منهما من
مصدر خارجي موثوق:

    goal_id=112   match_id=1265738  2024-08-08
        الأهلي 3-1 مغير السرحان، د.90 Penalty
        → أحمد الإدريسي (الهدف الثالث، د.90+2)

    goal_id=4429  match_id=1127394  2023-09-16
        مغير السرحان 1-0 الأهلي، د.81 Own Goal
        → زيد أبو ريالة (مدافع مغير السرحان، هدف بمرماه)

المزوّد نفسه أرجع اسم النادي بدل اللاعب لهذين الحدثين تحديداً
— نمط معروف عند بعض المزوّدين مع البنالتي والأهداف العكسية.
النتيجة الإجمالية للمباراتين صحيحة دائماً؛ الخطأ في عمود
player_en فقط.

⚠️ نسخة احتياطية قبل الكتابة.

التشغيل:
    python fix_al_ahli.py --check   <- عرض فقط
    python fix_al_ahli.py           <- تنفيذ
"""

import shutil
import sqlite3
import sys

DB = "football.db"
CHECK = "--check" in sys.argv

FIXES = {
    112: ("A. Al Idrisi", "أحمد الإدريسي"),
    4429: ("Z. Abu Rialah", "زيد أبو ريالة"),
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 58)
    print("  تصحيح اسمي اللاعبين بدل اسم النادي")
    print("=" * 58)

    for gid, (en, ar) in FIXES.items():
        row = conn.execute("""
            SELECT id, player_en, match_id, minute, detail
            FROM goals WHERE id = ?
        """, (gid,)).fetchone()

        if not row:
            print(f"\n  ❌ goal_id={gid} غير موجود — تأكد من رقم السجل")
            continue

        print(f"\n  goal_id={gid}  match_id={row['match_id']}  "
              f"د.{row['minute']}  {row['detail']}")
        print(f"    قبل : player_en={row['player_en']!r}")
        print(f"    بعد : player_en={en!r}  player_ar={ar!r}")

    print()
    print("=" * 58)

    if CHECK:
        print("  [وضع الفحص] — ما انكتب شي")
        print("=" * 58 + "\n")
        conn.close()
        return

    conn.close()
    shutil.copy(DB, "football_before_alahli_fix.db")
    print("  نسخة احتياطية: football_before_alahli_fix.db")

    conn = sqlite3.connect(DB)
    changed = 0
    for gid, (en, ar) in FIXES.items():
        cur = conn.execute("""
            UPDATE goals SET player_en = ?, player_ar = ?
            WHERE id = ?
        """, (en, ar, gid))
        changed += cur.rowcount
    conn.commit()
    conn.close()

    print(f"  سجلات معدّلة: {changed}")
    print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
      python make_players.py
      python make_search.py
      python make_sitemap.py
    """)


if __name__ == "__main__":
    main()
