#!/usr/bin/env python3
"""
توليد صفحة لكل لاعب — بلغتين
================================
    players/mohanad-ali.html       → العربي
    en/players/mohanad-ali.html    → الإنجليزي

كل صفحة فيها:
  - الاسم والنادي الأخير
  - ملخص: أهداف · أندية · مواسم · دوريات
  - تفاصيل السعودي (إن توفّرت): مباريات · متوسط تقييم ·
    دقائق · بطاقات — عبر جسر player_id
  - الأهداف موزّعة على المواسم والأندية، كل هدف يربط بمباراته

⚠️ **جسر `player_id`** (درس 44): `goals` لا يحمل معرّفات، و
   `player_stats` يحمل الاسم الكامل لا المختصر. `lineup_players`
   يحمل **الاسم المختصر + المعرّف** فهو الجسر بينهما.
   النتيجة: 490 هدّافاً بتفاصيل بدل 126.

⚠️ **السقف البنيوي:** التفاصيل للسعودي فقط (93.9%). العراقي
   1.5% والأردني 0.3% — المزوّد لا يوفّر تشكيلاتهما (درس 25).
   الصفحة تقول ذلك صراحةً بدل أن تبدو ناقصة.

⚠️ **`noindex` للصفحات الرقيقة:** لاعب بهدف واحد وبلا تفاصيل
   يحصل على صفحة كاملة يصلها الزائر بالضغط، لكن Google لا
   يفهرسها. 590 لاعباً في هذه الحالة (39%)، وفهرستها تُضعف
   تقييم الموقع كله.

⚠️ **`player_id = 0` مستثنى** — يجمع 12 لاعباً مختلفين.

صفر طلبات API.

التشغيل:
    python make_players.py
"""

import csv
import os
import sqlite3
from collections import defaultdict

from config import DB_FILE, TEAMS_FILE
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from player_slug import build_slug_map
from search_view import (SEARCH_CSS, search_box, search_script,
                         search_overlay)
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)

BASE = DB_FILE.parent

# صفحة بأقل من هذا وبلا تفاصيل → noindex
THIN_GOALS = 2


STYLE = """
<style>""" + VARS + """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:820px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:14px; }
  .lang { background:var(--card); color:var(--muted);
          border:1px solid var(--line); padding:6px 14px;
          border-radius:8px; font-size:13px; text-decoration:none; }
  .lang:hover { background:var(--card2); color:var(--text); }

  header { text-align:center; margin-bottom:22px; }
  h1 { font-size:26px; line-height:1.3; }
  .sub { color:var(--muted); font-size:14px; margin-top:6px;
         display:flex; align-items:center; justify-content:center;
         gap:7px; flex-wrap:wrap; }
  .sub img { width:20px; height:20px; object-fit:contain; }
  .sub a { color:var(--muted); text-decoration:none; }
  .sub a:hover { color:var(--accent); }

  .cards { display:flex; flex-wrap:wrap; gap:9px;
           justify-content:center; margin-bottom:22px; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:11px; padding:11px 16px; text-align:center;
          min-width:82px; }
  .card .v { font-size:21px; font-weight:700; }
  .card .k { color:var(--muted); font-size:11px; margin-top:2px; }
  .card.hi .v { color:var(--accent); }

  h2 { font-size:16px; margin:24px 0 10px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  h3 { font-size:13px; color:var(--muted); margin:16px 0 7px; }

  .grow { background:var(--card); border:1px solid var(--line);
          border-radius:11px; overflow:hidden; }
  .g { display:flex; align-items:center; gap:10px; padding:9px 13px;
       border-bottom:1px solid var(--line); font-size:14px;
       text-decoration:none; color:var(--text); }
  .g:last-child { border-bottom:none; }
  .g:hover { background:var(--card2); }
  .g .min { background:var(--deep); color:var(--accent);
            border-radius:6px; padding:2px 8px; font-size:12px;
            min-width:42px; text-align:center; font-weight:600; }
  .g .vs { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .g .dt { color:var(--muted); font-size:11px; white-space:nowrap; }
  .g .tag { background:var(--card2); color:var(--muted);
            border-radius:5px; padding:1px 6px; font-size:10px; }

  .note { background:var(--card); border:1px solid var(--line);
          border-radius:10px; padding:13px; color:var(--muted);
          font-size:13px; line-height:1.8; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:34px; line-height:1.9; }
  footer a { color:var(--accent); text-decoration:none; }
""" + SEARCH_CSS + """
</style>"""


def clean(v):
    return (v or "").strip()


