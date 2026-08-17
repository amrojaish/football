#!/usr/bin/env python3
"""
توليد صفحة لكل نادي — بلغتين
================================
بيولّد نسختين لكل نادٍ:
    clubs/4532.html       → العربي (RTL)
    en/clubs/4532.html    → الإنجليزي (LTR)

كل صفحة فيها:
  - الشعار والاسم والمدينة
  - تبويبات المواسم
  - ملخص قابل للفلترة (اضغط فاز/تعادل/خسر)
  - المباريات (آخر 3، وزر يفتح الباقي)
  - هدافو النادي (أول 5، وزر يفتح الباقي)

كل النصوص من i18n.py.

صفر طلبات API.

التشغيل:
    python make_clubs.py
"""

import sqlite3
import csv
import os
from config import DB_FILE, TEAMS_FILE
from tiebreak import sort_table
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)

BASE = DB_FILE.parent


STYLE = """
<style>""" + VARS + """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:900px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:14px; }
  .back { display:inline-block; color:var(--accent); text-decoration:none;
          font-size:14px; }
  .back:hover { text-decoration:underline; }
  .lang { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:var(--card2); color:var(--text); }
  .club-head { display:flex; align-items:center; gap:16px;
               background:var(--card); border-radius:12px;
               padding:20px; margin-bottom:8px; }
  .club-head img { width:64px; height:64px; object-fit:contain; }
  .club-head h1 { font-size:24px; }
  .club-head .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  h2 { font-size:17px; margin:28px 0 12px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  h3 { font-size:14px; color:var(--muted); margin:18px 0 8px;
       font-weight:normal; }
  .summary { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
  .stat { background:var(--card); border-radius:9px; padding:10px 14px;
          text-align:center; min-width:64px; flex:1; }
  .stat .n { font-size:19px; font-weight:700; }
  .stat .l { font-size:11px; color:var(--muted); }
  .stat.hi .n { color:var(--accent); }
  .stat.click { cursor:pointer; transition:.15s; }
  .stat.click:hover { background:var(--card2); }
  .stat.act { background:var(--accent); }
  .stat.act .n, .stat.act .l { color:var(--bg); }
  .match { background:var(--card); border-radius:10px; padding:12px;
           margin-bottom:7px; display:grid;
           grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; }
  .match.filt { display:none; }
  .side { display:flex; align-items:center; gap:8px; font-size:14px;
          min-width:0; }
  .side.away { justify-content:flex-end; }
  a.side { text-decoration:none; color:var(--text); }
  a.side:hover span { color:var(--accent); }
  .side img { width:24px; height:24px; object-fit:contain; }
  .side span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .score { font-size:17px; font-weight:700; padding:4px 12px;
           background:var(--deep); border-radius:6px; white-space:nowrap; }
  .date { grid-column:1/-1; text-align:center; color:var(--muted);
          font-size:11px; margin-top:4px; }
  .date a { color:var(--muted); text-decoration:none; }
  .date a:hover { color:var(--accent); }
  .rw { border-inline-start:3px solid var(--green); }
  .rd { border-inline-start:3px solid var(--muted); }
  .rl { border-inline-start:3px solid var(--red); }
  .rn { border-inline-start:3px solid var(--accent); }
  ol { list-style:none; background:var(--card); border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid var(--line); font-size:14px; }
  ol li:last-child { border-bottom:none; }
  ol li.hidden { display:none; }
  .num { color:var(--muted); width:20px; }
  .pname { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .pgoals { font-weight:700; color:var(--accent); min-width:22px;
            text-align:end; }
  .more { display:block; width:100%; margin:6px 0 14px;
          background:var(--card); color:var(--accent); border:1px solid var(--line);
          padding:11px; border-radius:9px; cursor:pointer;
          font-family:inherit; font-size:14px; }
  .more:hover { background:var(--card2); }
  .hidden { display:none; }
  .stabs { display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 4px; }
  .stab { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:8px 16px; border-radius:8px; cursor:pointer;
          font-family:inherit; font-size:14px; }
  .stab:hover { background:var(--card2); color:var(--text); }
  .stab.active { background:var(--green); color:var(--bg); border-color:var(--green); }
  .spanel { display:none; }
  .spanel.on { display:block; }
  footer { text-align:center; color:var(--muted); font-size:12px;
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
                "name_en": (clean(r.get("name_en_official"))
                            or clean(r.get("name_en"))),
                "short": clean(r.get("short_name_ar")),
                "city": clean(r.get("city")),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
                "league": clean(r.get("league_code")),
            }
    return teams


def tname(t, lang, full=False):
    """اسم النادي حسب اللغة"""
    if lang == "ar":
        return (t["name_ar"] if full else t["short"]) or t["name_en"]
    return t["name_en"] or t["short"] or t["name_ar"]


def logo_url(t, lang):
    """
    الشعار — المسار النسبي يعتمد على عمق الصفحة:
      clubs/x.html      → ../logos/
      en/clubs/x.html   → ../../logos/
    """
    up = "../" if lang == "ar" else "../../"
    if t["logo_local"]:
        return up + t["logo_local"]
    return t["logo"] or ""


def standings(conn, code, season):
    """جدول الترتيب — نفس منطق make_site3 مع tiebreak"""
    rows = conn.execute("""
        WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL
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
        SELECT m.match_id, m.date, m.home_id, m.away_id,
               m.home_goals, m.away_goals
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


