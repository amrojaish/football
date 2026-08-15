#!/usr/bin/env python3
"""
سحب إحصائيات المباريات
=========================
بيسحب من fixtures/statistics: الاستحواذ، التسديدات، الركنيات،
التمريرات، الأخطاء، والتسديدات المتوقعة (xG).

طلب واحد لكل مباراة — نفس تكلفة fetch_events.

⚠️ **لا يلمس** matches ولا goals ولا events. التصحيحات بأمان.

تزايدي: المباريات اللي عندها إحصائيات مخزّنة بينتخطاها.
المباريات القادمة (بلا نتيجة) بتنتخطى تلقائياً.

التشغيل:
    python fetch_stats.py --check              <- كم مباراة ناقصة
    python fetch_stats.py --budget 400
    python fetch_stats.py SAU --budget 300
    python fetch_stats.py SAU --season 2026
"""

import requests
import sqlite3
import time
import sys

from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3

# أسماء الـAPI → أعمدة الجدول
FIELD_MAP = {
    "Ball Possession": "possession",
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on",
    "Shots off Goal": "shots_off",
    "Blocked Shots": "shots_blocked",
    "Shots insidebox": "shots_inbox",
    "Shots outsidebox": "shots_outbox",
    "Corner Kicks": "corners",
    "Offsides": "offsides",
    "Fouls": "fouls",
    "Yellow Cards": "yellow",
    "Red Cards": "red",
    "Goalkeeper Saves": "saves",
    "Total passes": "passes_total",
    "Passes accurate": "passes_ok",
    "Passes %": "passes_pct",
    "expected_goals": "xg",
}

COLS = ["possession", "shots_total", "shots_on", "shots_off",
        "shots_blocked", "shots_inbox", "shots_outbox", "corners",
        "offsides", "fouls", "yellow", "red", "saves",
        "passes_total", "passes_ok", "passes_pct", "xg"]


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
    """بيرجع (نجح؟, البيانات, سبب الفشل)"""
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


def num(v):
    """
    قيم الـAPI تجي بأشكال: 55 · '55%' · '12.3' · None
    بترجع رقم أو None.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("%", "")
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


def pending(conn, code, season):
    """مباريات منتهية بلا إحصائيات"""
    q = """
        SELECT m.match_id, m.league_code, m.season, m.date,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM match_stats s WHERE s.match_id = m.match_id
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

    try:
        conn.execute("SELECT 1 FROM match_stats LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول match_stats غير موجود — شغّل add_stats_table.py أول")
        conn.close()
        return

    todo = pending(conn, code, season)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا إحصائيات: {len(todo)}")
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
        print(f"  الوقت لو سحبتهم كلهم: "
              f"~{len(todo) * DELAY / 60:.0f} دقيقة\n")
        conn.close()
        return

    to_fetch = todo[:budget]
    print(f"\n  رح أسحب {len(to_fetch)} ماتش "
          f"(~{len(to_fetch) * DELAY / 60:.0f} دقيقة)")
    print("  خليه يشتغل ولا تسكّره.\n")

    ok = failed = empty = 0
    failed_list = []

    placeholders = ", ".join(["?"] * (2 + len(COLS)))
    col_names = ", ".join(["match_id", "team_id"] + COLS)

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} × {m['away']}"

        success, stats, reason = get("fixtures/statistics",
                                     {"fixture": mid})

        if not success:
            print(f"  [{i}/{len(to_fetch)}] فشل — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            failed_list.append((mid, label, reason))
            time.sleep(DELAY)
            continue

        if not stats:
            empty += 1
            time.sleep(DELAY)
            continue

        rows = []
        for team_block in stats:
            tid = (team_block.get("team") or {}).get("id")
            if tid is None:
                continue

            vals = {c: None for c in COLS}
            for item in team_block.get("statistics", []):
                key = FIELD_MAP.get(item.get("type"))
                if key:
                    vals[key] = num(item.get("value"))

            rows.append([mid, tid] + [vals[c] for c in COLS])

        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO match_stats ({col_names}) "
                f"VALUES ({placeholders})", rows)
            conn.commit()
            ok += 1
        else:
            empty += 1

        if i % 25 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}]  نجح: {ok}  فاضي: {empty}")

        time.sleep(DELAY)

    n_rows = conn.execute("SELECT COUNT(*) FROM match_stats").fetchone()[0]

    print(f"""
{'=' * 58}
  فيها إحصائيات: {ok}   |   فاضية: {empty}   |   فشل: {failed}
  إجمالي السجلات بالجدول: {n_rows}
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
