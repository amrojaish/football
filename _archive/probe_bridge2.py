#!/usr/bin/env python3
"""
فحص الجسر — النسخة الثانية
=============================
`probe_bridge.py` تجاهل 356 معرّفاً لأن لها أكثر من اسم:

    id=44443: F. Al Ghamdi | Feras Al Ghamdi | Firas Al-Ghamdi

لكن هذا **ليس التباساً** — `player_id` هو الحقيقة، وتعدّد
الأسماء تحته **تأكيد** أنها لاعب واحد لا العكس. الخريطة
الصحيحة: كل اسم → معرّفه، لا معرّف → اسم واحد.

⚠️ الالتباس الحقيقي في الاتجاه المعاكس: **اسم واحد لمعرّفين
   مختلفين** (لاعبان بنفس الاسم المختصر). هذا يُستثنى.

يقيس أيضاً:
    - كم من الـ72 حالة المرشحة يحسمها player_id؟
    - السقف البنيوي: العراقي والأردني بلا lineup_players أصلاً

⚠️ للقراءة فقط.

التشغيل:
    python probe_bridge2.py
"""

import sqlite3
from collections import defaultdict

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── الخريطة: اسم → مجموعة معرّفات ─────────────────
    name_ids = defaultdict(set)
    id_names = defaultdict(set)

    for r in conn.execute("""
            SELECT player_id, player_en FROM lineup_players
            WHERE player_id IS NOT NULL AND player_id != 0
              AND player_en IS NOT NULL AND player_en != ''
        """):
        name_ids[r["player_en"]].add(r["player_id"])
        id_names[r["player_id"]].add(r["player_en"])

    ambiguous = {n: ids for n, ids in name_ids.items()
                 if len(ids) > 1}
    usable = {n: list(ids)[0] for n, ids in name_ids.items()
              if len(ids) == 1}

    print()
    print("=" * 62)
    print("  الخريطة الصحيحة — اسم ← معرّف")
    print("=" * 62)
    print(f"    أسماء في lineup_players : {len(name_ids):,}")
    print(f"    اسم ← معرّف واحد ✅     : {len(usable):,}")
    print(f"    اسم ← أكثر من معرّف ⚠️  : {len(ambiguous):,}")

    if ambiguous:
        print("\n    عيّنة ملتبسة فعلاً (لاعبان بنفس الاسم):")
        for n, ids in list(ambiguous.items())[:5]:
            print(f"      {n}: {sorted(ids)}")

    # ── الأهداف ───────────────────────────────────────
    goals = {}
    goal_league = {}
    for r in conn.execute("""
            SELECT g.player_en, COUNT(g.player_en) AS n,
                   MIN(m.league_code) AS lg
            FROM goals g JOIN matches m ON m.match_id = g.match_id
            WHERE g.player_en IS NOT NULL AND g.player_en != ''
            GROUP BY g.player_en
        """):
        goals[r["player_en"]] = r["n"]
        goal_league[r["player_en"]] = r["lg"]

    # ── من له تفاصيل عبر المعرّف؟ ────────────────────
    ps_ids = set()
    for r in conn.execute("""
            SELECT DISTINCT player_id FROM player_stats
            WHERE player_id IS NOT NULL AND player_id != 0
        """):
        ps_ids.add(r["player_id"])

    bridged = [p for p in goals
               if p in usable and usable[p] in ps_ids]

    print()
    print("=" * 62)
    print("  هدّافون لهم تقييمات ودقائق")
    print("=" * 62)
    print(f"    بالاسم المباشر      : 126")
    print(f"    بالجسر (نسخة 1)     : 278")
    print(f"    بالجسر (نسخة 2) ✅  : {len(bridged):,}")

    # ── السقف البنيوي ─────────────────────────────────
    by_lg = defaultdict(lambda: [0, 0])
    for p in goals:
        lg = goal_league[p]
        by_lg[lg][0] += 1
        if p in usable and usable[p] in ps_ids:
            by_lg[lg][1] += 1

    print()
    print("-" * 62)
    print("  التغطية حسب الدوري")
    print("-" * 62)
    for lg in sorted(by_lg):
        tot, cov = by_lg[lg]
        pct = cov / tot * 100 if tot else 0
        print(f"    {lg}   {cov:>4} من {tot:>4} هدّاف  "
              f"({pct:5.1f}%)")

    print("\n  ⚠️ العراقي والأردني بلا lineup_players إطلاقاً")
    print("     (درس 25) — سقف بنيوي لا يُتجاوز.")

    # ── هل يحسم المعرّف الحالات المرشحة؟ ─────────────
    print()
    print("=" * 62)
    print("  هل يحسم player_id الحالات المرشحة؟")
    print("=" * 62)

    tests = [
        ("A. Al Bulayhi", "Ali Al Bulayhi"),
        ("A. Al Amri", "Abdulelah Al Amri"),
        ("A. Al Ghamdi", "Ahmed Al Ghamdi"),
        ("A. Al Hamdan", "Abdullah Al Hamdan"),
        ("M. Al Kuwaykibi", "Mohammed Al Kuwaykibi"),
        ("A. Ghareeb", "Abdulrahman Ghareeb"),
        ("A. Al Hatila", "Abdulaziz Al Hatila"),
        ("N. Al Habashi", "Nawaf Al Habashi"),
        ("M. Al Burayk", "Mohammed Al Burayk"),
        ("Abbas Al Hassan", "Ali Al Hassan"),
    ]

    same = diff = unknown = 0
    for a, b in tests:
        ia = name_ids.get(a, set())
        ib = name_ids.get(b, set())
        if not ia or not ib:
            mark = "؟ أحدهما غير موجود"
            unknown += 1
        elif ia & ib:
            mark = f"✅ نفس اللاعب — id={sorted(ia & ib)[0]}"
            same += 1
        else:
            mark = f"❌ لاعبان مختلفان — {sorted(ia)} / {sorted(ib)}"
            diff += 1
        print(f"    {a:<24} ≟ {b:<26} {mark}")

    print(f"\n    محسومة كنفس اللاعب : {same}")
    print(f"    محسومة كمختلفَين   : {diff}")
    print(f"    غير محسومة        : {unknown}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