def render_season(conn, tid, teams, code, season, lang):
    """قسم موسم واحد بصفحة النادي"""
    t = T[lang]
    table = standings(conn, code, season)

    me = None
    pos = 0
    for i, r in enumerate(table, 1):
        if r["team_id"] == tid:
            me, pos = r, i
            break
    if me is None:
        me = {"played": 0, "wins": 0, "draws": 0, "losses": 0,
              "scored": 0, "conceded": 0, "points": 0}
        pos = "—"

    lg = league_name(code, lang)

    stats = (
        f'<div class="summary">'
        f'<div class="stat hi"><div class="n">{pos}</div>'
        f'<div class="l">{t["rank"]}</div></div>'
        f'<div class="stat hi"><div class="n">{me["points"]}</div>'
        f'<div class="l">{t["points"]}</div></div>'
        f'<div class="stat"><div class="n">{me["played"]}</div>'
        f'<div class="l">{t["played"]}</div></div>'
        f'<div class="stat click" data-f="rw"><div class="n">{me["wins"]}</div>'
        f'<div class="l">{t["won"]}</div></div>'
        f'<div class="stat click" data-f="rd"><div class="n">{me["draws"]}</div>'
        f'<div class="l">{t["drawn"]}</div></div>'
        f'<div class="stat click" data-f="rl"><div class="n">{me["losses"]}</div>'
        f'<div class="l">{t["lost"]}</div></div>'
        f'<div class="stat"><div class="n">{me["scored"]}</div>'
        f'<div class="l">{t["gf"]}</div></div>'
        f'<div class="stat"><div class="n">{me["conceded"]}</div>'
        f'<div class="l">{t["ga"]}</div></div>'
        f'</div>'
    )

    arrow = "←" if lang == "ar" else "→"
    up = "../" if lang == "ar" else "../../"

    cards = ""
    idx = 0
    blank = {"short": "", "name_en": "", "name_ar": "",
             "logo": "", "logo_local": ""}

    # القادمة أولاً (الأقرب فالأبعد)، ثم المنتهية (الأحدث فالأقدم)
    all_m = club_matches(conn, tid, code, season)
    upcoming = sorted([m for m in all_m if m["home_goals"] is None],
                      key=lambda m: m["date"])
    played = [m for m in all_m if m["home_goals"] is not None]

    for m in upcoming + played:
        h, a = m["home_id"], m["away_id"]
        hg, ag = m["home_goals"], m["away_goals"]
        ht = teams.get(h, dict(blank, short=str(h)))
        at = teams.get(a, dict(blank, short=str(a)))

        if hg is None or ag is None:
            cls = "rn"
            score = "—"
        else:
            my_gf = hg if h == tid else ag
            my_ga = ag if h == tid else hg
            cls = "rw" if my_gf > my_ga else ("rd" if my_gf == my_ga else "rl")
            score = f"{hg} - {ag}"

        idx += 1
        hide = " hidden" if idx > 3 else ""
        cards += (
            f'<div class="match {cls}{hide}" data-m="1">'
            f'<a class="side" href="{h}.html">'
            f'<img src="{logo_url(ht, lang)}" alt="">'
            f'<span>{tname(ht, lang)}</span></a>'
            f'<div class="score">{score}</div>'
            f'<a class="side away" href="{a}.html">'
            f'<span>{tname(at, lang)}</span>'
            f'<img src="{logo_url(at, lang)}" alt=""></a>'
            f'<div class="date">'
            f'<a href="../matches/{m["match_id"]}.html">'
            f'{m["date"]} {arrow}</a></div></div>'
        )

    sc = ""
    n_sc = 0
    for i, s in enumerate(club_scorers(conn, tid, code, season), 1):
        name = (clean(s["ar"]) if lang == "ar" else "") or clean(s["en"])
        n_sc = i
        hide_s = "hidden" if i > 5 else ""
        sc += (f'<li class="{hide_s}"><span class="num">{i}</span>'
               f'<span class="pname">{name}</span>'
               f'<span class="pgoals">{s["goals"]}</span></li>')

    scorers_block = ""
    if sc:
        more_s = (f'<button class="more">'
                  f'{t["show_all_scorers"]} ({n_sc - 5})</button>'
                  if n_sc > 5 else '')
        scorers_block = (f'<h3>{t["club_scorers"]}</h3>'
                         f'<ol>{sc}</ol>{more_s}')

    more_m = (f'<button class="more" data-s="{code}_{season}">'
              f'{t["show_all_matches"]} ({idx - 3})</button>'
              if idx > 3 else '')

    panel = (
        f'<section class="spanel" id="s_{code}_{season}">'
        f'<h2>{lg} — {t["season"]} {season}-{season+1}</h2>'
        f'{stats}'
        f'<h3>{t["all_matches"]}</h3><div class="mbox">{cards}</div>'
        f'{more_m}{scorers_block}'
        f'</section>'
    )

    return panel, f'{code}_{season}', f'{lg} {season}-{season+1}'


