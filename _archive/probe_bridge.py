#!/usr/bin/env python3
"""
فحص الجسر: goals ↔ player_stats عبر lineup_players
=====================================================
المشكلة (درس 44): المزوّد يرجع اسمين لنفس اللاعب

    goals          : J. Harkass              ← مختصر
    lineup_players : J. Harkass              ← مختصر + player_id ✅
    player_stats   : Jamal Harkass           ← كامل + player_id ✅

فـ`lineup_players` **جسر جاهز**: يحمل الاسم المختصر والمعرّف معاً.
لو صحّ، نربط أهداف اللاعب بتقييماته ودقائقه — وتصير صفحة اللاعب
غنية لـ1,256 لاعباً بدل 126.

يفحص:
    1. كم اسماً في goals له مطابق في lineup_players؟
    2. كم player_id له اسم مختصر **واحد** فقط؟ (خريطة نظيفة)
    3. كم player_id ملتبس (أكثر من اسم)؟
    4. أثر id=0 — كم سجلاً؟

⚠️ للقراءة فقط.

التشغيل:
    python probe_bridge.py
"""

import sqlite3
from collections import defaultdict

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── 1. id=0 ───────────────────────────────────────
    print()
    print("=" * 62)
    print("  أثر player_id = 0")
    print("=" * 62)

    for tbl in ("lineup_players", "player_stats"):
        try:
            n = conn.execute(f"""
                SELECT COUNT(*) FROM {tbl} WHERE player_id = 0
            """).fetchone()[0]
            names = conn.execute(f"""
                SELECT COUNT(DISTINCT player_en) FROM {tbl}
                WHERE player_id = 0
            """).fetchone()[0]
            print(f"    {tbl:<18} {n:>6} سجل   "
                  f"{names} اسماً مختلفاً")
        except sqlite3.Error as e:
            print(f"    {tbl}: {e}")

    print("\n  ⚠️ id=0 يجمع لاعبين مختلفين — يُستثنى دائماً")

    # ── 2. خريطة المعرّف ← الاسم المختصر ─────────────
    lp = defaultdict(set)
    for r in conn.execute("""
            SELECT player_id, player_en FROM lineup_players
            WHERE player_id IS NOT NULL AND player_id != 0
              AND player_en IS NOT NULL AND player_en != ''
        """):
        lp[r["player_id"]].add(r["player_en"])

    clean = {pid: list(names)[0]
             for pid, names in lp.items() if len(names) == 1}
    messy = {pid: names for pid, names in lp.items()
             if len(names) > 1}

    print()
    print("=" * 62)
    print("  خريطة player_id ← الاسم في lineup_players")
    print("=" * 62)
    print(f"    معرّفات إجمالاً   : {len(lp):,}")
    print(f"    باسم واحد (نظيف) : {len(clean):,}")
    print(f"    بأكثر من اسم     : {len(messy):,}")

    if messy:
        print("\n    عيّنة ملتبسة:")
        for pid, names in list(messy.items())[:5]:
            print(f"      id={pid}: {' | '.join(sorted(names))}")

    # ── 3. هل أسماء goals موجودة في lineup_players؟ ──
    goals = {}
    for r in conn.execute("""
            SELECT player_en, COUNT(player_en) AS n FROM goals
            WHERE player_en IS NOT NULL AND player_en != ''
            GROUP BY player_en
        """):
        goals[r["player_en"]] = r["n"]

    lp_names = set()
    for names in lp.values():
        lp_names |= names

    matched = {p: n for p, n in goals.items() if p in lp_names}
    unmatched = {p: n for p, n in goals.items() if p not in lp_names}

    print()
    print("=" * 62)
    print("  مطابقة أسماء goals مع lineup_players")
    print("=" * 62)
    print(f"    أسماء في goals    : {len(goals):,}")
    print(f"    لها مطابق ✅      : {len(matched):,}")
    print(f"    بلا مطابق ❌      : {len(unmatched):,}")

    g_matched = sum(matched.values())
    g_total = sum(goals.values())
    print(f"\n    الأهداف المغطّاة  : {g_matched:,} من "
          f"{g_total:,}  ({g_matched / g_total * 100:.0f}%)")

    # الأهم: أعلى الهدافين — هل مغطّون؟
    top = sorted(goals.items(), key=lambda x: -x[1])[:15]
    print("\n    أعلى 15 هدافاً:")
    for p, n in top:
        mark = "✅" if p in lp_names else "❌"
        print(f"      {mark}  {p:<28} {n:>3}")

    # ── 4. الجسر الكامل: goals → id → player_stats ───
    ps_by_id = defaultdict(int)
    for r in conn.execute("""
            SELECT player_id, COUNT(*) AS n FROM player_stats
            WHERE player_id IS NOT NULL AND player_id != 0
            GROUP BY player_id
        """):
        ps_by_id[r["player_id"]] = r["n"]

    name_to_id = {}
    for pid, name in clean.items():
        name_to_id.setdefault(name, pid)

    bridged = [p for p in goals
               if p in name_to_id and name_to_id[p] in ps_by_id]

    print()
    print("=" * 62)
    print("  الجسر الكامل — هدّاف له تقييمات ودقائق")
    print("=" * 62)
    print(f"    قبل الجسر (بالاسم)  : 126")
    print(f"    بعد الجسر (بالمعرّف): {len(bridged):,}")

    if len(bridged) > 126:
        print(f"\n  ✅ الجسر يضيف {len(bridged) - 126:,} لاعباً")
        print("     صفحة اللاعب تصير غنية فعلاً.")
    else:
        print("\n  ⚠️ الجسر لا يضيف كثيراً — راجع الافتراض")

    conn.close()
    print()


if __name__ == "__main__":
    main()
