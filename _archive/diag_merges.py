"""
تشخيص بطء build_merges.py
============================
يعدّ فقط — لا تحليل ولا كتابة. يكشف إن كانت هناك مجموعة ضخمة
تفجّر الحلقة الزوجية (تكلفتها n² لكل مجموعة).
"""

import sqlite3
from collections import defaultdict

conn = sqlite3.connect('football.db')

rev = defaultdict(set)
for t in ("goals", "lineup_players", "player_stats", "events"):
    try:
        rows = conn.execute(f"""
            SELECT DISTINCT player_en, player_ar FROM {t}
            WHERE player_en != ''
              AND player_ar IS NOT NULL AND player_ar != ''
        """).fetchall()
    except sqlite3.OperationalError:
        continue
    for en, ar in rows:
        rev[ar].add(en)

groups = {k: v for k, v in rev.items() if len(v) > 1}
sizes = sorted((len(v) for v in groups.values()), reverse=True)

print()
print("مجموعات (نفس الترجمة لصيغ متعددة):", len(groups))
print("إجمالي الصيغ فيها                :", sum(sizes))
print("أكبر مجموعة                      :", sizes[0] if sizes else 0)
print("مجموع المقارنات الزوجية          :",
      sum(n * (n - 1) // 2 for n in sizes))
print()
print("أكبر 10 مجموعات:")
big = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:10]
for ar, ens in big:
    print(f"  {len(ens):4}  {ar}")
    if len(ens) > 8:
        print(f"        {sorted(ens)[:6]} ...")
