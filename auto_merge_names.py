#!/usr/bin/env python3
"""
توحيد آلي — فروق اللكنة والشرطة والمسافات
============================================
`find_dupes.py` كشف 18 تكراراً **مؤكداً**، وكلها تعود لنمطين
لا ثالث لهما:

    1. لكنة أوروبية : M. Dembele  /  M. Dembélé
                      Tozé / Toze · F. Kessié · Cláudio Maradona
    2. شرطة/مسافة   : H. Al Dardour  /  H. Al-Dardour
                      M. Al Attar / M. Al-Attar
    3. مسافات زائدة : "Abdullah Al Ammar" / "Abdullah Al Ammar   "

الثلاثة **قابلة للحل آلياً بيقين** — لا تحتاج حكماً بشرياً،
بخلاف الـ68 المرشحة (`Ali Hussein` ≠ `Aymen Hussein`) التي
تبقى للمراجعة اليدوية.

المعيار: اسمان يُدمَجان **فقط** إذا تطابقا حرفياً بعد:
    تجريد اللكنات · توحيد الشرطة والمسافة · إزالة الزوائد

⚠️ الاسم **الأكثر تكراراً** هو المُحتفَظ به (لا الأطول ولا الأول).

⚠️ **لا يكتب على الديتابيس.** يكتب مقترحات في
   `player_merges.csv` فقط، والتطبيق بـ`apply_player_merges.py`.

⚠️ يحترم الموجود: لا يضيف سطراً مكرراً ولا يمسّ ما كتبتَه يدوياً.

التشغيل:
    python auto_merge_names.py --check    <- عرض فقط
    python auto_merge_names.py            <- كتابة المقترحات
"""

import csv
import os
import sqlite3
import sys
import unicodedata
from collections import defaultdict

DB = "football.db"
MERGES = "player_merges.csv"
CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fold(name):
    """
    البصمة الموحّدة: اسمان لهما نفس البصمة = نفس اللاعب.
    تجرّد اللكنات وتوحّد الشرطة والمسافة وتزيل الزوائد.
    """
    s = (name or "").strip()
    if not s:
        return ""
    # تجريد اللكنات: é → e ، ć → c ، í → i
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # الفاصلة العليا **تُحذف** لا تُستبدل بمسافة —
    # وإلا فشل G. N'Koudou مقابل G. Nkoudou
    for ch in "'\u2019\u2018\u02bc":
        s = s.replace(ch, "")
    # الشرطة والنقطة → مسافة
    for ch in "-.":
        s = s.replace(ch, " ")
    # مسافات متعددة → واحدة
    s = " ".join(s.split())
    return s.lower()


def load_existing():
    """الأسماء المسجّلة في player_merges.csv"""
    if not os.path.exists(MERGES):
        return set(), []
    with open(MERGES, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    old = {(r.get("old_name") or "").strip() for r in rows}
    return old, rows


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # كل الأسماء وعدد أهدافها
    counts = defaultdict(int)
    for r in conn.execute("""
            SELECT player_en, COUNT(player_en) AS n
            FROM goals
            WHERE player_en IS NOT NULL AND player_en != ''
            GROUP BY player_en"""):
        counts[r["player_en"]] += r["n"]

    # أسماء التشكيلات كذلك — التكرار موجود فيها أيضاً
    for tbl in ("lineup_players", "player_stats"):
        try:
            for r in conn.execute(f"""
                    SELECT player_en, COUNT(player_en) AS n
                    FROM {tbl}
                    WHERE player_en IS NOT NULL AND player_en != ''
                    GROUP BY player_en"""):
                counts.setdefault(r["player_en"], 0)
        except sqlite3.Error:
            pass

    conn.close()

    # تجميع بالبصمة
    groups = defaultdict(list)
    for name in counts:
        f = fold(name)
        if f:
            groups[f].append(name)

    dupes = {f: names for f, names in groups.items() if len(names) > 1}

    existing, old_rows = load_existing()

    print()
    print("=" * 62)
    print(f"  أسماء مفحوصة: {len(counts):,}")
    print(f"  مجموعات متطابقة بعد التوحيد: {len(dupes)}")
    print("=" * 62)

    new_rows = []

    for f in sorted(dupes, key=lambda x: -max(
            counts.get(n, 0) for n in dupes[x])):
        names = dupes[f]
        # المُحتفَظ به: الأكثر أهدافاً، ثم الأطول (أوضح)
        keep = max(names, key=lambda n: (counts.get(n, 0), len(n)))
        others = [n for n in names if n != keep]

        shown = False
        for o in others:
            if o in existing:
                continue
            if not shown:
                print(f"\n  ✅ {keep}   ({counts.get(keep, 0)} هدف)")
                shown = True
            print(f"      ← {o}   ({counts.get(o, 0)} هدف)")
            new_rows.append({
                "old_name": o,
                "keep_name": keep,
                "confidence": "مؤكد",
                "note": "توحيد آلي — فرق لكنة أو شرطة أو مسافة "
                        "(auto_merge_names.py)",
            })

    print()
    print("=" * 62)
    if not new_rows:
        print("  ✅ ما في جديد — كل التطابقات مسجّلة أصلاً")
        print("=" * 62 + "\n")
        return

    print(f"  مقترحات جديدة: {len(new_rows)}")
    print("=" * 62)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    # نسخة احتياطية ثم إضافة
    fields = ["old_name", "keep_name", "confidence", "note"]
    if old_rows:
        import shutil
        shutil.copy(MERGES, "player_merges_before_auto.csv")
        print("\n  نسخة احتياطية: player_merges_before_auto.csv")

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
      python make_site3.py
      python make_clubs.py
      python make_search.py
    """)


if __name__ == "__main__":
    main()
