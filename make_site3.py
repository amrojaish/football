#!/usr/bin/env python3
"""
الصفحة الرئيسية — بلغتين
===========================
بيولّد نسختين:
    index.html       → العربي (RTL)
    en/index.html    → الإنجليزي (LTR)

كل النصوص من i18n.py — ما في نص مكتوب هون مباشرة.

التشغيل:
    python make_site3.py
"""

import sqlite3
import csv
import os
from config import DB_FILE, TEAMS_FILE, LEAGUES
from tiebreak import sort_table
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name

BASE = DB_FILE.parent


SCRIPT = """
<script>
  const leagueTabs  = document.querySelectorAll('.tab-league');
  const seasonTabs  = document.querySelectorAll('.tab-season');
  const sections    = document.querySelectorAll('.panel');

  let current = { league: null, season: null };

  function render() {
    sections.forEach(s => s.classList.remove('visible'));

    const id = current.season + '_' + current.league;
    const target = document.getElementById(id);

    if (target) {
      target.classList.add('visible');
      document.getElementById('empty').style.display = 'none';
    } else {
      document.getElementById('empty').style.display = 'block';
    }

    leagueTabs.forEach(t =>
      t.classList.toggle('active', t.dataset.league === current.league));
    seasonTabs.forEach(t =>
      t.classList.toggle('active', t.dataset.season === current.season));
  }

  leagueTabs.forEach(t => {
    t.addEventListener('click', function () {
      current.league = this.dataset.league;
      render();
    });
  });

  seasonTabs.forEach(t => {
    t.addEventListener('click', function () {
      current.season = this.dataset.season;
      render();
    });
  });

  if (seasonTabs.length && leagueTabs.length) {
    current.season = seasonTabs[0].dataset.season;
    current.league = leagueTabs[0].dataset.league;
    render();
  }
</script>
"""


STYLE = """
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:#0f1419;
         color:#e8eaed; padding:24px 16px; line-height:1.6; }
  .wrap { max-width:900px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:6px; }
  .lang { background:#161b22; color:#7d8590; border:1px solid #21262d;
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:#1c2128; color:#e8eaed; }
  header { text-align:center; margin-bottom:20px; }
  h1 { font-size:26px; }
  .sub { color:#7d8590; font-size:13px; margin-top:4px; }
  .tabs { display:flex; gap:8px; justify-content:center;
          margin-bottom:12px; flex-wrap:wrap; }
  .tabs.seasons { margin-bottom:20px; }
  .tab { background:#161b22; color:#7d8590; border:1px solid #21262d;
         padding:8px 18px; border-radius:8px; cursor:pointer;
         font-family:inherit; font-size:14px; transition:.15s; }
  .tab:hover { background:#1c2128; color:#e8eaed; }
  .tab.active { background:#2f81f7; color:#fff; border-color:#2f81f7; }
  .tab-season { padding:6px 14px; font-size:13px; }
  .tab-season.active { background:#238636; border-color:#238636; }
  .panel { display:none; }
  .panel.visible { display:block; }
  #empty { display:none; text-align:center; color:#7d8590;
           padding:50px 20px; background:#161b22; border-radius:10px; }
  h2 { font-size:17px; margin:28px 0 12px; padding-inline-start:10px;
       border-inline-start:3px solid #2f81f7; }
  table { width:100%; border-collapse:collapse; background:#161b22;
          border-radius:10px; overflow:hidden; }
  th,td { padding:10px 8px; text-align:center; font-size:14px; }
  th { background:#1c2128; color:#7d8590; font-size:12px; }
  th.r { text-align:start; }
  tr { border-bottom:1px solid #21262d; }
  tr:last-child { border-bottom:none; }
  .team { text-align:start; display:flex; align-items:center; gap:9px;
          min-width:0; }
  .team img { width:22px; height:22px; object-fit:contain; }
  .team a { color:#e8eaed; text-decoration:none; overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap; }
  .team a:hover { color:#2f81f7; }
  .pos { color:#7d8590; width:34px; }
  .pts { font-weight:700; color:#2f81f7; }
  .top .pos { color:#3fb950; font-weight:700; }
  .bottom .pos { color:#f85149; }
  .match { background:#161b22; border-radius:10px; padding:13px;
           margin-bottom:8px; display:grid;
           grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; }
  .side { display:flex; align-items:center; gap:8px; font-size:14px;
          min-width:0; text-decoration:none; color:#e8eaed; }
  .side.away { justify-content:flex-end; }
  .side img { width:26px; height:26px; object-fit:contain; }
  .side span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  a.side:hover span { color:#2f81f7; }
  .score { font-size:18px; font-weight:700; padding:4px 13px;
           background:#0d1117; border-radius:6px; white-space:nowrap; }
  .date { grid-column:1/-1; text-align:center; color:#7d8590;
          font-size:11px; margin-top:5px; }
  .date a { color:#7d8590; text-decoration:none; }
  .date a:hover { color:#2f81f7; }
  ol { list-style:none; background:#161b22; border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid #21262d; font-size:14px; }
  ol li:last-child { border-bottom:none; }
  .num { color:#7d8590; width:20px; }
  .pname { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .pteam { color:#7d8590; font-size:12px; }
  .pgoals { font-weight:700; color:#2f81f7; min-width:22px;
            text-align:end; }
  .meta { color:#7d8590; font-size:12px; text-align:center;
          margin-top:14px; }
  footer { text-align:center; color:#7d8590; font-size:12px;
           margin-top:36px; line-height:1.9; }
</style>
"""


