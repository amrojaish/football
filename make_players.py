#!/usr/bin/env python3
"""
توليد صفحة لكل لاعب — بلغتين
================================
    players/mohanad-ali.html       → العربي
    en/players/mohanad-ali.html    → الإنجليزي

كل صفحة فيها (18 أكتوبر 2026، شكل FotMob): رأس بصورة دائرية 72px (من player_info.has_photo = 1، وإلا دائرة فارغة بلا حروف)
والاسم والنادي الحالي ونجمة المتابعة، ثم تبويبات «الملف · المباريات · الإحصائيات · المسيرة» (الافتراضي الملف). لا شيء حُذف — نُقل للتبويبات:
  - الملف: العمر (من تاريخ الميلاد) · الجنسية · الطول · المركز · الرقم · النادي — من player_info (fetch_player_info.py)، وإلا المركز/الرقم
    من الإحصائيات/التشكيلات؛ أي حقل غائب يُخفى
  - المباريات: صف لكل مباراة لُعبت (بطاقة match_row المشتركة + سطر الدقائق/الأهداف/الصناعة/البطاقات/التقييم)، الأحدث أولاً، 20 ثم «عرض الكل»؛
    تحتها «كل الأهداف» كما كانت (العراقي/الأردني: الأهداف وحدها + ملاحظتهما القديمة أسفلها؛ المغربي: «المباريات الأساسية فقط»)
  - الإحصائيات: البطاقات + جدول الموسم بالمسابقة (كما كانا)
  - المسيرة: موسم × نادٍ × أهداف + المباريات من التشكيلات حيث توفّرت
السابق:
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
from thumbs_util import thumb_src, logo_img
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from player_pages import get_plan
from player_slug import build_slug_map
from theme import SITE
from search_view import SEARCH_CSS
from navbar import (NAV_CSS, navbar, settings_button, settings_overlay,
                    nav_script, IC_FOLLOWING, appbar)
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)
from matchtime import matchtime_script
from prefs import prefs_script
from match_row import ROW_CSS, card_css, match_row
from tabs_view import TABS_CSS, NOSCRIPT, tabs_html
import assets
from datetime import date

BASE = DB_FILE.parent

# صفحة بأقل من هذا وبلا تفاصيل → noindex
THIN_GOALS = 2


CSS_TYPE = VARS + """
  /* جدول المسيرة */
  .career { width:100%; border-collapse:collapse; font-size:13.5px;
            margin-top:6px; }
  .career th { color:var(--muted); font-weight:600; font-size:12px;
               padding:8px 6px; text-align:start; }
  .career th:last-child, .career td.cg { text-align:end; }
  .career td { padding:11px 6px; border-top:1px solid var(--line); }
  .career td.cs { color:var(--muted); font-size:12.5px;
                  white-space:nowrap; }
  .career td.cc { display:flex; align-items:center; gap:8px; }
  .career td.cc img { width:22px; height:22px; object-fit:contain; }
  .career td.cc a { color:var(--text); text-decoration:none; }
  .career td.cc a:hover { color:var(--accent); }
  .career td.cg { font-weight:700; }
  .career .ca { text-align:center; color:var(--muted); }
  .career tr.ct td { border-top:2px solid var(--line);
                     color:var(--muted); font-size:12.5px; }
  .career tr.ct td.cg { color:var(--accent); font-size:14px; }
  .cwarn { color:var(--muted); font-size:12px; margin-top:8px;
           line-height:1.6; }

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
  /* زر متابعة اللاعب (جزء أ، 22 سبتمبر) — نجمة مفرَّغة/معبَّأة،
     نفس أيقونة "المتابَعة" بالشريط السفلي (IC_FOLLOWING) لتناسق
     بصري كامل. بجانب الاسم مباشرة داخل h1 نفسها فتتمركز معه. */
  .followbtn { background:none; border:none; cursor:pointer;
               padding:11px; margin-block:-11px; color:var(--muted);
               vertical-align:middle; margin-inline-start:8px;
               display:inline-flex; }
  .followbtn svg { width:22px; height:22px; display:block;
                    fill:none; stroke:currentColor; stroke-width:1.7;
                    stroke-linecap:round; stroke-linejoin:round;
                    transition:fill .15s, color .15s; }
  .followbtn:hover { color:var(--accent); }
  .followbtn.on { color:var(--accent); }
  .followbtn.on svg { fill:currentColor; }
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
  .card .k { color:var(--muted); font-size:12px; margin-top:2px; }
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
  .g .dt { color:var(--muted); font-size:12px; white-space:nowrap; }
  .g .tag { background:var(--card2); color:var(--muted);
            border-radius:5px; padding:1px 6px; font-size:12px; }

  .stw { overflow-x:auto; -webkit-overflow-scrolling:touch;
         border:1px solid var(--line); border-radius:11px;
         background:var(--card); }
  .stt { width:100%; border-collapse:collapse; font-size:13px;
         white-space:nowrap; }
  .stt th { background:var(--deep); color:var(--muted);
            font-size:12px; font-weight:600; padding:9px 10px;
            text-align:center; border-bottom:1px solid var(--line); }
  .stt td { padding:9px 10px; text-align:center;
            border-bottom:1px solid var(--line); }
  .stt tbody tr:last-child td { border-bottom:none; }
  .stt tbody tr:hover { background:var(--card2); }
  .stt .sn { text-align:start; font-weight:600;
             position:sticky; inset-inline-start:0;
             background:var(--card); }
  .stt thead .sn { background:var(--deep); }
  .stt .yr { color:var(--muted); font-weight:400; font-size:12px; }

  .seas { margin-bottom:10px; }
  .shead { width:100%; display:flex; align-items:center; gap:9px;
           background:var(--card); border:1px solid var(--line);
           border-radius:11px; padding:11px 14px; cursor:pointer;
           font-family:inherit; color:var(--text); font-size:13px;
           text-align:start; min-height:44px; }
  .shead:hover { background:var(--card2); }
  .sarrow { color:var(--muted); font-size:12px;
            transition:transform .18s; display:inline-block; }
  .seas.open .sarrow { transform:rotate(180deg); }
  .stitle { flex:1; min-width:0; overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap;
            font-weight:600; }
  .scount { color:var(--muted); font-size:12px; white-space:nowrap; }
  .sbody { margin-top:7px; }
  .sbody.hidden { display:none; }
  .g.hidden { display:none; }
  .gmore { display:block; width:100%; margin-top:7px;
           background:var(--card); color:var(--accent);
           border:1px solid var(--line); border-radius:9px;
           padding:8px; font-size:13px; cursor:pointer;
           font-family:inherit; }
  .gmore:hover { background:var(--card2); }

  .note { background:var(--card); border:1px solid var(--line);
          border-radius:10px; padding:13px; color:var(--muted);
          font-size:13px; line-height:1.8; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:34px; line-height:1.9; }
  footer a { color:var(--accent); text-decoration:none; }
