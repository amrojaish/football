#!/usr/bin/env python3
"""
فحص: هل تصلح إحصائيات اللاعبين للعرض موسماً بموسم؟
======================================================
`player_stats` يحمل 33 حقلاً لكل لاعب لكل مباراة، لكنه
**لا يحمل عمود season** — الربط بالموسم يمر عبر `matches`.

قبل بناء العرض، نحتاج نعرف:
    1. كم لاعباً له إحصائيات في أكثر من موسم؟
    2. ما متوسط عدد المواسم لكل لاعب؟
    3. هل الحقول ممتلئة فعلاً أم معظمها أصفار/NULL؟
    4. عيّنة حقيقية لأشهر لاعب — كيف ستبدو صفحته؟

⚠️ للقراءة فقط.

التشغيل:
    python probe_pstats.py
"""

import sqlite3
from collections import defaultdict

DB = "football.db"

FIELDS = [
    ("shots_total", "تسديدات"),
    ("shots_on", "على المرمى"),
    ("goals", "أهداف"),
    ("assists", "صناعة"),
    ("passes_total", "تمريرات"),
    ("passes_key", "مفتاحية"),
    ("passes_pct", "دقة %"),
    ("tackles", "تدخلات"),
    ("blocks", "بلوكات"),
    ("interceptions", "اعتراضات"),
    ("duels_total", "مواجهات"),
    ("duels_won", "مكسوبة"),
    ("dribbles_try", "مراوغات"),
    ("dribbles_ok", "ناجحة"),
    ("fouls_drawn", "أخطاء له"),
    ("fouls_made", "أخطاء عليه"),
    ("yellow", "صفراء"),
    ("red", "حمراء"),
    ("saves", "تصديات"),
    ("conceded", "استقبل"),
    ("pen_scored", "ركلات سجّلها"),
    ("pen_missed", "أضاعها"),
    ("pen_saved", "صدّها"),
]


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 62)
    print("  تغطية player_stats عبر المواسم")
    print("=" * 62)

    # ── مواسم لكل لاعب ────────────────────────────────
    rows = list(conn.execute("""
        SELECT ps.player_id, ps.player_en,
               COUNT(DISTINCT m.season) AS seasons,
               COUNT(ps.match_id) AS apps
        FROM player_stats ps
        JOIN matches m ON m.match_id = ps.match_id
        WHERE ps.player_id IS NOT NULL AND ps.player_id != 0
          AND ps.minutes IS NOT NULL AND ps.minutes > 0
        GROUP BY ps.player_id
    """))

    if not rows:
        print("  ما في بيانات")
        conn.close()
        return

    dist = defaultdict(int)
    for r in rows:
        dist[r["seasons"]] += 1

    print(f"\n  لاعبون لهم إحصائيات : {len(rows):,}")
    print("\n  توزيع عدد المواسم:")
    for n in sorted(dist):
        pct = dist[n] / len(rows) * 100
        bar = "\u2588" * int(pct / 2)
        print(f"    {n} موسم  {dist[n]:>5}  ({pct:4.1f}%)  {bar}")

    multi = sum(v for k, v in dist.items() if k > 1)
    print(f"\n  \u26a0\ufe0f لهم أكثر من موسم: {multi:,} "
          f"({multi / len(rows) * 100:.0f}%)")

    # ── امتلاء الحقول ─────────────────────────────────
    print()
    print("=" * 62)
    print("  امتلاء الحقول (نسبة السجلات غير الصفرية)")
    print("=" * 62)

    total = conn.execute("""
        SELECT COUNT(*) FROM player_stats
        WHERE minutes IS NOT NULL AND minutes > 0
    """).fetchone()[0]

    for col, label in FIELDS:
        try:
            n = conn.execute(f"""
                SELECT COUNT(*) FROM player_stats
                WHERE minutes > 0 AND {col} IS NOT NULL AND {col} > 0
            """).fetchone()[0]
        except sqlite3.Error:
            print(f"    {label:<14} \u274c العمود غير موجود")
            continue
        pct = n / total * 100 if total else 0
        mark = "\u2705" if pct > 20 else "\u26a0\ufe0f" if pct > 2 else "\u274c"
        print(f"    {label:<14} {n:>6} / {total}  ({pct:5.1f}%)  {mark}")

    # ── عيّنة: أكثر لاعب ظهوراً ───────────────────────
    top = max(rows, key=lambda r: r["apps"])
    print()
    print("=" * 62)
    print(f"  عيّنة — {top['player_en']} (id={top['player_id']})")
    print("=" * 62)

    for s in conn.execute("""
            SELECT m.season, m.league_code,
                   COUNT(ps.match_id) AS apps,
                   SUM(ps.minutes) AS mins,
                   ROUND(AVG(ps.rating), 2) AS rate,
                   SUM(ps.goals) AS goals,
                   SUM(ps.assists) AS assists,
                   SUM(ps.shots_total) AS shots,
                   SUM(ps.passes_total) AS passes,
                   SUM(ps.tackles) AS tackles,
                   SUM(ps.duels_won) AS dwon,
                   SUM(ps.yellow) AS yel
            FROM player_stats ps
            JOIN matches m ON m.match_id = ps.match_id
            WHERE ps.player_id = ? AND ps.minutes > 0
            GROUP BY m.season, m.league_code
            ORDER BY m.season DESC
        """, (top["player_id"],)):
        print(f"\n  {s['league_code']} {s['season']}:  "
              f"{s['apps']} مباراة · {s['mins']} دقيقة · "
              f"تقييم {s['rate']}")
        print(f"    أهداف {s['goals']} · صناعة {s['assists']} · "
              f"تسديدات {s['shots']} · تمريرات {s['passes']}")
        print(f"    تدخلات {s['tackles']} · مواجهات مكسوبة "
              f"{s['dwon']} · صفراء {s['yel']}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
