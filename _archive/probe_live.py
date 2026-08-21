#!/usr/bin/env python3
"""
فحص: هل نقطة البث المباشر متاحة؟
==================================
المستخدم رأى مباراتين عراقيتين **مباشرتين** (دقيقة 45 و43،
نتيجة 0-1 و0-0) على FotMob، بينما موقعه يعرضهما "لم تبدأ".

السبب المرجَّح: سكربتات المشروع لا تستعمل نقطة `live` إطلاقاً —
`fetch_upcoming.py` يجلب المجدولة، و`fetch_matches2.py` يجلب
المنتهية. لا أحد يسأل: "ما الذي يُلعب الآن؟"

الخطة Pro تدعم البث المباشر نظرياً. هذا السكربت يتحقق عملياً
بطلبين:

    1. fixtures?live=all         → كل المباريات الجارية عالمياً
    2. fixtures?live={league_ids} → دورياتنا الثلاثة فقط

ويعرض لكل مباراة: الدقيقة · النتيجة · الحالة — لنعرف يقيناً
إن كانت البيانات متاحة لنا أم لا.

⚠️ للقراءة فقط. الكلفة: طلبان.

التشغيل:
    python probe_live.py
"""

import json
import urllib.request

from config import API_BASE, LEAGUES, check_key, headers


def get(endpoint):
    url = f"{API_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def show(data, title):
    print()
    print("=" * 62)
    print(f"  {title}")
    print("=" * 62)

    errs = data.get("errors")
    if errs:
        print(f"  \u274c خطأ من المزوّد: {errs}")
        if isinstance(errs, dict) and any(
                "plan" in str(v).lower() or "subscription" in str(v).lower()
                for v in errs.values()):
            print("  \u26a0\ufe0f الخطة لا تدعم هذه النقطة")
        return 0

    resp = data.get("response") or []
    print(f"  عدد المباريات الجارية: {len(resp)}")

    if not resp:
        print("\n  \u26a0\ufe0f صفر — إما لا مباريات الآن، أو النقطة")
        print("     لا ترجع شيئاً لخطتك")
        return 0

    for f in resp[:15]:
        fx = f.get("fixture", {})
        lg = f.get("league", {})
        tm = f.get("teams", {})
        gl = f.get("goals", {})
        st = fx.get("status", {})

        home = (tm.get("home") or {}).get("name", "?")
        away = (tm.get("away") or {}).get("name", "?")
        elapsed = st.get("elapsed")
        short = st.get("short")

        print(f"\n    [{lg.get('id')}] {lg.get('name')} — "
              f"{lg.get('country')}")
        print(f"      {home} {gl.get('home')}-{gl.get('away')} {away}")
        print(f"      الدقيقة: {elapsed}   الحالة: {short}")
        print(f"      fixture_id: {fx.get('id')}")

    if len(resp) > 15:
        print(f"\n    ... و{len(resp) - 15} مباراة أخرى")

    return len(resp)


def main():
    if not check_key():
        return

    # ── 1. كل المباريات الجارية عالمياً ───────────────
    try:
        d1 = get("fixtures?live=all")
        n1 = show(d1, "كل المباريات الجارية عالمياً (live=all)")
    except Exception as e:
        print(f"\n  \u274c فشل الطلب: {type(e).__name__}: {e}")
        n1 = 0

    # ── 2. دورياتنا فقط ───────────────────────────────
    ids = []
    for code, cfg in LEAGUES.items():
        lid = cfg.get("id") if isinstance(cfg, dict) else cfg
        if lid:
            ids.append(str(lid))

    if ids:
        joined = "-".join(ids)
        try:
            d2 = get(f"fixtures?live={joined}")
            n2 = show(d2, f"دورياتنا فقط (live={joined})")
        except Exception as e:
            print(f"\n  \u274c فشل الطلب: {type(e).__name__}: {e}")
            n2 = 0
    else:
        print("\n  \u26a0\ufe0f ما قدرت أقرأ معرّفات الدوريات من config")
        n2 = 0

    print()
    print("=" * 62)
    print("  الخلاصة")
    print("=" * 62)
    if n1 or n2:
        print("  \u2705 **نقطة البث المباشر تعمل مع خطتك.**")
        print("     الحل: سكربت جديد يسحب live كل بضع دقائق")
        print("     ويحدّث النتيجة والدقيقة — بلا اشتراك إضافي.")
    else:
        print("  \u26a0\ufe0f ما رجّعت مباريات. إما لا شيء يُلعب الآن،")
        print("     أو النقطة غير متاحة. أعد التشغيل أثناء مباراة")
        print("     مؤكَّدة لتحسم الأمر.")
    print()


if __name__ == "__main__":
    main()