def load_teams():
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
                "en": (clean(r.get("name_en_official"))
                       or clean(r.get("name_en"))),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


def tname(t, lang):
    if not t:
        return "—"
    return (t["ar"] or t["en"]) if lang == "ar" else (t["en"] or t["ar"])


def logo_url(t, lang, depth):
    if not t:
        return ""
    up = "../" * depth
    if t["logo_local"]:
        return up + t["logo_local"]
    return t["logo"]


def gather(conn):
    """كل بيانات اللاعبين — استعلام واحد لكل جدول"""
    goals = defaultdict(list)

    q = """
        SELECT g.player_en AS en, g.player_ar AS ar,
               g.team_id, g.minute, g.detail,
               m.match_id, m.date, m.season, m.league_code,
               m.home_id, m.away_id
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en IS NOT NULL AND g.player_en != ''
        ORDER BY m.date DESC
    """
    for r in conn.execute(q):
        goals[r["en"]].append(dict(r))

    # جسر: اسم → player_id
    name_ids = defaultdict(set)
    for r in conn.execute("""
            SELECT player_id, player_en FROM lineup_players
            WHERE player_id IS NOT NULL AND player_id != 0
              AND player_en IS NOT NULL AND player_en != ''
        """):
        name_ids[r["player_en"]].add(r["player_id"])

    bridge = {n: list(ids)[0] for n, ids in name_ids.items()
              if len(ids) == 1}

    # إحصائيات مجمّعة لكل معرّف
    stats = {}
    try:
        for r in conn.execute("""
                SELECT player_id,
                       COUNT(match_id) AS apps,
                       SUM(minutes) AS mins,
                       AVG(rating) AS rate,
                       SUM(assists) AS ast,
                       SUM(yellow) AS yel,
                       SUM(red) AS red
                FROM player_stats
                WHERE player_id IS NOT NULL AND player_id != 0
                  AND minutes IS NOT NULL AND minutes > 0
                GROUP BY player_id
            """):
            stats[r["player_id"]] = dict(r)
    except sqlite3.Error:
        pass

    return goals, bridge, stats


