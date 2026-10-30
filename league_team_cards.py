#!/usr/bin/env python3
"""
بطاقات «إحصائيات الفرق» بصفحة الدوري على نمط FotMob (30 أكتوبر 2026، دفعة 4 بند 1)
====================================================================================
أربع بطاقات لـ(دوري، موسم) بالضبط، نفس شكل بطاقات اللاعبين (league_player_cards: .pscard/.psr، أول 3 + «›» لصفحة القائمة):
    أهداف بالمباراة (الأعلى) · أهداف مستقبَلة بالمباراة (الأقل) · شباك نظيفة (الأكثر، من نتائج المباريات) · متوسط الاستحواذ (الأعلى)
الأرقام من المباريات المنتهية نفسها التي يُبنى منها جدول الترتيب (make_site3.get_table: بلا المستبعَدة من الترتيب).
صفحات القوائم: leagues/<code>[-<season>]-team-<stat>.html و en/leagues/… (stat = scored | conceded | cs | poss) — كل الفرق: المركز،
النادي (رابط صفحته)، القيمة. noindex (صفحة مشتقة).

⚠️ **الاستحواذ بشرط التغطية (لا أرقام جزئية):** يظهر فقط إن كان لـ≥ 90% (COVER) من مباريات الموسم المنتهية استحواذ الفريقين بـmatch_stats.
   المتوسط لكل فريق = متوسط مبارياته التي لها استحواذ. البطاقات الثلاث الأخرى من النتائج فتظهر لكل الدوريات.
ترتيب التعادل: القيمة، ثم (للأهداف/الاستقبال) عدد الأهداف المطلق، ثم اسم النادي؛ المركز المشترك بنفس الرقم.

صفر طلبات API.
"""
from html import escape

COVER = 0.9
STATS = ("scored", "conceded", "cs", "poss")
STR = {
    "ar": {"scored": "أهداف بالمباراة", "conceded": "أهداف مستقبَلة بالمباراة", "cs": "شباك نظيفة", "poss": "متوسط الاستحواذ",
           "all": "عرض الكل"},
    "en": {"scored": "Goals per match", "conceded": "Goals conceded per match", "cs": "Clean sheets", "poss": "Average possession",
           "all": "See all"},
}
TOP = 3


def coverage(conn, code, season, excluded=()):
    """نسبة مباريات الموسم المنتهية التي لها استحواذ الفريقين بـmatch_stats"""
    ex = ",".join("?" * len(excluded)) or "0"
    fin, cov = conn.execute(f"""
        SELECT COUNT(*), SUM(CASE WHEN (SELECT COUNT(*) FROM match_stats x WHERE x.match_id = m.match_id
                                        AND x.possession IS NOT NULL) = 2 THEN 1 ELSE 0 END)
        FROM matches m WHERE m.league_code = ? AND m.season = ? AND m.home_goals IS NOT NULL
          AND m.match_id NOT IN ({ex})""", (code, season, *excluded)).fetchone()
    return (cov or 0) / fin if fin else 0.0


def team_rows(conn, code, season, excluded=()):
    """{tid: {tid, played, gf, ga, cs, poss_sum, poss_n}} من المباريات المنتهية (نفس مجموعة جدول الترتيب)"""
    ex = ",".join("?" * len(excluded)) or "0"
    out = {}
    for mid, h, a, hg, ag in conn.execute(f"""
            SELECT match_id, home_id, away_id, home_goals, away_goals FROM matches
            WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL AND match_id NOT IN ({ex})""",
            (code, season, *excluded)):
        for tid, gf, ga in ((h, hg, ag), (a, ag, hg)):
            r = out.setdefault(tid, {"tid": tid, "played": 0, "gf": 0, "ga": 0, "cs": 0, "poss_sum": 0, "poss_n": 0})
            r["played"] += 1
            r["gf"] += gf
            r["ga"] += ga
            r["cs"] += 1 if ga == 0 else 0
    for tid, poss in conn.execute(f"""
            SELECT s.team_id, s.possession FROM match_stats s JOIN matches m ON m.match_id = s.match_id
            WHERE m.league_code = ? AND m.season = ? AND m.home_goals IS NOT NULL AND s.possession IS NOT NULL
              AND m.match_id NOT IN ({ex})""", (code, season, *excluded)):
        if tid in out:
            out[tid]["poss_sum"] += poss
            out[tid]["poss_n"] += 1
    return out


