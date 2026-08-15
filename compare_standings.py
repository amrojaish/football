#!/usr/bin/env python3
"""
مقارنة الجدول: حسابنا مقابل المزوّد
======================================
يقارن الجدول المحسوب من مبارياتنا مع ترتيب المزوّد،
صفاً بصف وعموداً بعمود.

⚠️ **الاختلاف لا يعني أننا مخطئون** — اكتشفنا مراراً أن
   المزوّد هو المخطئ (درس 13). هذا كاشف للفروق، لا حَكَم.

الاختلافات المتوقعة والمشروعة:
  - المباريات المضافة يدوياً (manual_matches) لا يعرفها المزوّد
  - النتائج المصححة (match_corrections) تخالفه عمداً
  - المباريات المستثناة (excluded_matches) موجودة عنده

فأي فرق يجب تفسيره — لا إصلاحه تلقائياً.

صفر طلبات API.

التشغيل:
    python compare_standings.py
    python compare_standings.py IRQ 2025
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES
from tiebreak import sort_table

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else None
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else None

FIELDS = [
    ("played", "لعب"),
    ("wins", "ف"),
    ("draws", "ت"),
    ("losses", "خ"),
    ("goals_for", "له"),
    ("goals_against", "عليه"),
    ("points", "نقاط"),
]


def our_table(conn, code, season):
    rows = conn.execute("""
        WITH g AS (
            SELECT home_id AS team, home_goals gf, away_goals ga
            FROM matches WHERE league_code=? AND season=?
              AND home_goals IS NOT NULL
            UNION ALL
            SELECT away_id, away_goals, home_goals
            FROM matches WHERE league_code=? AND season=?
              AND home_goals IS NOT NULL
        )
        SELECT t.team_id, t.short_name_ar AS name,
            COUNT(*) AS played,
            SUM(CASE WHEN gf>ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf=ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf<ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) AS goals_for, SUM(ga) AS goals_against,
            SUM(gf)-SUM(ga) AS diff, SUM(gf) AS scored,
            SUM(CASE WHEN gf>ga THEN 3 WHEN gf=ga THEN 1 ELSE 0 END)
                AS points
        FROM g JOIN teams t ON t.team_id = g.team
        GROUP BY t.team_id ORDER BY points DESC
    """, (code, season, code, season)).fetchall()
    return sort_table(conn, code, season, rows)


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM api_standings LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول api_standings غير موجود — شغّل fetch_standings.py أول")
        conn.close()
        return

    combos = conn.execute("""
        SELECT DISTINCT league_code AS lg, season AS s
        FROM api_standings ORDER BY season DESC, league_code
    """).fetchall()

    if CODE:
        combos = [c for c in combos if c["lg"] == CODE]
    if SEASON is not None:
        combos = [c for c in combos if c["s"] == SEASON]

    if not combos:
        print("ما في ترتيب مخزّن — شغّل fetch_standings.py")
        conn.close()
        return

    print(f"\n{'#' * 66}")
    print("#  مقارنة: حسابنا مقابل ترتيب المزوّد")
    print(f"{'#' * 66}")

    all_clean = True

    for c in combos:
        lg, s = c["lg"], c["s"]
        name = LEAGUES.get(lg, {}).get("name_ar", lg)

        ours = {r["team_id"]: r for r in our_table(conn, lg, s)}
        order = [r["team_id"] for r in our_table(conn, lg, s)]

        theirs = {}
        for r in conn.execute("""
            SELECT * FROM api_standings
            WHERE league_code = ? AND season = ?
        """, (lg, s)):
            theirs[r["team_id"]] = r

        names = {}
        for r in conn.execute("SELECT team_id, short_name_ar FROM teams"):
            names[r["team_id"]] = r["short_name_ar"] or str(r["team_id"])

        print(f"\n{'=' * 66}")
        print(f"  {name}  —  موسم {s}-{s+1}")
        print(f"{'=' * 66}")

        only_ours = set(ours) - set(theirs)
        only_theirs = set(theirs) - set(ours)

        if only_ours:
            print(f"\n  ⚠️ عندنا وليس عندهم: "
                  f"{', '.join(names.get(t, str(t)) for t in only_ours)}")
            all_clean = False
        if only_theirs:
            print(f"\n  ⚠️ عندهم وليس عندنا: "
                  f"{', '.join(names.get(t, str(t)) for t in only_theirs)}")
            all_clean = False

        diffs = []
        for tid in order:
            if tid not in theirs:
                continue
            o, t = ours[tid], theirs[tid]
            bad = []
            for key, label in FIELDS:
                if o[key] != t[key]:
                    bad.append((label, o[key], t[key]))
            if bad:
                diffs.append((names.get(tid, str(tid)), bad))

        if not diffs and not only_ours and not only_theirs:
            print(f"\n  ✅ مطابق تماماً — {len(ours)} فريقاً")
            continue

        all_clean = False

        if diffs:
            print(f"\n  {len(diffs)} فريقاً فيه فرق:\n")
            for team, bad in diffs:
                parts = "   ".join(
                    f"{lbl}: {a} ≠ {b}" for lbl, a, b in bad)
                print(f"      {team:<18} {parts}")

        # فحص الترتيب نفسه
        our_rank = {tid: i for i, tid in enumerate(order, 1)}
        rank_diff = [
            (names.get(tid, str(tid)), our_rank[tid], theirs[tid]["rank"])
            for tid in order
            if tid in theirs and our_rank[tid] != theirs[tid]["rank"]
        ]
        if rank_diff:
            print(f"\n  ترتيب مختلف ({len(rank_diff)}):")
            for team, a, b in rank_diff[:10]:
                print(f"      {team:<18} عندنا {a}  ≠  عندهم {b}")

    conn.close()

    print(f"\n{'#' * 66}")
    if all_clean:
        print("#  ✅ كل الجداول مطابقة لترتيب المزوّد")
    else:
        print("""#  ⚠️ يوجد فروق

  تذكّر: الفرق **لا يعني أننا مخطئون**. المباريات المضافة
  يدوياً والنتائج المصححة تخالف المزوّد عمداً — وهذا
  جوهر المشروع.

  راجع كل فرق مقابل match_corrections.csv و manual_matches.csv
  قبل افتراض وجود خطأ.""")
    print(f"{'#' * 66}\n")


if __name__ == "__main__":
    main()
