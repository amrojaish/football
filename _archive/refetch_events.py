#!/usr/bin/env python3
"""
إعادة سحب الأحداث الناقصة
===========================
بيسحب أحداث المباريات اللي طلعت فاضية بالسحب الأول،
بس هالمرة:
  - بمعدل آمن (طلب كل 7 ثواني = ~8 بالدقيقة)
  - مع فحص فعلي للأخطاء بدل ابتلاعها
  - مع إعادة محاولة عند الفشل

التشغيل:
    python refetch_events.py --budget 40
    python refetch_events.py JOR --budget 40
    python refetch_events.py --check          <- عرض بس

مهم: بياخد وقت — كل ماتش ~7 ثواني.
     40 ماتش = حوالي 5 دقايق. خليه يشتغل.
"""

import requests
import sqlite3
import time
import sys

from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

# الفاصل بين الطلبات — هذا هو الإصلاح الأساسي
DELAY = 1.0
MAX_RETRIES = 2


def parse_args():
    code = None
    budget = 30
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].upper() in LEAGUES:
        code = args[0].upper()

    if "--budget" in sys.argv:
        i = sys.argv.index("--budget")
        if i + 1 < len(sys.argv):
            try:
                budget = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, budget, check_only


def fetch_events(match_id):
    """
    بيرجع (نجح؟, الأحداث, سبب الفشل)
    بدل ما يبتلع الخطأ زي الكود القديم.
    """
    try:
        r = requests.get(f"{API_BASE}/fixtures/events",
                         headers=headers(),
                         params={"fixture": match_id}, timeout=25)
    except Exception as e:
        return False, [], f"شبكة: {e}"

    if r.status_code == 429:
        return False, [], "تجاوز معدل الطلبات (429)"

    if r.status_code != 200:
        return False, [], f"HTTP {r.status_code}"

    try:
        data = r.json()
    except Exception:
        return False, [], "رد غير صالح"

    errors = data.get("errors")
    # الـAPI أحياناً بيرجع errors كقاموس فيه تفاصيل
    if errors and isinstance(errors, dict) and errors:
        return False, [], f"خطأ API: {errors}"

    return True, data.get("response", []), ""


def missing_matches(conn, code=None):
    """المباريات اللي فيها أهداف بالنتيجة بس بلا أحداث مسجّلة"""
    q = """
        SELECT m.match_id, m.league_code, m.date,
               m.home_goals + m.away_goals AS goals,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE (m.home_goals + m.away_goals) > 0
          AND (SELECT COUNT(*) FROM goals g
               WHERE g.match_id = m.match_id) = 0
    """
    params = []
    if code:
        q += " AND m.league_code = ?"
        params.append(code)
    q += " ORDER BY m.date DESC"

    return conn.execute(q, params).fetchall()


def main():
    if not check_key():
        return

    code, budget, check_only = parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    missing = missing_matches(conn, code)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا أحداث: {len(missing)}")
    print(f"{'=' * 58}")

    by_league = {}
    for m in missing:
        by_league[m["league_code"]] = by_league.get(m["league_code"], 0) + 1
    for lg, n in by_league.items():
        print(f"  {LEAGUES[lg]['name_ar']}: {n}")

    if not missing:
        print("\n  ما في شي ناقص\n")
        conn.close()
        return

    if check_only:
        print("\n  [وضع الفحص] — ما انسحب شي\n")
        conn.close()
        return

    to_fetch = missing[:budget]
    mins = len(to_fetch) * DELAY / 60

    print(f"""
  رح أسحب {len(to_fetch)} ماتش
  الفاصل بين الطلبات: {DELAY} ثانية (لتجنّب تجاوز المعدل)
  الوقت المتوقع: ~{mins:.0f} دقيقة

  خليه يشتغل ولا تسكّره.
{'=' * 58}
    """)

    ok = failed = empty = 0
    total_goals = 0

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} vs {m['away']}"

        success, events, reason = False, [], ""

        for attempt in range(MAX_RETRIES + 1):
            if attempt:
                print(f"      إعادة محاولة {attempt} ...")
                time.sleep(DELAY)

            success, events, reason = fetch_events(mid)
            if success:
                break

        if not success:
            print(f"  [{i}/{len(to_fetch)}] فشل — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            time.sleep(DELAY)
            continue

        goals = [e for e in events
         if e.get("type") == "Goal"
         and e.get("detail") != "Missed Penalty"]

        if not goals:
            # رد سليم بس فاضي فعلاً
            print(f"  [{i}/{len(to_fetch)}] فاضي فعلاً — {label} "
                  f"(النتيجة تقول {m['goals']} أهداف)")
            empty += 1
        else:
            conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))
            for g in goals:
                conn.execute("""
                    INSERT INTO goals
                    (match_id, team_id, minute, player_en, player_ar, detail)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (mid, g["team"]["id"], g["time"]["elapsed"],
                      g["player"]["name"] or "", "", g.get("detail", "")))
            conn.commit()
            total_goals += len(goals)
            ok += 1

            status = "✓" if len(goals) == m["goals"] else "~"
            print(f"  [{i}/{len(to_fetch)}] {status} {label} — "
                  f"{len(goals)}/{m['goals']} هدف")

        time.sleep(DELAY)

    remaining = len(missing) - len(to_fetch)

    print(f"""
{'=' * 58}
  نجح: {ok}  |  فاضي فعلاً: {empty}  |  فشل: {failed}
  أهداف أُضيفت: {total_goals}
{'=' * 58}""")

    if failed:
        print("""
  في طلبات فشلت — على الأغلب الحصة خلصت.
  جرّب بكرة بنفس الأمر.""")

    if remaining:
        print(f"""
  لسا ناقص {remaining} ماتش.
  شغّل نفس الأمر بكرة وبيكمل.""")

    print("""
  للتحقق من النتيجة:
      python audit.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
