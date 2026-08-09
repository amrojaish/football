#!/usr/bin/env python3
"""
تحقيق: ليش عدد الأهداف زايد؟
==============================
النتائج تقول 350 هدف، وجدول goals فيه 352.
هالسكربت بيفحص أنواع الأهداف ويكشف السبب.

صفر طلبات API.

التشغيل:
    python investigate.py
"""

import sqlite3
from config import DB_FILE, LEAGUES


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # 1. أنواع الأهداف الموجودة
    print("\n" + "=" * 58)
    print("  أنواع الأهداف المسجّلة")
    print("=" * 58)

    types = conn.execute("""
        SELECT detail, COUNT(*) AS n
        FROM goals
        GROUP BY detail
        ORDER BY n DESC
    """).fetchall()

    for t in types:
        label = t["detail"] or "(فارغ)"
        print(f"  {label:<28} {t['n']:>4}")

    # 2. المباريات اللي فيها اختلاف
    print("\n" + "=" * 58)
    print("  المباريات اللي فيها اختلاف بالعدد")
    print("=" * 58)

    rows = conn.execute("""
        SELECT
            m.match_id, m.league_code, m.date,
            m.home_goals, m.away_goals,
            m.home_goals + m.away_goals AS real_goals,
            (SELECT COUNT(*) FROM goals g
             WHERE g.match_id = m.match_id) AS recorded,
            h.short_name_ar AS home,
            a.short_name_ar AS away
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE recorded > real_goals
        ORDER BY m.date
    """).fetchall()

    if not rows:
        print("  ما في اختلاف")
        conn.close()
        return

    for r in rows:
        diff = r["recorded"] - r["real_goals"]
        print(f"""
  {LEAGUES.get(r['league_code'], {}).get('name_ar', r['league_code'])}
  {r['home']} {r['home_goals']} - {r['away_goals']} {r['away']}   ({r['date']})
  النتيجة تقول {r['real_goals']} — المسجّل {r['recorded']}  (+{diff})""")

        # تفاصيل أهداف هالماتش
        goals = conn.execute("""
            SELECT g.minute, g.player_en, g.detail,
                   t.short_name_ar AS team
            FROM goals g
            JOIN teams t ON t.team_id = g.team_id
            WHERE g.match_id = ?
            ORDER BY g.minute
        """, (r["match_id"],)).fetchall()

        for g in goals:
            minute = g["minute"] if g["minute"] is not None else "؟"
            detail = g["detail"] or ""
            print(f"      د.{minute}'  {g['player_en']:<22} "
                  f"{g['team']:<14} [{detail}]")

    print("\n" + "=" * 58)
    print("  كيف تقرأ النتيجة")
    print("=" * 58)
    print("""
  دوّر بالتفاصيل أعلاه عن:

  - "Penalty Shootout"  --> ركلات ترجيح، لازم تُستثنى
  - دقيقة كبيرة (120+)  --> وقت إضافي أو ترجيح
  - "Own Goal"          --> هدف عكسي، بينحسب للخصم
  - نفس اللاعب مكرر بنفس الدقيقة --> تكرار بالداتا

  لو طلع السبب واضح، منعدّل الاستعلامات لتستثنيه.
    """)

    conn.close()


if __name__ == "__main__":
    main()
