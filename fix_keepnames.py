#!/usr/bin/env python3
"""
تصحيح الأسماء المُحتفَظ بها في player_merges.csv
==================================================
يكشف الصفوف التي يكون فيها `keep_name` صيغة **مشوّهة** من
المزوّد، ويقترح بديلاً نظيفاً من نفس مجموعة الدمج.

⚠️ **سبب المشكلة:** معيار اختيار الاسم في build_merges.py
   يفضّل "الأكثر مقاطع"، فتفوز صيغ مثل:
       K. A. Al Sibyani H.     على  Hussain Al Sibyani
       M. Y. Dawran M.         على  Majed Dawran
       R. B. Martinez Tobinson على  Roger Martínez
   والاسم المُحتفَظ به هو ما **يظهر على الموقع**، فالتشويه مرئي.

⚠️ المعيار هنا: الاسم النظيف = بلا أحرف مفردة، وبمقاطع أكثر.
   يُقلب اتجاه الصفوف داخل المجموعة فقط — لا يُحذف صف ولا
   يُضاف دمج جديد.

⚠️ نسخة احتياطية قبل الكتابة. لا يلمس الديتابيس.

    python fix_keepnames.py --check    <- عرض بس
    python fix_keepnames.py            <- تنفيذ
"""

import csv
import re
import sys
import shutil
import unicodedata
from collections import defaultdict
from config import BASE_DIR

MAIN = BASE_DIR / "player_merges.csv"
CHECK = "--check" in sys.argv
STOP = ("al", "el", "bin", "ibn", "abu", "de", "da")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def toks(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z ]", " ", s.replace("-", " "))
    return [w for w in s.split() if w not in STOP]


def initials(s):
    return sum(1 for t in toks(s) if len(t) == 1)


def acceptable(cur, cand):
    """
    ⚠️ شرطان يمنعان "تصحيحاً" يخرّب الاسم:

    1. **نفس اللقب.** بدونه تمرّ حالات محقَّقة مثل:
           M. Al Yami   -> Mohammed Essa Harbush
           S. Balobaid  -> Saad Yaslam
       وهي دمجات خاطئة أصلاً في البيانات، فلا نكرّسها بجعلها
       الاسم المعروض على الموقع.

    2. **مقطعان على الأقل.** "أقل أحرف مفردة" وحده يفضّل لقباً
       مفرداً على "حرف + لقب" فنخسر الاسم الأول:
           A. Alhaj     -> Alhaj
           C. El Bahri  -> El Bahri
           U. Hussein   -> Adi
    """
    tc, tn = toks(cur), toks(cand)
    if len(tn) < 2 or not tc or not tn:
        return False
    return tc[-1] == tn[-1]



def clean_score(s):
    """الأنظف: أقل أحرف مفردة، ثم أكثر مقاطع، ثم أطول"""
    return (-initials(s), len(toks(s)), len(s))


def main():
    if not MAIN.exists():
        print(f"ما لقيت {MAIN.name}")
        return

    with open(MAIN, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    groups = defaultdict(set)
    for r in rows:
        o = (r.get("old_name") or "").strip()
        k = (r.get("keep_name") or "").strip()
        if o and k:
            groups[k].add(o)
            groups[k].add(k)

    fixes = {}
    rejected = []
    for keep, members in groups.items():
        if initials(keep) == 0:
            continue                      # نظيف أصلاً
        # ⚠️ sorted() إجباري: ترتيب المجموعة عشوائي، فبدونه
        #    يختلف الاسم المختار بين تشغيلتين على نفس الملف.
        cands = [m for m in sorted(members)
                 if m != keep and initials(m) < initials(keep)]
        good = [m for m in cands if acceptable(keep, m)]
        bad = [m for m in cands if not acceptable(keep, m)]
        if good:
            fixes[keep] = max(good, key=clean_score)
        elif bad:
            rejected.append((keep, bad))

    print()
    print("=" * 62)
    print(f"  مجموعات دمج : {len(groups)}")
    print(f"  اسمها المُحتفَظ به مشوّه ولها بديل أنظف: {len(fixes)}")
    print("=" * 62)
    for old_keep, new_keep in sorted(fixes.items()):
        print(f"   {old_keep:30} -> {new_keep}")

    if rejected:
        print(f"\n  ⛔ مُنع {len(rejected)} بديلاً (لقب مختلف أو اسم ناقص):")
        for keep, bad in sorted(rejected):
            print(f"   {keep:30} != {', '.join(bad)}")
        print("     هذه غالباً **دمجات خاطئة** في player_merges.csv"
              " — راجعها يدوياً.")

    if not fixes:
        print("\n  ما في شي يُصحَّح\n")
        return

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    changed = 0
    out = []
    for r in rows:
        o = (r.get("old_name") or "").strip()
        k = (r.get("keep_name") or "").strip()
        if k in fixes:
            new_keep = fixes[k]
            if o == new_keep:
                # الاتجاه ينقلب: البديل صار هو المُحتفَظ به
                r["old_name"] = k
                r["keep_name"] = new_keep
            else:
                r["keep_name"] = new_keep
            r["note"] = ((r.get("note") or "") + " [صُحِّح الاسم المعروض]").strip()
            changed += 1
        out.append(r)

    shutil.copy(MAIN, MAIN.parent / "player_merges_backup_keepfix.csv")
    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"\n  نسخة احتياطية: player_merges_backup_keepfix.csv")
    print(f"  صفوف معدّلة: {changed}")
    print("""
  الخطوة الجاية:
      python apply_player_merges.py --check
    """)


if __name__ == "__main__":
    main()
