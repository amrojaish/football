#!/usr/bin/env python3
"""
تحقيق: "Al Ahli" ظاهر كلاعب في جدول الأهداف
==============================================
players_ar.csv يحمل سطراً:
    priority=B, league=JOR, team_ar=الأهلي, player_en="Al Ahli"

"Al Ahli" اسم نادٍ لا لاعب. هذا يعني أن جدول `goals` نفسه
يحمل سجلاً بعمود player_en = اسم الفريق بدل اسم لاعب حقيقي —
[مرجّح] المزوّد أرجع هدفاً بلا اسم لاعب معروف والسكربت الذي
استوعبه وضع اسم الفريق كبديل بدل تركه فارغاً أو NULL.

يعرض: المباراة/المباريات بالضبط، تاريخها، ودقيقة الهدف —
لنعرف إن كان هذا هدفاً حقيقياً بلا مسجّل معروف (نتركه) أم خطأ
استيراد فعلياً قابلاً للتصحيح.

⚠️ للقراءة فقط. لا يعدّل شيئاً.

التشغيل:
    python probe_al_ahli.py
"""

import sqlite3

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 62)
    print('  البحث عن "Al Ahli" كاسم لاعب في جدول goals')
    print("=" * 62)

    rows = list(conn.execute("""
        SELECT g.id, g.match_id, g.team_id, g.minute, g.detail,
               g.player_en, g.player_ar,
               m.date, m.league_code, m.season,
               m.home_id, m.away_id, m.home_goals, m.away_goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en = 'Al Ahli'
    """))

    if not rows:
        print("\n  ما لقيت أي سجل — قد يكون اسماً مشابهاً لا مطابقاً حرفياً")
        rows2 = list(conn.execute("""
            SELECT g.player_en, COUNT(*) AS n FROM goals g
            WHERE g.player_en LIKE '%Ahli%'
            GROUP BY g.player_en
        """))
        if rows2:
            print("\n  أقرب تطابقات:")
            for r in rows2:
                print(f"    {r['player_en']!r}  ({r['n']})")
        conn.close()
        return

    names = {t["team_id"]: t["short_name_ar"]
             for t in conn.execute("SELECT team_id, short_name_ar FROM teams")}

    print(f"\n  عدد السجلات: {len(rows)}\n")

    for r in rows:
        print(f"  match_id={r['match_id']}  goal_id={r['id']}")
        print(f"    التاريخ : {r['date'][:10]}   "
              f"{r['league_code']} موسم {r['season']}")
        print(f"    الفريقان: {names.get(r['home_id'], r['home_id'])} "
              f"{r['home_goals']}-{r['away_goals']} "
              f"{names.get(r['away_id'], r['away_id'])}")
        print(f"    فريق الهدف: {names.get(r['team_id'], r['team_id'])}"
              f"   دقيقة: {r['minute']}   نوع: {r['detail']}")
        print(f"    player_en={r['player_en']!r}  "
              f"player_ar={r['player_ar']!r}")
        print()

    print("-" * 62)
    print("  بقية أهداف نفس المباراة/المباريات (للمقارنة)")
    print("-" * 62)
    for r in rows:
        others = list(conn.execute("""
            SELECT minute, player_en, team_id FROM goals
            WHERE match_id = ? AND id != ?
            ORDER BY minute
        """, (r["match_id"], r["id"])))
        print(f"\n  مباراة {r['match_id']}:")
        if not others:
            print("    (هذا الهدف الوحيد بالمباراة)")
        for o in others:
            print(f"    د.{o['minute']}  {o['player_en']!r}  "
                  f"({names.get(o['team_id'], o['team_id'])})")

    conn.close()
    print()
    print("=" * 62)
    print("""
  القراءة:
  - لو بقية أهداف المباراة بأسماء لاعبين طبيعية، فهذا الهدف
    تحديداً هو الخطأ — المزوّد لم يُرجع لاعباً وشيء ما عوّضه
    باسم الفريق.
  - راجع match_corrections.csv إن كانت هذه مباراة مُصحَّحة يدوياً
    — قد يكون المصدر هناك لا من المزوّد.
    """)


if __name__ == "__main__":
    main()
