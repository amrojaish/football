#!/usr/bin/env python3
"""
حسم تكرارات الأسماء عبر player_id
====================================
`find_dupes.py` يترك 72 حالة **مرشحة** لأن التشابه اللفظي
لا يكفي للحكم:

    A. Al Amri  ≟  Abdulelah Al Amri     → نفس اللاعب؟
    Abbas Al Hassan ≟ Ali Al Hassan      → أم لاعبان؟

`lineup_players` يحمل `player_id` **والاسم معاً**، فهو حَكَم
قاطع: اسمان تحت نفس المعرّف = نفس اللاعب، يقيناً لا ترجيحاً.

⚠️ **يعمل للسعودي فقط** — لا `lineup_players` للأردني ولا
   العراقي (درس 25). الحالات العراقية والأردنية تبقى للمراجعة
   اليدوية.

⚠️ **يُستثنى:**
   - `player_id = 0` — يجمع 12 لاعباً مختلفاً
   - اسم له أكثر من معرّف — لاعبان بنفس الاسم فعلاً
     (M. Al Dawsari له معرّفان مختلفان)

⚠️ الاسم المُحتفَظ به: **الأكثر أهدافاً** في جدول goals.

⚠️ لا يكتب على الديتابيس — يضيف مقترحات لـ`player_merges.csv`
   والتطبيق بـ`apply_player_merges.py`.

التشغيل:
    python merge_by_id.py --check    <- عرض فقط
    python merge_by_id.py            <- كتابة المقترحات
"""

import csv
import os
import shutil
import sqlite3
import sys
from collections import defaultdict

DB = "football.db"
MERGES = "player_merges.csv"
CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── الخريطة: اسم ← معرّف ─────────────────────────
    name_ids = defaultdict(set)
    id_names = defaultdict(set)

    for r in conn.execute("""
            SELECT player_id, player_en FROM lineup_players
            WHERE player_id IS NOT NULL AND player_id != 0
              AND player_en IS NOT NULL AND player_en != ''
        """):
        name_ids[r["player_en"]].add(r["player_id"])
        id_names[r["player_id"]].add(r["player_en"])

    # اسم له أكثر من معرّف = ملتبس، يُستبعد
    ambiguous = {n for n, ids in name_ids.items() if len(ids) > 1}

    # ── أهداف كل اسم ─────────────────────────────────
    goals = defaultdict(int)
    for r in conn.execute("""
            SELECT player_en, COUNT(player_en) AS n FROM goals
            WHERE player_en IS NOT NULL AND player_en != ''
            GROUP BY player_en
        """):
        goals[r["player_en"]] = r["n"]

    conn.close()

    # ── المجموعات: معرّف له أكثر من اسم ──────────────
    existing = set()
    old_rows = []
    if os.path.exists(MERGES):
        with open(MERGES, encoding="utf-8-sig") as f:
            old_rows = list(csv.DictReader(f))
        existing = {(r.get("old_name") or "").strip()
                    for r in old_rows}

    print()
    print("=" * 62)
    print("  حسم التكرارات عبر player_id")
    print("=" * 62)
    print(f"    معرّفات مفحوصة   : {len(id_names):,}")
    print(f"    أسماء ملتبسة (تُستبعد): {len(ambiguous)}")

    new_rows = []
    groups = 0

    for pid, names in sorted(id_names.items()):
        names = {n for n in names if n not in ambiguous}
        if len(names) < 2:
            continue

        # الأكثر أهدافاً، ثم الأطول
        keep = max(names, key=lambda n: (goals.get(n, 0), len(n)))
        others = [n for n in names
                  if n != keep and n not in existing]
        if not others:
            continue

        groups += 1
        total = sum(goals.get(n, 0) for n in names)
        print(f"\n  ✅ id={pid}   المجموع: {total} هدف")
        print(f"      ✔ {keep}   ({goals.get(keep, 0)})")
        for o in others:
            print(f"      ← {o}   ({goals.get(o, 0)})")
            new_rows.append({
                "old_name": o,
                "keep_name": keep,
                "confidence": "مؤكد",
                "note": f"player_id={pid} — حَكَم قاطع "
                        f"(merge_by_id.py)",
            })

    print()
    print("=" * 62)

    if not new_rows:
        print("  ✅ ما في جديد — كل التطابقات مسجّلة أصلاً")
        print("=" * 62 + "\n")
        return

    print(f"  مجموعات جديدة : {groups}")
    print(f"  أسماء ستُدمَج  : {len(new_rows)}")
    print("=" * 62)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    fields = ["old_name", "keep_name", "confidence", "note"]
    if old_rows:
        shutil.copy(MERGES, "player_merges_before_id.csv")
        print("\n  نسخة احتياطية: player_merges_before_id.csv")

    with open(MERGES, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in old_rows:
            w.writerow({k: r.get(k, "") for k in fields})
        w.writerows(new_rows)

    print(f"  أُضيف {len(new_rows)} سطراً لـ{MERGES}")
    print("""
  الخطوة الجاية:
      python apply_player_merges.py
      python find_dupes.py
    """)


if __name__ == "__main__":
    main()
