#!/usr/bin/env python3
"""
فحص المباريات القادمة
=======================
بيشوف كم مباراة غير منتهية عند المزوّد لكل دوري بالموسم الحالي،
قبل ما نقرر نسحبها.

حالات المباراة عند API-Football:
    NS   = لم تبدأ (Not Started)
    TBD  = الموعد غير محدد
    PST  = مؤجلة
    FT   = انتهت

بيستهلك طلب واحد لكل دوري (3 طلبات).

التشغيل:
    python check_upcoming.py
    python check_upcoming.py 2026
"""

import requests
import sys
from config import API_BASE, LEAGUES, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2026


def main():
    if not check_key():
        return

    print(f"\n{'=' * 62}")
    print(f"  المباريات القادمة — موسم {SEASON}")
    print(f"{'=' * 62}")

    total_all = 0

    for code, info in LEAGUES.items():
        try:
            r = requests.get(
                f"{API_BASE}/fixtures",
                headers=headers(),
                params={"league": info["id"], "season": SEASON},
                timeout=25,
            )
            data = r.json()
        except Exception as e:
            print(f"\n  {info['name_ar']}: فشل — {type(e).__name__}")
            continue

        errors = data.get("errors")
        if errors and isinstance(errors, dict) and errors:
            print(f"\n  {info['name_ar']}: خطأ API — {errors}")
            continue

        fx = data.get("response", [])
        if not fx:
            print(f"\n  {info['name_ar']}: ما في مباريات بهالموسم")
            continue

        # تجميع حسب الحالة
        by_status = {}
        for f in fx:
            s = f["fixture"]["status"]["short"]
            by_status[s] = by_status.get(s, 0) + 1

        upcoming = [f for f in fx
                    if f["fixture"]["status"]["short"] in ("NS", "TBD", "PST")]
        total_all += len(upcoming)

        print(f"\n  {'-' * 58}")
        print(f"  {info['name_ar']}   (إجمالي {len(fx)} مباراة)")
        print(f"  {'-' * 58}")
        for s, n in sorted(by_status.items(), key=lambda x: -x[1]):
            label = {
                "FT": "منتهية",
                "NS": "لم تبدأ",
                "TBD": "الموعد غير محدد",
                "PST": "مؤجلة",
            }.get(s, s)
            print(f"      {s:<5} {label:<20} {n}")

        if upcoming:
            print(f"\n      أقرب 5 مباريات:")
            for f in upcoming[:5]:
                d = f["fixture"]["date"][:16].replace("T", "  ")
                h = f["teams"]["home"]["name"]
                a = f["teams"]["away"]["name"]
                print(f"        {d}   {h}  vs  {a}")

    print(f"\n{'=' * 62}")
    print(f"  إجمالي المباريات القادمة: {total_all}")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
