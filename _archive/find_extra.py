#!/usr/bin/env python3
"""
كشف المباريات الزائدة — العراقي 2023
======================================
find_missing.py يبحث عن **نقص**. هنا **فائض**:
383 مباراة موجودة مقابل 380 متوقعة = 3 زائدة.

الأندية المتأثرة (من compare_standings):
    دهوك        لعب 40  (+2)
    الزوراء     لعب 39  (+1)
    النجف       لعب 39  (+1)
    نفط البصرة  لعب 39  (+1)
    القاسم      لعب 39  (+1)

مجموع الظهور الزائد = 6 = 3 مباريات × ناديين.

يفحص ثلاثة احتمالات:
    1. مواجهة تكررت أكثر من مرتين (ذهاب وإياب فقط هو الطبيعي)
    2. مباريات خارج نافذة تواريخ الموسم
    3. مباريات تجمع الأندية المتأثرة تحديداً

⚠️ للقراءة فقط. لا يحذف ولا يعدّل. الحذف يتم عبر
   excluded_matches.csv و apply_exclusions.py — لا يدوياً.

التشغيل:
    python find_extra.py
    python find_extra.py IRQ 2024
"""

import sqlite3
import sys
from collections import Counter, defaultdict

DB = "football.db"

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "IRQ"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2023

# الأندية التي أظهرت عدد مباريات زائداً
SUSPECT = {
    ("IRQ", 2023): [20463, 8010, 11066, 11072, 15546],
}


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    names = {}
    for r in conn.execute("SELECT team_id, short_name_ar FROM teams"):
        names[r["team_id"]] = r["short_name_ar"] or str(r["team_id"])

    def nm(tid):
        return names.get(tid, f"[{tid}]")

    rows = list(conn.execute("""
        SELECT match_id, date, home_id, away_id,
               home_goals, away_goals
        FROM matches
        WHERE league_code = ? AND season = ?
        ORDER BY date
    """, (CODE, SEASON)))

    print()
    print("=" * 62)
    print(f"  {CODE} — موسم {SEASON}   ({len(rows)} مباراة)")
    print("=" * 62)

    # ── 1. مواجهات مكررة أكثر من مرتين ────────────────
    pair_count = Counter()
    pair_matches = defaultdict(list)
    for r in rows:
        key = tuple(sorted((r["home_id"], r["away_id"])))
        pair_count[key] += 1
        pair_matches[key].append(r)

    extra_pairs = {k: v for k, v in pair_count.items() if v > 2}

    print()
    print("-" * 62)
    print("  1. مواجهات تكررت أكثر من مرتين")
    print("-" * 62)

    if not extra_pairs:
        print("  ما في — كل مواجهة مرتان أو أقل")
    else:
        for key, n in sorted(extra_pairs.items(),
                             key=lambda x: -x[1]):
            a, b = key
            print(f"\n  ⚠️ {nm(a)} × {nm(b)}  —  {n} مرات:")
            for m in pair_matches[key]:
                print(f"      {m['date'][:10]}  id={m['match_id']}  "
                      f"{nm(m['home_id'])} {m['home_goals']}-"
                      f"{m['away_goals']} {nm(m['away_id'])}")

    # ── 2. شذوذ التواريخ ──────────────────────────────
    dates = sorted(r["date"][:10] for r in rows if r["date"])
    if dates:
        first, last = dates[0], dates[-1]
        month_count = Counter(d[:7] for d in dates)

        print()
        print("-" * 62)
        print("  2. توزيع المباريات على الأشهر")
        print("-" * 62)
        print(f"  من {first}  إلى {last}")
        print()
        for mo in sorted(month_count):
            n = month_count[mo]
            bar = "█" * min(n // 2, 40)
            flag = "  ⚠️" if n <= 4 else ""
            print(f"    {mo}  {n:>3}  {bar}{flag}")
        print("\n  ⚠️ الأشهر بعدد ضئيل جداً مشبوهة — قد تكون")
        print("     مباريات كأس أو ودية تسللت تحت رقم الدوري")

    # ── 3. مباريات الأندية المتأثرة ───────────────────
    sus = SUSPECT.get((CODE, SEASON), [])
    if sus:
        print()
        print("-" * 62)
        print("  3. المباريات التي تجمع الأندية المتأثرة")
        print("-" * 62)
        print("  " + " · ".join(nm(t) for t in sus))
        print()

        both = [r for r in rows
                if r["home_id"] in sus and r["away_id"] in sus]
        for m in both:
            print(f"    {m['date'][:10]}  id={m['match_id']}  "
                  f"{nm(m['home_id'])} {m['home_goals']}-"
                  f"{m['away_goals']} {nm(m['away_id'])}")
        print(f"\n  المجموع: {len(both)} مباراة بين الأندية المتأثرة")

        # عدد مباريات كل نادٍ متأثر
        print()
        print("  عدد مباريات كل نادٍ متأثر:")
        for t in sus:
            n = sum(1 for r in rows
                    if r["home_id"] == t or r["away_id"] == t)
            flag = "  ⚠️" if n != 38 else ""
            print(f"    {nm(t):<14} {n}{flag}")

    # ── 4. معرّفات شاذة ───────────────────────────────
    print()
    print("-" * 62)
    print("  4. معرّفات المباريات — قفزات كبيرة")
    print("-" * 62)
    ids = sorted(r["match_id"] for r in rows)
    print(f"  الأدنى: {ids[0]}   الأعلى: {ids[-1]}")
    manual = [i for i in ids if i >= 9000000]
    if manual:
        print(f"  ⚠️ {len(manual)} مباراة مضافة يدوياً "
              f"(id >= 9000000): {manual}")

    conn.close()
    print()
    print("=" * 62)
    print("""
  إن تأكدت مباراة زائدة، لا تحذفها يدوياً —
  أضفها لـexcluded_matches.csv ثم:
      python apply_exclusions.py
    """)


if __name__ == "__main__":
    main()
