#!/usr/bin/env python3
"""
توليد صفحة لكل نادي
=====================
بيعمل مجلد clubs/ وفيه ملف HTML لكل نادي:
  clubs/4532.html

كل صفحة فيها:
  - الشعار والاسم والمدينة
  - لكل موسم: ملخص (لعب/ف/ت/خ/له/عليه/نقاط + المركز)
  - كل مباريات النادي بالموسم (مش آخر 10)
  - هدافو النادي
  - رابط رجوع للصفحة الرئيسية

صفر طلبات API.

التشغيل:
    python make_clubs.py
"""

import sqlite3
import csv
import os
from config import DB_FILE, TEAMS_FILE, LEAGUES
from tiebreak import sort_table

OUT_DIR = DB_FILE.parent / "clubs"


STYLE = """
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:#0f1419;
         color:#e8eaed; padding:24px 16px; line-height:1.6; }
  .wrap { max-width:900px; margin:0 auto; }
  .back { display:inline-block; color:#2f81f7; text-decoration:none;
          font-size:14px; margin-bottom:18px; }
  .back:hover { text-decoration:underline; }
  .club-head { display:flex; align-items:center; gap:16px;
               background:#161b22; border-radius:12px;
               padding:20px; margin-bottom:8px; }
  .club-head img { width:64px; height:64px; object-fit:contain; }
  .club-head h1 { font-size:24px; }
  .club-head .sub { color:#7d8590; font-size:13px; margin-top:2px; }
  h2 { font-size:17px; margin:28px 0 12px; padding-right:10px;
       border-right:3px solid #2f81f7; }
  h3 { font-size:14px; color:#7d8590; margin:18px 0 8px;
       font-weight:normal; }
  .summary { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
  .stat { background:#161b22; border-radius:9px; padding:10px 14px;
          text-align:center; min-width:64px; flex:1; }
  .stat .n { font-size:19px; font-weight:700; }
  .stat .l { font-size:11px; color:#7d8590; }
  .stat.hi .n { color:#2f81f7; }
  .match { background:#161b22; border-radius:10px; padding:12px;
           margin-bottom:7px; display:grid;
           grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; }
  .side { display:flex; align-items:center; gap:8px; font-size:14px;
          min-width:0; }
  .side.away { justify-content:flex-end; }
  .side img { width:24px; height:24px; object-fit:contain; }
  .side span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .score { font-size:17px; font-weight:700; padding:4px 12px;
           background:#0d1117; border-radius:6px; white-space:nowrap; }
  .date { grid-column:1/-1; text-align:center; color:#7d8590;
          font-size:11px; margin-top:4px; }
  .w { border-right:3px solid #3fb950; }
  .d { border-right:3px solid #7d8590; }
  .l { border-right:3px solid #f85149; }
  ol { list-style:none; background:#161b22; border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid #21262d; font-size:14px; }
  ol li:last-child { border-bottom:none; }
  .num { color:#7d8590; width:20px; }
  .pname { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .pgoals { font-weight:700; color:#2f81f7; min-width:22px; text-align:left; }
  footer { text-align:center; color:#7d8590; font-size:12px;
           margin-top:36px; line-height:1.9; }
</style>
"""


def clean(t):
    return (t or "").strip()


def load_teams():
    """كل الأندية من الـCSV مع الشعار المحلي"""
    teams = {}
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "name_ar": clean(r.get("name_ar")),
                "short": clean(r.get("short_name_ar")),
                "city": clean(r.get("city")),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
                "league": clean(r.get("league_code")),
            }
    return teams


def logo_url(t, for_club_page=True):
    """الشعار المحلي إن وُجد، وإلا شعار الـAPI"""
    if t["logo_local"]:
        return ("../" + t["logo_local"]) if for_club_page else t["logo_local"]
    return t["logo"] or ""


def standings(conn, code, season):
    """جدول الترتيب — نفس منطق make_site3 مع tiebreak"""
    rows = conn.execute("""
        WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
        )
        SELECT team AS team_id,
            COUNT(*) AS played,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) AS scored, SUM(ga) AS conceded,
            SUM(gf) - SUM(ga) AS diff,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS points
        FROM all_games
        GROUP BY team
        ORDER BY points DESC
    """, (code, season, code, season)).fetchall()
    return sort_table(conn, code, season, rows)


def club_seasons(conn, tid):
    """أي مواسم لعب فيها هذا النادي"""
    return conn.execute("""
        SELECT DISTINCT league_code, season FROM matches
        WHERE home_id = ? OR away_id = ?
        ORDER BY season DESC
    """, (tid, tid)).fetchall()


def club_matches(conn, tid, code, season):
    return conn.execute("""
        SELECT m.date, m.home_id, m.away_id, m.home_goals, m.away_goals
        FROM matches m
        WHERE m.league_code = ? AND m.season = ?
          AND (m.home_id = ? OR m.away_id = ?)
        ORDER BY m.date DESC
    """, (code, season, tid, tid)).fetchall()


