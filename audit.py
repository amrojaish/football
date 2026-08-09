#!/usr/bin/env python3
"""
فحص جودة الداتا
=================
بيقارن النتيجة النهائية (من جدول matches) مع عدد الأهداف
المسجّلة تفصيلياً (من جدول goals) — ويكشف الفجوة.

صفر طلبات API.

التشغيل:
    python audit.py           <- كل الدوريات
    python audit.py JOR       <- دوري محدد
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else None


def audit_league(conn, code):
    rows = conn.execute("""
        SELECT
            m.match_id,
            m.date,
            m.home_goals + m.away_goals AS real_goals,
            (SELECT COUNT(*) FROM goals g
             WHERE g.match_id = m.match_id) AS recorded,
            h.short_name_ar AS home,
            a.short_name_ar AS away,
            m.home_goals, m.away_goals
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ?
        ORDER BY m.date
    """, (code,)).fetchall()

    if not rows:
        return None

    complete = partial = missing = goalless = 0
    total_real = total_recorded = 0
    problem_matches = []

    for r in rows:
        real = r["real_goals"]
        rec = r["recorded"]
        total_real += real
        total_recorded += rec

        if real == 0:
            goalless += 1           # 0-0 طبيعي إنه بدون أحداث
        elif rec == 0:
            missing += 1
            problem_matches.append((r, "لا أحداث"))
        elif rec < real:
            partial += 1
            problem_matches.append((r, f"{rec} من {real}"))
        else:
            complete += 1

    with_goals = len(rows) - goalless
    coverage = complete / with_goals * 100 if with_goals else 0

    return {
        "name": LEAGUES[code]["name_ar"],
        "total": len(rows),
        "goalless": goalless,
        "complete": complete,
        "partial": partial,
        "missing": missing,
        "coverage": coverage,
        "total_real": total_real,
        "total_recorded": total_recorded,
        "problems": problem_matches,
    }


def print_report(r):
    print("\n" + "=" * 58)
    print(f"  {r['name']}")
    print("=" * 58)

    print(f"""
  إجمالي المباريات:        {r['total']}
  مباريات بدون أهداف (0-0): {r['goalless']}
  ---------------------------------------------
  أحداث كاملة:             {r['complete']}
  أحداث ناقصة:             {r['partial']}
  بدون أحداث نهائياً:       {r['missing']}
  ---------------------------------------------
  أهداف حقيقية (من النتائج):  {r['total_real']}
  أهداف مسجّلة تفصيلياً:       {r['total_recorded']}
  الفجوة:                     {r['total_real'] - r['total_recorded']}""")

    # شريط التغطية
    filled = int(r["coverage"] / 100 * 30)
    bar = "█" * filled + "░" * (30 - filled)
    print(f"\n  التغطية: [{bar}] {r['coverage']:.0f}%")

    # الحكم
    if r["coverage"] >= 90:
        verdict = "ممتازة — الميزة قابلة للتنفيذ"
    elif r["coverage"] >= 60:
        verdict = "متوسطة — تحتاج تنبيه للمستخدم"
    elif r["coverage"] >= 25:
        verdict = "ضعيفة — قائمة الهدافين مضللة"
    else:
        verdict = "سيئة — لا تعرض هدافين من هذه الداتا"

    print(f"  الحكم: {verdict}")

    # عينة من المشاكل
    if r["problems"]:
        print(f"\n  عينة من المباريات الناقصة (أول 5):")
        for row, why in r["problems"][:5]:
            print(f"    {row['date']}  {row['home']} "
                  f"{row['home_goals']}-{row['away_goals']} "
                  f"{row['away']}   [{why}]")


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    codes = [CODE] if CODE else list(LEAGUES.keys())
    results = []

    print("\n" + "#" * 58)
    print("#  فحص جودة الداتا — تغطية أحداث المباريات")
    print("#" * 58)

    for code in codes:
        if code not in LEAGUES:
            continue
        r = audit_league(conn, code)
        if r:
            print_report(r)
            results.append(r)

    conn.close()

    if len(results) > 1:
        print("\n" + "=" * 58)
        print("  المقارنة")
        print("=" * 58)
        for r in results:
            print(f"  {r['name']:<18} {r['coverage']:>5.0f}%   "
                  f"({r['complete']}/{r['total'] - r['goalless']} ماتش)")

    print("""
==========================================================
  ماذا يعني هذا عملياً:

  - جدول الترتيب، أقوى هجوم/دفاع، السلاسل
    --> دقيقة 100% (محسوبة من النتائج النهائية)

  - قائمة الهدافين، توزيع الأهداف
    --> تعتمد على الأحداث، وناقصة بقدر الفجوة أعلاه

  القرار: إما تخفي الهدافين، أو تعرضهم مع تنبيه واضح.
  عرض داتا ناقصة كأنها كاملة يهدم الثقة بالتطبيق كله.
==========================================================
    """)


if __name__ == "__main__":
    main()
