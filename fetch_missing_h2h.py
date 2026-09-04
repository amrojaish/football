#!/usr/bin/env python3
"""
سحب الأزواج الشاذة عبر head-to-head — لا القائمة الأساسية
==============================================================
`find_missing_season.py` يكشف الأزواج التي لم تلتقِ مرتين، لكن
`fetch_matches2.py --check` قد يقول "الموسم مكتمل" رغم ذلك —
لأن قائمة المزوّد الأساسية (`/fixtures?league=X&season=Y`) قد
لا تحوي هذه المباريات إطلاقاً، بينما تظهر عبر
`/fixtures/headtohead` (اكتُشف بالمصري 4 سبتمبر: 180 زوجاً
شاذاً، القائمة الأساسية تقول "صفر ناقص" لهم جميعاً).

هذا السكربت يفحص كل زوج شاذ عبر h2h ويصنّفه:
    found_new   مباراة إضافية بنتيجة حقيقية غير موجودة عندنا
    found_null  موجودة عند المزوّد لكن بلا نتيجة (لسا/لن تُلعب)
    none        غائبة تماماً حتى عن h2h — **فجوة دائمة، لا حل
                عبر API إطلاقاً**. تحتاج بحثاً يدوياً من مصدر
                خارجي (نفس نمط manual_matches.csv) لا هذا السكربت.

⚠️ **معرّفات المباريات هنا حقيقية من المزوّد** — خلاف
   `manual_matches.csv` (معرّفات اصطناعية 9000001+ للمباريات
   الغائبة كلياً). لا تخلط الاثنين.

⚠️ **مطابقة الفريق المضيف بالاسم لا بالتخمين** — لو الاسم ما
   طابق أي من فريقَي الزوج (نادٍ بمسمّى تاريخي مختلف، تشابه
   أسماء)، يُستبعد المباراة ويُطبع تحذيراً بدل تخمين الهوية
   (درس 6).

التشغيل:
    python fetch_missing_h2h.py EGY --check          <- فحص كل الأزواج الشاذة
    python fetch_missing_h2h.py EGY --season 2024 --check
    python fetch_missing_h2h.py EGY                  <- يسحب الموجود بنتيجة فقط
"""

import sqlite3
import sys
import time
import requests
from collections import defaultdict
from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
CHECK_ONLY = "--check" in sys.argv


def parse_args():
    code = next((a for a in sys.argv[1:] if a.upper() in LEAGUES), None)
    season = None
    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass
    return code.upper() if code else None, season


