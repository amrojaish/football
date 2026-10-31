#!/usr/bin/env python3
"""
بطاقات «إحصائيات اللاعبين» بصفحة الدوري على نمط FotMob (30 أكتوبر 2026، دفعة 3 بند 5)
======================================================================================
ثلاث بطاقات لـ(دوري، موسم) بالضبط من player_stats (مجمَّعة بـplayer_id):
    الهدّافون (أول 4، القيمة = الأهداف) · صناعة الأهداف (أول 5) · أهداف + صناعة (أول 5)
بلا صور لاعبين: شعار النادي بجانب الاسم. رأس كل بطاقة رابط «›» لصفحة القائمة الكاملة لتلك الإحصائية:
    leagues/<code>[-<season>]-<stat>.html و en/leagues/… (stat = goals | assists | ga) — كل اللاعبين: المركز، الاسم (رابط صفحته)،
    النادي، القيمة. noindex (صفحة مشتقة).

⚠️ **شرط التغطية (لا أرقام جزئية):** البطاقات تظهر فقط إن غطّت player_stats ≥ 90% من مباريات الموسم المنتهية (COVER). غير ذلك
   (الأردني/العراقي/الكويتي/التونسي/الجزائري/المغربي بلا player_stats، والإماراتي 2026 76%) لا بطاقات وتبقى قائمة الهدّافين القديمة من
   جدول goals كما هي. الصناعة و«أهداف + صناعة» تحتاجان أيضاً قيم assists فعلية بالموسم (مجموعها > 0).
ترتيب التعادل: القيمة، ثم الإحصائية الأخرى (الصناعة للأهداف، الأهداف للصناعة ولـG+A)، ثم دقائق أقل، ثم الاسم؛ المركز المشترك بنفس الرقم.

صفر طلبات API.
"""
from html import escape

import short_names as SN

COVER = 0.9
STATS = ("goals", "assists", "ga")
STR = {
    "ar": {"goals": "الهدّافون", "assists": "صناعة الأهداف", "ga": "أهداف + صناعة", "all": "عرض الكل",
           "player": "اللاعب", "club": "النادي", "season": "موسم"},
    "en": {"goals": "Top scorers", "assists": "Assists", "ga": "Goals + Assists", "all": "See all",
           "player": "Player", "club": "Club", "season": "Season"},
}
TOP = {"goals": 4, "assists": 5, "ga": 5}

CARDS_CSS = """
  /* بطاقات إحصائيات اللاعبين (league_player_cards.py، نمط FotMob) */
  .pcards { display:grid; gap:12px; }
  .pscard { background:var(--card); border-radius:12px; padding:4px 0 6px; }
  .pscard .psh { display:flex; align-items:center; justify-content:space-between; gap:10px; min-height:44px;
                 padding:0 14px; color:var(--text); text-decoration:none; font-size:15px; font-weight:700; }
  .pscard .psh .go { width:18px; height:18px; color:var(--muted); display:inline-flex; }
  .pscard .psh .go svg { width:18px; height:18px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  [dir="rtl"] .pscard .psh .go svg { transform:scaleX(-1); }
  .psr { display:flex; align-items:center; gap:10px; min-height:48px; padding:0 14px; border-top:1px solid var(--line); }
  .psr img, .psr .noimg { width:24px; height:24px; object-fit:contain; flex:0 0 24px; }
  .psr .pn { flex:1; min-width:0; display:flex; flex-direction:column; line-height:1.25; }
  .psr .pn a, .psr .pn span.nm { color:var(--text); text-decoration:none; font-size:15px; font-weight:600;
                                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .psr .pn small { color:var(--muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .psr .pv { min-width:34px; text-align:center; font-weight:800; font-size:15px; font-variant-numeric:tabular-nums; }
  .psr.first .pv { background:var(--accent); color:#fff; border-radius:999px; padding:2px 10px; }
  .psr .rk { width:22px; color:var(--muted); font-size:13px; text-align:center; flex:0 0 22px; font-variant-numeric:tabular-nums; }
"""

GO_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg>'


def coverage(conn, code, season):
    """(نسبة مباريات الموسم المنتهية التي لها صفوف player_stats، هل للصناعة قيم)"""
    fin = conn.execute("SELECT COUNT(*) FROM matches WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL",
                       (code, season)).fetchone()[0]
    if not fin:
        return 0.0, False
    n, ast = conn.execute("""SELECT COUNT(DISTINCT ps.match_id), COALESCE(SUM(ps.assists), 0) FROM player_stats ps
                             JOIN matches m ON m.match_id = ps.match_id
                             WHERE m.league_code = ? AND m.season = ? AND m.home_goals IS NOT NULL""", (code, season)).fetchone()
    return n / fin, ast > 0


