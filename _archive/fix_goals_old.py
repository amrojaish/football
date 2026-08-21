#!/usr/bin/env python3
"""
تنظيف سجلات الأهداف الخاطئة
=============================
بيشيل من جدول goals:
  1. ركلات الجزاء الضائعة (Missed Penalty) — مش أهداف
  2. الأهداف بدون اسم لاعب بمباريات انتهت 0-0 — أهداف ملغاة

وبيعمل نسخة احتياطية من الديتابيس قبل أي حذف.

التشغيل:
    python fix_goals.py --check    <- عرض بس
    python fix_goals.py            <- تنفيذ
"""

import sqlite3
import shutil
import sys
from config import DB_FILE

CHECK_ONLY = "--check" in sys.argv


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 58)
    print("  السجلات المرشحة للحذف")
    print("=" * 58)

    # 1. ركلات الجزاء الضائعة
    missed = conn.execute("""
        SELECT COUNT(*) FROM goals WHERE detail = 'Missed Penalty'
    """).fetchone()[0]

    print(f"\n  ركلات جزاء ضائعة: {missed}")

    if missed:
        rows = conn.execute("""
            SELECT g.player_en, t.short_name_ar AS team, g.minute
            FROM goals g
            JOIN teams t ON t.team_id = g.team_id
            WHERE g.detail = 'Missed Penalty'
        """).fetchall()
        for r in rows:
            print(f"      د.{r['minute']}'  {r['player_en']} ({r['team']})")

    # 2. أهداف بمباريات 0-0 (ملغاة على الأغلب)
    ghost = conn.execute("""
        SELECT g.id, g.minute, g.player_en, t.short_name_ar AS team,
               m.date, h.short_name_ar AS home, a.short_name_ar AS away
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t ON t.team_id = g.team_id
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals + m.away_goals = 0
    """).fetchall()

    print(f"\n  أهداف بمباريات انتهت 0-0: {len(ghost)}")
    for r in ghost:
        name = r["player_en"] or "(بدون اسم)"
        print(f"      {r['home']} 0-0 {r['away']} ({r['date']}) "
              f"— د.{r['minute']}' {name}")

    total = missed + len(ghost)

    if total == 0:
        print("\n  ما في شي للحذف — الداتا نظيفة\n")
        conn.close()
        return

    if CHECK_ONLY:
        print(f"\n  [وضع الفحص] — {total} سجل مرشح، ما انحذف شي")
        print("  شغّل بدون --check للتنفيذ\n")
        conn.close()
        return

    # نسخة احتياطية قبل الحذف
    backup = DB_FILE.parent / "football_backup.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    conn.execute("DELETE FROM goals WHERE detail = 'Missed Penalty'")

    conn.execute("""
        DELETE FROM goals
        WHERE match_id IN (
            SELECT match_id FROM matches
            WHERE home_goals + away_goals = 0
        )
    """)

    conn.commit()

    # التحقق بعد الحذف
    remaining = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]

    check = conn.execute("""
        SELECT
            (SELECT SUM(home_goals + away_goals) FROM matches) AS real_goals,
            (SELECT COUNT(*) FROM goals) AS recorded
    """).fetchone()

    print(f"""
{'=' * 58}
  انحذف: {total} سجل
  باقي بجدول goals: {remaining}
{'=' * 58}

  التحقق النهائي:
    أهداف من النتائج:  {check['real_goals']}
    أهداف مسجّلة:      {check['recorded']}
    الفرق:             {check['real_goals'] - check['recorded']}

  (الفرق الموجب طبيعي — مباريات لسا بلا أحداث.
   الفرق السالب كان هو المشكلة، ولازم يصير صفر أو موجب.)
    """)

    conn.close()

    print("""
  الخطوات الجاية:
      python audit.py           <- تأكد إنو الفجوة ما عادت سالبة
      python make_site2.py      <- أعد توليد الصفحة
      python stats.py           <- إحصائيات مصححة
    """)


if __name__ == "__main__":
    main()
