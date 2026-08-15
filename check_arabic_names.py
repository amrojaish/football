#!/usr/bin/env python3
"""
فحص دعم المزوّد للأسماء العربية
==================================
بيجرّب عدة طرق للحصول على أسماء اللاعبين بالعربية:

  1. endpoint players مع معرّف لاعب معروف
  2. رأس Accept-Language: ar
  3. معامل lang / locale
  4. فحص كل الحقول الراجعة بحثاً عن نص عربي

بيستهلك ~4 طلبات.

التشغيل:
    python check_arabic_names.py
"""

import requests
import sqlite3
import json
import sys
from config import API_BASE, DB_FILE, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def has_arabic(text):
    """هل النص فيه حروف عربية؟"""
    if not isinstance(text, str):
        return False
    return any('\u0600' <= c <= '\u06FF' for c in text)


def scan(obj, path=""):
    """بيمشي على كل حقول الرد ويلاقي النصوص العربية"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += scan(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            found += scan(v, f"{path}[{i}]")
    elif has_arabic(obj):
        found.append((path, obj))
    return found


def main():
    if not check_key():
        return

    # نجيب معرّف لاعب معروف من الـDB
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT player_id, player_en FROM player_stats
        WHERE player_en != ''
        GROUP BY player_id
        ORDER BY SUM(COALESCE(minutes,0)) DESC LIMIT 1
    """).fetchone()
    conn.close()

    if row is None:
        print("ما لقيت لاعبين بجدول player_stats")
        return

    pid = row["player_id"]
    pname = row["player_en"]

    print(f"\n{'=' * 62}")
    print(f"  فحص الأسماء العربية")
    print(f"{'=' * 62}")
    print(f"  لاعب الاختبار: {pname}  (id={pid})")

    tests = [
        ("عادي", f"{API_BASE}/players/profiles",
         {"player": pid}, headers()),

        ("Accept-Language: ar", f"{API_BASE}/players/profiles",
         {"player": pid},
         dict(headers(), **{"Accept-Language": "ar"})),

        ("معامل lang=ar", f"{API_BASE}/players/profiles",
         {"player": pid, "lang": "ar"}, headers()),

        ("بحث بالاسم", f"{API_BASE}/players/profiles",
         {"search": "Ronaldo"}, headers()),
    ]

    for label, url, params, hdrs in tests:
        print(f"\n{'-' * 62}")
        print(f"  {label}")
        print(f"{'-' * 62}")

        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=25)
        except Exception as e:
            print(f"      فشل: {type(e).__name__}")
            continue

        if r.status_code != 200:
            print(f"      HTTP {r.status_code}")
            continue

        try:
            data = r.json()
        except Exception:
            print("      رد غير صالح")
            continue

        errors = data.get("errors")
        if errors and isinstance(errors, dict) and errors:
            print(f"      خطأ API: {errors}")
            continue

        resp = data.get("response", [])
        if not resp:
            print("      رد فارغ")
            continue

        # عرض الحقول المتاحة
        first = resp[0]
        player = first.get("player") if isinstance(first, dict) else None
        if player:
            print(f"      الحقول المتاحة:")
            for k, v in player.items():
                if isinstance(v, (str, int, float, type(None))):
                    print(f"          {k:<16} = {v}")

        arabic = scan(resp[:2])
        if arabic:
            print(f"\n      ✅ نصوص عربية موجودة:")
            for path, val in arabic[:10]:
                print(f"          {path} = {val}")
        else:
            print(f"\n      ❌ ما في نص عربي بالرد")

    print(f"\n{'=' * 62}")
    print("""
  الخلاصة:
  لو ما ظهر أي نص عربي بأي محاولة، المزوّد لا يوفّر
  الأسماء العربية، والترجمة اليدوية هي الخيار الوحيد.
""")


if __name__ == "__main__":
    main()
