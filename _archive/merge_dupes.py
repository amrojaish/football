#!/usr/bin/env python3
"""
دمج تكرارات أسماء اللاعبين — الآمن فقط
=========================================
المزوّد يكتب اللاعب بصيغتين تختلفان **بالتشكيل اللاتيني أو
النقاط فقط**:
    Sadio Mané    ←→  Sadio Mane
    J. Quiñones   ←→  J. Quinones
    H. Al-Dardour ←→  H. Al Dardour

هذه الحالات **مؤكدة** — بعد إزالة التشكيل يصير الاسمان متطابقين
حرفياً، فلا احتمال أن يكونا لاعبَين مختلفَين.

⚠️ **لا يلمس** الحالات التي تختلف بالكلمات (مثل C. Ronaldo مقابل
   Cristiano Ronaldo، أو Karrar Ali مقابل Kosrat Ali). تلك تحتاج
   مراجعة يدوية عبر player_merges.csv.

المنطق: توحيد كل الصيغ على **الأكثر تكراراً** — لأنها الأرجح
أن تكون الصيغة القياسية عند المزوّد.

بيعمل نسخة احتياطية قبل أي تعديل.

التشغيل:
    python merge_dupes.py --check    <- عرض بس
    python merge_dupes.py            <- تنفيذ
"""

import sqlite3
import sys
import shutil
import unicodedata
from collections import defaultdict
from config import DB_FILE

CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalize(name):
    """تطبيع: بلا تشكيل ولا نقاط ولا شرطات ولا مسافات زائدة"""
    s = strip_accents(name).lower()
    s = s.replace(".", " ").replace("-", " ").replace("'", "")
    return " ".join(s.split())


def has_table(conn, name):
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # ---- كل صيغ الأسماء بجدول goals مع عدد الأهداف ----
    rows = conn.execute("""
        SELECT player_en AS en, COUNT(*) AS n
        FROM goals WHERE player_en != ''
        GROUP BY player_en
    """).fetchall()

    groups = defaultdict(list)
    for r in rows:
        groups[normalize(r["en"])].append((r["en"], r["n"]))

    dupes = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"\n{'=' * 62}")
    print(f"  تكرارات آمنة للدمج: {len(dupes)}")
    print(f"{'=' * 62}")

    if not dupes:
        print("\n  ما في تكرارات ✅\n")
        conn.close()
        return

    # ---- تحديد الصيغة القياسية لكل مجموعة ----
    plan = []
    for norm, items in sorted(
            dupes.items(), key=lambda x: -sum(i[1] for i in x[1])):
        items.sort(key=lambda x: -x[1])
        keep = items[0][0]
        total = sum(i[1] for i in items)

        print(f"\n  المجموع الحقيقي: {total} هدف")
        print(f"      ✅ {keep}   ({items[0][1]})")
        for other, n in items[1:]:
            print(f"      ↳  {other}   ({n})")
            plan.append((other, keep))

    tables = ["goals"]
    for t in ("lineup_players", "player_stats", "events"):
        if has_table(conn, t):
            tables.append(t)

    if CHECK_ONLY:
        print(f"\n{'=' * 62}")
        print(f"  [وضع الفحص] — ما انكتب شي")
        print(f"  صيغ ستُوحَّد: {len(plan)}")
        print(f"  الجداول المتأثرة: {', '.join(tables)}")
        print(f"{'=' * 62}\n")
        conn.close()
        return

    # ---- نسخة احتياطية ----
    backup = DB_FILE.parent / "football_before_dupes.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    total_rows = 0
    for table in tables:
        n = 0
        for old, keep in plan:
            cur = conn.execute(
                f"UPDATE {table} SET player_en = ? WHERE player_en = ?",
                (keep, old))
            n += cur.rowcount
        conn.commit()
        print(f"      {table:<18} {n} سجل")
        total_rows += n

    # ---- التحقق بعد الدمج ----
    after = conn.execute("""
        SELECT COUNT(DISTINCT player_en) FROM goals WHERE player_en != ''
    """).fetchone()[0]

    print(f"\n{'=' * 62}")
    print(f"  انوحّد: {len(plan)} صيغة   |   سجلات معدّلة: {total_rows}")
    print(f"  أسماء مختلفة بجدول goals الآن: {after}")
    print(f"{'=' * 62}")
    print("""
  ⚠️ ملف players_ar.csv صار فيه صيغ لم تعد موجودة.
     أعد تصديره:  python export_players_ar.py

  الخطوة الجاية:
      python export_players_ar.py
      python merge_players_ar.py
      python apply_players_ar.py
      python make_site3.py + make_clubs.py + make_matches.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
