#!/usr/bin/env python3
"""
سحب المباريات — نسخة مقاومة لانقطاع الشبكة
=============================================
نفس المنطق التزايدي، بس مع:
  - إعادة محاولة عند فشل الشبكة (مع تأخير متزايد)
  - تخطي الماتش الفاشل بدل انهيار البرنامج
  - حفظ مستمر فما بينضيع شي عند التوقف
  - تقرير بالمباريات اللي فشلت

التشغيل:
    python fetch_matches2.py IRQ --budget 400
    python fetch_matches2.py IRQ --check
"""

import requests
import sqlite3
import time
import sys

from config import API_BASE, SEASON, DB_FILE, LEAGUES, check_key, headers

DELAY = 1.0          # الفاصل بين الطلبات
TIMEOUT = 30         # مهلة الطلب الواحد
MAX_RETRIES = 3      # عدد المحاولات قبل التخطي


def parse_args():
    code, budget = "JOR", 50
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


def get(endpoint, params, label=""):
    """
    بيرجع (نجح؟, البيانات, سبب الفشل)
    بيحاول عدة مرات، وكل محاولة بتأخير أطول.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{API_BASE}/{endpoint}",
                             headers=headers(), params=params,
                             timeout=TIMEOUT)

            if r.status_code == 429:
                wait = attempt * 10
                print(f"      تجاوز المعدل — انتظار {wait}ث")
                time.sleep(wait)
                continue

            if r.status_code != 200:
                return False, [], f"HTTP {r.status_code}"

            data = r.json()
            errors = data.get("errors")
            if errors and isinstance(errors, dict) and errors:
                return False, [], f"API: {errors}"

            return True, data.get("response", []), ""

        except requests.exceptions.Timeout:
            wait = attempt * 3
            if attempt < MAX_RETRIES:
                print(f"      مهلة انتهت — إعادة محاولة بعد {wait}ث "
                      f"({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                return False, [], "مهلة انتهت"

        except requests.exceptions.ConnectionError:
            wait = attempt * 5
            if attempt < MAX_RETRIES:
                print(f"      انقطاع اتصال — إعادة بعد {wait}ث "
                      f"({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                return False, [], "انقطاع اتصال"

        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def stored_ids(conn, code):
    rows = conn.execute("""
        SELECT match_id FROM matches
        WHERE league_code = ? AND season = ?
    """, (code, SEASON)).fetchall()
    return {r[0] for r in rows}


def main():
    if not check_key():
        return

    code, budget, check_only = parse_args()

    if code not in LEAGUES:
        print(f"دوري غير معروف: {code}")
        return

    league = LEAGUES[code]
    conn = sqlite3.connect(DB_FILE)

    print(f"\n{'=' * 55}")
    print(f"  {league['name_ar']} — موسم {SEASON}")
    print(f"{'=' * 55}")

    ok, fixtures, reason = get("fixtures", {"league": league["id"],
                                            "season": SEASON,
                                            "status": "FT"})
    if not ok:
        print(f"  فشل جلب القائمة: {reason}")
        conn.close()
        return

    if not fixtures:
        print("  ما رجعت مباريات")
        conn.close()
        return

    have = stored_ids(conn, code)
    missing = [f for f in fixtures if f["fixture"]["id"] not in have]

    print(f"""
  إجمالي الموسم:  {len(fixtures)}
  موجود عندك:     {len(have)}
  ناقص:           {len(missing)}
    """)

    if not missing:
        print("  الموسم مكتمل\n")
        conn.close()
        return

    if check_only:
        print("  [وضع الفحص]\n")
        conn.close()
        return

    to_fetch = missing[:budget - 1]
    print(f"  رح أسحب {len(to_fetch)} ماتش "
          f"(~{len(to_fetch) * DELAY / 60:.0f} دقيقة)\n")

    saved = failed = 0
    total_goals = 0
    failed_list = []

    for i, fx in enumerate(to_fetch, 1):
        mid = fx["fixture"]["id"]
        label = (f"{fx['teams']['home']['name']} vs "
                 f"{fx['teams']['away']['name']}")

        success, events, reason = get("fixtures/events", {"fixture": mid})

        if not success:
            print(f"  [{i}/{len(to_fetch)}] تخطي — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            failed_list.append((mid, label, reason))
            time.sleep(DELAY)
            continue

        # نخزّن الماتش فقط بعد نجاح جلب أحداثه
        conn.execute("""
            INSERT OR REPLACE INTO matches
            (match_id, league_code, season, date,
             home_id, away_id, home_goals, away_goals, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mid, code, SEASON, fx["fixture"]["date"][:10],
              fx["teams"]["home"]["id"], fx["teams"]["away"]["id"],
              fx["goals"]["home"], fx["goals"]["away"], "FT"))

        conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))

        for e in events:
            if e.get("type") != "Goal":
                continue
            if e.get("detail") == "Missed Penalty":
                continue
            conn.execute("""
                INSERT INTO goals
                (match_id, team_id, minute, player_en, player_ar, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (mid, e["team"]["id"], e["time"]["elapsed"],
                  e["player"]["name"] or "", "", e.get("detail", "")))
            total_goals += 1

        conn.commit()
        saved += 1

        if i % 20 == 0 or i == len(to_fetch):
            done = len(have) + saved
            print(f"  [{i}/{len(to_fetch)}]  "
                  f"الموسم: {done}/{len(fixtures)}  "
                  f"({done / len(fixtures) * 100:.0f}%)")

        time.sleep(DELAY)

    print(f"""
{'=' * 55}
  نجح: {saved}  |  فشل: {failed}  |  أهداف: {total_goals}
{'=' * 55}""")

    if failed_list:
        print("\n  المباريات اللي فشلت:")
        for mid, label, reason in failed_list[:10]:
            print(f"    {mid}  {label}  [{reason}]")
        print("\n  شغّل نفس الأمر مرة تانية وبيحاول فيهم.")

    still = len(missing) - saved
    if still:
        print(f"\n  لسا ناقص {still} ماتش — أعد التشغيل بنفس الأمر.")
    else:
        print("\n  الموسم مكتمل. شغّل: python make_site3.py")

    conn.close()


if __name__ == "__main__":
    main()