def build(name, rows, st, teams, lang, slugs, thin):
    t = T[lang]
    depth = 1 if lang == "ar" else 2
    up = "../" * depth

    ar = clean(rows[0]["ar"])
    en = clean(name)
    disp = (ar or en) if lang == "ar" else (en or ar)

    n_goals = len(rows)
    clubs = {r["team_id"] for r in rows}
    seasons = {r["season"] for r in rows}
    lgs = {r["league_code"] for r in rows}

    last_team = teams.get(rows[0]["team_id"])

    # ── البطاقات ─────────────────────────────────────
    cards = (f'<div class="card hi"><div class="v">{n_goals}</div>'
             f'<div class="k">{t["p_goals"]}</div></div>')

    if st:
        apps = st.get("apps") or 0
        rate = st.get("rate")
        mins = st.get("mins") or 0
        ast = st.get("ast") or 0
        yel = st.get("yel") or 0
        red = st.get("red") or 0

        if apps:
            cards += (f'<div class="card"><div class="v">{apps}</div>'
                      f'<div class="k">{t["p_apps"]}</div></div>')
        if rate:
            cards += (f'<div class="card"><div class="v">'
                      f'{rate:.2f}</div>'
                      f'<div class="k">{t["p_rating"]}</div></div>')
        if mins:
            cards += (f'<div class="card"><div class="v">'
                      f'{int(mins):,}</div>'
                      f'<div class="k">{t["p_mins"]}</div></div>')
        if ast:
            cards += (f'<div class="card"><div class="v">{int(ast)}</div>'
                      f'<div class="k">{t["p_assists"]}</div></div>')
        if yel or red:
            cards += (f'<div class="card"><div class="v">'
                      f'{int(yel)}/{int(red)}</div>'
                      f'<div class="k">{t["p_cards"]}</div></div>')
    else:
        cards += (f'<div class="card"><div class="v">{len(seasons)}</div>'
                  f'<div class="k">{t["p_seasons"]}</div></div>')
        cards += (f'<div class="card"><div class="v">{len(clubs)}</div>'
                  f'<div class="k">{t["p_clubs"]}</div></div>')

    # ── الأهداف حسب الموسم ───────────────────────────
    by_season = defaultdict(list)
    for r in rows:
        by_season[(r["season"], r["league_code"])].append(r)

    blocks = ""
    for (season, code), items in sorted(by_season.items(),
                                        key=lambda x: -x[0][0]):
        lg = league_name(code, lang)
        blocks += (f'<h3>{lg} — {t["season"]} {season}'
                   f'  ·  {len(items)} {t["p_goals"]}</h3>'
                   f'<div class="grow">')
        for r in items:
            opp_id = (r["away_id"] if r["team_id"] == r["home_id"]
                      else r["home_id"])
            opp = tname(teams.get(opp_id), lang)
            mine = tname(teams.get(r["team_id"]), lang)
            minute = r["minute"]
            mtxt = f"{minute}'" if minute is not None else "—"
            tag = ""
            d = clean(r["detail"])
            if d == "Penalty":
                tag = f'<span class="tag">{t["penalty"]}</span>'
            elif d == "Own Goal":
                tag = f'<span class="tag">{t["own_goal"]}</span>'

            blocks += (
                f'<a class="g" href="{up}matches/{r["match_id"]}.html">'
                f'<span class="min">{mtxt}</span>'
                f'<span class="vs">{mine} × {opp}</span>{tag}'
                f'<span class="dt">{r["date"][:10]}</span></a>'
            )
        blocks += '</div>'

    # ── ملاحظة الدوريات بلا تفاصيل ───────────────────
    note = ""
    if not st and lgs & {"JOR", "IRQ"}:
        note = (f'<h2>{t["p_more"]}</h2>'
                f'<div class="note">{t["p_nodetail"]}</div>')

    # ── الرأس ────────────────────────────────────────
    other = slugs[name]
    switch = (f"../en/players/{other}.html" if lang == "ar"
              else f"../../players/{other}.html")

    club_line = ""
    if last_team:
        lg_img = logo_url(last_team, lang, depth)
        club_line = (f'<img src="{lg_img}" alt="">'
                     f'<a href="{up}clubs/{rows[0]["team_id"]}.html">'
                     f'{tname(last_team, lang)}</a>')

    robots = ('<meta name="robots" content="noindex,follow">\n'
              if thin else "")

    desc = f'{disp} — {n_goals} {t["p_goals"]}'

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n'
        '<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f'<title>{disp} — {t["site_title"]}</title>\n'
        + robots
        + head_meta(disp, desc, up)
        + THEME_HEAD + STYLE
        + '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">{back_button(t["back"])}'
        f'<span style="display:flex;gap:8px">'
        f'<a class="lang" href="{switch}">{SWITCH_LABEL[lang]}</a>'
        f'{search_box(t)}{THEME_BUTTON}</span></div>\n'
        f'<header><h1>{disp}</h1>'
        f'<div class="sub">{club_line}</div></header>\n'
        f'<div class="cards">{cards}</div>\n'
        f'<h2>{t["p_all_goals"]}</h2>\n{blocks}\n{note}\n'
        f'<footer><a href="{up}about.html">{t["about"]}</a><br>'
        f'{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + THEME_SCRIPT + BACK_SCRIPT
        + search_script(t, depth, lang)
        + '\n</body>\n</html>'
    )


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    teams = load_teams()
    goals, bridge, stats = gather(conn)
    conn.close()

    if not goals:
        print("ما في أهداف مخزّنة")
        return

    counts = {n: len(rows) for n, rows in goals.items()}
    slugs = build_slug_map(counts)

    os.makedirs(BASE / "players", exist_ok=True)
    os.makedirs(BASE / "en" / "players", exist_ok=True)

    made = thin_n = with_stats = 0

    for name, rows in goals.items():
        s = slugs.get(name)
        if not s:
            continue

        pid = bridge.get(name)
        st = stats.get(pid) if pid else None
        if st:
            with_stats += 1

        thin = (len(rows) < THIN_GOALS) and not st
        if thin:
            thin_n += 1

        for lang in LANGS:
            html = build(name, rows, st, teams, lang, slugs, thin)
            path = (BASE / "players" / f"{s}.html" if lang == "ar"
                    else BASE / "en" / "players" / f"{s}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        made += 1

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} لاعب × لغتين")
    print(f"  players/  +  en/players/")
    print(f"{'=' * 55}")
    print(f"  بتفاصيل (تقييم ودقائق) : {with_stats}")
    print(f"  رقيقة — noindex        : {thin_n}")
    print(f"  إجمالي الصفحات         : {made * 2:,}")

    sample = sorted(counts.items(), key=lambda x: -x[1])[0]
    print(f"\n  جرّب:")
    print(f"      start players\\{slugs[sample[0]]}.html")
    print()


if __name__ == "__main__":
    main()
