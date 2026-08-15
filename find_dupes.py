#!/usr/bin/env python3
"""
كشف تكرارات أسماء اللاعبين
=============================
المزوّد يكتب اللاعب أحياناً بصيغتين:
    C. Ronaldo   +   Cristiano Ronaldo
    J. Quinones  +   J. Quiñones

النتيجة: أهدافه تتوزع على "لاعبَين"، وقائمة الهدافين تصير خاطئة.

بيكشف التكرارات بثلاث طرق:
  1. عبر player_id — الأدق، من player_stats (السعودي فقط)
  2. تطبيع الحروف — إزالة النقاط والتشكيل اللاتيني
  3. مطابقة اللقب + الحرف الأول

⚠️ جدول goals لا يخزّن player_id (درس 26)، فالطريقة 1 لا
   تغطي الأردني والعراقي.

صفر طلبات API — قراءة فقط.

التشغيل:
    python find_dupes.py
    python find_dupes.py JOR
"""

import sqlite3
import sys
import unicodedata
from collections import defaultdict
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


def strip_accents(s):
    """Quiñones → Quinones"""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalize(name):
    """تطبيع للمقارنة: أحرف صغيرة، بلا نقاط ولا تشكيل"""
    s = strip_accents(name).lower()
    s = s.replace(".", " ").replace("-", " ").replace("'", "")
    return " ".join(s.split())


def surname_key(name):
    """آخر كلمة + الحرف الأول — يمسك 'C. Ronaldo' و'Cristiano Ronaldo'"""
    parts = normalize(name).split()
    if len(parts) < 2:
        return None
    return (parts[0][0], parts[-1])


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    q = """
        SELECT g.player_en AS en, m.league_code AS lg,
               COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en != ''
    """
    params = []
    if ONLY:
        q += " AND m.league_code = ?"
        params.append(ONLY)
    q += " GROUP BY g.player_en, m.league_code"

    rows = conn.execute(q, params).fetchall()

    print(f"\n{'#' * 66}")
    print(f"#  كشف تكرارات أسماء اللاعبين")
    print(f"{'#' * 66}")
    print(f"\n  أسماء مفحوصة: {len(rows)}")

    # ---------------------------------------------------------------
    # 1) التطبيع الكامل — نفس الاسم بفروق شكلية
    # ---------------------------------------------------------------
    by_norm = defaultdict(list)
    for r in rows:
        by_norm[(normalize(r["en"]), r["lg"])].append(r)

    exact = {k: v for k, v in by_norm.items() if len(v) > 1}

    print(f"\n{'=' * 66}")
    print(f"  1) نفس الاسم بفروق شكلية (نقاط / تشكيل)")
    print(f"{'=' * 66}")

    if not exact:
        print("\n      ما في ✅")
    else:
        for (norm, lg), items in sorted(
                exact.items(), key=lambda x: -sum(i["goals"] for i in x[1])):
            total = sum(i["goals"] for i in items)
            name = LEAGUES.get(lg, {}).get("name_ar", lg)
            print(f"\n  ⚠️  {name}   المجموع الحقيقي: {total} هدف")
            for i in sorted(items, key=lambda x: -x["goals"]):
                print(f"        {i['goals']:>3}  {i['en']}")

    # ---------------------------------------------------------------
    # 2) اللقب + الحرف الأول
    # ---------------------------------------------------------------
    by_sur = defaultdict(list)
    for r in rows:
        k = surname_key(r["en"])
        if k:
            by_sur[(k, r["lg"])].append(r)

    sur_dupes = {}
    for k, v in by_sur.items():
        # نتجاهل اللي مسكناهم بالطريقة الأولى
        norms = {normalize(x["en"]) for x in v}
        if len(v) > 1 and len(norms) > 1:
            sur_dupes[k] = v

    print(f"\n{'=' * 66}")
    print(f"  2) نفس اللقب ونفس الحرف الأول")
    print(f"{'=' * 66}")

    if not sur_dupes:
        print("\n      ما في ✅")
    else:
        print("\n  ⚠️ هذه **مرشحة** — قد تكون لاعبَين مختلفَين فعلاً")
        for (k, lg), items in sorted(
                sur_dupes.items(), key=lambda x: -sum(i["goals"] for i in x[1])):
            total = sum(i["goals"] for i in items)
            name = LEAGUES.get(lg, {}).get("name_ar", lg)
            print(f"\n      {name}   المجموع لو كانا واحداً: {total}")
            for i in sorted(items, key=lambda x: -x["goals"]):
                print(f"        {i['goals']:>3}  {i['en']}")

    # ---------------------------------------------------------------
    # 3) عبر player_id (السعودي فقط)
    # ---------------------------------------------------------------
    print(f"\n{'=' * 66}")
    print(f"  3) عبر player_id — الأدق (السعودي فقط)")
    print(f"{'=' * 66}")

    try:
        pid_rows = conn.execute("""
            SELECT player_id, player_en, COUNT(*) n
            FROM player_stats
            GROUP BY player_id, player_en
        """).fetchall()

        by_pid = defaultdict(set)
        for r in pid_rows:
            by_pid[r["player_id"]].add(r["player_en"])

        multi = {p: names for p, names in by_pid.items() if len(names) > 1}

        if not multi:
            print("\n      كل معرّف له اسم واحد ✅")
        else:
            print(f"\n  ⚠️ {len(multi)} معرّف له أكثر من صيغة اسم:")
            for pid, names in list(multi.items())[:15]:
                print(f"\n      id={pid}")
                for n in names:
                    print(f"        {n}")
    except sqlite3.OperationalError:
        print("\n      جدول player_stats غير موجود")

    conn.close()

    n_fix = len(exact)
    print(f"""
{'#' * 66}
  الخلاصة

  تكرارات مؤكدة (فروق شكلية) : {n_fix}
  مرشحة تحتاج مراجعة          : {len(sur_dupes)}

  ⚠️ كل تكرار يعني أن أهداف اللاعب موزعة، وقائمة الهدافين
     المعروضة **خاطئة**.

  الحل: ملف player_merges.csv يوحّد الصيغ — بنفس فلسفة
  team_merges.csv.
{'#' * 66}
""")


if __name__ == "__main__":
    main()