def clean(t):
    return (t or "").strip()


def load_overrides():
    """الشعارات المحلية — logo_note لم يعد يُعرض"""
    logos = {}
    if not TEAMS_FILE.exists():
        return logos
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = clean(row.get("team_id"))
            if tid and clean(row.get("logo_local")):
                logos[tid] = clean(row.get("logo_local"))
    return logos


def available(conn):
    """أي تركيبات موسم/دوري موجودة فعلاً بالديتابيس"""
    return conn.execute("""
        SELECT season, league_code, COUNT(*) AS n
        FROM matches
        GROUP BY season, league_code
        ORDER BY season DESC, league_code
    """).fetchall()


def get_data(conn, code, season):
    """كل استعلام يفلتر على الدوري AND الموسم"""
    table = conn.execute("""
       WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL
        )
        SELECT t.team_id, t.short_name_ar AS name,
            COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS name_en,
            t.logo,
            COUNT(*) AS played,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) - SUM(ga) AS diff,
            SUM(gf) AS scored,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS points
        FROM all_games
        JOIN teams t ON t.team_id = all_games.team
        GROUP BY t.team_id, t.short_name_ar
        ORDER BY points DESC
    """, (code, season, code, season)).fetchall()

    matches = conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en,
               a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ?
        ORDER BY m.date DESC LIMIT 10
    """, (code, season)).fetchall()

    scorers = conn.execute("""
        SELECT g.player_en AS player, g.player_ar AS player_ar,
               t.short_name_ar AS team,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS team_en,
               COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t ON t.team_id = g.team_id
        WHERE g.player_en != ''
          AND m.league_code = ? AND m.season = ?
        GROUP BY g.player_en, t.short_name_ar
        ORDER BY goals DESC LIMIT 10
    """, (code, season)).fetchall()

    table = sort_table(conn, code, season, table)
    return table, matches, scorers


def tname(row, lang, ar_key="name", en_key="name_en"):
    """اسم النادي حسب اللغة، مع ارتداد"""
    if lang == "ar":
        return clean(row[ar_key]) or clean(row[en_key])
    return clean(row[en_key]) or clean(row[ar_key])


def render_panel(code, season, table, matches, scorers, logos, lang):
    t = T[lang]

    def logo_of(tid, fb):
        return logos.get(str(tid), fb)

    rows = ""
    for i, r in enumerate(table, 1):
        cls = "top" if i <= 3 else ("bottom" if i > len(table) - 2 else "")
        rows += (
            f'<tr class="{cls}"><td class="pos">{i}</td>'
            f'<td class="team">'
            f'<img src="{logo_of(r["team_id"], r["logo"])}" alt="">'
            f'<a href="clubs/{r["team_id"]}.html">{tname(r, lang)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )

    cards = ""
    for m in matches:
        hn = tname(m, lang, "home", "home_en")
        an = tname(m, lang, "away", "away_en")
        arrow = "←" if lang == "ar" else "→"
        cards += (
            f'<div class="match">'
            f'<a class="side" href="clubs/{m["home_id"]}.html">'
            f'<img src="{logo_of(m["home_id"], m["home_logo"])}" alt="">'
            f'<span>{hn}</span></a>'
            f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>'
            f'<a class="side away" href="clubs/{m["away_id"]}.html">'
            f'<span>{an}</span>'
            f'<img src="{logo_of(m["away_id"], m["away_logo"])}" alt=""></a>'
            f'<div class="date">'
            f'<a href="matches/{m["match_id"]}.html">'
            f'{m["date"]} {arrow}</a></div></div>'
        )

    sc = ""
    for i, s in enumerate(scorers, 1):
        pl = clean(s["player_ar"]) if lang == "ar" else ""
        pl = pl or clean(s["player"])
        tm = tname(s, lang, "team", "team_en")
        sc += (
            f'<li><span class="num">{i}</span>'
            f'<span class="pname">{pl}</span>'
            f'<span class="pteam">{tm}</span>'
            f'<span class="pgoals">{s["goals"]}</span></li>'
        )

    same = len({r["played"] for r in table}) == 1
    warn = "" if same else f' · {t["incomplete"]}'

    return (
        f'<section class="panel" id="{season}_{code}">'
        f'<h2>{t["standings"]}</h2>'
        f'<table><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th>'
        f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
        f'<th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>'
        f'{rows}</table>'
        f'<div class="meta">{t["season"]} {season}-{season+1}{warn}</div>'
        f'<h2>{t["results"]}</h2>{cards}'
        f'<h2>{t["scorers"]}</h2><ol>{sc}</ol>'
        f'</section>'
    )


def build(conn, lang, combos, seasons, leagues, logos):
    """بيبني صفحة كاملة بلغة واحدة"""
    t = T[lang]

    panels = ""
    for c in combos:
        table, matches, scorers = get_data(conn, c["league_code"],
                                           c["season"])
        if table:
            panels += render_panel(c["league_code"], c["season"],
                                   table, matches, scorers, logos, lang)

    season_tabs = "".join(
        f'<button class="tab tab-season" data-season="{s}">'
        f'{s}-{s+1}</button>' for s in seasons)

    league_tabs = "".join(
        f'<button class="tab tab-league" data-league="{c}">'
        f'{league_name(c, lang)}</button>' for c in leagues)

    # رابط اللغة الأخرى
    switch = "en/index.html" if lang == "ar" else "../index.html"
    # مسارات الأصول حسب موقع الملف
    asset = "" if lang == "ar" else "../"

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{t["site_title"]}</title>\n'
        + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<a class="lang" href="{switch}">{SWITCH_LABEL[lang]}</a>'
        f'<span></span></div>\n'
        f'<header><h1>{t["site_title"]}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'
        f'<div class="tabs seasons">{season_tabs}</div>\n'
        f'<div class="tabs">{league_tabs}</div>\n'
        f'{panels}\n'
        f'<div id="empty">{t["empty_combo"]}</div>\n'
        f'<footer>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + SCRIPT +
        '</body>\n</html>'
    )

    # الإنجليزي داخل en/ — الروابط النسبية تحتاج تصحيحاً
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')

    return html


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    logos = load_overrides()

    combos = available(conn)
    if not combos:
        print("ما في مباريات بالديتابيس")
        conn.close()
        return

    seasons = sorted({c["season"] for c in combos}, reverse=True)
    leagues = [c for c in LEAGUES
               if any(x["league_code"] == c for x in combos)]

    os.makedirs(BASE / "en", exist_ok=True)

    for lang in LANGS:
        html = build(conn, lang, combos, seasons, leagues, logos)
        path = BASE / "index.html" if lang == "ar" else BASE / "en" / "index.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    conn.close()

    print(f"\n{'=' * 55}")
    print("  تم: index.html  +  en/index.html")
    print(f"{'=' * 55}")
    for c in combos:
        print(f"  {league_name(c['league_code'], 'ar'):<18} "
              f"موسم {c['season']}   {c['n']} ماتش")
    print("""
  زر اللغة أعلى الصفحة.
  العربي بالجذر، الإنجليزي بمجلد en/
    """)


if __name__ == "__main__":
    main()
