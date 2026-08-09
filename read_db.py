#!/usr/bin/env python3
"""
قراءة الديتابيس — صفر طلبات API
==================================
كل شي هون بينقرأ من football.db المحلية.
شغّله ألف مرة، حصتك ما بتنقص ولا واحد.

التشغيل:
    python read_db.py
"""

import sqlite3
from config import DB_FILE


def connect():
    if not DB_FILE.exists():
        print("ما لقيت football.db — شغّل build_db.py أول")
        return None
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row   # يخلينا نوصل للأعمدة بالاسم
    return conn


def show_results(conn, limit=8):
    """آخر النتائج بالأسماء العربية"""
    print("\n" + "=" * 50)
    print("  آخر النتائج")
    print("=" * 50)

    # لاحظ: بنربط جدول المباريات بجدول الأندية مرتين
    # مرة للمضيف ومرة للضيف — هاد اسمه JOIN
    rows = conn.execute("""
        SELECT
            m.date,
            h.short_name_ar AS home,
            a.short_name_ar AS away,
            m.home_goals, m.away_goals
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        ORDER BY m.date DESC
        LIMIT ?
    """, (limit,)).fetchall()

    for r in rows:
        print(f"  {r['date']}   {r['home']} {r['home_goals']} - "
              f"{r['away_goals']} {r['away']}")


def show_scorers(conn, limit=10):
    """الهدافين — محسوبين من جدول الأهداف"""
    print("\n" + "=" * 50)
    print("  الهدافون")
    print("=" * 50)

    rows = conn.execute("""
        SELECT
            g.player_en,
            t.short_name_ar AS team,
            COUNT(*) AS goals
        FROM goals g
        JOIN teams t ON t.team_id = g.team_id
        WHERE g.player_en != ''
        GROUP BY g.player_en, t.short_name_ar
        ORDER BY goals DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        print("  ما في أهداف مخزنة")
        return

    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['player_en']:<22} {r['team']:<12} {r['goals']} هدف")


def show_table(conn):
    """جدول الترتيب — محسوب من النتائج، مش مسحوب من الـAPI"""
    print("\n" + "=" * 50)
    print("  جدول الترتيب (من المباريات المخزنة)")
    print("=" * 50)

    # بنجمع نتائج كل فريق كمضيف وكضيف
    rows = conn.execute("""
        WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches
        )
        SELECT
            t.short_name_ar AS name,
            COUNT(*) AS played,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) AS scored,
            SUM(ga) AS conceded,
            SUM(gf) - SUM(ga) AS diff,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS points
        FROM all_games
        JOIN teams t ON t.team_id = all_games.team
        GROUP BY t.short_name_ar
        ORDER BY points DESC, diff DESC
    """).fetchall()

    print(f"  {'#':<3} {'الفريق':<14} {'لعب':>4} {'ف':>3} "
          f"{'ت':>3} {'خ':>3} {'له':>4} {'عليه':>5} {'نقاط':>5}")
    print("  " + "-" * 52)

    for i, r in enumerate(rows, 1):
        print(f"  {i:<3} {r['name']:<14} {r['played']:>4} {r['wins']:>3} "
              f"{r['draws']:>3} {r['losses']:>3} {r['scored']:>4} "
              f"{r['conceded']:>5} {r['points']:>5}")


def show_stats(conn):
    """إحصائيات سريعة"""
    m = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    g = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    t = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]

    print("\n" + "=" * 50)
    print(f"  بالديتابيس: {t} نادي | {m} ماتش | {g} هدف")
    if m:
        print(f"  معدل الأهداف بالماتش: {g / m:.2f}")
    print("=" * 50)


def main():
    conn = connect()
    if conn is None:
        return

    show_stats(conn)
    show_results(conn)
    show_table(conn)
    show_scorers(conn)

    print("""
  ملاحظة مهمة:
  كل اللي فوق انحسب من ملف على جهازك.
  صفر طلبات API — شغّله قد ما بدك.

  جدول الترتيب مش مسحوب جاهز — الكود حسبه
  من النتائج (فوز=3، تعادل=1). هاد شغلك إنت.
    """)

    conn.close()


if __name__ == "__main__":
    main()
