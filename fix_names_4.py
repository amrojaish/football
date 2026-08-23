#!/usr/bin/env python3
"""
استبدال ثلاث ترجمات خاطئة (23 أغسطس — الدفعة الثانية)
=========================================================
كشفتها مراجعة الأسماء المتبقية، وأكّدها فحص `player_id`:

  M. Al Saad   : محمد آل سعد  -> مهند السعد
                 (id=439986 يظهر أيضاً باسم Muhannad Al Saad)
  L. Antunes   : ليونيل       -> ليوناردو أنتونيس   (id=41982)
  Z. Youssouf  : زكرياء       -> زايدو يوسف
                 (id=1272؛ الاسم الكامل عند المزوّد Zaydou Youssouf)

⚠️ **`merge_batch.py` لا يستبدل قيمة موجودة** — يطبع "تعارض"
   ويترك القديم. الاستبدال يحتاج خطوة صريحة.

⚠️ **ولم تُصحَّح `Y. Al Shammari`** رغم أن ترجمتها خاطئة لأحد
   اللاعبَين: الصيغة يتقاسمها **معرّفان** —
       id=44731  الحزم   = يوسف الشمري
       id=613458 الاتفاق = ياسر الشمري
   والترجمة تعمل على النص لا المعرّف، فتصحيحها يكسر الآخر
   (درس 78). عولجت جزئياً بترجمة `Yasir Shammari` منفصلةً.

⚠️ نسخة احتياطية قبل الكتابة.

    python fix_names_4.py --check
    python fix_names_4.py
"""

import csv
import sqlite3
import shutil
import sys
from config import DB_FILE, BASE_DIR

CHECK = "--check" in sys.argv
MAIN = BASE_DIR / "players_ar.csv"

FIXES = {
    "M. Al Saad":   "مهند السعد",
    "L. Antunes":   "ليوناردو أنتونيس",
    "Z. Youssouf":  "زايدو يوسف",
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    with open(MAIN, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fields = list(r.fieldnames)
        rows = list(r)

    conn = sqlite3.connect(DB_FILE)
    print()
    print("=" * 62)
    for en, new in FIXES.items():
        cur = next((x.get("player_ar", "").strip() for x in rows
                    if x.get("player_en", "").strip() == en), None)
        n = 0
        for t in ("goals", "lineup_players", "player_stats", "events"):
            try:
                n += conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE player_en = ?",
                    (en,)).fetchone()[0]
            except sqlite3.OperationalError:
                pass
        print(f"  {en:16} {cur or '(غير موجود)':20} -> {new:20} [{n} سجلاً]")
    print("=" * 62)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        conn.close()
        return

    shutil.copy(MAIN, BASE_DIR / "players_ar_backup.csv")
    shutil.copy(DB_FILE, BASE_DIR / "football_before_namefix4.db")

    seen = set()
    for x in rows:
        en = x.get("player_en", "").strip()
        if en in FIXES:
            x["player_ar"] = FIXES[en]
            seen.add(en)

    # الصيغ غير الموجودة بالملف تُضاف
    for en, new in FIXES.items():
        if en not in seen:
            nr = {k: "" for k in fields}
            nr["player_en"] = en
            nr["player_ar"] = new
            if "priority" in nr:
                nr["priority"] = "E"
            rows.append(nr)

    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total = 0
    for en, new in FIXES.items():
        for t in ("goals", "lineup_players", "player_stats", "events"):
            try:
                total += conn.execute(
                    f"UPDATE {t} SET player_ar = ? WHERE player_en = ?",
                    (new, en)).rowcount
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()

    print(f"\n  نسخ احتياطية: players_ar_backup.csv + football_before_namefix4.db")
    print(f"  سجلات محدَّثة: {total}")
    print("""
  الخطوة الجاية:
      python merge_batch.py --check
    """)


if __name__ == "__main__":
    main()
