#!/usr/bin/env python3
"""
تعبئة أسماء أندية موسم 2023-24
=================================
    4543   سحاب        Sahab           عمّان (JOR)
    11474  الجليل      Al-Jalil        إربد (JOR)
    2942   الطائي      Al-Taee         حائل (SAU)
    11073  نفط الوسط   Naft Al-Wasat   النجف (IRQ)

المصادر: ويكيبيديا (Sahab SC, Al-Jalil SC Irbid) + TheSportsDB

⚠️ **6689 Newroz لا يُعبَّأ** — سجل مكرر لنوروز (25062) وموثّق
   في team_merges.csv. يبقى في teams حتى لا تختفي مبارياته قبل
   الدمج، لكن apply_merges.py يوحّده تلقائياً بعد السحب.

⚠️ مدينة الطائي عند المزوّد بترميز HTML: Ha&apos;il — تُنظَّف هنا.

بيعمل نسخة احتياطية. إعادة التشغيل آمنة.

التشغيل:
    python fill_2023_clubs.py --check
    python fill_2023_clubs.py
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
    "4543": {
        "name_ar": "نادي سحاب",
        "short_name_ar": "سحاب",
        "name_en_official": "Sahab",
        "city": "Amman",
    },
    "11474": {
        "name_ar": "نادي الجليل",
        "short_name_ar": "الجليل",
        "name_en_official": "Al-Jalil",
        "city": "Irbid",
    },
    "2942": {
        "name_ar": "نادي الطائي",
        "short_name_ar": "الطائي",
        "name_en_official": "Al-Taee",
        "city": "Hail",
    },
    "11073": {
        "name_ar": "نادي نفط الوسط",
        "short_name_ar": "نفط الوسط",
        "name_en_official": "Naft Al-Wasat",
        "city": "Najaf",
    },
}

# لا يُعبَّأ — مكرر ومدموج
SKIP = {"6689": "نوروز — سجل مكرر، يعالجه apply_merges.py"}


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
    print("  أندية موسم 2023-24")
    print(f"{'=' * 58}")

    filled = already = 0
    seen = set()

    for row in rows:
        tid = (row.get("team_id") or "").strip()
        row.setdefault("name_en_official", "")

        if tid in SKIP:
            print(f"\n  ⏭️ {tid} — {SKIP[tid]}")
            continue

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
        print(f"     المدينة  : {vals['city']}")

        if CHECK_ONLY:
            continue

        for k, v in vals.items():
            row[k] = v
        filled += 1

    notfound = [t for t in NEW if t not in seen]
    for t in notfound:
        print(f"\n  ❌ {t} — مش موجود بالملف")
        print("     شغّل: python update_teams.py 2023 <الدوري>")

    if not CHECK_ONLY and filled:
        backup = TEAMS_FILE.parent / "teams_arabic_before_2023.csv"
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
      python fetch_matches2.py JOR --season 2023 --budget 150
        """)


if __name__ == "__main__":
    main()
