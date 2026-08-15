#!/usr/bin/env python3
"""
سحب البطاقات والتبديلات
==========================
بيسحب أحداث المباريات (غير الأهداف) ويخزّنها بجدول events.

ليش منفصل عن fetch_matches2.py:
هذا السكربت **لا يلمس** جدولي matches و goals إطلاقاً.
فالتصحيحات والاستثناءات والدمج كلها بأمان — ما في داعي
لإعادة تشغيل السلسلة بعده.

تزايدي: المباريات اللي عندها أحداث مخزّنة بينتخطاها.

التشغيل:
    python fetch_events.py --check              <- كم مباراة ناقصة
    python fetch_events.py --budget 400         <- كل الدوريات
    python fetch_events.py JOR --budget 200     <- دوري محدد
    python fetch_events.py JOR --season 2024 --budget 200
"""

import requests
import sqlite3
import time
import sys

from config import API_BASE, SEASON, DB_FILE, LEAGUES, check_key, headers

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3

# أنواع الأحداث اللي بنخزّنها (الأهداف لها جدولها الخاص)
KEEP_TYPES = {"Card", "subst", "Var"}


def parse_args():
    code, budget = None, 100
    season = None
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

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, budget, check_only, season


def get(endpoint, params):
    """بيرجع (نجح؟, البيانات, سبب الفشل) — لا يبتلع الأخطاء"""
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
            if attempt < MAX_RETRIES:
                print(f"      مهلة — إعادة ({attempt}/{MAX_RETRIES})")
                time.sleep(attempt * 3)
            else:
                return False, [], "مهلة انتهت"

        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                print(f"      انقطاع — إعادة ({attempt}/{MAX_RETRIES})")
                time.sleep(attempt * 5)
            else:
                return False, [], "انقطاع اتصال"

        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def pending(conn, code, season):
    """المباريات اللي ما عندها أحداث مخزّنة بعد"""
    q = """
        SELECT m.match_id, m.date, m.league_code, m.season,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM events e WHERE e.match_id = m.match_id
        )
    """
    params = []
    if code:
        q += " AND m.league_code = ?"
        params.append(code)
    if season is not None:
        q += " AND m.season = ?"
        params.append(season)
    q += " ORDER BY m.date DESC"

    return conn.execute(q, params).fetchall()


def main():
    if not check_key():
        return

    code, budget, check_only, season = parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # التأكد من وجود الجدول
    try:
        conn.execute("SELECT 1 FROM events LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول events غير موجود — شغّل add_events_table.py أول")
        conn.close()
        return

    todo = pending(conn, code, season)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا أحداث مخزّنة: {len(todo)}")
    print(f"{'=' * 58}")

    by = {}
    for m in todo:
        k = (m["league_code"], m["season"])
        by[k] = by.get(k, 0) + 1
    for (lg, s), n in sorted(by.items()):
        name = LEAGUES.get(lg, {}).get("name_ar", lg)
        print(f"  {name:<18} موسم {s}   {n}")

    if not todo:
        print("\n  ما في شي ناقص\n")
        conn.close()
        return

    if check_only:
        print(f"\n  [وضع الفحص] — ما انسحب شي")
        print(f"  الوقت المتوقع لو سحبتهم كلهم: "
              f"~{len(todo) * DELAY / 60:.0f} دقيقة\n")
        conn.close()
        return

    to_fetch = todo[:budget]
    print(f"\n  رح أسحب {len(to_fetch)} ماتش "
          f"(~{len(to_fetch) * DELAY / 60:.0f} دقيقة)")
    print("  خليه يشتغل ولا تسكّره.\n")

    ok = failed = empty = 0
    n_cards = n_subs = 0
    failed_list = []

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} × {m['away']}"

        success, events, reason = get("fixtures/events", {"fixture": mid})

        if not success:
            print(f"  [{i}/{len(to_fetch)}] فشل — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            failed_list.append((mid, label, reason))
            time.sleep(DELAY)
            continue

        rows = []
        for e in events:
            etype = e.get("type") or ""
            if etype not in KEEP_TYPES:
                continue

            player = (e.get("player") or {}).get("name") or ""
            assist = (e.get("assist") or {}).get("name") or ""
            team = (e.get("team") or {}).get("id")
            minute = (e.get("time") or {}).get("elapsed")
            detail = e.get("detail") or ""

            rows.append((mid, team, minute, etype, detail,
                         player, "", assist))

            if etype == "Card":
                n_cards += 1
            elif etype == "subst":
                n_subs += 1

        # نمسح أحداث هالماتش القديمة قبل الإضافة (لو أُعيد السحب)
        conn.execute("DELETE FROM events WHERE match_id = ?", (mid,))

        if rows:
            conn.executemany("""
                INSERT INTO events
                (match_id, team_id, minute, type, detail,
                 player_en, player_ar, assist_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            ok += 1
        else:
            # سجل فارغ عشان ما نعيد سحبها كل مرة
            conn.execute("""
                INSERT INTO events
                (match_id, team_id, minute, type, detail,
                 player_en, player_ar, assist_en)
                VALUES (?, NULL, NULL, 'none', '', '', '', '')
            """, (mid,))
            empty += 1

        conn.commit()

        if i % 25 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}]  بطاقات: {n_cards}  "
                  f"تبديلات: {n_subs}")

        time.sleep(DELAY)

    print(f"""
{'=' * 58}
  فيها أحداث: {ok}   |   فاضية فعلاً: {empty}   |   فشل: {failed}
  بطاقات: {n_cards}   |   تبديلات: {n_subs}
{'=' * 58}""")

    if failed_list:
        print("\n  اللي فشلت (أول 10):")
        for mid, label, reason in failed_list[:10]:
            print(f"    {mid}  {label}  [{reason}]")
        print("\n  شغّل نفس الأمر مرة تانية وبيحاول فيهم.")

    still = len(todo) - len(to_fetch)
    if still:
        print(f"\n  لسا ناقص {still} ماتش — أعد التشغيل بنفس الأمر.")
    else:
        print("\n  خلصت كل المباريات.")

    conn.close()


if __name__ == "__main__":
    main()
