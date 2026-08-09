#!/usr/bin/env python3
"""
تشخيص فرق النقاط — مقارنة صف بصف
===================================
بيطبع:
  1. مباريات الحسين × الفيصلي (المشتبه بها)
  2. تفصيل كامل لكل فريق: P/W/D/L/GF/GA/Pts
  3. أي مباراة حالتها ليست FT

صفر طلبات API — كله من الديتابيس.

التشغيل:
    python check_points.py
    python check_points.py IRQ 2025
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "JOR"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2025


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    print(f"\n{'#' * 60}")
    print(f"#  {LEAGUES[CODE]['name_ar']} — موسم {SEASON}")
    print(f"{'#' * 60}")

    # ---- 1. المواجهات المباشرة بين المتصدرين ----
    print(f"\n{'=' * 60}")
    print("  المواجهات المباشرة (الحسين × الفيصلي)")
    print("=" * 60)

    h2h = conn.execute("""
        SELECT m.match_id, m.date, m.status,
               h.short_name_ar AS home, a.short_name_ar AS away,
               m.home_goals, m.away_goals
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ?
          AND h.short_name_ar IN ('الحسين','الفيصلي')
          AND a.short_name_ar IN ('الحسين','الفيصلي')
        ORDER BY m.date
    """, (CODE, SEASON)).fetchall()

    if not h2h:
        print("  ما لقيت مواجهات — تأكد من الأسماء بالجدول")
    for m in h2h:
        gh, ga = m["home_goals"], m["away_goals"]
        result = "فوز المضيف" if gh > ga else ("تعادل" if gh == ga
                                               else "فوز الضيف")
        print(f"  {m['date']}  {m['home']} {gh} - {ga} {m['away']}"
              f"   [{result}]   id={m['match_id']}  status={m['status']}")

    # ---- 2. تفصيل كامل لكل فريق ----
    print(f"\n{'=' * 60}")
    print("  التفصيل الكامل — قارن كل عمود مع المصدر الرسمي")
    print("=" * 60)

    rows = conn.execute("""
        WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
        )
        SELECT t.short_name_ar AS name,
            COUNT(*) AS P,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS W,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS D,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS L,
            SUM(gf) AS GF, SUM(ga) AS GA,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS Pts
        FROM all_games
        JOIN teams t ON t.team_id = all_games.team
        GROUP BY t.short_name_ar
        ORDER BY Pts DESC, (SUM(gf) - SUM(ga)) DESC
    """, (CODE, SEASON, CODE, SEASON)).fetchall()

    print(f"  {'#':<3} {'الفريق':<16} {'P':>3} {'W':>3} {'D':>3} "
          f"{'L':>3} {'GF':>4} {'GA':>4} {'Pts':>5}   تحقق")
    print("  " + "-" * 58)

    for i, r in enumerate(rows, 1):
        # فحص داخلي: هل W+D+L = P ؟ وهل النقاط = 3W+D ؟
        sum_ok = (r["W"] + r["D"] + r["L"]) == r["P"]
        pts_ok = (r["W"] * 3 + r["D"]) == r["Pts"]
        flag = "" if (sum_ok and pts_ok) else "  <-- خلل"

        print(f"  {i:<3} {r['name']:<16} {r['P']:>3} {r['W']:>3} "
              f"{r['D']:>3} {r['L']:>3} {r['GF']:>4} {r['GA']:>4} "
              f"{r['Pts']:>5}{flag}")

    # ---- 3. مباريات حالتها ليست FT ----
    print(f"\n{'=' * 60}")
    print("  فحص حالات المباريات")
    print("=" * 60)

    statuses = conn.execute("""
        SELECT status, COUNT(*) AS n
        FROM matches WHERE league_code = ? AND season = ?
        GROUP BY status
    """, (CODE, SEASON)).fetchall()

    for s in statuses:
        mark = "" if s["status"] == "FT" else "  <-- ليست منتهية"
        print(f"  {s['status'] or '(فارغ)':<10} {s['n']:>4}{mark}")

    # ---- 4. مباريات مكررة محتملة ----
    print(f"\n{'=' * 60}")
    print("  فحص التكرار (نفس الفريقين بنفس التاريخ)")
    print("=" * 60)

    dups = conn.execute("""
        SELECT date, home_id, away_id, COUNT(*) AS n
        FROM matches
        WHERE league_code = ? AND season = ?
        GROUP BY date, home_id, away_id
        HAVING n > 1
    """, (CODE, SEASON)).fetchall()

    if dups:
        for d in dups:
            print(f"  {d['date']}  {d['home_id']} vs {d['away_id']}"
                  f"  ({d['n']} مرات)  <-- مكرر")
    else:
        print("  ما في تكرار")

    print(f"""
{'=' * 60}
  كيف تقرأ النتيجة:

  - إذا W/D/L مطابق للرسمي والنقاط لأ
    --> خصم نقاط إداري (لا يظهر بالنتائج)

  - إذا مباراة الحسين × الفيصلي مسجّلة فوزاً
    وهي رسمياً تعادل
    --> نتيجة معدّلة إدارياً، والـAPI يحتفظ بالأصلية

  - إذا P مختلف عن الرسمي
    --> مباراة زائدة أو ناقصة

  الفرق المتوقع: الحسين +2 (فوز بدل تعادل)
                  الفيصلي -1 (خسارة بدل تعادل)
  وهذا يطابق مباراة واحدة بينهما.
{'=' * 60}
    """)

    conn.close()


if __name__ == "__main__":
    main()