def page_script(t):
    """الـJS — نصوص الأزرار من الترجمة"""
    return (
        '<script>\n'
        'const T=document.querySelectorAll(".stab");\n'
        'const P=document.querySelectorAll(".spanel");\n'
        'function go(k){P.forEach(p=>p.classList.toggle("on",p.id==="s_"+k));\n'
        'T.forEach(t=>t.classList.toggle("active",t.dataset.k===k));}\n'
        'T.forEach(t=>t.addEventListener("click",function(){go(this.dataset.k);}));\n'
        'if(T.length)go(T[0].dataset.k);\n'
        f'var SA="{t["show_all"]}",SL="{t["show_less"]}";\n'
        'document.querySelectorAll(".more").forEach(function(b){\n'
        'b.dataset.open="0";\n'
        'b.addEventListener("click",function(){\n'
        'var box=this.previousElementSibling;\n'
        'var kids=box.children;\n'
        'var lim=box.tagName==="OL"?5:3;\n'
        'var op=this.dataset.open==="1";\n'
        'var vis=[];\n'
        'for(var i=0;i<kids.length;i++){\n'
        'if(!kids[i].classList.contains("filt")){vis.push(kids[i]);}}\n'
        'var lm=box.tagName==="OL"?5:(vis.length<kids.length?5:lim);\n'
        'vis.forEach(function(m,j){\n'
        'if(j>=lm){m.classList.toggle("hidden",op);}});\n'
        'this.dataset.open=op?"0":"1";\n'
        'this.textContent=(op?SA+" ("+(vis.length-lm)+")":SL);\n'
        '});});\n'
        'document.querySelectorAll(".stat.click").forEach(function(s){\n'
        's.addEventListener("click",function(){\n'
        'var p=this.closest(".spanel");\n'
        'var f=this.dataset.f;\n'
        'var was=this.classList.contains("act");\n'
        'p.querySelectorAll(".stat.click").forEach(function(x){\n'
        'x.classList.remove("act");});\n'
        'var box=p.querySelector(".mbox");\n'
        'var btn=p.querySelector(".mbox+.more");\n'
        'if(was){\n'
        'box.querySelectorAll(".match").forEach(function(m,i){\n'
        'm.classList.remove("filt");\n'
        'm.classList.toggle("hidden",i>=3);});\n'
        'if(btn){btn.style.display="";btn.dataset.open="0";\n'
        'btn.textContent=SA+" ("+(box.children.length-3)+")";}\n'
        'return;}\n'
        'this.classList.add("act");\n'
        'var k=0;\n'
        'box.querySelectorAll(".match").forEach(function(m){\n'
        'var ok=m.classList.contains(f);\n'
        'm.classList.toggle("filt",!ok);\n'
        'if(ok){k++;m.classList.toggle("hidden",k>5);}\n'
        'else{m.classList.remove("hidden");}});\n'
        'if(btn){if(k>5){btn.style.display="";btn.dataset.open="0";\n'
        'btn.textContent=SA+" ("+(k-5)+")";}\n'
        'else{btn.style.display="none";}}\n'
        '});});\n'
        '</script>\n'
    )


