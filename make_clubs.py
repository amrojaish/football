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
from config import DB_FILE, TEAMS_FILE, BASE_DIR
from live_view import LIVE_CSS, live_script
from player_slug import slug as _pslug
from tiebreak import sort_table, STANDINGS_EXCLUDED
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from search_view import (SEARCH_CSS, search_box, search_script,
                         search_overlay)
from live_view import LIVE_CSS, live_script
from navbar import (NAV_CSS, navbar, settings_overlay,
                    nav_script, pwa_script)
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
  /* ⚠️ **قائمة المواسم صارت منسدلة** (26 أغسطس) — كانت صفّ
     أزرار يحتل ارتفاعاً كبيراً بخمسة مواسم أو أكثر، ويدفع
     المحتوى الفعلي تحت الطيّة. الآن زر واحد بمستوى "رجوع". */
  .seasonbox { position:relative; }
  .seasonbtn { background:var(--green); color:var(--bg); border:none;
               border-radius:8px; padding:8px 14px; font-size:13px;
               font-weight:600; cursor:pointer; font-family:inherit;
               display:flex; align-items:center; gap:7px; }
  .seasonbtn .cv { width:7px; height:7px; border-inline-end:2px solid;
                   border-bottom:2px solid; transform:rotate(45deg);
                   margin-top:-3px; transition:transform .18s; }
  .seasonbox.on .seasonbtn .cv { transform:rotate(-135deg);
                                 margin-top:2px; }
  .seasonlist { position:absolute; inset-inline-end:0; top:calc(100% + 6px);
                background:var(--card); border:1px solid var(--line);
                border-radius:10px; padding:6px; min-width:210px;
                display:none; z-index:400;
                box-shadow:0 8px 24px rgba(0,0,0,.4); }
  .seasonbox.on .seasonlist { display:block; }
  /* تبويبان داخل الموسم: مباريات | جدول */
  .itabs { display:flex; gap:0; margin:18px 0 6px;
           border-bottom:1px solid var(--line); }
  .itab { background:none; border:none; color:var(--muted);
          font-family:inherit; font-size:14px; font-weight:600;
          padding:10px 18px; cursor:pointer;
          border-bottom:2px solid transparent; margin-bottom:-1px; }
  .itab:hover { color:var(--text); }
  .itab.on { color:var(--accent); border-bottom-color:var(--accent); }
  .iview { display:none; }
  .iview.on { display:block; }

  /* جدول الترتيب داخل صفحة النادي */
  .tbl { width:100%; border-collapse:collapse; font-size:13px;
         margin-top:6px; }
  .tbl th { color:var(--muted); font-weight:600; font-size:11px;
            padding:8px 4px; text-align:center; }
  .tbl th.team, .tbl td.team { text-align:start; }
  .tbl td { padding:9px 4px; text-align:center;
            border-top:1px solid var(--line); }
  .tbl td.team { display:flex; align-items:center; gap:8px; }
  .tbl td.team img { width:20px; height:20px; object-fit:contain; }
  .tbl td.team a { color:var(--text); text-decoration:none; }
  .tbl td.team a:hover { color:var(--accent); }
  .tbl td.pts { font-weight:700; }
  .tbl tr.me { background:var(--card2); }
  .tbl tr.me td { font-weight:600; }

  /* الرابط الغامر على بطاقة المباراة */
  .match { position:relative; }
  .match .open { position:absolute; inset:0; z-index:1;
                 border-radius:10px; }
  .match .side, .match .date { position:relative; z-index:2; }
  .match .side { width:max-content; max-width:100%; }
  .match .side.away { margin-inline-start:auto; }

  .stabs { display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 4px; }
  .stab { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:8px 16px; border-radius:8px; cursor:pointer;
          font-family:inherit; font-size:14px; }
  .stab:hover { background:var(--card2); color:var(--text); }
  .stab.active { background:var(--green); color:var(--bg); border-color:var(--green); }
  /* داخل القائمة المنسدلة: صف كامل العرض لا شارة */
  .seasonlist .stab { display:block; width:100%; text-align:start;
                      border:none; background:none; border-radius:7px;
                      padding:10px 12px; margin:0; }
  .seasonlist .stab:hover { background:var(--card2); }
  .seasonlist .stab.active { background:var(--green); color:var(--bg); }
  .spanel { display:none; }
  .spanel.on { display:block; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }
