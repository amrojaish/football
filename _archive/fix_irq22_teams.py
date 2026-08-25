#!/usr/bin/env python3
"""
تصحيح هوية فريق بمباراتين — العراقي 2022 (25 أغسطس)
========================================================
كُشف بمقارنة ترتيب المزوّد (find_missing22.py، درس 85):
6 أزواج أندية لم تلتقِ العدد الصحيح من المرات — 3 "زائدة"
تقابلها 3 "ناقصة"، بسبب تشابه الأسماء عند المزوّد
(النفط / نفط ميسان / نفط البصرة).

⚠️ **هذا خطأ في هوية الفريق لا في النتيجة** — لذلك لا يُصحَّح
   عبر match_corrections.csv (يغيّر النتيجة فقط)، بل بتعديل
   مباشر على home_id/away_id.

المستخدم تحقّق من الموقع الرسمي للاتحاد العراقي (لا مصدر
مولَّد) وأكّد اثنتين من ثلاث حالات:

  match_id=1028170  2023-05-23  الفائز (home) مسجَّل "النفط"
                                 والصحيح "نفط ميسان"
  match_id=1028178  2023-05-25  الخاسر (away) مسجَّل "النجف"
                                 والصحيح "النفط"

⚠️ **الحالة الثالثة (match_id=968008، 2022-10-29، الديوانية
   2-2 النفط) لم تُؤكَّد** — لم تُوجَد في مصدر الاتحاد العراقي،
   فتبقى كما هي دون تصحيح. راجع درس 61: الفراغ آمن أفضل من
   تخمين مبني على فراغ الجدول.

⚠️ لا يغيّر النتيجة (الأهداف) — فقط أي طرف (home/away) هو
   الفريق الصحيح. نسخة احتياطية قبل الكتابة.

    python fix_irq22_teams.py --check
    python fix_irq22_teams.py
"""

import sqlite3
import shutil
import sys
from config import DB_FILE, BASE_DIR

CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (match_id, الطرف المصحَّح "home"/"away", الاسم الخاطئ المتوقَّع، الاسم الصحيح)
FIXES = [
    (1028170, "home", "النفط",  "نفط ميسان"),
    (1028178, "away", "النجف",  "النفط"),
]


def team_id(conn, name):
    r = conn.execute(
        "SELECT team_id FROM teams WHERE short_name_ar=?", (name,)
    ).fetchone()
    return r[0] if r else None


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 64)
    plan = []
    for mid, side, wrong_name, right_name in FIXES:
        m = conn.execute(
            "SELECT * FROM matches WHERE match_id=?", (mid,)).fetchone()
        if not m:
            print(f"  ⚠️ match_id={mid} غير موجود — تخطّي")
            continue

        col = f"{side}_id"
        cur_id = m[col]
        wrong_id = team_id(conn, wrong_name)
        right_id = team_id(conn, right_name)
        if right_id is None:
            print(f"  ⚠️ نادٍ غير موجود بجدول teams: {right_name} — تخطّي")
            continue

        cur_name = conn.execute(
            "SELECT short_name_ar FROM teams WHERE team_id=?",
            (cur_id,)).fetchone()
        cur_name = cur_name[0] if cur_name else f"id={cur_id}"

        h = conn.execute("SELECT short_name_ar FROM teams WHERE team_id=?",
                         (m["home_id"],)).fetchone()[0]
        a = conn.execute("SELECT short_name_ar FROM teams WHERE team_id=?",
                         (m["away_id"],)).fetchone()[0]
        print(f"  match_id={mid}  {m['date'][:10]}  "
              f"{h} {m['home_goals']}-{m['away_goals']} {a}")

        if cur_id != wrong_id:
            print(f"     ⚠️ {side}_id الحالي = {cur_name}، "
                  f"لكن المتوقَّع كان {wrong_name} — تحقّق يدوياً قبل المتابعة")
            continue

        print(f"     {side}: {cur_name} -> {right_name}")
        plan.append((mid, col, cur_id, right_id, cur_name, right_name))

    print("=" * 64)

    if not plan:
        print("\n  لا شيء قابل للتنفيذ\n")
        conn.close()
        return

    if CHECK:
        print(f"\n  [وضع الفحص] — {len(plan)} تصحيح جاهز، ما انكتب شي\n")
        conn.close()
        return

    shutil.copy(DB_FILE, BASE_DIR / "football_before_irq22fix.db")
    for mid, col, old_id, new_id, old_name, new_name in plan:
        conn.execute(f"UPDATE matches SET {col}=? WHERE match_id=?",
                     (new_id, mid))
    conn.commit()
    conn.close()

    print(f"\n  نسخة احتياطية: football_before_irq22fix.db")
    print(f"  صُحِّح: {len(plan)}")
    print("""
  الخطوة الجاية:
      python find_missing_season.py IRQ 2022
      (يجب أن يظهر: أزواج شاذة إجمالاً: 0 أو 2 فقط —
       الحالة الثالثة غير المؤكَّدة تبقى)
    """)


if __name__ == "__main__":
    main()
