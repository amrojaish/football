#!/usr/bin/env python3
"""
فحص الدوري القطري قبل الالتزام
==================================
فحص قراءة فقط — طلب واحد فقط. يجيب من /leagues كل المواسم
المتاحة لدوري نجوم قطر مع أعلام التغطية (أحداث/تشكيلات/
إحصائيات/لاعبين) لكل موسم، بنفس أسلوب فحص الأربعة دوريات
المرشحة قبل إضافة المصري (راجع بند مفتوح 6 بالREADME).

لا يكتب بالديتابيس ولا يستهلك أكثر من طلب واحد.

التشغيل:
    python check_qat_league.py
"""

import sys
import requests

from config import API_BASE, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    r = requests.get(f"{API_BASE}/leagues",
                      headers=headers(),
                      params={"search": "Qatar"},
                      timeout=30)
    data = r.json()

    errors = data.get("errors")
    if errors and isinstance(errors, dict) and errors:
        print(f"خطأ من الـAPI: {errors}")
        return

    resp = data.get("response", [])
    print(f"عدد النتائج: {len(resp)}\n")

    for item in resp:
        lg = item.get("league", {})
        country = item.get("country", {})
        print(f"{'=' * 60}")
        print(f"  id={lg.get('id')}  الاسم: {lg.get('name')}"
              f"  النوع: {lg.get('type')}  الدولة: {country.get('name')}")
        print(f"{'=' * 60}")

        for s in item.get("seasons", []):
            cov = s.get("coverage", {})
            fx = cov.get("fixtures", {})
            print(f"  موسم {s.get('year')}"
                  f"  ({s.get('start')} → {s.get('end')})"
                  f"  حالي: {s.get('current')}")
            print(f"      events={fx.get('events')}"
                  f"  lineups={fx.get('lineups')}"
                  f"  stats={fx.get('statistics_fixtures')}"
                  f"  players={fx.get('players_statistics')}"
                  f"  standings={cov.get('standings')}")


if __name__ == "__main__":
    main()
