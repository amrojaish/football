#!/usr/bin/env python3
"""
دمج ترشيحات build_merges.py في player_merges.csv
===================================================
يقرأ player_merges_new.csv ويضيف صفوفه للملف الرئيسي.

⚠️ **لا يضيف صفاً بلا فحص.** أربعة فحوص قبل أي كتابة:

  1. **مكرر**    — الصف موجود حرفياً ← يُتخطى بصمت
  2. **تعارض**   — old_name مُسجَّل أصلاً نحو keep_name مختلف
                   ← يُرفض ويُعرض؛ الموجود أقدم وقد رُوجع
  3. **سلسلة**   — keep_name الجديد مُسجَّل كـold_name في مكان
                   آخر (A→B وB→C) ← يُحلّ تلقائياً إلى A→C
  4. **انعكاس**  — الاتجاه المعاكس مُسجَّل (B→A موجود ونضيف A→B)
                   ← يُرفض، وإلا دارت الأسماء بلا نهاية

⚠️ الصفوف [تخميني] لا تُضاف إطلاقاً — `apply_player_merges.py`
   يتخطاها أصلاً، وإضافتها تلوّث الملف بلا فائدة.

⚠️ نسخة احتياطية قبل الكتابة. إعادة التشغيل آمنة.

    python add_merges.py --check    <- عرض بس
    python add_merges.py            <- تنفيذ
"""

import csv
import sys
import shutil
from config import BASE_DIR

MAIN = BASE_DIR / "player_merges.csv"
NEW = BASE_DIR / "player_merges_new.csv"
CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not MAIN.exists():
        print(f"ما لقيت {MAIN.name}")
        return
    if not NEW.exists():
        print(f"ما لقيت {NEW.name} — شغّل build_merges.py أول")
        return

    with open(MAIN, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or
                      ["old_name", "keep_name", "confidence", "note"])
        main_rows = list(reader)

    existing = {}
    for r in main_rows:
        o = (r.get("old_name") or "").strip()
        k = (r.get("keep_name") or "").strip()
        if o:
            existing[o] = k

    added, dup, conflict, chained, reversed_, skipped = [], 0, [], [], [], 0

    for r in csv.DictReader(open(NEW, encoding="utf-8-sig")):
        o = (r.get("old_name") or "").strip()
        k = (r.get("keep_name") or "").strip()
        conf = (r.get("confidence") or "").strip()
        note = (r.get("note") or "").strip()
        if not o or not k:
            continue
        if conf == "تخميني":
            skipped += 1
            continue

        if o in existing:
            if existing[o] == k:
                dup += 1
            else:
                conflict.append((o, k, existing[o]))
            continue

        if existing.get(k) == o:
            reversed_.append((o, k))
            continue

        # سلسلة: keep_name نفسه يُدمَج نحو اسم ثالث
        final = k
        seen = {o, k}
        while final in existing and existing[final] not in seen:
            seen.add(existing[final])
            final = existing[final]
        if final != k:
            chained.append((o, k, final))
            note = f"{note} [سلسلة عبر {k}]"

        row = {c: "" for c in fields}
        row.update({"old_name": o, "keep_name": final,
                    "confidence": conf, "note": note})
        added.append(row)
        existing[o] = final

    print()
    print("=" * 60)
    print(f"  جاهز للإضافة : {len(added)}")
    print(f"  مكرر موجود   : {dup}")
    print(f"  [تخميني] متروك: {skipped}")
    print(f"  سلاسل محلولة : {len(chained)}")
    print(f"  ⛔ تعارض     : {len(conflict)}")
    print(f"  ⛔ انعكاس    : {len(reversed_)}")
    print("=" * 60)

    for o, k, cur in conflict[:15]:
        print(f"  تعارض: {o} -> {k}  (موجود نحو {cur}) — تُرك الموجود")
    for o, k in reversed_[:10]:
        print(f"  انعكاس: {o} -> {k}  (موجود {k} -> {o}) — رُفض")
    for o, k, f2 in chained[:10]:
        print(f"  سلسلة: {o} -> {k} -> {f2}")

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    if not added:
        print("\n  ما في شي جديد يُضاف\n")
        return

    shutil.copy(MAIN, MAIN.parent / "player_merges_backup.csv")
    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(main_rows + added)

    print(f"\n  نسخة احتياطية: player_merges_backup.csv")
    print(f"  انضاف: {len(added)}")
    print("""
  الخطوة الجاية:
      python apply_player_merges.py --check
      python apply_player_merges.py
      python export_players_ar.py + merge/apply + التوليد
    """)


if __name__ == "__main__":
    main()
