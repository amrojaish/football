#!/usr/bin/env python3
"""
سحب إحصائيات اللاعبين
========================
بيسحب من fixtures/players: تقييم كل لاعب، دقائقه، تسديداته،
تمريراته، مراوغاته، التحاماته — لكل مباراة.

طلب واحد لكل مباراة، بس الرد ضخم (~30 لاعب × عشرات الحقول).

⚠️ **لا يلمس** أي جدول آخر.

تزايدي: المباريات اللي عندها إحصائيات لاعبين بتنتخطى.

⚠️ نفس نمط باقي التفاصيل: **السعودي فقط** على الأرجح.

التشغيل:
    python fetch_player_stats.py --check
    python fetch_player_stats.py SAU --budget 5     <- اختبار
    python fetch_player_stats.py SAU --budget 700
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

COLS = ["minutes", "rating", "captain", "substitute", "pos",
        "shots_total", "shots_on", "goals", "conceded", "assists",
        "saves", "passes_total", "passes_key", "passes_pct",
        "tackles", "blocks", "interceptions",
        "duels_total", "duels_won", "dribbles_try", "dribbles_ok",
        "fouls_drawn", "fouls_made", "yellow", "red",
        "pen_scored", "pen_missed", "pen_saved"]


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


def num(v):
    """قيم الـAPI: 12 · '7.5' · '85%' · None · True"""
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
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


def extract(p):
    """صف واحد من كتلة لاعب"""
    s = (p.get("statistics") or [{}])[0]
    g = s.get("games") or {}
    sh = s.get("shots") or {}
    go = s.get("goals") or {}
    pa = s.get("passes") or {}
    ta = s.get("tackles") or {}
    du = s.get("duels") or {}
    dr = s.get("dribbles") or {}
    fo = s.get("fouls") or {}
    ca = s.get("cards") or {}
    pe = s.get("penalty") or {}

    return {
        "minutes": num(g.get("minutes")),
        "rating": num(g.get("rating")),
        "captain": num(g.get("captain")),
        "substitute": num(g.get("substitute")),
        "pos": g.get("position") or "",
        "shots_total": num(sh.get("total")),
        "shots_on": num(sh.get("on")),
        "goals": num(go.get("total")),
        "conceded": num(go.get("conceded")),
        "assists": num(go.get("assists")),
        "saves": num(go.get("saves")),
        "passes_total": num(pa.get("total")),
        "passes_key": num(pa.get("key")),
        "passes_pct": num(pa.get("accuracy")),
        "tackles": num(ta.get("total")),
        "blocks": num(ta.get("blocks")),
        "interceptions": num(ta.get("interceptions")),
        "duels_total": num(du.get("total")),
        "duels_won": num(du.get("won")),
        "dribbles_try": num(dr.get("attempts")),
        "dribbles_ok": num(dr.get("success")),
        "fouls_drawn": num(fo.get("drawn")),
        "fouls_made": num(fo.get("committed")),
        "yellow": num(ca.get("yellow")),
        "red": num(ca.get("red")),
        "pen_scored": num(pe.get("scored")),
        "pen_missed": num(pe.get("missed")),
        "pen_saved": num(pe.get("saved")),
    }


def pending(conn, code, season):
    q = """
        SELECT m.match_id, m.league_code, m.season, m.date,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM player_stats p WHERE p.match_id = m.match_id
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
        conn.execute("SELECT 1 FROM player_stats LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول player_stats غير موجود — "
              "شغّل add_player_stats_table.py أول")
        conn.close()
        return

    todo = pending(conn, code, season)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا إحصائيات لاعبين: {len(todo)}")
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
    n_rows = 0
    failed_list = []

    col_names = ", ".join(
        ["match_id", "team_id", "player_id", "player_en", "player_ar"]
        + COLS)
    placeholders = ", ".join(["?"] * (5 + len(COLS)))

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} × {m['away']}"

        success, data, reason = get("fixtures/players", {"fixture": mid})

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

        rows = []
        for blk in data:
            tid = (blk.get("team") or {}).get("id")
            if tid is None:
                continue
            for item in blk.get("players") or []:
                p = item.get("player") or {}
                pid = p.get("id")
                if pid is None:
                    continue
                vals = extract(item)
                rows.append(
                    [mid, tid, pid, p.get("name") or "", ""]
                    + [vals[c] for c in COLS])

        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO player_stats ({col_names}) "
                f"VALUES ({placeholders})", rows)
            conn.commit()
            n_rows += len(rows)
            ok += 1
        else:
            empty += 1

        if i % 25 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}]  نجح: {ok}  سجلات: {n_rows}")

        time.sleep(DELAY)

    tot = conn.execute("SELECT COUNT(*) FROM player_stats").fetchone()[0]
    uniq = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM player_stats"
    ).fetchone()[0]

    print(f"""
{'=' * 58}
  نجح: {ok}   |   فاضي: {empty}   |   فشل: {failed}
  إجمالي السجلات: {tot}   |   لاعبون مختلفون: {uniq}
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
