#!/usr/bin/env python3
"""
تحديث جدول الأندية — بالدمج مش الاستبدال
==========================================
بيسحب أندية موسم معيّن، وبيضيف الجديد بس.
الأسماء العربية والمدن والشعارات اللي عبّيتها بتضل محفوظة.

التشغيل:
    python update_teams.py 2025          <- كل الدوريات
    python update_teams.py 2025 JOR      <- دوري محدد
    python update_teams.py 2025 --check  <- عرض بس
"""

import requests
import csv
import time
import sys

from config import API_BASE, TEAMS_FILE, LEAGUES, check_key, headers

FIELDS = ["league_code", "league_ar", "team_id", "name_en", "name_ar",
          "short_name_ar", "city", "logo", "logo_local", "logo_note"]


def parse_args():
    season = None
    code = None
    check_only = "--check" in sys.argv

    for a in sys.argv[1:]:
        if a.startswith("--"):
            continue
        if a.isdigit():
            season = int(a)
        elif a.upper() in LEAGUES:
            code = a.upper()

    return season, code, check_only


def load_existing():
    """بيقرأ الملف الحالي — القاموس مفتاحه team_id"""
    rows = {}
    if not TEAMS_FILE.exists():
        return rows

    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = (r.get("team_id") or "").strip()
            if tid:
                rows[tid] = {k: (r.get(k) or "").strip() for k in FIELDS}
    return rows


def fetch(league_id, season):
    r = requests.get(f"{API_BASE}/teams", headers=headers(),
                     params={"league": league_id, "season": season},
                     timeout=25)
    return r.json().get("response", [])


def main():
    if not check_key():
        return

    season, code, check_only = parse_args()

    if not season:
        print("لازم تحدد الموسم:  python update_teams.py 2025")
        return

    existing = load_existing()
    print(f"\nالملف الحالي فيه {len(existing)} نادي")

    codes = [code] if code else list(LEAGUES.keys())
    new_teams = []
    seen = 0

    for c in codes:
        info = LEAGUES[c]
        print(f"\nبسحب أندية {info['name_ar']} — موسم {season} ...")

        teams = fetch(info["id"], season)
        if not teams:
            print("   ما رجع ولا نادي")
            continue

        print(f"   رجع {len(teams)} نادي")
        seen += len(teams)

        for item in teams:
            t = item["team"]
            v = item.get("venue") or {}
            tid = str(t["id"])

            if tid in existing:
                continue   # موجود — ما نلمسه

            new_teams.append({
                "league_code": c,
                "league_ar": info["name_ar"],
                "team_id": tid,
                "name_en": t["name"],
                "name_ar": "",          # <- تعبّيه إنت
                "short_name_ar": "",    # <- تعبّيه إنت
                "city": v.get("city") or "",
                "logo": t.get("logo") or "",
                "logo_local": "",
                "logo_note": "",
            })

        time.sleep(1)

    print(f"\n{'=' * 55}")
    print(f"  أندية الموسم:   {seen}")
    print(f"  موجودة أصلاً:   {seen - len(new_teams)}")
    print(f"  جديدة:          {len(new_teams)}")
    print(f"{'=' * 55}")

    if not new_teams:
        print("\n  ما في أندية جديدة — الملف كامل\n")
        return

    print("\n  الأندية الجديدة:")
    for t in new_teams:
        print(f"    {t['team_id']:<8} {t['name_en']:<24} "
              f"{t['league_code']}   {t['city']}")

    if check_only:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    # نسخة احتياطية قبل الكتابة
    backup = TEAMS_FILE.parent / "teams_arabic_before_merge.csv"
    if TEAMS_FILE.exists():
        with open(TEAMS_FILE, encoding="utf-8-sig") as src:
            content = src.read()
        with open(backup, "w", encoding="utf-8-sig") as dst:
            dst.write(content)
        print(f"\n  نسخة احتياطية: {backup.name}")

    # نكتب القديم كما هو + الجديد
    all_rows = list(existing.values()) + new_teams

    with open(TEAMS_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)

    print(f"""
  انضاف {len(new_teams)} نادي.  المجموع: {len(all_rows)}

  المطلوب منك:
  افتح teams_arabic.csv وعبّي name_ar و short_name_ar
  للأندية الجديدة (الصفوف الأخيرة).

  بعدها:  python make_site3.py
    """)


if __name__ == "__main__":
    main()
