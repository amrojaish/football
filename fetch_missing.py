#!/usr/bin/env python3
"""
جلب اسمي الناديين المفقودين — 17472 و 22188
=============================================
ظهرا في مباريات الأردني 2026-27 (أول مباراة 3 سبتمبر) لكنهما
غير موجودين في teams_arabic.csv، فلا صفحات لهما ولا مبارياتهما
تظهر — make_clubs.py و make_matches.py يتخطيانهما.

بيطبع الاسم والبلد والمدينة ورابط الشعار.

⚠️ **لا يعدّل أي ملف.** الإضافة لـteams_arabic.csv يدوية بعد
   مراجعة الأسماء العربية.

الكلفة: طلبان اثنان فقط.

التشغيل:
    python fetch_missing.py
"""

import json
import urllib.request

from config import API_BASE, API_KEY, check_key, headers

MISSING = [17472, 22188]


def get_team(tid):
    url = f"{API_BASE}/teams?id={tid}"
    req = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not check_key():
        return

    print("=" * 55)

    for tid in MISSING:
        print(f"\n  النادي {tid}")
        print("  " + "-" * 51)

        try:
            data = get_team(tid)
        except Exception as e:
            print(f"  ❌ فشل الطلب: {type(e).__name__}")
            continue

        # درس: المزوّد يرجع 200 مع أخطاء داخل errors
        errs = data.get("errors")
        if errs:
            print(f"  ❌ خطأ من المزوّد: {errs}")
            continue

        resp = data.get("response") or []
        if not resp:
            print("  ⚠️ ما رجّع بيانات لهذا المعرّف")
            continue

        team = resp[0].get("team", {})
        venue = resp[0].get("venue", {})

        print(f"  الاسم      : {team.get('name')}")
        print(f"  الاسم المختصر: {team.get('code')}")
        print(f"  البلد      : {team.get('country')}")
        print(f"  التأسيس    : {team.get('founded')}")
        print(f"  الملعب     : {venue.get('name')}")
        print(f"  المدينة    : {venue.get('city')}")
        print(f"  الشعار     : {team.get('logo')}")

    print("\n" + "=" * 55)
    print("  استُهلك: طلبان")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
