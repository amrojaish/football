#!/usr/bin/env python3
"""
فحص: هل يوفّر المزوّد player_id للأردني والعراقي؟
====================================================
جدول `goals` لا يحمل `player_id` — لهذا احتجنا
`player_merges.csv` أصلاً، ولهذا لا يمكن بناء صفحة لاعب
موثوقة للأردني والعراقي بالربط بالاسم.

درس 25 يقول إن المزوّد لا يوفّر **تفاصيل المباريات**
(`fixtures/players`) لهذين الدوريين. لكن هناك نقطة **أخرى**
لم تُفحص: `players/squads` — قوائم لاعبي النادي.

إن كانت متوفّرة، فلكل لاعب `player_id` حقيقي، وتُحلّ مشكلة
الربط من جذرها.

الفحص: نادٍ أردني + نادٍ عراقي + نادٍ سعودي (مرجع للمقارنة).

⚠️ **لا يكتب شيئاً.** فحص قراءة فقط.

الكلفة: 3 طلبات.

التشغيل:
    python probe_squads.py
"""

import json
import urllib.request

from config import API_BASE, check_key, headers

# نادٍ من كل دوري
TARGETS = [
    (4537, "الوحدات", "JOR"),
    (5242, "الشرطة", "IRQ"),
    (2939, "النصر", "SAU"),
]


def get(endpoint, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_BASE}/{endpoint}?{q}"
    req = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not check_key():
        return

    print()
    print("=" * 60)
    print("  هل يوفّر المزوّد قوائم اللاعبين بمعرّفاتهم؟")
    print("=" * 60)

    results = {}

    for tid, name, code in TARGETS:
        print()
        print("-" * 60)
        print(f"  {name}  ({code})  —  team={tid}")
        print("-" * 60)

        try:
            data = get("players/squads", {"team": tid})
        except Exception as e:
            print(f"  ❌ فشل الطلب: {type(e).__name__}")
            results[code] = 0
            continue

        errs = data.get("errors")
        if errs:
            print(f"  ❌ خطأ من المزوّد: {errs}")
            results[code] = 0
            continue

        resp = data.get("response") or []
        if not resp:
            print("  ⚠️ ما رجّع شي — القائمة غير متوفّرة")
            results[code] = 0
            continue

        players = resp[0].get("players") or []
        results[code] = len(players)

        print(f"  ✅ رجّع {len(players)} لاعباً")

        if players:
            print("\n  عيّنة (أول 5):")
            for p in players[:5]:
                print(f"    id={p.get('id'):<8} {p.get('name')}"
                      f"   #{p.get('number')}  {p.get('position')}")

    # ── الخلاصة ───────────────────────────────────────
    print()
    print("=" * 60)
    print("  الخلاصة")
    print("=" * 60)

    for _, name, code in TARGETS:
        n = results.get(code, 0)
        mark = "✅" if n else "❌"
        print(f"  {mark}  {code}  {name:<12} {n} لاعباً")

    jor = results.get("JOR", 0)
    irq = results.get("IRQ", 0)

    print()
    if jor and irq:
        print("  ✅ **المعرّفات متوفّرة للدوريين.**")
        print("     يمكن بناء طبقة player_id حقيقية بدل الربط")
        print("     بالاسم — تُحلّ المشكلة من جذرها.")
        print()
        print("     ⚠️ لكن انتبه: القائمة تعطي لاعبي النادي")
        print("        **الحاليين** لا مسجّلي الأهداف التاريخيين.")
        print("        الربط بالأهداف يبقى بالاسم، لكن يصير")
        print("        لدينا مرجع معرّفات نطابق عليه.")
    elif jor or irq:
        print("  ⚠️ متوفّرة لدوري واحد فقط — حل جزئي.")
    else:
        print("  ❌ **غير متوفّرة.** الربط بالاسم هو الخيار")
        print("     الوحيد للأردني والعراقي، معتمداً على")
        print("     player_merges.csv لتوحيد الصيغ.")

    print()
    print("  استُهلك: 3 طلبات")
    print()


if __name__ == "__main__":
    main()
