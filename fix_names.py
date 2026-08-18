#!/usr/bin/env python3
"""
تنظيف أسماء اللاعبين — أرقام ملتصقة ومسافات زائدة
====================================================
جدول `goals` فيه 46 سجلاً باسم لاعب مشوّه:

    '1                         Sumayhan Al Nabit'   ← رقم قبل
    'I. Toney                                  6'   ← رقم بعد
    'Abdullah Al Ammar                        '     ← مسافات فقط
    'Mohammed  Abu Al-Shamat'                       ← مسافة مزدوجة

[مرجّح] الرقم هو دقيقة المباراة — حقلان انضغطا في حقل واحد
عند السحب. الموقع يتبدّل (قبل/بعد) فليس نمطاً واحداً.

⚠️ **لماذا تنظيف المسافات وحده لا يكفي:**
   ' '.join(s.split()) يحوّل '0    A. Hamed Allah' إلى
   '0 A. Hamed Allah' — أي يحفظ الرقم داخل الاسم إلى الأبد.
   لذلك نجرّد الرقم الطرفي **أولاً**، ثم ننظّف المسافات.

⚠️ **شرط أمان:** لا يُجرَّد الرقم إلا إذا كان **معزولاً بمسافات
   متعددة** — حتى لا نتلف اسماً يحوي رقماً مشروعاً.

**الأثر المتوقع:**
    34 اسماً لهم صيغة نظيفة موجودة → يندمجون فوراً
     7 أسماء بلا صيغة نظيفة        → أهدافهم كانت **مفقودة**
                                      من قوائم الهدافين وتعود

الجداول: goals · lineup_players · player_stats · events · lineups

⚠️ نسخة احتياطية قبل أي كتابة.

التشغيل:
    python fix_names.py --check    <- عرض فقط
    python fix_names.py            <- تنفيذ
"""

import os
import re
import shutil
import sqlite3
import sys

DB = "football.db"
CHECK = "--check" in sys.argv

TARGETS = {
    "goals": ["player_en", "player_ar", "assist_en"],
    "lineup_players": ["player_en", "player_ar"],
    "player_stats": ["player_en", "player_ar"],
    "events": ["player_en", "player_ar", "assist_en"],
    "lineups": ["coach_en", "coach_ar"],
}

# رقم معزول بمسافتين فأكثر — في البداية أو النهاية
LEAD = re.compile(r"^\s*\d{1,3}\s{2,}")
TRAIL = re.compile(r"\s{2,}\d{1,3}\s*$")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def tidy(s):
    """يجرّد الرقم الطرفي المعزول ثم يوحّد المسافات"""
    if s is None:
        return None
    v = str(s)
    v = LEAD.sub("", v)
    v = TRAIL.sub("", v)
    return " ".join(v.split())


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 64)
    print("  تنظيف أسماء اللاعبين")
    print("=" * 64)

    plan = []
    total = 0
    merged = new = 0

    for table, cols in TARGETS.items():
        try:
            have = {c[1] for c in
                    conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if not have:
            continue

        for col in [c for c in cols if c in have]:
            rows = list(conn.execute(f"""
                SELECT DISTINCT {col} AS v FROM {table}
                WHERE {col} IS NOT NULL AND {col} != ''
            """))

            bad = []
            for r in rows:
                v = r["v"]
                t = tidy(v)
                if t and t != v:
                    bad.append((v, t))

            if not bad:
                continue

            print(f"\n  {table}.{col} — {len(bad)} قيمة")

            for v, t in bad:
                # هل الاسم النظيف موجود أصلاً؟
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                    (t,)).fetchone()[0]
                if n:
                    merged += 1
                    mark = f"↩ يندمج مع سجل موجود ({n})"
                else:
                    new += 1
                    mark = "★ كان مفقوداً — يعود للقوائم"
                if len(bad) <= 50:
                    print(f"      {v!r}")
                    print(f"      → {t!r}   {mark}")

            total += len(bad)
            plan.append((table, col, bad))

    print()
    print("=" * 64)

    if not total:
        print("  ✅ الأسماء نظيفة — ما في شي للتصحيح")
        print("=" * 64 + "\n")
        conn.close()
        return

    print(f"  قيم تحتاج تنظيفاً : {total}")
    print(f"  منها تندمج مع موجود : {merged}")
    print(f"  منها كانت مفقودة    : {new}  ★")
    print("=" * 64)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        conn.close()
        return

    conn.close()
    shutil.copy(DB, "football_before_names.db")
    print("\n  نسخة احتياطية: football_before_names.db")

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
      python auto_merge_names.py --check   <- صيغ جديدة للتوحيد؟
      python find_dupes.py                 <- تأكد
      python make_site3.py
      python make_clubs.py
      python make_matches.py
      python make_search.py
    """)


if __name__ == "__main__":
    main()
