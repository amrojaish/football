#!/usr/bin/env python3
"""
سحب الترتيب الرسمي من المزوّد
================================
طلب واحد لكل (دوري، موسم) — رخيص جداً.

⚠️ **لا يلمس** أي جدول آخر. مرجع للمقارنة فقط.

⚠️ الترتيب يتغيّر مع كل جولة، فأعد السحب دورياً للمواسم
   الجارية. المواسم المنتهية ثابتة.

التشغيل:
    python fetch_standings.py --check      <- أي تركيبات ناقصة
    python fetch_standings.py              <- كل الموجود بالـDB
    python fetch_standings.py SAU
    python fetch_standings.py --season 2026
"""

import requests
import sqlite3
import time
import sys
from datetime import datetime

from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3


def parse_args():
    code = None
    season = None
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].upper() in LEAGUES:
        code = args[0].upper()

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, check_only, season


def get(params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{API_BASE}/standings",
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
                time.sleep(attempt * 3)
            else:
                return False, [], "مهلة انتهت"

        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 5)
            else:
                return False, [], "انقطاع اتصال"

        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def main():
    if not check_key():
        return

    code, check_only, season = parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM api_standings LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول api_standings غير موجود — "
              "شغّل add_standings_table.py أول")
        conn.close()
        return

    # التركيبات الموجودة بالـDB
    q = """
        SELECT DISTINCT league_code AS lg, season AS s
        FROM matches ORDER BY season DESC, league_code
    """
    combos = conn.execute(q).fetchall()

    if code:
        combos = [c for c in combos if c["lg"] == code]
    if season is not None:
        combos = [c for c in combos if c["s"] == season]

    print(f"\n{'=' * 62}")
    print(f"  سحب الترتيب الرسمي — {len(combos)} تركيبة")
    print(f"{'=' * 62}")

    if check_only:
        for c in combos:
            n = conn.execute("""
                SELECT COUNT(*) FROM api_standings
                WHERE league_code = ? AND season = ?
            """, (c["lg"], c["s"])).fetchone()[0]
            name = LEAGUES.get(c["lg"], {}).get("name_ar", c["lg"])
            mark = f"{n} صف" if n else "ناقص"
            print(f"      {name:<18} {c['s']}   {mark}")
        print(f"\n  الطلبات المطلوبة: {len(combos)}\n")
        conn.close()
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ok = failed = 0
    total_rows = 0

    for c in combos:
        lg, s = c["lg"], c["s"]
        name = LEAGUES.get(lg, {}).get("name_ar", lg)

        success, data, reason = get({
            "league": LEAGUES[lg]["id"], "season": s
        })

        if not success:
            print(f"\n  {name} {s}: فشل — {reason}")
            failed += 1
            time.sleep(DELAY)
            continue

        if not data:
            print(f"\n  {name} {s}: ما رجع ترتيب")
            failed += 1
            time.sleep(DELAY)
            continue

        rows = []
        # البنية: response[0].league.standings[0] = قائمة الفرق
        try:
            groups = data[0]["league"]["standings"]
        except (KeyError, IndexError, TypeError):
            print(f"\n  {name} {s}: بنية غير متوقعة")
            failed += 1
            time.sleep(DELAY)
            continue

        for group in groups:
            for t in group:
                all_ = t.get("all") or {}
                goals = all_.get("goals") or {}
                rows.append((
                    lg, s,
                    (t.get("team") or {}).get("id"),
                    t.get("rank"),
                    all_.get("played"),
                    all_.get("win"),
                    all_.get("draw"),
                    all_.get("lose"),
                    goals.get("for"),
                    goals.get("against"),
                    t.get("points"),
                    t.get("form") or "",
                    t.get("description") or "",
                    now,
                ))

        if rows:
            conn.executemany("""
                INSERT OR REPLACE INTO api_standings
                (league_code, season, team_id, rank, played, wins,
                 draws, losses, goals_for, goals_against, points,
                 form, description, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)
            conn.commit()
            print(f"\n  ✅ {name} {s}   {len(rows)} فريق")
            ok += 1
            total_rows += len(rows)

        time.sleep(DELAY)

    tot = conn.execute("SELECT COUNT(*) FROM api_standings").fetchone()[0]
    conn.close()

    print(f"""
{'=' * 62}
  نجح: {ok}   |   فشل: {failed}   |   صفوف: {total_rows}
  إجمالي الجدول: {tot}
{'=' * 62}

  الخطوة الجاية:  python compare_standings.py
""")


if __name__ == "__main__":
    main()