def club_scorers(conn, tid, code, season):
    return conn.execute("""
        SELECT g.player_en AS en, g.player_ar AS ar, COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.team_id = ? AND m.league_code = ? AND m.season = ?
          AND g.player_en != ''
        GROUP BY g.player_en
        ORDER BY goals DESC LIMIT 12
    """, (tid, code, season)).fetchall()


def render_season(conn, tid, teams, code, season):
    """قسم موسم واحد بصفحة النادي"""
    table = standings(conn, code, season)

    me = None
    pos = 0
    for i, r in enumerate(table, 1):
        if r["team_id"] == tid:
            me, pos = r, i
            break
    if me is None:
        return ""

    league_ar = LEAGUES.get(code, {}).get("name_ar", code)

    stats = (
        f'<div class="summary">'
        f'<div class="stat hi"><div class="n">{pos}</div><div class="l">المركز</div></div>'
        f'<div class="stat hi"><div class="n">{me["points"]}</div><div class="l">نقاط</div></div>'
        f'<div class="stat"><div class="n">{me["played"]}</div><div class="l">لعب</div></div>'
        f'<div class="stat"><div class="n">{me["wins"]}</div><div class="l">فاز</div></div>'
        f'<div class="stat"><div class="n">{me["draws"]}</div><div class="l">تعادل</div></div>'
        f'<div class="stat"><div class="n">{me["losses"]}</div><div class="l">خسر</div></div>'
        f'<div class="stat"><div class="n">{me["scored"]}</div><div class="l">له</div></div>'
        f'<div class="stat"><div class="n">{me["conceded"]}</div><div class="l">عليه</div></div>'
        f'</div>'
    )

    # المباريات
    cards = ""
    for m in club_matches(conn, tid, code, season):
        h, a = m["home_id"], m["away_id"]
        hg, ag = m["home_goals"], m["away_goals"]
        ht = teams.get(h, {"short": str(h), "logo": "", "logo_local": ""})
        at = teams.get(a, {"short": str(a), "logo": "", "logo_local": ""})

        # نتيجة هذا النادي
        my_gf = hg if h == tid else ag
        my_ga = ag if h == tid else hg
        cls = "w" if my_gf > my_ga else ("d" if my_gf == my_ga else "l")

        cards += (
            f'<div class="match {cls}">'
            f'<div class="side"><img src="{logo_url(ht)}" alt="">'
            f'<span>{ht["short"]}</span></div>'
            f'<div class="score">{hg} - {ag}</div>'
            f'<div class="side away"><span>{at["short"]}</span>'
            f'<img src="{logo_url(at)}" alt=""></div>'
            f'<div class="date">{m["date"]}</div></div>'
        )

    # الهدافون
    sc = ""
    for i, s in enumerate(club_scorers(conn, tid, code, season), 1):
        name = clean(s["ar"]) or clean(s["en"])
        sc += (f'<li><span class="num">{i}</span>'
               f'<span class="pname">{name}</span>'
               f'<span class="pgoals">{s["goals"]}</span></li>')

    scorers_block = f'<h3>هدافو النادي</h3><ol>{sc}</ol>' if sc else ""

    return (
        f'<h2>{league_ar} — موسم {season}-{season+1}</h2>'
        f'{stats}'
        f'{scorers_block}'
        f'<h3>كل المباريات</h3>{cards}'
    )


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    teams = load_teams()

    os.makedirs(OUT_DIR, exist_ok=True)

    # الأندية اللي عندها مباريات فعلاً
    ids = [r[0] for r in conn.execute("""
        SELECT DISTINCT home_id FROM matches
        UNION SELECT DISTINCT away_id FROM matches
    """).fetchall()]

    made = skipped = 0

    for tid in sorted(ids):
        t = teams.get(tid)
        if not t:
            print(f"  ⚠️ نادي {tid} مش موجود بجدول teams — تخطي")
            skipped += 1
            continue

        body = ""
        for s in club_seasons(conn, tid):
            body += render_season(conn, tid, teams,
                                  s["league_code"], s["season"])

        if not body:
            skipped += 1
            continue

        html = (
            '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{t["name_ar"]}</title>\n'
            + STYLE +
            '</head>\n<body>\n<div class="wrap">\n'
            '<a class="back" href="../index.html">→ رجوع للصفحة الرئيسية</a>\n'
            f'<div class="club-head"><img src="{logo_url(t)}" alt="">'
            f'<div><h1>{t["name_ar"]}</h1>'
            f'<div class="sub">{t["city"]}</div></div></div>\n'
            f'{body}\n'
            '<footer>الأسماء والشعارات المصححة من إعداد المطوّر<br>'
            'البيانات الأساسية من API-Football</footer>\n'
            '</div>\n</body>\n</html>'
        )

        with open(OUT_DIR / f"{tid}.html", "w", encoding="utf-8") as f:
            f.write(html)
        made += 1

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} صفحة نادي بمجلد clubs/")
    if skipped:
        print(f"  متخطى: {skipped}")
    print(f"{'=' * 55}")
    print("""
  جرّب: افتح clubs/4532.html بالمتصفح (الحسين إربد)

  الخطوة الجاية: ربط أسماء الأندية بجدول الترتيب
  بصفحاتها — تعديل على make_site3.py
    """)


if __name__ == "__main__":
    main()
