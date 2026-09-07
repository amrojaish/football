#!/usr/bin/env python3
"""
كشف الدورات بملف دمج أسماء اللاعبين
=======================================
دورة (A→B بصف، وB→A بصف آخر — أو أطول) تعني أن كل تشغيل لـ
`apply_player_merges.py` يعكس الاسم بلا توقّف، للأبد. أخطر من
قيمة تالفة عادية: صامتة، ومتكرّرة كل 30 دقيقة عبر الأتمتة، بلا
أي أداة كانت ترصدها قبل اليوم.

اكتُشفت 7 سبتمبر يدوياً (فحص idempotency كشف 3 دورات: M. Rodák
↔ M. Rodak · Salman Al Mowasher ↔ Salman Al-Mowasher · Hamed Al
Shanqiti ↔ Hamed Al-Shanqity — راجع البند المفتوح بالـREADME).
هذه الأداة تكشفها آلياً بدل الاعتماد على فحص يدوي.

⚠️ **مصدرها المتكرر:** صفان من أداتين مختلفتين لنفس اللاعب —
   `auto_merge_names.py` (استدلال بعدد الأهداف) و`merge_by_id.py`
   (مطابقة `player_id` فعلية، دليل أقوى) — يختاران اتجاهاً
   معاكساً. لا حل آلي هنا: قرار حذف/توحيد يدوي بعد المراجعة.

الاستخدام:
    python check_merge_cycles.py --check   <- تقرير فقط، رمز خروج 0 دائماً
    python check_merge_cycles.py           <- تقرير، ورمز خروج 1 لو وُجدت دورة

يُستورَد أيضاً من `apply_player_merges.py` كبوّابة قبل أي كتابة:
    from check_merge_cycles import load_pairs, find_cycles
"""

import csv
import sys

from config import BASE_DIR

CHECK = "--check" in sys.argv
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SOURCE = BASE_DIR / "player_merges.csv"


def load_pairs(path=SOURCE):
    """
    old→keep من player_merges.csv، بعد استبعاد [تخميني] وself-pair
    (old==keep بعد strip — ضجيج حميد، ليس دورة). يرجع
    [(رقم السطر, old, keep, note), ...].
    """
    pairs = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            old = (r.get("old_name") or "").strip()
            keep = (r.get("keep_name") or "").strip()
            conf = (r.get("confidence") or "").strip()
            note = (r.get("note") or "").strip()
            if not old or not keep or conf == "تخميني" or old == keep:
                continue
            pairs.append((i, old, keep, note))
    return pairs


def find_cycles(pairs):
    """
    دورات بأي طول (لا A→B→A فقط) عبر DFS بتتبّع مسار الزيارة
    الحالي. يرجع قائمة دورات، كل دورة قائمة أسماء ترجع لنقطة
    البداية: [A, B, C, A].
    """
    graph = {}
    for i, old, keep, note in pairs:
        graph.setdefault(old, []).append((keep, i, note))

    cycles = []
    seen = set()

    def dfs(node, path, path_set):
        for keep, line_no, note in graph.get(node, []):
            if keep in path_set:
                start = path.index(keep)
                cyc = path[start:] + [keep]
                key = tuple(sorted(set(cyc)))
                if key not in seen:
                    seen.add(key)
                    cycles.append(cyc)
                continue
            if keep in graph:  # تابع فقط لو keep نفسه old بصف آخر
                dfs(keep, path + [keep], path_set | {keep})

    for old in graph:
        dfs(old, [old], {old})

    return cycles


def find_fanout(pairs):
    """
    old_name واحد → أكثر من keep_name مختلف. ليست دورة بالضرورة
    (قد تتقارب عبر سلسلة، كما تحقّقنا بحالة M. Al Juwayr) — تحذير
    لا منع.
    """
    by_old = {}
    for i, old, keep, note in pairs:
        by_old.setdefault(old, set()).add(keep)
    return {old: sorted(keeps) for old, keeps in by_old.items()
            if len(keeps) > 1}


def main():
    pairs = load_pairs()
    cycles = find_cycles(pairs)
    fanout = find_fanout(pairs)

    print(f"\n{'=' * 62}")
    print(f"  أزواج مفحوصة: {len(pairs)}")
    print(f"{'=' * 62}")

    if cycles:
        print(f"\n  🔴 دورات (تمنع الكتابة): {len(cycles)}")
        for c in cycles:
            print("      " + " → ".join(c))
    else:
        print("\n  ✅ صفر دورات")

    if fanout:
        print(f"\n  ⚠️ توجيه متعدّد (لا يمنع، يحتاج مراجعة): {len(fanout)}")
        for old, keeps in fanout.items():
            print(f"      {old!r} → {keeps}")

    print(f"\n{'=' * 62}\n")

    if cycles and not CHECK:
        sys.exit(1)


if __name__ == "__main__":
    main()