def get(endpoint, params):
    for attempt in range(1, 4):
        try:
            r = requests.get(f"{API_BASE}/{endpoint}", headers=headers(),
                             params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(attempt * 10)
                continue
            d = r.json()
            errors = d.get("errors")
            if errors and isinstance(errors, dict) and errors:
                return False, [], f"API: {errors}"
            return True, d.get("response", []), ""
        except Exception as e:
            time.sleep(attempt * 3)
    return False, [], "فشل بعد كل المحاولات"


def missing_pairs(conn, code, season_filter):
    """نفس منطق find_missing_season.py — بيرجع (season, x, y)"""
    seasons = ([season_filter] if season_filter else
               [r[0] for r in conn.execute(
                   "SELECT DISTINCT season FROM matches WHERE league_code=?",
                   (code,))])
    out = []
    for season in seasons:
        teams = set()
        pair = defaultdict(int)
        for h, a in conn.execute(
                "SELECT home_id, away_id FROM matches "
                "WHERE league_code=? AND season=?", (code, season)):
            teams.add(h); teams.add(a)
            pair[frozenset((h, a))] += 1
        for i, x in enumerate(sorted(teams)):
            for y in sorted(teams)[i + 1:]:
                if pair.get(frozenset((x, y)), 0) != 2:
                    out.append((season, x, y))
    return out


def main():
    if not check_key():
        return

    code, season_filter = parse_args()
    if not code:
        print("الاستعمال: python fetch_missing_h2h.py <JOR|IRQ|SAU|EGY|UAE|QAT> [--season N] [--check]")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    pairs = missing_pairs(conn, code, season_filter)
    print(f"\n{'=' * 60}\n  أزواج شاذة: {len(pairs)}\n{'=' * 60}")
    if not pairs:
        conn.close()
        return

    names = {r["team_id"]: r["name_en"] for r in
             conn.execute("SELECT team_id, name_en FROM teams")}

    counts = defaultdict(int)
    to_insert = []

    for i, (season, x, y) in enumerate(pairs, 1):
        have = {r[0] for r in conn.execute(
            "SELECT match_id FROM matches WHERE league_code=? AND season=? "
            "AND ((home_id=? AND away_id=?) OR (home_id=? AND away_id=?))",
            (code, season, x, y, y, x))}

        ok, resp, reason = get("fixtures/headtohead",
                               {"h2h": f"{x}-{y}", "season": season})
        if not ok:
            print(f"  [{i}/{len(pairs)}] فشل — {reason}")
            counts["error"] += 1
            time.sleep(DELAY)
            continue

        new = [f for f in resp if f["fixture"]["id"] not in have]
        if not new:
            counts["none"] += 1
        else:
            f = new[0]
            gh, ga = f["goals"]["home"], f["goals"]["away"]
            if gh is None or ga is None:
                counts["found_null"] += 1
            else:
                hn, an = f["teams"]["home"]["name"], f["teams"]["away"]["name"]
                if names.get(x) == hn:
                    hid, aid = x, y
                elif names.get(y) == hn:
                    hid, aid = y, x
                else:
                    print(f"  ⚠️ ما قدرت أطابق الاسم: {hn} — تخطّي "
                          f"match={f['fixture']['id']}")
                    counts["name_mismatch"] += 1
                    time.sleep(DELAY)
                    continue
                counts["found_new"] += 1
                to_insert.append({
                    "mid": f["fixture"]["id"], "season": season,
                    "date": f["fixture"]["date"][:10],
                    "hid": hid, "aid": aid, "gh": gh, "ga": ga,
                    "status": f["fixture"]["status"]["short"],
                    "label": f"{hn} {gh}-{ga} {an}",
                })
        time.sleep(DELAY)

    print(f"\nالنتيجة: {dict(counts)}")

    if CHECK_ONLY or not to_insert:
        print("\n[وضع الفحص] — ما انكتب شي" if CHECK_ONLY else
              "\nلا مباريات جاهزة للإدخال")
        conn.close()
        return

    ok = 0
    total_goals = 0
    for i, r in enumerate(to_insert, 1):
        success, events, reason = get("fixtures/events", {"fixture": r["mid"]})
        if not success:
            print(f"  [{i}/{len(to_insert)}] فشل الأحداث — {r['label']}")
            time.sleep(DELAY)
            continue

        conn.execute(f"""
            INSERT OR REPLACE INTO matches
            (match_id, league_code, season, date,
             home_id, away_id, home_goals, away_goals, status)
            VALUES (?, '{code}', ?, ?, ?, ?, ?, ?, ?)
        """, (r["mid"], r["season"], r["date"], r["hid"], r["aid"],
              r["gh"], r["ga"], r["status"]))
        conn.execute("DELETE FROM goals WHERE match_id = ?", (r["mid"],))
        for e in events:
            if e.get("type") != "Goal" or e.get("detail") == "Missed Penalty":
                continue
            conn.execute("""
                INSERT INTO goals
                (match_id, team_id, minute, player_en, player_ar, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (r["mid"], e["team"]["id"], e["time"]["elapsed"],
                  e["player"]["name"] or "", "", e.get("detail", "")))
            total_goals += 1
        conn.commit()
        ok += 1
        time.sleep(DELAY)

    print(f"\nأُضيف: {ok}/{len(to_insert)}  |  أهداف: {total_goals}")
    conn.close()


if __name__ == "__main__":
    main()
