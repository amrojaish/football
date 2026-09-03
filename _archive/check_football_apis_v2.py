#!/usr/bin/env python3
"""
النسخة 2 — فحص عملي حقيقي
==========================
الهدف: نشوف هدف حقيقي بدقيقته واسم هدافه من الدوري الأردني والعراقي والسعودي.
مش بس نصدّق علامة ✅ من الـAPI.

التشغيل:
    python check_football_apis_v2.py
"""

import requests
import time

# ==========================================================
API_FOOTBALL_KEY = "ef532d52a54b6364ec2ffbe9a61c2423"   # حط مفتاحك هون
# ==========================================================

BASE = "https://v3.football.api-sports.io"
SEASONS_TO_TRY = [2025, 2024, 2023, 2022, 2021]

OK = "\033[92m[نعم]\033[0m"
NO = "\033[91m[لا]\033[0m"
WARN = "\033[93m[تنبيه]\033[0m"


def get(endpoint, params):
    r = requests.get(f"{BASE}/{endpoint}",
                     headers={"x-apisports-key": API_FOOTBALL_KEY},
                     params=params, timeout=25)
    data = r.json()
    if data.get("errors"):
        errs = data["errors"]
        if errs and not isinstance(errs, list):
            print(f"   {WARN} رسالة من الـAPI: {errs}")
    return data.get("response", [])


def has_arabic(text):
    return any("\u0600" <= ch <= "\u06FF" for ch in str(text))


def find_league(country_variants, keyword):
    """بيدور على الدوري الرئيسي لدولة، بيجرب أكتر من صيغة للاسم"""
    for name in country_variants:
        leagues = get("leagues", {"country": name, "type": "League"})
        if leagues:
            for item in leagues:
                lg = item["league"]
                if keyword.lower() in lg["name"].lower() or len(leagues) == 1:
                    return lg["id"], lg["name"], name
            lg = leagues[0]["league"]
            return lg["id"], lg["name"], name
        time.sleep(1)
    return None, None, None


def test_league(label, country_variants, keyword):
    print("\n" + "=" * 58)
    print(f"  {label}")
    print("=" * 58)

    lid, lname, matched = find_league(country_variants, keyword)
    if not lid:
        print(f"{NO} ما لقيت دوري لهالدولة")
        return

    print(f"{OK} {lname}  (id={lid})  [اسم الدولة الصحيح: {matched}]")

    # ندور على ماتش منتهي بأي موسم متاح
    for season in SEASONS_TO_TRY:
        time.sleep(1)
        fixtures = get("fixtures", {"league": lid, "season": season,
                                    "status": "FT"})
        if not fixtures:
            print(f"   موسم {season}: ما في مباريات متاحة")
            continue

        print(f"\n{OK} موسم {season}: عدد المباريات المنتهية = {len(fixtures)}")

        fx = fixtures[-1]
        fid = fx["fixture"]["id"]
        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        gh = fx["goals"]["home"]
        ga = fx["goals"]["away"]
        date = fx["fixture"]["date"][:10]

        print(f"   ماتش للفحص: {home} {gh}-{ga} {away}  ({date})")
        print(f"   الأسماء عربية من الـAPI؟ "
              f"{OK if has_arabic(home) else NO + ' <-- شغل الأسماء عليك'}")

        # الفحص الحقيقي: الأحداث
        time.sleep(1)
        events = get("fixtures/events", {"fixture": fid})
        goals = [e for e in events if e.get("type") == "Goal"]

        if goals:
            print(f"\n   {OK} الأحداث شغالة فعلياً — {len(goals)} هدف:")
            for g in goals:
                scorer = g["player"]["name"]
                minute = g["time"]["elapsed"]
                team = g["team"]["name"]
                print(f"      د.{minute}'  {scorer}  ({team})")
            print(f"\n   ==> هاد بالضبط اللي بتحتاجه لإشعار الهدف")
        else:
            print(f"   {NO} ما رجعت أحداث — العلامة الخضرا كانت وعد مش واقع")

        return  # لقينا موسم شغال، بنوقف

    print(f"{WARN} ما في ولا موسم متاح بالخطة المجانية لهالدوري")


def check_quota():
    print("\n" + "=" * 58)
    print("  حصتك اليومية")
    print("=" * 58)
    r = requests.get(f"{BASE}/status",
                     headers={"x-apisports-key": API_FOOTBALL_KEY}, timeout=20)
    d = r.json().get("response", {})
    req = d.get("requests", {})
    sub = d.get("subscription", {})
    print(f"   الخطة: {sub.get('plan')}")
    print(f"   استهلكت: {req.get('current')} من {req.get('limit_day')} باليوم")


def main():
    if not API_FOOTBALL_KEY:
        print("حط المفتاح بأول الملف أول")
        return

    print("\n" + "#" * 58)
    print("#  الفحص العملي — بدنا نشوف أهداف حقيقية")
    print("#" * 58)

    test_league("الأردن", ["Jordan"], "League")
    test_league("العراق", ["Iraq"], "League")
    test_league("السعودية", ["Saudi-Arabia", "Saudi Arabia", "Saudi"], "Pro")

    check_quota()

    print("\n" + "=" * 58)
    print("""
  القراءة:
  - إذا شفت أسماء هدافين ودقائق  --> الفكرة قابلة للتنفيذ، امشِ
  - إذا مباريات بدون أحداث       --> نتائج وترتيب بس، بدون إشعارات لحظية
  - إذا ولا موسم متاح            --> الخطة المجانية ما بتكفي، بدها اشتراك
    """)


if __name__ == "__main__":
    main()
