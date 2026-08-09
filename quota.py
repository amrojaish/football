#!/usr/bin/env python3
"""
فحص الحصة المتبقية
===================
بيقلك كم طلب استهلكت وكم ضايل من حصتك اليومية.

التشغيل:
    python quota.py
"""

import requests
from config import API_BASE, check_key, headers


def main():
    if not check_key():
        return

    try:
        r = requests.get(f"{API_BASE}/status",
                         headers=headers(), timeout=20)
        data = r.json().get("response", {})
    except Exception as e:
        print(f"ما قدرت أوصل للـAPI: {e}")
        return

    if not data:
        print("ما رجع رد — تأكد من المفتاح")
        return

    sub = data.get("subscription", {})
    req = data.get("requests", {})

    used = req.get("current", 0)
    limit = req.get("limit_day", 100)
    left = limit - used

    # شريط بصري بسيط
    filled = int((used / limit) * 30) if limit else 0
    bar = "#" * filled + "." * (30 - filled)

    print("\n" + "=" * 45)
    print(f"  الخطة:      {sub.get('plan', '؟')}")
    print(f"  الحد اليومي: {limit}")
    print("=" * 45)
    print(f"\n  [{bar}]\n")
    print(f"  استهلكت:  {used}")
    print(f"  ضايل:     {left}")

    # تقدير كم عملية بتقدر تعمل
    print("\n" + "-" * 45)
    print("  بالحصة الضايلة بتقدر تعمل تقريباً:")
    print(f"    - تشغيلة build_db كاملة (26 طلب):  {left // 26}")
    print(f"    - تشغيلة show_matches (7 طلبات):   {left // 7}")

    if left < 15:
        print("\n  تنبيه: الحصة شارفت تخلص. استنى بكرة.")
    elif left < 40:
        print("\n  الحصة نص. خطط لباقي اليوم.")

    print()


if __name__ == "__main__":
    main()
