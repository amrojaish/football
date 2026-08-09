#!/usr/bin/env python3
"""
الصفحة الموحدة — مع فلترة الموسم
===================================
الجديد: تبويبات للمواسم + تبويبات للدوريات.
كل استعلام صار يفلتر على league_code AND season.

التشغيل:
    python make_site3.py
"""

import sqlite3
import csv
from config import DB_FILE, TEAMS_FILE, LEAGUES

OUTPUT = DB_FILE.parent / "site.html"


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
  h2 { font-size:17px; margin:28px 0 12px; padding-right:10px;
       border-right:3px solid #2f81f7; }
  table { width:100%; border-collapse:collapse; background:#161b22;
          border-radius:10px; overflow:hidden; }
  th,td { padding:10px 8px; text-align:center; font-size:14px; }
  th { background:#1c2128; color:#7d8590; font-size:12px; }
  th.r { text-align:right; }
  tr { border-bottom:1px solid #21262d; }
  tr:last-child { border-bottom:none; }
  .team { text-align:right; display:flex; align-items:center; gap:9px; }
  .team img { width:22px; height:22px; object-fit:contain; }
  .pos { color:#7d8590; width:34px; }
  .pts { font-weight:700; color:#2f81f7; }
  .top .pos { color:#3fb950; font-weight:700; }
  .bottom .pos { color:#f85149; }
  .match { background:#161b22; border-radius:10px; padding:13px;
           margin-bottom:8px; display:grid;
           grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; }
  .side { display:flex; align-items:center; gap:8px; font-size:14px; }
  .side.away { justify-content:flex-end; }
  .side img { width:26px; height:26px; object-fit:contain; }
  .score { font-size:18px; font-weight:700; padding:4px 13px;
           background:#0d1117; border-radius:6px; white-space:nowrap; }
  .date { grid-column:1/-1; text-align:center; color:#7d8590;
          font-size:11px; margin-top:5px; }
  ol { list-style:none; background:#161b22; border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid #21262d; font-size:14px; }
  ol li:last-child { border-bottom:none; }
  .num { color:#7d8590; width:20px; }
  .pname { flex:1; }
  .pteam { color:#7d8590; font-size:12px; }
  .pgoals { font-weight:700; color:#2f81f7; min-width:22px; text-align:left; }
  .meta { color:#7d8590; font-size:12px; text-align:center;
          margin-top:14px; }
  .fixes { list-style:none; background:#161b22; border-radius:10px;
           padding:14px 18px; font-size:13px; color:#7d8590; }
  .fixes li { padding:5px 0; }
  .fixes b { color:#e8eaed; }
  footer { text-align:center; color:#7d8590; font-size:12px;
           margin-top:36px; line-height:1.9; }
</style>
"""


def clean(t):
    return (t or "").strip()


def load_overrides():
    logos, notes = {}, {}
    if not TEAMS_FILE.exists():
        return logos, notes
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = clean(row.get("team_id"))
            if not tid:
                continue
            if clean(row.get("logo_local")):
                logos[tid] = clean(row.get("logo_local"))
            if clean(row.get("logo_note")):
                notes[tid] = clean(row.get("logo_note"))
    return logos, notes


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
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
        )
        SELECT t.team_id, t.short_name_ar AS name, t.logo,
            COUNT(*) AS played,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) - SUM(ga) AS diff,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS points
        FROM all_games
        JOIN teams t ON t.team_id = all_games.team
        GROUP BY t.team_id, t.short_name_ar
        ORDER BY points DESC, diff DESC
    """, (code, season, code, season)).fetchall()

    matches = conn.execute("""
        SELECT m.date, m.home_goals, m.away_goals,
               h.team_id AS home_id, h.short_name_ar AS home, h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away, a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ?
        ORDER BY m.date DESC LIMIT 10
    """, (code, season)).fetchall()

    scorers = conn.execute("""
        SELECT g.player_en AS player, t.short_name_ar AS team,
               COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t ON t.team_id = g.team_id
        WHERE g.player_en != ''
          AND m.league_code = ? AND m.season = ?
        GROUP BY g.player_en, t.short_name_ar
        ORDER BY goals DESC LIMIT 10
    """, (code, season)).fetchall()

    return table, matches, scorers


def render_panel(code, season, table, matches, scorers, logos, notes):
    def logo_of(tid, fb):
        return logos.get(str(tid), fb)

    rows = ""
    for i, r in enumerate(table, 1):
        cls = "top" if i <= 3 else ("bottom" if i > len(table) - 2 else "")
        rows += (
            f'<tr class="{cls}"><td class="pos">{i}</td>'
            f'<td class="team"><img src="{logo_of(r["team_id"], r["logo"])}" alt="">'
            f'<span>{clean(r["name"])}</span></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )

    cards = ""
    for m in matches:
        cards += (
            f'<div class="match">'
            f'<div class="side"><img src="{logo_of(m["home_id"], m["home_logo"])}" alt="">'
            f'<span>{clean(m["home"])}</span></div>'
            f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>'
            f'<div class="side away"><span>{clean(m["away"])}</span>'
            f'<img src="{logo_of(m["away_id"], m["away_logo"])}" alt=""></div>'
            f'<div class="date">{m["date"]}</div></div>'
        )

    sc = ""
    for i, s in enumerate(scorers, 1):
        sc += (
            f'<li><span class="num">{i}</span>'
            f'<span class="pname">{clean(s["player"])}</span>'
            f'<span class="pteam">{clean(s["team"])}</span>'
            f'<span class="pgoals">{s["goals"]}</span></li>'
        )

    ids = {str(r["team_id"]) for r in table}
    mine = {t: n for t, n in notes.items() if t in ids}
    fixes = ""
    if mine:
        items = "".join(
            f'<li><b>{next((clean(r["name"]) for r in table if str(r["team_id"]) == t), t)}</b>'
            f' — {n}</li>' for t, n in mine.items())
        fixes = f'<h2>تصحيحات يدوية</h2><ul class="fixes">{items}</ul>'

    return (
        f'<section class="panel" id="{season}_{code}">'
        f'<h2>جدول الترتيب</h2>'
        f'<table><tr><th>#</th><th class="r">الفريق</th><th>لعب</th>'
        f'<th>ف</th><th>ت</th><th>خ</th><th>+/-</th><th>نقاط</th></tr>'
        f'{rows}</table>'
        f'<div class="meta">موسم {season}-{season+1}</div>'
        f'<h2>آخر النتائج</h2>{cards}'
        f'<h2>الهدافون</h2><ol>{sc}</ol>'
        f'{fixes}</section>'
    )


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    logos, notes = load_overrides()

    combos = available(conn)
    if not combos:
        print("ما في مباريات بالديتابيس")
        conn.close()
        return

    seasons = sorted({c["season"] for c in combos}, reverse=True)
    leagues = [c for c in LEAGUES if any(x["league_code"] == c for x in combos)]

    panels = ""
    for c in combos:
        table, matches, scorers = get_data(conn, c["league_code"], c["season"])
        if table:
            panels += render_panel(c["league_code"], c["season"],
                                   table, matches, scorers, logos, notes)

    season_tabs = "".join(
        f'<button class="tab tab-season" data-season="{s}">'
        f'{s}-{s+1}</button>' for s in seasons)

    league_tabs = "".join(
        f'<button class="tab tab-league" data-league="{c}">'
        f'{LEAGUES[c]["name_ar"]}</button>' for c in leagues)

    html = (
        '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>الدوريات العربية</title>\n'
        + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        '<header><h1>الدوريات العربية</h1>'
        '<div class="sub">أرشيف المواسم</div></header>\n'
        f'<div class="tabs seasons">{season_tabs}</div>\n'
        f'<div class="tabs">{league_tabs}</div>\n'
        f'{panels}\n'
        '<div id="empty">ما في بيانات لهذا الدوري بهذا الموسم</div>\n'
        '<footer>الأسماء والشعارات المصححة من إعداد المطوّر<br>'
        'البيانات الأساسية من API-Football</footer>\n'
        '</div>\n'
        + SCRIPT +
        '</body>\n</html>'
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم: {OUTPUT.name}")
    print(f"{'=' * 55}")
    for c in combos:
        print(f"  {LEAGUES[c['league_code']]['name_ar']:<18} "
              f"موسم {c['season']}   {c['n']} ماتش")
    print(f"""
  تبويبات المواسم فوق (خضرا)، والدوريات تحتها (زرقا).
  التركيبات غير الموجودة بتعرض رسالة بدل جدول فاضي.
    """)


if __name__ == "__main__":
    main()
