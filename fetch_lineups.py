#!/usr/bin/env python3
"""
سحب التشكيلات
================
بيسحب من fixtures/lineups: الخطة، المدرب، التشكيلة الأساسية
والاحتياط لكل فريق.

طلب واحد لكل مباراة.

⚠️ **لا يلمس** matches ولا goals ولا events ولا match_stats.

تزايدي: المباريات اللي عندها تشكيلات بينتخطاها.
المباريات القادمة (بلا نتيجة) بتنتخطى — التشكيلة تُعلَن قبل
المباراة بساعة، فلا فائدة من سحبها مبكراً.

⚠️ نفس نمط الأحداث والإحصائيات: **المزوّد يوفّرها للسعودي فقط**
   على الأرجح. اختبر بعيّنة صغيرة قبل السحب الكامل.

التشغيل:
    python fetch_lineups.py --check
    python fetch_lineups.py SAU --budget 5      <- اختبار
    python fetch_lineups.py SAU --budget 700
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
    """مباريات منتهية بلا تشكيلات"""
    q = """
        SELECT m.match_id, m.league_code, m.season, m.date,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lineups l WHERE l.match_id = m.match_id
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
        conn.execute("SELECT 1 FROM lineups LIMIT 1")
    except sqlite3.OperationalError:
        print("جداول التشكيلات غير موجودة — شغّل add_lineups_table.py أول")
        conn.close()
        return

    todo = pending(conn, code, season)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا تشكيلات: {len(todo)}")
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
    n_players = 0
    failed_list = []

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} × {m['away']}"

        success, data, reason = get("fixtures/lineups", {"fixture": mid})

        if not success:
            print(f"  [{i}/{len(to_fetch)}] فشل — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            failed_list.append((mid, label, reason))
            time.sleep(DELAY)
            continue

        if not data:
            empty += 1
            time.sleep(DELAY)
            continue

        lines = []
        players = []

        for blk in data:
            tid = (blk.get("team") or {}).get("id")
            if tid is None:
                continue

            coach = (blk.get("coach") or {}).get("name") or ""
            formation = blk.get("formation") or ""
            lines.append((mid, tid, formation, coach, ""))

            for grp, starter in (("startXI", 1), ("substitutes", 0)):
                for item in blk.get(grp) or []:
                    p = item.get("player") or {}
                    pid = p.get("id")
                    if pid is None:
                        continue
                    players.append((
                        mid, tid, pid,
                        p.get("name") or "", "",
                        p.get("number"),
                        p.get("pos") or "",
                        p.get("grid") or "",
                        starter,
                    ))

        if lines:
            conn.executemany("""
                INSERT OR REPLACE INTO lineups
                (match_id, team_id, formation, coach_en, coach_ar)
                VALUES (?, ?, ?, ?, ?)
            """, lines)

            if players:
                conn.executemany("""
                    INSERT OR REPLACE INTO lineup_players
                    (match_id, team_id, player_id, player_en, player_ar,
                     number, pos, grid, starter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, players)
                n_players += len(players)

            conn.commit()
            ok += 1
        else:
            empty += 1

        if i % 25 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}]  نجح: {ok}  "
                  f"لاعبين: {n_players}")

        time.sleep(DELAY)

    tot_l = conn.execute("SELECT COUNT(*) FROM lineups").fetchone()[0]
    tot_p = conn.execute(
        "SELECT COUNT(*) FROM lineup_players").fetchone()[0]
    uniq = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM lineup_players"
    ).fetchone()[0]

    print(f"""
{'=' * 58}
  فيها تشكيلات: {ok}   |   فاضية: {empty}   |   فشل: {failed}
  تشكيلات بالجدول: {tot_l}   |   سجلات لاعبين: {tot_p}
  لاعبون مختلفون: {uniq}
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