""" + SEARCH_CSS + NAV_CSS + LIVE_CSS + """
</style>"""

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
    # ⚠️ STANDINGS_EXCLUDED: راجع standings_exclusions.csv وget_table
    #    بـmake_site3.py (نفس المنطق بالضبط)
    excl_ids = STANDINGS_EXCLUDED or {0}
    excl = ", ".join("?" * len(excl_ids))
    rows = conn.execute(f"""
        WITH all_games AS (
            SELECT home_id AS team, home_goals AS gf, away_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL AND match_id NOT IN ({excl})
            UNION ALL
            SELECT away_id AS team, away_goals AS gf, home_goals AS ga
            FROM matches WHERE league_code = ? AND season = ?
              AND home_goals IS NOT NULL AND match_id NOT IN ({excl})
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
    """, (code, season, *excl_ids, code, season, *excl_ids)).fetchall()
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


# ⚠️ نصوص محلية لا في i18n — ثلاثة عناوين تخصّ هذه الصفحة وحدها.
#    (`upcoming` في i18n مفرد "مباراة قادمة" ولا يصلح عنوان قسم.)
SEC = {
    "ar": {"recent": "آخر المباريات", "next": "المباريات القادمة",
           "more": "عرض المزيد", "stats": "الإحصائيات",
           "assists": "صناعة الأهداف", "yellow": "البطاقات الصفراء",
           "red": "البطاقات الحمراء", "goals_c": "هدف",
           "assists_c": "صناعة", "cards_c": "بطاقة"},
    "en": {"recent": "Recent matches", "next": "Upcoming matches",
           "more": "Show more", "stats": "Stats",
           "assists": "Assists", "yellow": "Yellow cards",
           "red": "Red cards", "goals_c": "goals",
           "assists_c": "assists", "cards_c": "cards"},
}


def club_assists(conn, tid, code, season):
    """صنّاع الأهداف — من player_stats (السعودي فقط عملياً)"""
    return conn.execute("""
        SELECT p.player_en AS en, MAX(p.player_ar) AS ar,
               SUM(p.assists) AS n
        FROM player_stats p JOIN matches m ON m.match_id = p.match_id
        WHERE p.team_id = ? AND m.league_code = ? AND m.season = ?
          AND p.assists > 0 AND p.player_en != ''
        GROUP BY p.player_en ORDER BY n DESC LIMIT 20
    """, (tid, code, season)).fetchall()


def club_cards(conn, tid, code, season, kind):
    """البطاقات — من events. kind: 'Yellow Card' أو 'Red Card'"""
    try:
        return conn.execute("""
            SELECT e.player_en AS en, MAX(e.player_ar) AS ar,
                   COUNT(*) AS n
            FROM events e JOIN matches m ON m.match_id = e.match_id
            WHERE e.team_id = ? AND m.league_code = ? AND m.season = ?
              AND e.type = 'Card' AND e.detail = ?
              AND e.player_en IS NOT NULL AND e.player_en != ''
            GROUP BY e.player_en ORDER BY n DESC LIMIT 20
        """, (tid, code, season, kind)).fetchall()
    except Exception:
        return []


_PLAYER_PAGES = None


def _player_pages():
    global _PLAYER_PAGES
    if _PLAYER_PAGES is None:
        d = BASE_DIR / "players"
        _PLAYER_PAGES = ({f.stem for f in d.glob("*.html")}
                         if d.exists() else set())
    return _PLAYER_PAGES


def player_link(player_en):
    s = _pslug(player_en)
    if s not in _player_pages():
        return ""
    return f"../players/{s}.html"


def render_season(conn, tid, teams, code, season, lang):
    """قسم موسم واحد بصفحة النادي"""
    t = T[lang]
    sec = SEC[lang]
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

    blank = {"short": "", "name_en": "", "name_ar": "",
             "logo": "", "logo_local": ""}

    # ⚠️ **قسمان منفصلان بدل قائمة واحدة** (26 أغسطس): "آخر
    #    المباريات" (المنتهية، الأحدث أولاً) و"القادمة" (الأقرب
    #    أولاً). كانتا مدمجتين فيبدأ القسم بمباريات لم تُلعب بعد.
    all_m = club_matches(conn, tid, code, season)
    upcoming = sorted([m for m in all_m if m["home_goals"] is None],
                      key=lambda m: m["date"])
    played = [m for m in all_m if m["home_goals"] is not None]

    def build_cards(lst, first):
        """بطاقات قسم واحد — `first` كم بطاقة تظهر قبل الضغط"""
        out = ""
        for i, m in enumerate(lst, 1):
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
                cls = ("rw" if my_gf > my_ga
                       else ("rd" if my_gf == my_ga else "rl"))
                score = f"{hg} - {ag}"

            hide = " hidden" if i > first else ""
            # الرابط الغامر: الضغط بأي مكان يفتح المباراة
            out += (
                f'<div class="match {cls}{hide}" data-m="1" '
                f'data-mid="{m["match_id"]}">'
                f'<a class="open" href="../matches/{m["match_id"]}.html"'
                f' aria-label="{tname(ht, lang)} - {tname(at, lang)}"></a>'
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
        return out

    def more_btn(total, first):
        """زر يكشف 5 مباريات إضافية بكل ضغطة"""
        if total <= first:
            return ""
        return (f'<button class="more step">'
                f'{sec["more"]} ({total - first})</button>')

    played_html = build_cards(played, 3)
    upcoming_html = build_cards(upcoming, 3)

    sc = ""
    n_sc = 0
    for i, s in enumerate(club_scorers(conn, tid, code, season), 1):
        name = (clean(s["ar"]) if lang == "ar" else "") or clean(s["en"])
        n_sc = i
        hide_s = "hidden" if i > 5 else ""
        href = player_link(s["en"])
        name_html = (f'<a href="{href}">{name}</a>' if href else name)
        sc += (f'<li class="{hide_s}"><span class="num">{i}</span>'
               f'<span class="pname">{name_html}</span>'
               f'<span class="pgoals">{s["goals"]}</span></li>')

    scorers_block = ""
    if sc:
        more_s = (f'<button class="more">'
                  f'{t["show_all_scorers"]} ({n_sc - 5})</button>'
                  if n_sc > 5 else '')
        scorers_block = (f'<h3>{t["club_scorers"]}</h3>'
                         f'<ol>{sc}</ol>{more_s}')

    # ═══ قوائم اللاعبين: هدافون · صناعات · بطاقات ═══
    def player_list(rows, first=5):
        """
        قائمة مرتّبة بالعدد. تُخفى كلياً إن كانت فارغة.

        ⚠️ **الفارغ يعني قيد المزوّد لا عيب تنفيذ** — الصناعات
           والبطاقات من `player_stats`/`events`، وهما للسعودي
           فقط. لا نعرض قسماً فارغاً ولا رسالة اعتذار.
        """
        if not rows:
            return ""
        li = ""
        for i, r in enumerate(rows, 1):
            name = (clean(r["ar"]) if lang == "ar" else "") or clean(r["en"])
            href = player_link(r["en"])
            nm = f'<a href="{href}">{name}</a>' if href else name
            hide = " hidden" if i > first else ""
            li += (f'<li class="{hide.strip()}">'
                   f'<span class="num">{i}</span>'
                   f'<span class="pname">{nm}</span>'
                   f'<span class="pgoals">{r["n"]}</span></li>')
        btn = ""
        if len(rows) > first:
            btn = (f'<button class="more step">'
                   f'{sec["more"]} ({len(rows) - first})</button>')
        return f'<ol>{li}</ol>{btn}'

    scorers_rows = [{"en": s["en"], "ar": s["ar"], "n": s["goals"]}
                    for s in club_scorers(conn, tid, code, season)]
    stats_blocks = ""
    for rows, title in (
            (scorers_rows, t["club_scorers"]),
            (club_assists(conn, tid, code, season), sec["assists"]),
            (club_cards(conn, tid, code, season, "Yellow Card"),
             sec["yellow"]),
            (club_cards(conn, tid, code, season, "Red Card"), sec["red"])):
        blk = player_list(rows)
        if blk:
            stats_blocks += f'<h3>{title}</h3>{blk}'


    # ═══ جدول الترتيب — النادي مميَّز ═══
    trows = ""
    for i, r in enumerate(table, 1):
        mine = " me" if r["team_id"] == tid else ""
        rt = teams.get(r["team_id"], dict(blank, short=str(r["team_id"])))
        trows += (
            f'<tr class="{mine.strip()}"><td class="pos">{i}</td>'
            f'<td class="team">'
            f'<img src="{logo_url(rt, lang)}" alt="">'
            f'<a href="{r["team_id"]}.html">{tname(rt, lang)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td>'
            f'<td>{r["draws"]}</td><td>{r["losses"]}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )
    table_html = ""
    if trows:
        table_html = (
            f'<table class="tbl"><thead><tr>'
            f'<th>#</th><th class="team">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th>'
            f'<th>{t["drawn"]}</th><th>{t["lost"]}</th>'
            f'<th>{t["points"]}</th>'
            f'</tr></thead><tbody>{trows}</tbody></table>'
        )

    # ⚠️ تبويبان داخل الموسم — الجدول لم يكن معروضاً في صفحة
    #    النادي إطلاقاً قبل 26 أغسطس، رغم أن الداتا محسوبة أصلاً
    #    لاستخراج مركز النادي.
    key = f'{code}_{season}'
    inner = (
        f'<div class="itabs">'
        f'<button class="itab on" data-i="m_{key}">{t["all_matches"]}</button>'
        f'<button class="itab" data-i="t_{key}">{t["standings"]}</button>'
        + (f'<button class="itab" data-i="p_{key}">{sec["stats"]}'
           f'</button>' if stats_blocks else '')
        + f'</div>'
    )

    matches_view = (
        f'<div class="iview on" id="m_{key}">'
        + (f'<h3>{sec["recent"]}</h3>'
           f'<div class="mbox">{played_html}</div>'
           f'{more_btn(len(played), 3)}' if played_html else '')
        + (f'<h3>{sec["next"]}</h3>'
           f'<div class="mbox">{upcoming_html}</div>'
           f'{more_btn(len(upcoming), 3)}' if upcoming_html else '')
        + f'</div>'
    )
    table_view = f'<div class="iview" id="t_{key}">{table_html}</div>'
    stats_view = (f'<div class="iview" id="p_{key}">{stats_blocks}</div>'
                  if stats_blocks else '')

    panel = (
        f'<section class="spanel" id="s_{key}">'
        f'<h2>{lg} — {t["season"]} {season}-{season+1}</h2>'
        f'{stats}{inner}{matches_view}{table_view}{stats_view}'
        f'</section>'
    )

    return panel, f'{code}_{season}', f'{lg} {season}-{season+1}'


def page_script(t, lang="ar"):
    """الـJS — نصوص الأزرار من الترجمة"""
    return (
        '<script>\n'
        'const T=document.querySelectorAll(".stab");\n'
        'const P=document.querySelectorAll(".spanel");\n'
        'function go(k){P.forEach(p=>p.classList.toggle("on",p.id==="s_"+k));\n'
        'T.forEach(t=>t.classList.toggle("active",t.dataset.k===k));\n'
        # نص الزر = الموسم المختار
        'var a=document.querySelector(".stab.active");\n'
        'var l=document.getElementById("seasonlbl");\n'
        'if(a&&l)l.textContent=a.textContent;}\n'
        'T.forEach(t=>t.addEventListener("click",function(){\n'
        'go(this.dataset.k);\n'
        'var b=document.getElementById("seasonbox");if(b)b.classList.remove("on");\n'
        '}));\n'
        'if(T.length)go(T[0].dataset.k);\n'
        # تبويبا "مباريات/جدول" داخل كل موسم
        'document.querySelectorAll(".itab").forEach(function(b){\n'
        'b.addEventListener("click",function(){\n'
        'var sec=this.closest(".spanel");\n'
        'sec.querySelectorAll(".itab").forEach(function(x){\n'
        'x.classList.toggle("on",x===b);});\n'
        'sec.querySelectorAll(".iview").forEach(function(v){\n'
        'v.classList.toggle("on",v.id===b.dataset.i);});\n'
        '});});\n'
        # زر "+5": يكشف خمساً بكل ضغطة ثم يختفي
        'document.querySelectorAll(".more.step").forEach(function(b){\n'
        'b.addEventListener("click",function(){\n'
        'var box=this.previousElementSibling;\n'
        'var hid=box.querySelectorAll(".hidden");\n'
        'for(var i=0;i<5&&i<hid.length;i++)hid[i].classList.remove("hidden");\n'
        'var left=box.querySelectorAll(".hidden").length;\n'
        'if(left===0){this.style.display="none";}\n'
        'else{this.textContent=MORE+" ("+left+")";}\n'
        '});});\n'
        # فتح/إغلاق القائمة + إغلاقها بالضغط خارجها
        'var sb=document.getElementById("seasonbox");\n'
        'var st=document.getElementById("seasonbtn");\n'
        'if(st&&sb){st.addEventListener("click",function(e){\n'
        'e.stopPropagation();sb.classList.toggle("on");});\n'
        'document.addEventListener("click",function(){sb.classList.remove("on");});\n'
        'sb.addEventListener("click",function(e){e.stopPropagation();});}\n'
        f'var SA="{t["show_all"]}",SL="{t["show_less"]}";\n'
        f'var MORE="{SEC[lang]["more"]}";\n'
        # ⚠️ `:not(.step)` إجباري — بدونه يمسك هذا المعالج أزرار
        #    "+5" أيضاً (لأن كلاسها `.more step`) فيفتح الكل دفعة
        #    واحدة ويخفي الزر، ملغياً الكشف التدريجي.
        'document.querySelectorAll(".more:not(.step)").forEach(function(b){\n'
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

    # ⚠️ التبويبات لم تعد ضمن `body` — انتقلت للشريط العلوي
    #    بمستوى زر "رجوع"، وتُمرَّر كوسيط منفصل.
    season_menu = (
        f'<div class="seasonbox" id="seasonbox">'
        f'<button class="seasonbtn" id="seasonbtn">'
        f'<span id="seasonlbl"></span><span class="cv"></span></button>'
        f'<div class="seasonlist">{tabs}</div>'
        f'</div>'
    )

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
                    "../" if lang == "ar" else "../../", lang)
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<span style="display:flex;gap:8px;align-items:center">'
        f'{back_button(t["back"])}'
        f'</span>'
        f'<span style="display:flex;gap:8px;align-items:center">'
        f'{season_menu}'
        f'</span>'
        f'</div>\n'
        f'<div class="club-head">'
        f'<img src="{logo_url(team, lang)}" alt="">'
        f'<div><h1>{tname(team, lang, full=True)}</h1>'
        f'<div class="sub">{team["city"]}</div></div></div>\n'
        f'{body}\n'
        f'<footer><a href="../about.html" style="color:var(--accent);text-decoration:none">{t["about"]}</a><br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        # ⚠️ **العمق يتبع اللغة:** الصفحة العربية بـ`matches/`
        #    (عمق 1) والإنجليزية بـ`en/matches/` (عمق 2).
        #    تمرير 1 ثابتاً كان يجعل زر "المباريات" يحلّ إلى
        #    `en/matches/index.html` — صفحة غير موجودة (404).
        + navbar(t, 1 if lang == "ar" else 2, "", lang)
        + settings_overlay(t, switch, lang)
        + page_script(t, lang) + THEME_SCRIPT + BACK_SCRIPT
                + nav_script(t) + pwa_script(lang)
        + live_script(t, 1)
        + search_script(t, 1 if lang == "ar" else 2, lang) +
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
