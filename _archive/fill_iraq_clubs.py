#!/usr/bin/env python3
"""
تعبئة أسماء الأندية الصاعدة — العراقي 2026-27
================================================
    28222  الجولان      Al-Jolan      الأنبار
    28223  غاز الشمال   Ghaz Al-Shamal  كركوك

المصادر:
  - صحيفة الخليج (22 و25 مايو 2026): الجولان بطل الدوري الممتاز
    بـ80 نقطة وصعد لدوري النجوم لأول مرة بتاريخه، وغاز الشمال
    الوصيف بـ74 نقطة من محافظة كركوك
  - صحيفة الزمان: قائمة أندية دوري نجوم العراق 2026-27 وفيها الاثنان
  - شفق نيوز والمدى وأشورلاند

⚠️ الجولان من محافظة الأنبار (مثل الكرمة) — صرّح رئيس الاتحاد
   عدنان درجال بوجود فريقين من الأنبار في دوري النجوم.

بيعمل نسخة احتياطية قبل الكتابة. إعادة التشغيل آمنة.

التشغيل:
    python fill_iraq_clubs.py --check    <- عرض بس
    python fill_iraq_clubs.py            <- تنفيذ
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
    "28222": {
        "name_ar": "نادي الجولان",
        "short_name_ar": "الجولان",
        "name_en_official": "Al-Jolan",
        "city": "Anbar",
    },
    "28223": {
        "name_ar": "نادي غاز الشمال",
        "short_name_ar": "غاز الشمال",
        "name_en_official": "Ghaz Al-Shamal",
        "city": "Kirkuk",
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
    print("  الأندية الصاعدة — العراقي 2026-27")
    print(f"{'=' * 58}")

    filled = already = 0
    seen = set()

    for row in rows:
        tid = (row.get("team_id") or "").strip()
        row.setdefault("name_en_official", "")

        if tid not in NEW:
            continue

        seen.add(tid)
        vals = NEW[tid]
        cur = (row.get("short_name_ar") or "").strip()

        if cur == vals["short_name_ar"]:
            print(f"\n  ✅ {tid}  {vals['short_name_ar']}  —  معبّأ أصلاً")
            already += 1
            continue

        print(f"\n  ➕ {tid}")
        print(f"     عربي     : {vals['name_ar']}  ({vals['short_name_ar']})")
        print(f"     إنجليزي  : {vals['name_en_official']}")
        print(f"     المحافظة : {vals['city']}")

        if CHECK_ONLY:
            continue

        for k, v in vals.items():
            row[k] = v
        filled += 1

    notfound = [t for t in NEW if t not in seen]
    for t in notfound:
        print(f"\n  ❌ {t} — مش موجود بالملف")
        print("     شغّل: python update_teams.py 2026 IRQ")

    if not CHECK_ONLY and filled:
        backup = TEAMS_FILE.parent / "teams_arabic_before_iraq.csv"
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