def build_page(conn, tid, teams, lang):
    """صفحة نادٍ واحدة بلغة واحدة — None لو ما في محتوى"""
    t = T[lang]
    team = teams[tid]

    body = ""
    tabs = ""
    for s in club_seasons(conn, tid):
        out = render_season(conn, tid, teams,
                            s["league_code"], s["season"], lang)
        if not out:
            continue
        panel, key, label = out
        body += panel
        tabs += f'<button class="stab" data-k="{key}">{label}</button>'

    if not body:
        return None

    body = f'<div class="stabs">{tabs}</div>' + body

    # الرئيسية بنفس اللغة
    home = "../index.html"
    # اللغة الأخرى لنفس النادي
    switch = (f'../en/clubs/{tid}.html' if lang == "ar"
              else f'../../clubs/{tid}.html')

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{tname(team, lang, full=True)} — {t["site_title"]}</title>\n'
        + head_meta(tname(team, lang, full=True), t["site_sub"],
                    "../" if lang == "ar" else "../../")
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<span style="display:flex;gap:8px;align-items:center">'
        f'{back_button(t["back"])}'
        f'<a class="back" href="{home}">{t["back_home"]}</a></span>'
        f'<span style="display:flex;gap:8px">'
        f'<a class="lang" href="{switch}">{SWITCH_LABEL[lang]}</a>'
        f'{THEME_BUTTON}</span>'
        f'</div>\n'
        f'<div class="club-head">'
        f'<img src="{logo_url(team, lang)}" alt="">'
        f'<div><h1>{tname(team, lang, full=True)}</h1>'
        f'<div class="sub">{team["city"]}</div></div></div>\n'
        f'{body}\n'
        f'<footer><a href="../about.html" style="color:var(--accent);text-decoration:none">{t["about"]}</a><br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + page_script(t) + THEME_SCRIPT + BACK_SCRIPT +
        '</body>\n</html>'
    )


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    teams = load_teams()

    os.makedirs(BASE / "clubs", exist_ok=True)
    os.makedirs(BASE / "en" / "clubs", exist_ok=True)

    ids = [r[0] for r in conn.execute("""
        SELECT DISTINCT home_id FROM matches
        UNION SELECT DISTINCT away_id FROM matches
    """).fetchall()]

    made = skipped = 0

    for tid in sorted(ids):
        if tid not in teams:
            print(f"  ⚠️ نادي {tid} مش موجود بجدول teams — تخطي")
            skipped += 1
            continue

        wrote = False
        for lang in LANGS:
            html = build_page(conn, tid, teams, lang)
            if html is None:
                continue
            out = ((BASE / "clubs" / f"{tid}.html") if lang == "ar"
                   else (BASE / "en" / "clubs" / f"{tid}.html"))
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            wrote = True

        if wrote:
            made += 1
        else:
            skipped += 1

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} نادٍ × لغتين")
    print("  clubs/  +  en/clubs/")
    if skipped:
        print(f"  متخطى: {skipped}")
    print(f"{'=' * 55}")
    print("""
  جرّب:
      start clubs\\4532.html
      start en\\clubs\\4532.html
    """)


if __name__ == "__main__":
    main()
