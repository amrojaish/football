#!/usr/bin/env python3
"""
تشخيص: ليش ما في أحداث؟
=========================
بيعيد طلب أحداث ماتش واحد معروف إنه بلا أحداث بالديتابيس،
وبيطبع الرد الخام كامل — بما فيه رسائل الخطأ.

الهدف: نفرّق بين احتمالين
  أ) الـAPI فعلاً ما عنده أحداث لهالماتش
  ب) طلبنا فشل بصمت والكود ابتلع الخطأ

يكلّف: 1-3 طلبات فقط.

التشغيل:
    python diagnose.py
"""

import requests
import sqlite3
import json
import time
from config import API_BASE, DB_FILE, check_key, headers


def raw_request(endpoint, params):
    """بيرجع الرد الخام كامل — بدون ما يخفي شي"""
    r = requests.get(f"{API_BASE}/{endpoint}",
                     headers=headers(), params=params, timeout=25)
    return r.status_code, r.json()


def main():
    if not check_key():
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # نجيب ماتش فيه أهداف بالنتيجة بس بلا أحداث مسجّلة
    row = conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE (m.home_goals + m.away_goals) > 0
          AND (SELECT COUNT(*) FROM goals g
               WHERE g.match_id = m.match_id) = 0
        ORDER BY m.date DESC
        LIMIT 1
    """).fetchone()

    if not row:
        print("ما لقيت ماتش بلا أحداث — كل شي سليم")
        conn.close()
        return

    print(f"""
{'=' * 58}
  ماتش الاختبار
{'=' * 58}
  {row['home']} {row['home_goals']} - {row['away_goals']} {row['away']}
  التاريخ: {row['date']}
  رقم الماتش: {row['match_id']}

  النتيجة تقول {row['home_goals'] + row['away_goals']} أهداف،
  والديتابيس فيها 0 حدث.
    """)

    # الحصة قبل
    print("بفحص الحصة قبل الطلب ...")
    _, st = raw_request("status", {})
    req = st.get("response", {}).get("requests", {})
    before = req.get("current", "?")
    print(f"  مستهلك: {before} من {req.get('limit_day', '?')}\n")

    print("=" * 58)
    print("  الطلب الخام لأحداث الماتش")
    print("=" * 58)

    time.sleep(1)
    status, data = raw_request("fixtures/events",
                               {"fixture": row["match_id"]})

    print(f"\n  HTTP status: {status}")
    print(f"  عدد النتائج: {data.get('results', '?')}")

    errors = data.get("errors")
    if errors:
        print(f"\n  >>> رسائل خطأ من الـAPI:")
        print(f"      {json.dumps(errors, ensure_ascii=False)}")
    else:
        print(f"  رسائل خطأ: لا يوجد")

    resp = data.get("response", [])
    print(f"  طول مصفوفة response: {len(resp)}")

    if resp:
        goals = [e for e in resp if e.get("type") == "Goal"]
        print(f"\n  >>> رجعت {len(resp)} حدث، منها {len(goals)} هدف:")
        for g in goals:
            print(f"      د.{g['time']['elapsed']}'  {g['player']['name']}")

    # الحصة بعد
    time.sleep(1)
    _, st2 = raw_request("status", {})
    after = st2.get("response", {}).get("requests", {}).get("current", "?")

    print(f"\n  الحصة بعد الطلب: {after}")

    # الحكم
    print("\n" + "=" * 58)
    print("  التشخيص")
    print("=" * 58)

    if errors:
        print("""
  (ب) الطلب فشل — في رسالة خطأ من الـAPI.
      المشكلة بالكود/الخطة، مش بالداتا.
      اقرأ رسالة الخطأ أعلاه لتعرف السبب.
        """)
    elif resp:
        print("""
  (ب) الأحداث موجودة فعلاً عند الـAPI!
      يعني طلبنا الأول فشل بصمت وقت السحب.

      الحل: نعيد سحب المباريات الناقصة مع
      فحص الأخطاء هالمرة.
        """)
    else:
        print("""
  (أ) الـAPI فعلاً ما عنده أحداث لهذا الماتش.
      رد سليم، بدون أخطاء، ومصفوفة فاضية.

      يعني التغطية الجزئية حقيقية، وفكرة
      إشعارات الأهداف محدودة بشدة على هذه الخطة.
        """)

    if before != "?" and after != "?":
        used = after - before
        print(f"  ملاحظة: هذا الفحص استهلك {used} طلب.\n")

    conn.close()


if __name__ == "__main__":
    main()
