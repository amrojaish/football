#!/usr/bin/env python3
"""
فحص: مباريات مضى موعدها وما زالت بلا نتيجة
=============================================
المستخدم لاحظ أن الموقع يعرض مباريات "لم تبدأ" وهي انتهت فعلاً.

`fetch_upcoming.py` يقول 368 قادمة من 380 (أي 12 انتهت عند
المزوّد)، لكن `fetch_matches2.py` يرى 10 فقط ويعتبر الموسم
مكتملاً — تناقض يحتاج تفسيراً.

يعرض لكل دوري:
    - مباريات تاريخها مضى وما زالت home_goals IS NULL
    - آخر مباراة لها نتيجة فعلية (متى آخر تحديث حقيقي؟)
    - حالة status إن كان العمود موجوداً

⚠️ للقراءة فقط.

التشغيل:
    python check_stale.py
"""

import sqlite3
from datetime import datetime

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    names = {}
    try:
        for r in conn.execute(
                "SELECT team_id, short_name_ar FROM teams"):
            names[r["team_id"]] = r["short_name_ar"] or str(r["team_id"])
    except sqlite3.Error:
        pass

    def nm(t):
        return names.get(t, str(t))

    cols = {c[1] for c in conn.execute("PRAGMA table_info(matches)")}
    has_status = "status" in cols

    print()
    print("=" * 62)
    print(f"  الوقت الآن: {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 62)

    for code, label in (("IRQ", "العراقي"), ("SAU", "السعودي"),
                        ("JOR", "الأردني")):
        print()
        print("-" * 62)
        print(f"  الدوري {label}")
        print("-" * 62)

        # مضى موعدها وبلا نتيجة
        q = f"""
            SELECT match_id, date, home_id, away_id
                   {", status" if has_status else ""}
            FROM matches
            WHERE league_code = ? AND season = 2026
              AND home_goals IS NULL
              AND date < datetime('now')
            ORDER BY date DESC
        """
        stale = list(conn.execute(q, (code,)))

        print(f"    مضى موعدها وبلا نتيجة: {len(stale)}")
        for r in stale[:12]:
            st = f"  [{r['status']}]" if has_status else ""
            print(f"      {r['date'][:16]}  "
                  f"{nm(r['home_id'])} × {nm(r['away_id'])}{st}")
        if len(stale) > 12:
            print(f"      ... و{len(stale) - 12} غيرها")

        # آخر مباراة لها نتيجة
        last = conn.execute("""
            SELECT date, home_id, away_id, home_goals, away_goals
            FROM matches
            WHERE league_code = ? AND season = 2026
              AND home_goals IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """, (code,)).fetchone()

        if last:
            print(f"\n    آخر نتيجة مسجَّلة: {last['date'][:16]}")
            print(f"      {nm(last['home_id'])} "
                  f"{last['home_goals']}-{last['away_goals']} "
                  f"{nm(last['away_id'])}")
        else:
            print("\n    ⚠️ لا نتائج مسجَّلة إطلاقاً بهذا الموسم")

        # إجمالي
        tot = conn.execute("""
            SELECT COUNT(match_id) FROM matches
            WHERE league_code = ? AND season = 2026
        """, (code,)).fetchone()[0]
        done = conn.execute("""
            SELECT COUNT(match_id) FROM matches
            WHERE league_code = ? AND season = 2026
              AND home_goals IS NOT NULL
        """, (code,)).fetchone()[0]
        print(f"\n    الإجمالي: {tot}  |  لها نتيجة: {done}  "
              f"|  بلا نتيجة: {tot - done}")

    conn.close()
    print()
    print("=" * 62)
    print("""
  القراءة:
  - "مضى موعدها وبلا نتيجة" > 0  ← السحب متأخر أو فشل
  - "آخر نتيجة" قديمة بأيام      ← الأتمتة متوقفة
  - status = "NS" رغم مرور الموعد ← المزوّد نفسه لم يحدّث
    """)


if __name__ == "__main__":
    main()
