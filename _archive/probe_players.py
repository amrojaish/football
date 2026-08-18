#!/usr/bin/env python3
"""
فحص قبل بناء صفحات اللاعبين
==============================
قبل توليد آلاف الصفحات، لازم نعرف:

    1. كم لاعباً سيحصل على صفحة؟
    2. كم منهم بهدف واحد فقط؟ (صفحة شبه فارغة)
    3. كم لاعباً سعودياً له تقييمات ودقائق؟
    4. كم لاعباً لعب لأكثر من نادٍ؟ (يحتاج تجميع)

⚠️ صفحة بهدف واحد وبلا تفاصيل = صفحة رقيقة، وGoogle يصنّفها
   "Crawled – currently not indexed" وقد تُضعف تقييم الموقع كله.
   لذلك قد نضع حداً أدنى.

⚠️ للقراءة فقط.

التشغيل:
    python probe_players.py
"""

import sqlite3
from collections import defaultdict

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── الأهداف لكل لاعب ──────────────────────────────
    goals = defaultdict(int)
    clubs = defaultdict(set)
    leagues = defaultdict(set)
    seasons = defaultdict(set)

    q = """
        SELECT g.player_en, g.team_id, m.league_code, m.season
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en IS NOT NULL AND g.player_en != ''
    """
    for r in conn.execute(q):
        p = r["player_en"]
        goals[p] += 1
        clubs[p].add(r["team_id"])
        leagues[p].add(r["league_code"])
        seasons[p].add(r["season"])

    total = len(goals)

    print()
    print("=" * 62)
    print(f"  لاعبون سجّلوا هدفاً واحداً على الأقل: {total:,}")
    print("=" * 62)

    # ── التوزيع حسب عدد الأهداف ───────────────────────
    buckets = {"1 هدف": 0, "2": 0, "3-4": 0, "5-9": 0,
               "10-19": 0, "20+": 0}
    for p, n in goals.items():
        if n == 1:
            buckets["1 هدف"] += 1
        elif n == 2:
            buckets["2"] += 1
        elif n <= 4:
            buckets["3-4"] += 1
        elif n <= 9:
            buckets["5-9"] += 1
        elif n <= 19:
            buckets["10-19"] += 1
        else:
            buckets["20+"] += 1

    print("\n  التوزيع حسب عدد الأهداف:")
    for k, v in buckets.items():
        pct = v / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"    {k:<8} {v:>5}  ({pct:4.1f}%)  {bar}")

    one = buckets["1 هدف"]
    print(f"\n  ⚠️ {one:,} لاعباً بهدف واحد "
          f"({one / total * 100:.0f}%) — صفحات رقيقة")

    # ── التغطية التفصيلية (السعودي) ───────────────────
    print()
    print("-" * 62)
    print("  اللاعبون الذين لهم تقييمات ودقائق")
    print("-" * 62)

    stat_players = set()
    try:
        for r in conn.execute("""
                SELECT DISTINCT player_en FROM player_stats
                WHERE player_en IS NOT NULL AND player_en != ''
            """):
            stat_players.add(r["player_en"])
    except sqlite3.Error:
        pass

    print(f"    في player_stats : {len(stat_players):,}")

    scorers_with_stats = sum(1 for p in goals if p in stat_players)
    print(f"    منهم مسجّلو أهداف: {scorers_with_stats:,}")
    print(f"    مسجّلون بلا تفاصيل: "
          f"{total - scorers_with_stats:,}")

    # ── لاعبون بأكثر من نادٍ ──────────────────────────
    multi = [p for p in goals if len(clubs[p]) > 1]
    multi_lg = [p for p in goals if len(leagues[p]) > 1]

    print()
    print("-" * 62)
    print("  تنقّل اللاعبين")
    print("-" * 62)
    print(f"    لعبوا لأكثر من نادٍ  : {len(multi):,}")
    print(f"    لعبوا في أكثر من دوري: {len(multi_lg):,}")

    if multi_lg:
        print("\n    عيّنة (أكثر من دوري):")
        for p in sorted(multi_lg,
                        key=lambda x: -goals[x])[:5]:
            lg = " · ".join(sorted(leagues[p]))
            print(f"      {p:<26} {goals[p]:>3} هدف   {lg}")

    # ── سيناريوهات الحد الأدنى ────────────────────────
    print()
    print("=" * 62)
    print("  كم صفحة سنولّد؟ (× لغتين)")
    print("=" * 62)

    for cut, label in ((1, "كل من سجّل"), (2, "هدفان فأكثر"),
                       (3, "ثلاثة فأكثر"), (5, "خمسة فأكثر")):
        n = sum(1 for p, g in goals.items() if g >= cut)
        with_stats = sum(1 for p, g in goals.items()
                         if g >= cut and p in stat_players)
        print(f"    {label:<16} {n:>5} لاعب  "
              f"= {n * 2:>5} صفحة   "
              f"(منهم {with_stats} بتفاصيل)")

    conn.close()
    print()
    print("  ⚠️ صفحات المباريات الحالية: 6,296")
    print("     إضافة آلاف الصفحات الرقيقة قد تضرّ الفهرسة.")
    print()


if __name__ == "__main__":
    main()