def _fmt(stat, v):
    if stat == "cs":
        return str(v)
    if stat == "poss":
        return f"{v:.1f}%"
    return f"{v:.2f}"


def ranked(teams, stat, name_of):
    """[(مركز، صف الفريق، القيمة المعروضة)] بترتيب التعادل أعلاه"""
    rows = [r for r in teams.values() if r["played"]]
    if stat == "poss":
        rows = [r for r in rows if r["poss_n"]]
        key = lambda r: (-round(r["poss_sum"] / r["poss_n"], 1), name_of(r["tid"]))
        val = lambda r: r["poss_sum"] / r["poss_n"]
    elif stat == "scored":
        key = lambda r: (-round(r["gf"] / r["played"], 2), -r["gf"], name_of(r["tid"]))
        val = lambda r: r["gf"] / r["played"]
    elif stat == "conceded":
        key = lambda r: (round(r["ga"] / r["played"], 2), r["ga"], name_of(r["tid"]))
        val = lambda r: r["ga"] / r["played"]
    else:
        key = lambda r: (-r["cs"], name_of(r["tid"]))
        val = lambda r: r["cs"]
    out, rank, prev = [], 0, None
    for i, r in enumerate(sorted(rows, key=key), 1):
        shown = _fmt(stat, val(r))
        if shown != prev:
            rank, prev = i, shown
        out.append((rank, r, shown))
    return out


def list_fname(code, season, newest, stat):
    base = code.lower() if season == newest else f"{code.lower()}-{season}"
    return f"{base}-team-{stat}.html"


def _row(rank, r, v, team_of, logo_of, first=False, show_rank=False):
    tid = r["tid"]
    src = logo_of(tid)
    img = (f'<img src="{escape(src, quote=True)}" alt="" width="24" height="24" loading="lazy" decoding="async">'
           if src else '<span class="noimg"></span>')
    rk = f'<span class="rk">{rank}</span>' if show_rank else ""
    return (f'<div class="psr{" first" if first else ""}">{rk}{img}<span class="pn">'
            f'<a href="clubs/{tid}.html">{escape(team_of(tid))}</a></span><span class="pv" dir="ltr">{v}</span></div>')


def cards_html(conn, code, season, newest, lang, team_of, logo_of, excluded=()):
    """(البطاقات، {stat: [(rank, r, v)]} لصفحات القوائم، نسبة تغطية الاستحواذ)"""
    from league_player_cards import GO_SVG
    s = STR[lang]
    teams = team_rows(conn, code, season, excluded)
    if not teams:
        return "", {}, 0.0
    cov = coverage(conn, code, season, excluded)
    lists, html = {}, ""
    for stat in STATS:
        if stat == "poss" and cov < COVER:
            continue
        lst = ranked(teams, stat, team_of)
        if not lst:
            continue
        lists[stat] = lst
        body = "".join(_row(rk, r, v, team_of, logo_of, first=(i == 0)) for i, (rk, r, v) in enumerate(lst[:TOP]))
        html += (f'<div class="pscard" data-tstat="{stat}"><a class="psh" href="{list_fname(code, season, newest, stat)}" '
                 f'aria-label="{s["all"]}: {s[stat]}"><span>{s[stat]}</span><span class="go">{GO_SVG}</span></a>{body}</div>')
    return (f'<div class="pcards tcards">{html}</div>' if html else ""), lists, cov


def list_body(lst, team_of, logo_of):
    """جسم صفحة القائمة الكاملة لإحصائية واحدة"""
    return '<div class="pscard">' + "".join(_row(rk, r, v, team_of, logo_of, first=(i == 0), show_rank=True)
                                            for i, (rk, r, v) in enumerate(lst)) + '</div>'
