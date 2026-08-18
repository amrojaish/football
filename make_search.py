#!/usr/bin/env python3
"""
فهرس البحث — ملف واحد خارجي
==============================
بيولّد `search_data.js` بجذر الموقع: أندية + لاعبون، بالعربي
والإنجليزي، للبحث الفوري داخل المتصفح.

⚠️ **لماذا ملف خارجي لا حقن في كل صفحة:**
   الفهرس ~80 كيلوبايت. ضربه في 6,444 صفحة = ~500 ميغابايت.
   الملف الخارجي يُحمَّل **مرة واحدة** ويُخزَّن في كاش المتصفح.

⚠️ **لماذا `.js` لا `.json`:**
   الاختبار المحلي يفتح الصفحات بـ`file://`، و`fetch()` ممنوع
   هناك بسبب CORS. بينما `<script src>` يعمل في الحالتين.
   الملف يعرّف متغيّراً عاماً: `window.FBSEARCH`.

⚠️ **البنية مصفوفات لا كائنات** — توفّر ~40% من الحجم:
   نادٍ  : [id, ar, en, league]
   لاعب : [ar, en, club_id, club_ar, club_en]

⚠️ ضغط اللاعب يوديه **لصفحة ناديه** — صفحة اللاعب غير موجودة
   بعد. لذلك اسم النادي معروض بجانبه في النتائج.

صفر طلبات API.

التشغيل:
    python make_search.py
"""

import csv
import json
import sqlite3

from config import DB_FILE, TEAMS_FILE

BASE = DB_FILE.parent
OUT = BASE / "search_data.js"


def clean(v):
    return (v or "").strip()


def load_teams():
    """نفس منطق make_clubs — الأسماء من CSV"""
    teams = {}
    if not TEAMS_FILE.exists():
        return teams
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "ar": clean(r.get("short_name_ar")),
                "full_ar": clean(r.get("name_ar")),
                "en": (clean(r.get("name_en_official"))
                       or clean(r.get("name_en"))),
                "league": clean(r.get("league_code")),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    teams = load_teams()

    # ── الأندية التي لها صفحة فعلاً ───────────────────
    have_page = set()
    for d in ("clubs", "en/clubs"):
        p = BASE / d
        if p.exists():
            for f in p.iterdir():
                if f.suffix == ".html":
                    try:
                        have_page.add(int(f.stem))
                    except ValueError:
                        pass

    clubs = []
    for tid, t in sorted(teams.items()):
        if tid not in have_page:
            continue
        ar = t["ar"] or t["full_ar"]
        en = t["en"]
        if not (ar or en):
            continue
        logo = (t.get("logo_local") or "").strip() or (t.get("logo") or "").strip()
        clubs.append([tid, ar, en, t["league"], logo])

    # ── اللاعبون — من جدول الأهداف ────────────────────
    players = []
    seen = set()
    q = """
        SELECT g.player_en, g.player_ar, g.team_id,
               COUNT(g.player_en) AS n
        FROM goals g
        WHERE g.player_en IS NOT NULL AND g.player_en != ''
        GROUP BY g.player_en, g.team_id
        ORDER BY n DESC
    """
    for r in conn.execute(q):
        en = clean(r["player_en"])
        ar = clean(r["player_ar"])
        tid = r["team_id"]

        key = (en, tid)
        if key in seen:
            continue
        seen.add(key)

        club = teams.get(tid)
        if not club:
            continue

        players.append([ar, en, tid,
                        club["ar"] or club["full_ar"],
                        club["en"]])

    conn.close()

    data = {"c": clubs, "p": players}
    payload = json.dumps(data, ensure_ascii=False,
                         separators=(",", ":"))

    js = ("/* فهرس البحث — مولّد بـmake_search.py. لا تعدّله يدوياً. */\n"
          "window.FBSEARCH=" + payload + ";\n")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)

    kb = OUT.stat().st_size / 1024

    print(f"\n{'=' * 55}")
    print(f"  search_data.js — {kb:.0f} كيلوبايت")
    print(f"{'=' * 55}")
    print(f"  أندية  : {len(clubs)}")
    print(f"  لاعبون : {len(players)}")

    ar_n = sum(1 for p in players if p[0])
    print(f"  منهم بأسماء عربية: {ar_n} "
          f"({ar_n / len(players) * 100:.0f}%)" if players else "")

    if kb > 300:
        print("\n  ⚠️ الحجم كبير — راجع ما يُدرَج بالفهرس")

    print()


if __name__ == "__main__":
    main()
