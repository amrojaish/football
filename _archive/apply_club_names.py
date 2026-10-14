#!/usr/bin/env python3
"""
تطبيق الأسماء الإنجليزية الرسمية
==================================
بيقرأ club_names_review.csv وبيحدّث عمود name_en_official
بملف teams_arabic.csv.

⚠️ لا يلمس name_en الأصلي — هذا اسم المزوّد ويُحتفظ به كمرجع
   للمقارنة والتنقيح مستقبلاً (نفس فلسفة logo و logo_local).

الأسماء بمستوى ثقة [تخميني] تُترك فارغة — الكود يرتد لاسم
المزوّد عندها.

صفر طلبات API.

التشغيل:
    python apply_club_names.py --check    <- عرض بس
    python apply_club_names.py            <- تنفيذ
"""

import csv
import sys
import shutil
from config import TEAMS_FILE, BASE_DIR

REVIEW_FILE = BASE_DIR / "club_names_review.csv"
CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not TEAMS_FILE.exists():
        print("ما لقيت teams_arabic.csv")
        return

    if not REVIEW_FILE.exists():
        print(f"ما لقيت {REVIEW_FILE.name}")
        return

    # الأسماء المراجَعة
    official = {}
    skipped_low = []
    with open(REVIEW_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = (r.get("team_id") or "").strip()
            name = (r.get("official_english") or "").strip()
            conf = (r.get("confidence") or "").strip()
            if not tid or not name:
                continue
            if conf == "تخميني":
                skipped_low.append((tid, name))
                continue
            official[tid] = {"name": name, "conf": conf,
                             "note": (r.get("note") or "").strip()}

    # الملف الحالي
    with open(TEAMS_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if "name_en_official" not in fields:
        # نضيفه بعد name_en مباشرة
        i = fields.index("name_en") + 1 if "name_en" in fields else len(fields)
        fields.insert(i, "name_en_official")

    print(f"\n{'=' * 66}")
    print(f"  أسماء مراجَعة: {len(official)}")
    print(f"{'=' * 66}")

    changed = same = missing = 0

    for row in rows:
        tid = (row.get("team_id") or "").strip()
        row.setdefault("name_en_official", "")

        if tid not in official:
            if tid:
                missing += 1
            continue

        o = official[tid]
        api = (row.get("name_en") or "").strip()

        if api == o["name"]:
            same += 1
        else:
            changed += 1
            flag = "⚠️" if "تصحيح" in o["note"] else "  "
            print(f"\n  {flag} {tid}")
            print(f"     المزوّد : {api}")
            print(f"     الرسمي  : {o['name']}   [{o['conf']}]")

        if not CHECK_ONLY:
            row["name_en_official"] = o["name"]

    if not CHECK_ONLY:
        backup = TEAMS_FILE.parent / "teams_arabic_before_names.csv"
        shutil.copy(TEAMS_FILE, backup)
        with open(TEAMS_FILE, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    print(f"\n{'=' * 66}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انكتب شي")
    else:
        print(f"  نسخة احتياطية: teams_arabic_before_names.csv")
    print(f"  مختلف عن المزوّد: {changed}  |  مطابق: {same}"
          f"  |  بلا مراجعة: {missing}")
    if skipped_low:
        print(f"  متروك [تخميني]: {len(skipped_low)}")
    print(f"{'=' * 66}")

    if not CHECK_ONLY:
        print("""
  الخطوة الجاية:
      python sync_teams.py
      python make_site3.py
      python make_clubs.py
      python make_matches.py
        """)


if __name__ == "__main__":
    main()