def rows(conn, code, season):
    """كل اللاعبين بالموسم: [{pid, en, ar, tid, team_ar, team_en, goals, assists, minutes}] (فريقه = آخر نادٍ لعب له بالموسم)"""
    out = {}
    for r in conn.execute("""
            SELECT ps.player_id, ps.player_en, ps.player_ar, ps.team_id, COALESCE(ps.goals, 0), COALESCE(ps.assists, 0),
                   COALESCE(ps.minutes, 0), m.date
            FROM player_stats ps JOIN matches m ON m.match_id = ps.match_id
            WHERE m.league_code = ? AND m.season = ? AND ps.player_id IS NOT NULL AND ps.player_id > 0
            ORDER BY m.date""", (code, season)):
        pid, en, ar, tid, g, a, mins, _d = r
        p = out.setdefault(pid, {"pid": pid, "en": "", "ar": "", "tid": tid, "goals": 0, "assists": 0, "minutes": 0})
        p["goals"] += g
        p["assists"] += a
        p["minutes"] += mins
        p["tid"] = tid
        if (en or "").strip():
            p["en"] = en.strip()
        if (ar or "").strip():
            p["ar"] = ar.strip()
    return list(out.values())


def ranked(players, stat):
    """[(مركز، لاعب، قيمة)] لمن قيمته > 0، بترتيب التعادل أعلاه"""
    val = {"goals": lambda p: p["goals"], "assists": lambda p: p["assists"], "ga": lambda p: p["goals"] + p["assists"]}[stat]
    second = (lambda p: p["assists"]) if stat == "goals" else (lambda p: p["goals"])
    lst = sorted((p for p in players if val(p) > 0), key=lambda p: (-val(p), -second(p), p["minutes"], p["en"]))
    out, rank, prev = [], 0, None
    for i, p in enumerate(lst, 1):
        if val(p) != prev:
            rank, prev = i, val(p)
        out.append((rank, p, val(p)))
    return out


def available(conn, code, season):
    """{stat: True} للبطاقات التي تظهر — {} إن لم تكفِ التغطية"""
    cov, has_ast = coverage(conn, code, season)
    if cov < COVER:
        return {}
    return {"goals": True, "assists": has_ast, "ga": has_ast}


def list_fname(code, season, newest, stat):
    base = code.lower() if season == newest else f"{code.lower()}-{season}"
    return f"{base}-{stat}.html"


def _name(p, lang):
    return (p["ar"] if lang == "ar" else "") or p["en"]


def _row(rank, p, v, lang, team_of, logo_of, href_of, first=False, show_rank=False, snm=None):
    tm = team_of(p["tid"])
    src = logo_of(p["tid"])
    img = f'<img src="{escape(src, quote=True)}" alt="" width="24" height="24" loading="lazy" decoding="async">' if src else '<span class="noimg"></span>'
    href = href_of(p)
    # (31 أكتوبر 2026، دفعة 7 بند 5) الاسم المعروض «الأول + الأخير» بحارس تصادم على مستوى القائمة؛ الرابط بالاسم الكامل كما هو
    nm = escape(SN.apply(snm or {}, _name(p, lang)))
    name = f'<a href="{href}">{nm}</a>' if href else f'<span class="nm">{nm}</span>'
    rk = f'<span class="rk">{rank}</span>' if show_rank else ""
    return (f'<div class="psr{" first" if first else ""}">{rk}{img}<span class="pn">{name}<small>{escape(tm)}</small></span>'
            f'<span class="pv">{v}</span></div>')


def cards_html(conn, code, season, newest, lang, team_of, logo_of, href_of):
    """البطاقات (أو "" إن لم تكفِ التغطية) + {stat: [(rank, p, v)]} للصفحات الكاملة"""
    av = available(conn, code, season)
    if not av:
        return "", {}
    s = STR[lang]
    players = rows(conn, code, season)
    snm = SN.page_map(_name(p, lang) for p in players)
    lists, html = {}, ""
    for stat in STATS:
        if not av.get(stat):
            continue
        lst = ranked(players, stat)
        if not lst:
            continue
        lists[stat] = lst
        body = "".join(_row(rk, p, v, lang, team_of, logo_of, href_of, first=(i == 0), snm=snm)
                       for i, (rk, p, v) in enumerate(lst[:TOP[stat]]))
        html += (f'<div class="pscard" data-stat="{stat}"><a class="psh" href="{list_fname(code, season, newest, stat)}" '
                 f'aria-label="{s["all"]}: {s[stat]}"><span>{s[stat]}</span><span class="go">{GO_SVG}</span></a>{body}</div>')
    return (f'<div class="pcards">{html}</div>' if html else ""), lists


def list_body(stat, lst, lang, team_of, logo_of, href_of):
    """جسم صفحة القائمة الكاملة لإحصائية واحدة"""
    snm = SN.page_map(_name(p, lang) for _, p, _ in lst)
    return '<div class="pscard">' + "".join(_row(rk, p, v, lang, team_of, logo_of, href_of, first=(i == 0), show_rank=True, snm=snm)
                                            for i, (rk, p, v) in enumerate(lst)) + '</div>'
