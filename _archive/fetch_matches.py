#!/usr/bin/env python3
"""
سحب تزايدي للمباريات
======================
بيسحب المباريات الناقصة بس، ضمن ميزانية طلبات تحددها،
وبيقدر يكمل من وين وقف لما تشغّله مرة تانية.

التشغيل:
    python fetch_matches.py JOR --budget 60
    python fetch_matches.py JOR              <- الميزانية الافتراضية 50
    python fetch_matches.py JOR --check      <- عرض الحالة بدون سحب

مثال على الاستخدام عبر أيام:
    اليوم:  python fetch_matches.py JOR --budget 60   -> 60 ماتش
    بكرة:   python fetch_matches.py JOR --budget 80   -> يكمل الباقي
"""

import requests
import sqlite3
import time
import sys

from config import API_BASE, SEASON, DB_FILE, LEAGUES, check_key, headers


def parse_args():
    code = "JOR"
    budget = 50
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        code = args[0].upper()

    if "--budget" in sys.argv:
        i = sys.argv.index("--budget")
        if i + 1 < len(sys.argv):
            try:
                budget = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, budget, check_only


def get(endpoint, params):
    r = requests.get(f"{API_BASE}/{endpoint}",
                     headers=headers(), params=params, timeout=25)
    return r.json().get("response", [])


def quota_left():
    """بيرجع كم طلب ضايل — هالطلب نفسه ما بينحسب"""
    try:
        r = requests.get(f"{API_BASE}/status", headers=headers(), timeout=20)
        d = r.json().get("response", {}).get("requests", {})
        return d.get("limit_day", 100) - d.get("current", 0)
    except Exception:
        return None


def stored_match_ids(conn, code):
    """أرقام المباريات الموجودة أصلاً بالديتابيس لهذا الدوري"""
    rows = conn.execute(
        "SELECT match_id FROM matches WHERE league_code = ? AND season = ?",
        (code, SEASON)
    ).fetchall()
    return {r[0] for r in rows}


def main():
    if not check_key():
        return

    code, budget, check_only = parse_args()

    if code not in LEAGUES:
        print(f"دوري غير معروف: {code}  (JOR / IRQ / SAU)")
        return

    league = LEAGUES[code]
    conn = sqlite3.connect(DB_FILE)

    # فحص الحصة قبل أي شي
    left = quota_left()
    if left is not None:
        print(f"\nالحصة المتبقية: {left}")
        if budget > left - 2:
            budget = max(0, left - 2)   # نترك هامش أمان
            print(f"عدّلت الميزانية لـ {budget} حسب الحصة")

    if budget < 2:
        print("الحصة ما بتكفي — استنى بكرة")
        conn.close()
        return

    print(f"\n{'=' * 55}")
    print(f"  {league['name_ar']} — موسم {SEASON}")
    print(f"{'=' * 55}")

    # طلب واحد: قائمة كل المباريات المنتهية
    print("بجيب قائمة المباريات ... (طلب واحد)")
    fixtures = get("fixtures", {"league": league["id"],
                                "season": SEASON, "status": "FT"})

    if not fixtures:
        print("ما رجعت مباريات")
        conn.close()
        return

    have = stored_match_ids(conn, code)
    missing = [f for f in fixtures if f["fixture"]["id"] not in have]

    print(f"""
  إجمالي مباريات الموسم:  {len(fixtures)}
  موجود عندك أصلاً:        {len(have)}
  ناقص:                    {len(missing)}
  ميزانية هذه الجلسة:      {budget - 1} ماتش
    """)

    if not missing:
        print("  الموسم مكتمل — ما في شي جديد\n")
        conn.close()
        return

    if check_only:
        print("  [وضع الفحص] — ما انسحب شي\n")
        conn.close()
        return

    to_fetch = missing[:budget - 1]
    print(f"  رح أسحب {len(to_fetch)} ماتش ...\n")

    saved_goals = 0

    for i, fx in enumerate(to_fetch, 1):
        mid = fx["fixture"]["id"]

        conn.execute("""
            INSERT OR REPLACE INTO matches
            (match_id, league_code, season, date,
             home_id, away_id, home_goals, away_goals, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mid, code, SEASON, fx["fixture"]["date"][:10],
            fx["teams"]["home"]["id"], fx["teams"]["away"]["id"],
            fx["goals"]["home"], fx["goals"]["away"], "FT"
        ))

        conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))

        time.sleep(1)
        events = get("fixtures/events", {"fixture": mid})

        for e in events:
            if e.get("type") != "Goal":
                continue
            conn.execute("""
                INSERT INTO goals
                (match_id, team_id, minute, player_en, player_ar, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (mid, e["team"]["id"], e["time"]["elapsed"],
                  e["player"]["name"] or "", "", e.get("detail", "")))
            saved_goals += 1

        conn.commit()

        # شريط تقدم بسيط
        if i % 5 == 0 or i == len(to_fetch):
            done = len(have) + i
            pct = done / len(fixtures) * 100
            print(f"  [{i}/{len(to_fetch)}]  "
                  f"إجمالي الموسم: {done}/{len(fixtures)}  ({pct:.0f}%)")

    still_missing = len(missing) - len(to_fetch)

    print(f"\n{'=' * 55}")
    print(f"  انسحب: {len(to_fetch)} ماتش  |  {saved_goals} هدف")
    print(f"{'=' * 55}")

    if still_missing:
        print(f"""
  لسا ناقص {still_missing} ماتش.
  بكرة شغّل نفس الأمر وبيكمل من وين وقف:

      python fetch_matches.py {code} --budget 90
        """)
    else:
        print(f"""
  الموسم مكتمل. جدول الترتيب صار دقيق فعلياً.
  شغّل:  python make_site2.py
        """)

    conn.close()


if __name__ == "__main__":
    main()
