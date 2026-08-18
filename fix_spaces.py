#!/usr/bin/env python3
"""
تنظيف المسافات الزائدة في أسماء اللاعبين
===========================================
المزوّد يخزّن أحياناً مسافات زائدة داخل الاسم أو في نهايته:

    "Abdullah Al Ammar"        ← الصحيح
    "Abdullah Al Ammar      "  ← نفس اللاعب، مسافات في النهاية
    "Mohammed  Abu Al-Shamat"  ← مسافتان في الوسط

`auto_merge_names.py` يمسك هذه الحالة عند **المقارنة**، لكن
`apply_player_merges.py` يقارن بالاسم الحرفي فيفشل — لأن
الطرفين يبدوان متطابقين بعد التنظيف فيبدو كأنه يدمج الاسم بنفسه.

الحل الصحيح: **تنظيف المصدر** لا إضافة سطر دمج.

يعمل على أربعة جداول: goals · lineup_players ·
player_stats · events

⚠️ نسخة احتياطية قبل أي كتابة.

التشغيل:
    python fix_spaces.py --check    <- عرض فقط
    python fix_spaces.py            <- تنفيذ
"""

import os
import shutil
import sqlite3
import sys

DB = "football.db"
CHECK = "--check" in sys.argv

# الجدول → أعمدة الأسماء فيه
TARGETS = {
    "goals": ["player_en", "player_ar", "assist_en"],
    "lineup_players": ["player_en", "player_ar"],
    "player_stats": ["player_en", "player_ar"],
    "events": ["player_en", "player_ar", "assist_en"],
    "lineups": ["coach_en", "coach_ar"],
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def tidy(s):
    """يزيل المسافات الطرفية ويحوّل المتعددة إلى واحدة"""
    if s is None:
        return None
    return " ".join(str(s).split())


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 62)
    print("  فحص المسافات الزائدة")
    print("=" * 62)

    total = 0
    plan = []

    for table, cols in TARGETS.items():
        # التأكد من وجود الجدول والأعمدة
        try:
            have = {c[1] for c in
                    conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if not have:
            continue

        cols = [c for c in cols if c in have]
        if not cols:
            continue

        for col in cols:
            rows = list(conn.execute(f"""
                SELECT DISTINCT {col} AS v FROM {table}
                WHERE {col} IS NOT NULL AND {col} != ''
            """))

            bad = []
            for r in rows:
                v = r["v"]
                t = tidy(v)
                if t != v:
                    bad.append((v, t))

            if not bad:
                continue

            print(f"\n  {table}.{col} — {len(bad)} قيمة")
            for v, t in bad[:12]:
                print(f"      {v!r}")
                print(f"      → {t!r}")
            if len(bad) > 12:
                print(f"      ... و{len(bad) - 12} غيرها")

            total += len(bad)
            plan.append((table, col, bad))

    print()
    print("=" * 62)

    if not total:
        print("  ✅ ما في مسافات زائدة — الداتا نظيفة")
        print("=" * 62 + "\n")
        conn.close()
        return

    print(f"  إجمالي القيم التي تحتاج تنظيفاً: {total}")
    print("=" * 62)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        conn.close()
        return

    conn.close()
    shutil.copy(DB, "football_before_spaces.db")
    print("\n  نسخة احتياطية: football_before_spaces.db")

    conn = sqlite3.connect(DB)
    changed = 0

    for table, col, bad in plan:
        for v, t in bad:
            cur = conn.execute(
                f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                (t, v))
            changed += cur.rowcount

    conn.commit()
    conn.close()

    print(f"  سجلات معدّلة: {changed}")
    print("""
  الخطوة الجاية:
      python find_dupes.py          <- تأكد أن التكرار اختفى
      python make_site3.py
      python make_clubs.py
      python make_matches.py
      python make_search.py
    """)


if __name__ == "__main__":
    main()
