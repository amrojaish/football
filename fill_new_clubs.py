#!/usr/bin/env python3
"""
تعبئة أسماء الأندية الصاعدة — السعودي 2026-27
================================================
بيعبّي أسماء الأندية الثلاثة الصاعدة بملف teams_arabic.csv:
    2930  الفيصلي   Al-Faisaly   المجمعة
    2951  أبها       Abha         أبها
    26738 الدرعية    Al-Diriyah   الدرعية

المصادر: ويكيبيديا (الدوري السعودي 2026-27 ودوري الدرجة الأولى
2025-26) + Arab News.

⚠️ الفيصلي السعودي (2930) غير الفيصلي الأردني (4531) — ناديان
   مختلفان بنفس الاسم العربي، ولكل منهما معرّف ودوري مختلف.

بيعمل نسخة احتياطية قبل الكتابة، وما بيلمس أي نادٍ آخر.
إعادة التشغيل آمنة.

التشغيل:
    python fill_new_clubs.py --check    <- عرض بس
    python fill_new_clubs.py            <- تنفيذ
"""

import csv
import sys
import shutil
from config import TEAMS_FILE

CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


NEW = {
    "2930": {
        "name_ar": "نادي الفيصلي",
        "short_name_ar": "الفيصلي",
        "name_en_official": "Al-Faisaly",
        "city": "Al Majma'ah",
    },
    "2951": {
        "name_ar": "نادي أبها",
        "short_name_ar": "أبها",
        "name_en_official": "Abha",
        "city": "Abha",
    },
    "26738": {
        "name_ar": "نادي الدرعية",
        "short_name_ar": "الدرعية",
        "name_en_official": "Al-Diriyah",
        "city": "Diriyah",
    },
}


def main():
    if not TEAMS_FILE.exists():
        print("ما لقيت teams_arabic.csv")
        return

    with open(TEAMS_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if "name_en_official" not in fields:
        i = fields.index("name_en") + 1 if "name_en" in fields else len(fields)
        fields.insert(i, "name_en_official")

    print(f"\n{'=' * 58}")
    print("  الأندية الصاعدة — السعودي 2026-27")
    print(f"{'=' * 58}")

    filled = already = notfound = 0
    seen = set()

    for row in rows:
        tid = (row.get("team_id") or "").strip()
        row.setdefault("name_en_official", "")

        if tid not in NEW:
            continue

        seen.add(tid)
        vals = NEW[tid]
        cur_ar = (row.get("short_name_ar") or "").strip()

        if cur_ar == vals["short_name_ar"]:
            print(f"\n  ✅ {tid}  {vals['short_name_ar']}  —  معبّأ أصلاً")
            already += 1
            continue

        print(f"\n  ➕ {tid}")
        print(f"     عربي     : {vals['name_ar']}  ({vals['short_name_ar']})")
        print(f"     إنجليزي  : {vals['name_en_official']}")
        print(f"     المدينة  : {vals['city']}")

        if CHECK_ONLY:
            continue

        for k, v in vals.items():
            row[k] = v
        filled += 1

    notfound = [t for t in NEW if t not in seen]
    for t in notfound:
        print(f"\n  ❌ {t} — مش موجود بالملف")
        print("     شغّل: python update_teams.py 2026 SAU")

    if not CHECK_ONLY and filled:
        backup = TEAMS_FILE.parent / "teams_arabic_before_new.csv"
        shutil.copy(TEAMS_FILE, backup)
        with open(TEAMS_FILE, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"\n  نسخة احتياطية: {backup.name}")

    print(f"\n{'=' * 58}")
    if CHECK_ONLY:
        print("  [وضع الفحص] — ما انكتب شي")
        print(f"  جاهز للتعبئة: {filled}  |  معبّأ أصلاً: {already}")
    else:
        print(f"  انعبّى: {filled}  |  كان معبّأ: {already}")
    if notfound:
        print(f"  مفقود: {len(notfound)}")
    print(f"{'=' * 58}")

    if filled and not CHECK_ONLY:
        print("""
  الخطوة الجاية:
      python sync_teams.py
      python make_site3.py
        """)


if __name__ == "__main__":
    main()