"""

# ── صفحة اللاعب بنمط FotMob (18 أكتوبر 2026): التبويبات المشتركة (tabs_view) + بطاقة المباراة المشتركة (match_row) ──
CSS_TYPE += TABS_CSS + card_css(".pms") + ROW_CSS + """
  /* الصورة: 72px دائرية؛ بلا صورة حقيقية = دائرة فارغة (لا حروف) */
  .pph { width:72px; height:72px; border-radius:50%; display:block; margin:0 auto 10px; background:var(--card2);
         border:1px solid var(--line); object-fit:cover; }
  .mp > h2:first-child { display:none; }
  .mp > .cards { margin-top:14px; }
  /* الملف: صف لكل حقل [التسمية … القيمة] */
  .pf { background:var(--card); border:1px solid var(--line); border-radius:11px; margin-top:12px; }
  .pfr { display:flex; justify-content:space-between; align-items:center; gap:12px; min-height:46px; padding:8px 14px;
         border-top:1px solid var(--line); font-size:14px; }
  .pfr:first-child { border-top:none; }
  .pfr .k { color:var(--muted); font-size:13px; flex:0 0 auto; }
  .pfr .v { font-weight:600; min-width:0; display:inline-flex; align-items:center; gap:6px; text-align:end; overflow-wrap:anywhere; }
  .pfr .v a { color:var(--text); text-decoration:none; }
  .pfr .v img { width:20px; height:20px; object-fit:contain; flex:0 0 20px; }
  /* المباريات: بطاقة match_row + سطر أداء اللاعب تحتها داخل البطاقة نفسها */
  .pms { margin-top:12px; }
  .pms .match { margin-bottom:6px; }
  .pms .match.hidden { display:none; }
  .pms .pml { grid-column:1/-1; text-align:center; color:var(--muted); font-size:12px; position:relative; z-index:2;
              pointer-events:none; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .pms .pml b { color:var(--text); }
  .pmore { display:block; width:100%; margin:4px 0 0; background:var(--card); color:var(--accent);
           border:1px solid var(--line); border-radius:9px; padding:8px; font-size:13px; cursor:pointer; font-family:inherit; }
  .pnote { color:var(--muted); font-size:12.5px; margin-top:12px; line-height:1.7; }
"""

# ⚠️ STYLE الكامل (inline) لم يعد يُستعمل بالصفحات — راجع assets.py
STYLE = "<style>" + CSS_TYPE + SEARCH_CSS + NAV_CSS + "\n</style>"


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
                "id": int(tid),
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
    """thumbs/ المصغّرة أولاً (thumbs_util)، ثم logo_local، ثم رابط المزوّد"""
    if not t:
        return ""
    up = "../" * depth
    th = thumb_src(t.get("id"), up) if t.get("id") else None
    if th:
        return th
    if t["logo_local"]:
        return up + t["logo_local"]
    return t["logo"]


def logo_tag(t, lang, depth, px, eager=False):
    """<img> بأبعاد ثابتة؛ eager لسطر النادي بالرأس فقط، غيره lazy"""
    return logo_img(t.get("id"), logo_url(t, lang, depth), "../" * depth, px, eager=eager)


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
            WHERE player_id > 0
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

    # إحصائيات مفصّلة موسماً بموسم
    # ⚠️ COALESCE إجباري — بعض الحقول كلها NULL فيرجع SUM قيمة None
    #    بدل صفر، فتظهر فراغات غريبة بالجدول
    seasons = defaultdict(list)
    try:
        for r in conn.execute("""
                SELECT ps.player_id, m.season, m.league_code,
                       COUNT(ps.match_id)                AS apps,
                       COALESCE(SUM(ps.minutes), 0)      AS mins,
                       ROUND(AVG(ps.rating), 2)          AS rate,
                       COALESCE(SUM(ps.goals), 0)        AS goals,
                       COALESCE(SUM(ps.assists), 0)      AS assists,
                       COALESCE(SUM(ps.shots_total), 0)  AS shots,
                       COALESCE(SUM(ps.shots_on), 0)     AS shots_on,
                       COALESCE(SUM(ps.passes_total), 0) AS passes,
                       COALESCE(SUM(ps.passes_key), 0)   AS keyp,
                       ROUND(AVG(ps.passes_pct), 0)      AS pct,
                       COALESCE(SUM(ps.tackles), 0)      AS tackles,
                       COALESCE(SUM(ps.interceptions), 0) AS inter,
                       COALESCE(SUM(ps.duels_won), 0)    AS dwon,
                       COALESCE(SUM(ps.duels_total), 0)  AS dtot,
                       COALESCE(SUM(ps.dribbles_ok), 0)  AS drok,
                       COALESCE(SUM(ps.saves), 0)        AS saves,
                       COALESCE(SUM(ps.conceded), 0)     AS conceded,
                       COALESCE(SUM(ps.yellow), 0)       AS yel,
                       COALESCE(SUM(ps.red), 0)          AS red,
                       MAX(ps.pos)                       AS pos
                FROM player_stats ps
                JOIN matches m ON m.match_id = ps.match_id
                WHERE ps.player_id IS NOT NULL AND ps.player_id != 0
                  AND ps.minutes IS NOT NULL AND ps.minutes > 0
                GROUP BY ps.player_id, m.season, m.league_code
                ORDER BY m.season DESC
            """):
            seasons[r["player_id"]].append(dict(r))
    except sqlite3.Error:
        pass

    return goals, bridge, stats, seasons


def gather_extra(conn, pids):
    """-> (info, plays). info = {pid: صف player_info بحالة ok} (الجدول يُنشئه fetch_player_info.py بالـCI؛ غيابه = {}).
    plays = {pid: [مباراة لُعبت، الأحدث أولاً]}: lineup_players + player_stats بالمعرّف، المنتهية فقط. «لُعبت» = دقائق > 0، أو
    (بلا إحصائيات: المغربي) أساسي بالتشكيلة — بديل بلا إحصائيات لا يُعرف إن نزل فيُترك."""
    info = {}
    try:
        for r in conn.execute("SELECT * FROM player_info WHERE status = 'ok'"):
            if r["player_id"] in pids:
                info[r["player_id"]] = dict(r)
    except sqlite3.Error:
        pass
    mx = {r["match_id"]: dict(r) for r in conn.execute(
        "SELECT match_id, date, season, league_code, home_id, away_id, home_goals, away_goals, status FROM matches")}
    pm = defaultdict(dict)
    for r in conn.execute("SELECT player_id, match_id, team_id, number, pos, starter FROM lineup_players WHERE player_id > 0"):
        if r[0] in pids:
            pm[r[0]][r[1]] = {"mid": r[1], "team": r[2], "number": r[3], "pos": r[4], "starter": r[5], "minutes": None}
    try:
        for r in conn.execute("SELECT player_id, match_id, team_id, minutes, rating, goals, assists, yellow, red, pos "
                              "FROM player_stats WHERE player_id > 0"):
            if r[0] not in pids:
                continue
            e = pm[r[0]].setdefault(r[1], {"mid": r[1], "team": r[2], "number": None, "pos": None, "starter": None})
            e.update(minutes=r[3], rating=r[4], goals=r[5], assists=r[6], yellow=r[7], red=r[8], spos=r[9], stats=True)
    except sqlite3.Error:
        pass
    plays = {}
    for pid, d in pm.items():
        lst = []
        for e in d.values():
            m = mx.get(e["mid"])
            if not m or m["home_goals"] is None or m["away_goals"] is None:
                continue
            played = (e.get("minutes") or 0) > 0 if e.get("stats") else e.get("starter") == 1
            if played:
                e["m"] = m
                lst.append(e)
        lst.sort(key=lambda e: (str(e["m"]["date"]), e["mid"]), reverse=True)
        plays[pid] = lst
    return info, plays


# نصوص صفحة اللاعب الجديدة (18 أكتوبر) — محلية لا في i18n
PT = {
    "ar": {"profile": "الملف", "matches": "المباريات", "stats": "الإحصائيات", "career": "المسيرة",
           "age": "العمر", "years": "سنة", "nat": "الجنسية", "height": "الطول", "cm": "سم", "pos": "المركز",
           "num": "الرقم", "club": "النادي", "assist": "صناعة",
           "starts_only": "المباريات الأساسية فقط",
           "positions": {"Goalkeeper": "حارس مرمى", "Defender": "مدافع", "Midfielder": "لاعب وسط", "Attacker": "مهاجم",
                         "G": "حارس مرمى", "D": "مدافع", "M": "لاعب وسط", "F": "مهاجم"}},
    "en": {"profile": "Profile", "matches": "Matches", "stats": "Stats", "career": "Career",
           "age": "Age", "years": "years", "nat": "Nationality", "height": "Height", "cm": "cm", "pos": "Position",
           "num": "Shirt number", "club": "Club", "assist": "assist",
           "starts_only": "Starts only (no substitution data)",
           "positions": {"Goalkeeper": "Goalkeeper", "Defender": "Defender", "Midfielder": "Midfielder", "Attacker": "Attacker",
                         "G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}},
}
# الجنسية بالعربي (المزوّد يرسلها بالإنجليزي): الأكثر تكراراً بالدوريات السبعة؛ غير الموجود يبقى بالإنجليزي
NAT_AR = {
    "Jordan": "الأردن", "Iraq": "العراق", "Saudi Arabia": "السعودية", "Egypt": "مصر", "United Arab Emirates": "الإمارات",
    "Qatar": "قطر", "Morocco": "المغرب", "Algeria": "الجزائر", "Tunisia": "تونس", "Libya": "ليبيا", "Syria": "سوريا",
    "Lebanon": "لبنان", "Palestine": "فلسطين", "Kuwait": "الكويت", "Bahrain": "البحرين", "Oman": "عُمان", "Yemen": "اليمن",
    "Sudan": "السودان", "Mauritania": "موريتانيا", "Comoros": "جزر القمر", "Iran": "إيران", "Turkey": "تركيا", "Türkiye": "تركيا",
    "Spain": "إسبانيا", "France": "فرنسا", "Brazil": "البرازيل", "Portugal": "البرتغال", "Argentina": "الأرجنتين",
    "Germany": "ألمانيا", "Italy": "إيطاليا", "England": "إنجلترا", "Netherlands": "هولندا", "Belgium": "بلجيكا",
    "Croatia": "كرواتيا", "Serbia": "صربيا", "Poland": "بولندا", "Romania": "رومانيا", "Greece": "اليونان", "Sweden": "السويد",
    "Norway": "النرويج", "Denmark": "الدنمارك", "Switzerland": "سويسرا", "Austria": "النمسا", "Czech Republic": "التشيك",
    "Slovakia": "سلوفاكيا", "Slovenia": "سلوفينيا", "Bosnia and Herzegovina": "البوسنة والهرسك", "Montenegro": "الجبل الأسود",
    "North Macedonia": "مقدونيا الشمالية", "Albania": "ألبانيا", "Kosovo": "كوسوفو", "Ukraine": "أوكرانيا", "Russia": "روسيا",
    "Georgia": "جورجيا", "Hungary": "المجر", "Bulgaria": "بلغاريا", "Scotland": "اسكتلندا", "Wales": "ويلز", "Ireland": "أيرلندا",
    "Senegal": "السنغال", "Côte d'Ivoire": "ساحل العاج", "Ivory Coast": "ساحل العاج", "Nigeria": "نيجيريا", "Ghana": "غانا",
    "Cameroon": "الكاميرون", "Mali": "مالي", "Guinea": "غينيا", "Burkina Faso": "بوركينا فاسو", "Gabon": "الغابون",
    "Congo DR": "الكونغو الديمقراطية", "Congo": "الكونغو", "Angola": "أنغولا", "South Africa": "جنوب أفريقيا", "Kenya": "كينيا",
    "Zambia": "زامبيا", "Zimbabwe": "زيمبابوي", "Benin": "بنين", "Togo": "توغو", "Niger": "النيجر", "Chad": "تشاد",
    "Gambia": "غامبيا", "Sierra Leone": "سيراليون", "Liberia": "ليبيريا", "Cape Verde Islands": "الرأس الأخضر",
    "Guinea-Bissau": "غينيا بيساو", "Equatorial Guinea": "غينيا الاستوائية", "Ethiopia": "إثيوبيا", "Uganda": "أوغندا",
    "Tanzania": "تنزانيا", "Madagascar": "مدغشقر", "Mozambique": "موزمبيق", "Uruguay": "الأوروغواي", "Colombia": "كولومبيا",
    "Chile": "تشيلي", "Peru": "بيرو", "Ecuador": "الإكوادور", "Venezuela": "فنزويلا", "Paraguay": "باراغواي", "Bolivia": "بوليفيا",
    "Mexico": "المكسيك", "USA": "الولايات المتحدة", "Canada": "كندا", "Costa Rica": "كوستاريكا", "Honduras": "هندوراس",
    "Jamaica": "جامايكا", "Haiti": "هايتي", "Curaçao": "كوراساو", "Suriname": "سورينام", "Japan": "اليابان",
    "Korea Republic": "كوريا الجنوبية", "South Korea": "كوريا الجنوبية", "China": "الصين", "Australia": "أستراليا",
    "Uzbekistan": "أوزبكستان", "Tajikistan": "طاجيكستان", "Kyrgyzstan": "قيرغيزستان", "Kazakhstan": "كازاخستان",
    "Afghanistan": "أفغانستان", "India": "الهند", "Pakistan": "باكستان", "Indonesia": "إندونيسيا", "Philippines": "الفلبين",
    "Thailand": "تايلاند", "Vietnam": "فيتنام", "Malaysia": "ماليزيا", "New Zealand": "نيوزيلندا", "Iceland": "آيسلندا",
    "Finland": "فنلندا", "Cyprus": "قبرص", "Israel": "إسرائيل", "Armenia": "أرمينيا", "Azerbaijan": "أذربيجان", "Lithuania": "ليتوانيا",
    "Latvia": "لاتفيا", "Estonia": "إستونيا", "Belarus": "بيلاروسيا", "Moldova": "مولدوفا", "Luxembourg": "لوكسمبورغ",
    "Northern Ireland": "أيرلندا الشمالية", "Burundi": "بوروندي", "Rwanda": "رواندا", "Central African Republic": "أفريقيا الوسطى",
    "Namibia": "ناميبيا", "Botswana": "بوتسوانا", "Malawi": "مالاوي", "Eritrea": "إريتريا", "Somalia": "الصومال", "Djibouti": "جيبوتي",
}


def player_age(birth, today=None):
    """العمر بالسنوات من YYYY-MM-DD، أو None"""
    try:
        y, m, d = (int(x) for x in str(birth)[:10].split("-"))
    except (ValueError, TypeError):
        return None
    today = today or date.today()
    return today.year - y - ((today.month, today.day) < (m, d))


def current_team(rows, plays):
    """النادي الحالي = نادي أحدث مباراة (لُعبت بالتشكيلة/الإحصائيات أو سُجّل فيها هدف)"""
    best = None
    if plays:
        best = (str(plays[0]["m"]["date"]), plays[0]["team"])
    if rows:
        g = (str(rows[0]["date"]), rows[0]["team_id"])
        if best is None or g[0] > best[0]:
            best = g
    return best[1] if best else None


def profile_html(info, plays, team, teams, lang, depth, upl):
    """«الملف»: صف لكل حقل متوفّر فقط (العمر · الجنسية · الطول · المركز · الرقم · النادي)"""
    P = PT[lang]
    out = []
    if info:
        a = player_age(info.get("birth_date"))
        if a is not None and 14 <= a <= 50:
            out.append((P["age"], f"{a} {P['years']}"))
        nat = clean(info.get("nationality"))
        if nat:
            out.append((P["nat"], NAT_AR.get(nat, nat) if lang == "ar" else nat))
        if info.get("height_cm"):
            out.append((P["height"], f"{info['height_cm']} {P['cm']}"))
    pos = (info or {}).get("position") or next((e.get("spos") or e.get("pos") for e in plays if e.get("spos") or e.get("pos")), None)
    if pos and P["positions"].get(pos):
        out.append((P["pos"], P["positions"][pos]))
    num = (info or {}).get("number")
    if num is None:
        num = next((e["number"] for e in plays if e.get("number") is not None), None)
    if num is not None:
        out.append((P["num"], str(num)))
    tm = teams.get(team) if team else None
    if tm:
        out.append((P["club"], f'{logo_tag(tm, lang, depth, 20)}<a href="{upl}clubs/{team}.html">{tname(tm, lang)}</a>'))
    if not out:
        return ""
    rows = "".join(f'<div class="pfr"><span class="k">{k}</span><span class="v">{v}</span></div>' for k, v in out)
    return f'<h2>{P["profile"]}</h2><div class="pf">{rows}</div>'


MATCH_LIMIT = 20


def matches_list_html(plays, rows, teams, lang, depth, upl, t):
    """بطاقة لكل مباراة لُعبت (match_row) + سطر الأداء: التاريخ · الدقائق · الأهداف · الصناعة · البطاقات · التقييم"""
    if not plays:
        return ""
    P = PT[lang]
    goals_by_match = defaultdict(int)
    for r in rows:
        goals_by_match[r["match_id"]] += 1
    out = ""
    for i, e in enumerate(plays):
        m = e["m"]
        h, a = teams.get(m["home_id"]), teams.get(m["away_id"])
        d = str(m["date"]).split()[0].split("-")
        bits = [f"{int(d[2])}/{int(d[1])}/{d[0]}"] if len(d) == 3 else []
        if e.get("minutes"):
            bits.append(f"{e['minutes']}'")
        g = e.get("goals") if e.get("stats") else goals_by_match.get(e["mid"], 0)
        if g:
            bits.append("⚽" + (f" {g}" if g > 1 else ""))
        if e.get("assists"):
            bits.append(f"{e['assists']} {P['assist']}")
        if e.get("yellow"):
            bits.append("🟨")
        if e.get("red"):
            bits.append("🟥")
        if e.get("rating"):
            bits.append(f"<b>{float(e['rating']):.1f}</b>")
        out += match_row(e["mid"], f'{upl}matches/{e["mid"]}.html',
                         (tname(h, lang), logo_tag(h, lang, depth, 22) if h else "", None),
                         (tname(a, lang), logo_tag(a, lang, depth, 22) if a else "", None),
                         f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>',
                         cls="match hidden" if i >= MATCH_LIMIT else "match",
                         tail=f'<div class="pml">{" · ".join(bits)}</div>')
    more = (f'<button class="pmore">{t["show_all"]} ({len(plays) - MATCH_LIMIT})</button>' if len(plays) > MATCH_LIMIT else "")
    return f'<h2>{P["matches"]}</h2><div class="pms">{out}</div>{more}'


def matches_more_script():
    """«عرض الكل» تحت قائمة مباريات اللاعب: يكشف الباقي"""
    return ('<script>\n'
            'document.querySelectorAll(".pmore").forEach(function(b){b.addEventListener("click",function(){\n'
            'var box=b.previousElementSibling;if(box)box.querySelectorAll(".match.hidden").forEach(function(x){x.classList.remove("hidden");});\n'
            'b.style.display="none";});});\n'
            '</script>')


# ⚠️ نصوص محلية لا في i18n — تخصّ هذا القسم وحده.
CAR = {
    "ar": {"title": "المسيرة", "season": "الموسم", "club": "النادي",
           "goals": "أهداف", "apps": "مباريات", "total": "المجموع",
           "seasons_n": "موسم", "clubs_n": "نادٍ",
           "warn": "قد تعود بعض هذه الأهداف للاعبين مختلفين "
                   "يتشاركون الاسم نفسه"},
    "en": {"title": "Career", "season": "Season", "club": "Club",
           "goals": "Goals", "apps": "Apps", "total": "Total",
           "seasons_n": "seasons", "clubs_n": "clubs",
           "warn": "Some of these goals may belong to different "
                   "players sharing the same name"},
}


def career_table(rows, teams, lang, depth, plays=None):
    """
    مسيرة اللاعب: موسم × نادٍ × أهداف — من جدول `goals`.

    ⚠️ **تعمل للدوريات الثلاثة** بخلاف `season_stats_table`
       التي تعتمد `player_stats` (السعودي فقط، درس 4).

    ⚠️ **تُعرض حتى لموسم واحد** — البنية تُبنى مرة وتمتلئ
       تلقائياً مع كل موسم جديد، فلا داعي لإخفائها ثم إظهارها.

    ⚠️ سطر لكل (موسم، نادٍ) لا لكل موسم — اللاعب قد ينتقل
       في منتصف الموسم فيسجّل لناديين.
    """
    s = CAR[lang]
    up = "../" * depth
    upl = up + ("en/" if lang == "en" else "")   # روابط الصفحات بلغة الصفحة (راجع build)

    agg = defaultdict(int)
    for r in rows:
        agg[(r["season"], r["team_id"], r["league_code"])] += 1
    # المباريات (18 أكتوبر): من التشكيلات/الإحصائيات بالمعرّف حيث توفّرت؛ عمودها يظهر فقط إن وُجدت
    apps = defaultdict(int)
    for e in plays or []:
        apps[(e["m"]["season"], e["team"], e["m"]["league_code"])] += 1
    keys = set(agg) | set(apps)
    show_apps = bool(apps)

    body = ""
    for (season, tid, lg) in sorted(keys, key=lambda k: -k[0]):
        n = agg.get((season, tid, lg), 0)
        tm = teams.get(tid)
        nm = tname(tm, lang) if tm else str(tid)
        logo = logo_tag(tm, lang, depth, 22) if tm else ""
        body += (
            f'<tr><td class="cs">{season}-{season + 1}</td>'
            f'<td class="cc">{logo}'
            f'<a href="{upl}clubs/{tid}.html">{nm}</a></td>'
            + (f'<td class="ca">{apps.get((season, tid, lg)) or "—"}</td>' if show_apps else "")
            + f'<td class="cg">{n}</td></tr>'
        )

    # (19 أكتوبر 2026) العدّ من كل الصفوف المعروضة (أهداف ∪ مباريات) لا من الأهداف وحدها — كان «1 موسم» بجدول من 4
    n_seasons = len({k[0] for k in keys})
    n_clubs = len({k[1] for k in keys})
    total = sum(agg.values())

    # ⚠️ **كشف تضارب الأسماء** — الجمع يتم على `player_en` نصياً،
    #    فلاعبان بالاسم نفسه تندمج مسيرتهما (درس 5). النمطان
    #    اللذان يفضحان ذلك:
    #      • دوريان مختلفان في موسم واحد — شبه مستحيل
    #      • ثلاثة أندية فأكثر في موسم واحد
    #    حالة محقَّقة: `Mohanad Ali` = أربعة لاعبين (سعودي وثلاثة
    #    عراقيين). لا نُخفي المسيرة، لكن لا نؤكّدها كحقيقة أيضاً.
    by_season = defaultdict(set)
    lg_season = defaultdict(set)
    for (season, tid, lg) in agg:
        by_season[season].add(tid)
        lg_season[season].add(lg)
    suspect = any(len(v) >= 3 for v in by_season.values()) or \
              any(len(v) >= 2 for v in lg_season.values())
    warn = (f'<p class="cwarn">⚠️ {s["warn"]}</p>' if suspect else "")
    foot = (f'<tr class="ct"><td colspan="2">{s["total"]} — '
            f'{n_seasons} {s["seasons_n"]} · {n_clubs} {s["clubs_n"]}</td>'
            + (f'<td class="ca">{sum(apps.values())}</td>' if show_apps else "")
            + f'<td class="cg">{total}</td></tr>')

    return (
        f'<h2>{s["title"]}</h2>'
        f'<table class="career"><thead><tr>'
        f'<th>{s["season"]}</th><th>{s["club"]}</th>'
        + (f'<th class="ca">{s["apps"]}</th>' if show_apps else "")
        + f'<th>{s["goals"]}</th></tr></thead>'
        f'<tbody>{body}{foot}</tbody></table>{warn}'
    )


def season_stats_table(srows, lang, t):
    """
    جدول الإحصائيات موسماً بموسم.

    ⚠️ الحراس يحصلون على أعمدة مختلفة (تصديات/استقبل بدل
       تسديدات/مراوغات) — يُكتشف من pos == 'G'.

    ⚠️ حقول شبه فارغة (حمراء 0.8%، ركلات الجزاء < 1%) لا
       تُعرض كأعمدة ثابتة — تظهر فقط إن كانت > 0، وإلا صفوف
       أصفار لمعظم اللاعبين.
    """
    if not srows:
        return ""

    is_gk = any((r.get("pos") or "") == "G" for r in srows)

    if is_gk:
        cols = [
            ("apps", t["ps_apps"]),
            ("mins", t["ps_mins"]),
            ("rate", t["ps_rate"]),
            ("saves", t["ps_saves"]),
            ("conceded", t["ps_conceded"]),
            ("passes", t["ps_passes"]),
            ("pct", t["ps_pct"]),
        ]
    else:
        cols = [
            ("apps", t["ps_apps"]),
            ("mins", t["ps_mins"]),
            ("rate", t["ps_rate"]),
            ("goals", t["ps_goals"]),
            ("assists", t["ps_assists"]),
            ("shots", t["ps_shots"]),
            ("keyp", t["ps_keyp"]),
            ("pct", t["ps_pct"]),
            ("tackles", t["ps_tackles"]),
            ("dwon", t["ps_duels"]),
        ]

    # عمود البطاقات يظهر فقط إن كان لأحد المواسم بطاقات
    has_cards = any((r.get("yel") or 0) or (r.get("red") or 0)
                    for r in srows)

    head = f'<th class="sn">{t["ps_season"]}</th>'
    for _, label in cols:
        head += f'<th>{label}</th>'
    if has_cards:
        head += f'<th>{t["ps_cards"]}</th>'

    body = ""
    for r in srows:
        lg = league_name(r["league_code"], lang)
        body += (f'<tr><td class="sn">{lg} '
                 f'<span class="yr">{r["season"]}</span></td>')
        for key, _ in cols:
            v = r.get(key)
            if v is None:
                txt = "—"
            elif key == "mins":
                txt = f"{int(v):,}"
            elif key == "pct":
                txt = f"{int(v)}%" if v else "—"
            elif key == "rate":
                txt = f"{v:.2f}" if v else "—"
            elif key == "dwon":
                tot = r.get("dtot") or 0
                txt = f"{int(v)}/{int(tot)}" if tot else str(int(v))
            else:
                txt = str(int(v))
            body += f'<td>{txt}</td>'
        if has_cards:
            y = int(r.get("yel") or 0)
            rd = int(r.get("red") or 0)
            cards = f'{y}' if not rd else f'{y}/{rd}'
            body += f'<td>{cards}</td>'
        body += '</tr>'

    return (f'<h2>{t["ps_title"]}</h2>'
            f'<div class="stw"><table class="stt">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def goals_script(t):
    """طي المواسم + زر عرض كل الأهداف"""
    sa = t["show_all"].replace('"', '\\"')
    sl = t["show_less"].replace('"', '\\"')
    return (
        '<script>\n'
        f'var GA="{sa}",GL="{sl}";\n'
        'document.querySelectorAll(".shead").forEach(function(h){\n'
        'h.addEventListener("click",function(){\n'
        'var s=this.parentElement;\n'
        'var b=s.querySelector(".sbody");\n'
        'var op=s.classList.toggle("open");\n'
        'b.classList.toggle("hidden",!op);});});\n'
        'document.querySelectorAll(".gmore").forEach(function(b){\n'
        'b.dataset.open="0";\n'
        'b.addEventListener("click",function(){\n'
        'var box=this.previousElementSibling;\n'
        'var kids=box.querySelectorAll(".g");\n'
        'var op=this.dataset.open==="1";\n'
        'var n=0;\n'
        'kids.forEach(function(g,i){\n'
        'if(i>=10){g.classList.toggle("hidden",op);n++;}});\n'
        'this.dataset.open=op?"0":"1";\n'
        'this.textContent=op?GA+" ("+n+")":GL;});});\n'
        '</script>'
    )


def follow_script(t):
    """
    زر متابعة اللاعب (جزء أ، 22 سبتمبر) — يقرأ/يكتب fbPlayers
    عبر FBPrefs (prefs_script() يجب أن تُحقَن قبله بالصفحة).

    ⚠️ **slug لا player_id** — راجع تعليق K بـprefs.py. الزر يحمل
       الـslug بـdata-slug، لا معرّف رقمي.
    """
    fl = t["follow_player"].replace('"', '\\"')
    ufl = t["unfollow_player"].replace('"', '\\"')
    return (
        '<script>\n'
        f'var FL="{fl}",UFL="{ufl}";\n'
        '(function(){\n'
        'var b=document.getElementById("followbtn");\n'
        'var FB=window.FBPrefs;\n'
        'if(!b||!FB)return;\n'
        'var slug=b.dataset.slug;\n'
        'var al=(b.dataset.al||"").split(",").filter(Boolean);\n'
        '(function(){var p=FB.getPlayers(),out=[],ch=false;\n'
        'p.forEach(function(s){if(al.indexOf(s)>=0){s=slug;ch=true;}\n'
        'if(out.indexOf(s)<0){out.push(s);}else{ch=true;}});\n'
        'if(ch){FB.setPlayers(out);}})();\n'
        'function mark(on){\n'
        'b.classList.toggle("on",on);\n'
        'b.title=on?UFL:FL;\n'
        'b.setAttribute("aria-pressed",on?"true":"false");}\n'
        'mark(FB.getPlayers().indexOf(slug)>=0);\n'
        'b.addEventListener("click",function(){\n'
        'var p=FB.getPlayers();\n'
        'var i=p.indexOf(slug);\n'
        'if(i>=0){p.splice(i,1);}else{p.push(slug);}\n'
        'FB.setPlayers(p);\n'
        'mark(i<0);});\n'
        '})();\n'
        '</script>'
    )


def pick_display_ar(rows):
    """اسم العرض العربي لصفحة اللاعب. الأصل: أحدث هدف بنفس
    النص (rows[0]) — يبقى كما هو دائماً إن كان مترجَماً. **فقط**
    حين يكون فارغاً (أحدث هدف بلا ترجمة، وقد يعود فعلياً لهوية
    مختلفة تشارك نفس النص — بند 39، مثال Zizo) يُستبدَل بأقرب
    صف غير فارغ بنفس المجموعة (لا تعادل تكراري ولا "الأكثر
    شيوعاً" — كلاهما قد يستبدل عرضاً صحيحاً حالياً بعرض هوية
    مختلفة، تحقَّق فعلياً بمحاكاة سبقت هذا التعديل: حالتا
    A. Hussein/M. Sylla كانتا سترفَضان لو اعتُمد "الأكثر تكراراً"
    بدل هذا المنطق الأضيق). التغيير محصور حصراً بحالة الفراغ —
    فحص شامل على كل أسماء جدول goals (3,688) قبل هذا التعديل
    أثبت أن Zizo هو الاسم الوحيد المتأثر."""
    first = clean(rows[0]["ar"])
    if first:
        return first
    for r in rows:
        v = clean(r["ar"])
        if v:
            return v
    return ""


def build(name, rows, st, srows, teams, lang, slugs, thin, slug, ar_override="", aliases=(), pid=None, info=None, plays=None):
    t = T[lang]
    depth = 1 if lang == "ar" else 2
    up = "../" * depth
    # ⚠️ روابط الصفحات (أندية/مباريات) بنسخة لغة الصفحة: `up` يصل لجذر الموقع (للأصول
    #    والشعارات فقط). كان `{up}matches/` من en/players/ يفتح /matches/ العربية.
    upl = up + ("en/" if lang == "en" else "")

    ar = ar_override or pick_display_ar(rows)
    en = clean(name)
    disp = (ar or en) if lang == "ar" else (en or ar)

    n_goals = len(rows)
    clubs = {r["team_id"] for r in rows}
    seasons = {r["season"] for r in rows}
    lgs = {r["league_code"] for r in rows}

    plays = plays or []
    cur_tid = current_team(rows, plays)
    last_team = teams.get(cur_tid) if cur_tid else None

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

    # ⚠️ الموسم الأحدث مفتوح، والباقي مطوي — صفحة فارغة تماماً
    #    تبدو مكسورة، والزائر يهمه الموسم الحالي أولاً.
    # ⚠️ حد 10 أهداف داخل الموسم المفتوح مع زر "عرض الكل" —
    #    نفس نمط قوائم الهدافين في make_clubs.py للاتساق.
    GOAL_LIMIT = 10

    blocks = ""
    for idx, ((season, code), items) in enumerate(
            sorted(by_season.items(), key=lambda x: -x[0][0])):
        lg = league_name(code, lang)
        is_first = idx == 0
        open_cls = " open" if is_first else ""
        body_cls = "" if is_first else " hidden"

        blocks += (
            f'<div class="seas{open_cls}">'
            f'<button class="shead">'
            f'<span class="sarrow">▾</span>'
            f'<span class="stitle">{lg} — {t["season"]} {season}</span>'
            f'<span class="scount">{len(items)} {t["p_goals"]}</span>'
            f'</button>'
            f'<div class="sbody{body_cls}">'
            f'<div class="grow">'
        )

        for i, r in enumerate(items):
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

            hide = " hidden" if i >= GOAL_LIMIT else ""
            # ⚠️ 7 سبتمبر — وقت اختياري بجانب التاريخ (بند مفتوح 28).
            #    matchtime.py لم يكن محمَّلاً بهذه الصفحة من قبل —
            #    أُضيف (matchtime_script()) بأسفل الملف. data-utc
            #    فقط لو وقت فعلي — 37 مباراة بلا وقت (بند مفتوح 20)
            #    تبقى بتاريخ وحده.
            g_parts = str(r["date"]).split()
            g_clock = g_parts[1][:5] if len(g_parts) > 1 else ""
            dt_html = (f'<span data-utcd="{g_parts[0]}T{g_clock}:00Z">'
                      f'{g_parts[0]}</span> '
                      f'<span data-utc="{g_parts[0]}T{g_clock}:00Z">'
                      f'{g_clock} UTC</span>'
                      if g_clock else g_parts[0])
            blocks += (
                f'<a class="g{hide}" '
                f'href="{upl}matches/{r["match_id"]}.html">'
                f'<span class="min">{mtxt}</span>'
                f'<span class="vs">{mine} × {opp}</span>{tag}'
                f'<span class="dt">{dt_html}</span></a>'
            )

        blocks += '</div>'
        if len(items) > GOAL_LIMIT:
            blocks += (f'<button class="gmore">'
                       f'{t["show_all"]} ({len(items) - GOAL_LIMIT})'
                       f'</button>')
        blocks += '</div></div>'

    # ── ملاحظة الدوريات بلا تفاصيل ───────────────────
    note = ""
    if not st and lgs & {"JOR", "IRQ", "KUW"}:   # KUW (مطفأ، 24 أكتوبر 2026): بلا تشكيلات ولا إحصائيات مثل JOR/IRQ
        note = (f'<h2>{t["p_more"]}</h2>'
                f'<div class="note">{t["p_nodetail"]}</div>')
    # المغربي: التشكيلات بلا إحصائيات لاعبين، فقائمة المباريات = الأساسية فقط (البديل الذي نزل لا يُعرف) — سطر تحت القائمة.
    # التونسي والجزائري (مطفآن، 24 أكتوبر 2026) بنفس الحالة
    starts_only = (f'<p class="pnote">{PT[lang]["starts_only"]}</p>'
                   if any(e["m"]["league_code"] in ("MAR", "TUN", "ALG") and not e.get("stats") for e in (plays or [])) else "")

    # ── الرأس ────────────────────────────────────────
    other = slugs[name]
    switch = (f"../en/players/{other}.html" if lang == "ar"
              else f"../../players/{other}.html")

    club_line = ""
    if last_team:
        club_line = (f'{logo_tag(last_team, lang, depth, 20, eager=True)}'
                     f'<a href="{upl}clubs/{cur_tid}.html">'
                     f'{tname(last_team, lang)}</a>')

    career_html = career_table(rows, teams, lang, depth, plays)
    stats_html = season_stats_table(srows, lang, t)

    # ── الصورة: الحقيقية فقط (player_info.has_photo = 1 من فحص الـCDN)، وإلا دائرة فارغة بلا حروف ──
    photo = (f'<img class="pph" src="https://media.api-sports.io/football/players/{pid}.png" alt="" width="72" height="72" decoding="async">'
             if pid and info and info.get("has_photo") == 1 else '<span class="pph" aria-hidden="true"></span>')
    P = PT[lang]
    tabs = tabs_html([
        ("profile", profile_html(info, plays, cur_tid, teams, lang, depth, upl)),
        ("matches", matches_list_html(plays, rows, teams, lang, depth, upl, t) + starts_only
         + f'<h2>{t["p_all_goals"]}</h2>\n{blocks}\n{note}'),
        ("stats", f'<h2>{P["stats"]}</h2><div class="cards">{cards}</div>\n{stats_html}'),
        ("career", career_html),
    ], {k: P[k] for k in ("profile", "matches", "stats", "career")}, "profile")

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
        + head_meta(disp, desc, up, lang,
                    f"players/{slug}.html" if lang == "ar"
                    else f"en/players/{slug}.html")
        + THEME_HEAD + assets.css_links("player") + NOSCRIPT
        + '</head>\n<body>\n<div class="wrap">\n'
        + appbar(t, lang, switch, back=True) +
        f'<header>{photo}<h1>{disp}'
        f'<button class="followbtn" id="followbtn" data-slug="{slug}" data-al="{",".join(aliases)}" '
        f'aria-pressed="false" title="{t["follow_player"]}">'
        f'{IC_FOLLOWING}</button></h1>'
        f'<div class="sub">{club_line}</div></header>\n'
        f'{tabs}\n'
        '</div>\n'
        + navbar(t, depth, "", lang)
        + assets.script_tags("player", lang)
        + '\n</body>\n</html>'
    )


STUB_TXT = {"ar": "تم نقل هذه الصفحة", "en": "This page has moved"}


def redirect_html(lang, new_slug, title):
    """
    Stub إعادة توجيه لرابط لاعب قديم (استضافة GitHub Pages ثابتة بلا 301 حقيقي): refresh فوري + canonical مطلق + JS.
    بلا noindex عمداً (تنتقل الإشارات للصفحة الجديدة)؛ الـmeta `saffara-redirect` يستبعدها من sitemap.
    الرابط نسبي (`new.html`) فيصلح للغتين لأن الصفحتين بنفس المجلد.
    """
    path = (f"players/{new_slug}.html" if lang == "ar" else f"en/players/{new_slug}.html")
    t = STUB_TXT[lang]
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        f'<meta name="saffara-redirect" content="/{path}">\n'
        f'<link rel="canonical" href="{SITE}/{path}">\n'
        f'<meta http-equiv="refresh" content="0; url={new_slug}.html">\n'
        f'<script>location.replace("{new_slug}.html"+location.search+location.hash);</script>\n'
        f'</head>\n<body><p><a href="{new_slug}.html">{t}: {title}</a></p></body>\n</html>\n'
    )


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    teams = load_teams()
    goals, bridge, stats, seasons = gather(conn)
    plan = get_plan()
    info, plays = gather_extra(conn, {p["stats_pid"] for p in plan["pages"] if p["stats_pid"]})
    conn.close()

    if not goals:
        print("ما في أهداف مخزّنة")
        return

    # سجلّ كل رابط لاعب نُشر (player_url_history.json، حالة دائمة بـdb-state): الجديد يُضاف هنا ويصعد مع db_push، والمختفي صار stub داخل الخطة نفسها
    import player_pages as _pp
    added = _pp.update_history(plan)
    if added:
        print(f"  player_url_history.json: +{added} (حالة دائمة: يصعد مع db_push، لا commit)")
    for u in plan.get("unresolved", []):
        print(f"  ⚠️ رابط منشور سابقاً بلا صفحة ولا معرّف يحوّله (يُتخطّى، سيعطي 404): {u}")
    counts = {n: len(rows) for n, rows in goals.items()}

    os.makedirs(BASE / "players", exist_ok=True)
    os.makedirs(BASE / "en" / "players", exist_ok=True)

    made = thin_n = with_stats = 0

    for page in plan["pages"]:
        s = page["slug"]
        rows = page["goals"]
        name = page["display_en"]
        pid = page["stats_pid"]
        st = stats.get(pid) if pid else None
        srows = seasons.get(pid, []) if pid else []
        if st:
            with_stats += 1

        thin = (len(rows) < THIN_GOALS) and not st
        if thin:
            thin_n += 1

        for lang in LANGS:
            html = build(name, rows, st, srows, teams, lang,
                         {name: s}, thin, s, ar_override=page["display_ar"],
                         aliases=plan["aliases"].get(s, ()), pid=pid,
                         info=info.get(pid) if pid else None, plays=plays.get(pid, []) if pid else [])
            path = (BASE / "players" / f"{s}.html" if lang == "ar"
                    else BASE / "en" / "players" / f"{s}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        made += 1

    # روابط قديمة اختفت (نصّ دُمج بصفحة معرّف): stub لكل لغة — لا 404
    by_slug = {p["slug"]: p for p in plan["pages"]}
    for old, new in sorted(plan["stubs"].items()):
        tgt = by_slug[new]
        for lang in LANGS:
            title = ((tgt["display_ar"] or tgt["display_en"]) if lang == "ar"
                     else (tgt["display_en"] or tgt["display_ar"]))
            path = (BASE / "players" / f"{old}.html" if lang == "ar"
                    else BASE / "en" / "players" / f"{old}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(redirect_html(lang, new, title))

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} لاعب × لغتين")
    print(f"  players/  +  en/players/")
    print(f"{'=' * 55}")
    print(f"  بتفاصيل (تقييم ودقائق) : {with_stats}")
    print(f"  رقيقة — noindex        : {thin_n}")
    print(f"  إجمالي الصفحات         : {made * 2:,}")
    print(f"  stubs إعادة توجيه      : {len(plan['stubs']) * 2:,}")

    top = plan["pages"][0]
    print(f"\n  جرّب:")
    print(f"      start players\\{top['slug']}.html")
    print()


if __name__ == "__main__":
    main()
