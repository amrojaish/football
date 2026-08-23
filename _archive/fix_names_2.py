#!/usr/bin/env python3
"""
تصحيح ترجمتين خاطئتين (22 أغسطس)
===================================
كشفهما حاجز `build_merges.py`: صيغتان ظهرتا **في كشف المباراة
نفسه**، أي أنهما لاعبان مختلفان أُعطيا الاسم العربي ذاته
(درس 70).

  1. `N. Al Sadi` (id=578978، الشباب 2025، 3 مباريات)
     كان مترجَماً "نواف الصعدي" — وهذا اسم لاعب آخر
     (id=310869: الشباب ← ضمك إعارةً ← الخليج).
     **تُفرَّغ** — الفراغ يرتد للإنجليزي، والتخمين يثبّت خطأً
     (درس 61).

  2. `Hawswi` (id=388481، حارس مرمى: ضمك ثم الاتفاق)
     كان "عبدالله هوساوي" والصحيح **عبدالباسط هوساوي**.
     عبدالله الهوساوي هو id=325902 (النجمة).

⚠️ حالتان أخريان كشفهما الحاجز **ليستا خطأً**: `الخيبري`
   و`العقل` — شخصان مختلفان يحملان الاسم نفسه فعلاً (درس 26).
   لا تصحيح لهما، والمطلوب فقط ألّا يندمجا.

⚠️ يعدّل `players_ar.csv` والديتابيس معاً. نسخة احتياطية أولاً.

    python fix_names_2.py --check
    python fix_names_2.py
"""

import csv
import sqlite3
import shutil
import sys
from config import DB_FILE, BASE_DIR

CHECK = "--check" in sys.argv
MAIN = BASE_DIR / "players_ar.csv"

FIXES = {
    "N. Al Sadi": "",                    # مجهول — يُفرَّغ
    "Hawswi": "عبدالباسط هوساوي",
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
    print("=" * 60)
    changed = []
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
        label = new or "(يُفرَّغ)"
        print(f"  {en:16} {cur or '(غير موجود بالملف)'} -> {label}"
              f"   [{n} سجلاً]")
        changed.append((en, new, n))
    print("=" * 60)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        conn.close()
        return

    shutil.copy(MAIN, BASE_DIR / "players_ar_backup.csv")
    shutil.copy(DB_FILE, BASE_DIR / "football_before_namefix.db")

    for x in rows:
        en = x.get("player_en", "").strip()
        if en in FIXES:
            x["player_ar"] = FIXES[en]

    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total = 0
    for en, new in FIXES.items():
        for t in ("goals", "lineup_players", "player_stats", "events"):
            try:
                cur = conn.execute(
                    f"UPDATE {t} SET player_ar = ? WHERE player_en = ?",
                    (new, en))
                total += cur.rowcount
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()

    print(f"\n  نسخ احتياطية: players_ar_backup.csv + football_before_namefix.db")
    print(f"  سجلات محدَّثة بالديتابيس: {total}")
    print("""
  الخطوة الجاية:
      python export_to_translate.py     (N. Al Sadi سيظهر ضمن الفاضي)
      python build_merges.py            (يجب أن تختفي الحالتان)
    """)


if __name__ == "__main__":
    main()
