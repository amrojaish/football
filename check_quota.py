#!/usr/bin/env python3
"""
فحص حصة API-Football
======================
يقرأ الحصة من نقطة /status — **طلب واحد فقط**، ولا يُحتسب
على الحصة اليومية عند معظم الخطط.

يعرض:
    الخطة · المستهلك اليوم · المتبقي · حد الدقيقة
وتقديراً لما تكفيه الحصة المتبقية من عمليات السحب.

⚠️ إعادة التعيين 00:00 UTC = 03:00 بتوقيت الأردن.

التشغيل:
    python check_quota.py
"""

import json
import urllib.request

from config import API_BASE, check_key, headers

# تكلفة العمليات الشائعة (طلب لكل مباراة)
COSTS = {
    "تفاصيل السعودي 2023 (4 سكربتات × 306)": 1224,
    "أحداث فقط (306)": 306,
    "دورة أتمتة واحدة بلا مباريات": 10,
    "دورة أتمتة في يوم جولة كاملة": 60,
}


def main():
    if not check_key():
        return

    url = f"{API_BASE}/status"
    req = urllib.request.Request(url, headers=headers())

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ❌ فشل الطلب: {type(e).__name__}")
        return

    errs = data.get("errors")
    if errs:
        print(f"  ❌ خطأ من المزوّد: {errs}")
        return

    resp = data.get("response") or {}
    sub = resp.get("subscription") or {}
    req_info = resp.get("requests") or {}

    used = req_info.get("current")
    limit = req_info.get("limit_day")

    print()
    print("=" * 56)
    print("  حصة API-Football")
    print("=" * 56)
    print(f"  الخطة        : {sub.get('plan')}")
    print(f"  فعّالة       : {sub.get('active')}")
    print(f"  تنتهي        : {sub.get('end')}")
    print()

    if used is None or limit is None:
        print("  ⚠️ المزوّد ما رجّع أرقام الحصة")
        print(f"  الاستجابة الخام: {resp}")
        return

    left = limit - used
    pct = (used / limit * 100) if limit else 0
    bar_n = int(pct / 2.5)
    bar = "█" * bar_n + "░" * (40 - bar_n)

    print(f"  مستهلك اليوم : {used:,} / {limit:,}   ({pct:.1f}%)")
    print(f"  [{bar}]")
    print(f"  **المتبقي**  : {left:,} طلب")
    print()
    print("  ⚠️ إعادة التعيين 00:00 UTC = 03:00 بتوقيت الأردن")

    print()
    print("-" * 56)
    print("  هل تكفي المتبقية؟")
    print("-" * 56)
    for label, cost in COSTS.items():
        mark = "✅" if left >= cost else "❌"
        print(f"  {mark}  {label:<42} {cost:>5}")

    # احتياطي للأتمتة حتى منتصف الليل
    print()
    reserve = 24 * 2 * 10  # دورتان بالساعة × 10 طلبات
    print(f"  ⚠️ احجز ~{reserve} طلباً للأتمتة (كل 30 دقيقة).")
    safe = left - reserve
    print(f"     المتاح بأمان للسحب اليدوي: {max(safe, 0):,}")

    print()


if __name__ == "__main__":
    main()
