#!/usr/bin/env python3
"""
صفحات الكؤوس — بلغتين (الموجة 1، 4 نوفمبر 2026 — cups_plan.md 3.5)
=====================================================================
    leagues/<code>.html  و  en/leagues/<code>.html     (<code> = رمز config.COMPETITIONS بحروف صغيرة: sau-kc، egy-sc…)

نفس إطار صفحة الدوري (make_leagues: الترويسة الثابتة + التبويبات + TAB_SCRIPT + تبويب المباريات بالأيام) بثلاثة تبويبات:
    المباريات       كل مباريات الموسم الجاري (المنتهية + القادمة) بالأيام — البطاقة تحمل «ترجيح 3-2» (match_card + pen_home)
    شجرة البطولة    cup_bracket.build: أعمدة الأدوار (سطح المكتب: جنباً إلى جنب بتمرير أفقي؛ الجوال: دور واحد بأزرار الأدوار)
    الهدّافون        get_scorers (جدول goals — ركلات الترجيح مستبعدة عند الكتابة، match_score.is_shootout)
(الموجة 3، 6 نوفمبر 2026) كأس بمرحلة مجموعات/دوري (config.COMPETITIONS[code]["table"]) يأخذ تبويب «الجدول» بعد المباريات
(cup_tables.py: محسوب من النتائج — المجموعات بعناوين «المجموعة N»، وخط تحت المركز table_line إن وُجد)، والشجرة من أدوار ما بعد
المرحلة وحدها (التبويب يغيب حتى تظهر أول مباراة إقصائية). الكؤوس الإقصائية بلا تغيير حرفياً (لا CSS ولا تبويب إضافي).
**لا جدول ترتيب ولا «الموسم حتى الآن» لكأس** (get_table = [] لكأس منذ الموجة 0). السوبر بمباراة واحدة = بطاقة نهائي واحدة
(الشجرة بمواجهة واحدة تُرسم بطاقة واحدة)؛ السوبر بنصف نهائي = نصف النهائي ← النهائي (+ المركز الثالث تحتها إن وُجد).

⚠️ الموسم = موسم المزوّد الجاري بالسجلّ (config.COMPETITIONS[code]["season"]) — ليس config.SEASON؛ التسمية CP.season_label.
⚠️ لا متابعة ولا جرس بصفحة الكأس بعد: اشتراكات الـworker (LEAGUE_IDS) بلا معرّفات الكؤوس — تُضاف مع البثّ الحي.
⚠️ الروابط نسبية بعمق 1 (العربية) و2 (الإنجليزية) كصفحة الدوري؛ الشعارات من make_clubs (thumbs/ ثم المحلي ثم المزوّد).

صفر طلبات API.
    python make_cups.py               ← كل كأس له مباريات بموسمه الجاري
    python make_cups.py SAU-KC EGY-SC ← هذه فقط
"""
import os
import sqlite3
import sys
from html import escape

import competitions as CP
import cup_bracket as B
import cup_tables as CT
import make_clubs as MC
import push_ui
from config import COMPETITIONS, DB_FILE
from i18n import DIR, LANGS, T, league_name, off_label
from live_view import live_script
from make_leagues import (COUNTRY, LOCAL_STYLE, TAB_SCRIPT, compact_row, league_days_script, matches_tab, scorer_names)
from make_site3 import STYLE, flag_path, get_scorers, load_league_logos, load_overrides, player_link
from match_round import label as round_label
from matchtime import matchtime_script
from navbar import appbar, nav_script, navbar, pwa_script
from prefs import prefs_script
from swipe_view import swipe_script
from theme import BACK_SCRIPT, THEME_HEAD, THEME_SCRIPT, head_meta
from thumbs_util import thumb_src

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = DB_FILE.parent

S = {
    "ar": {"bracket": "شجرة البطولة", "scorers": "الهدّافون", "champion": "البطل", "tbd": "يُحدَّد لاحقاً",
           "third": "مباراة المركز الثالث", "pens": "ركلات الترجيح", "aet": "بعد التمديد", "agg": "المجموع",
           "no_scorers": "لا أهداف مسجّلة بعد", "no_bracket": "لا مواجهات بعد",
           "table": "الجدول", "group": "المجموعة {n}", "table_note": "الترتيب محسوب من نتائج المباريات"},
    "en": {"bracket": "Bracket", "scorers": "Top Scorers", "champion": "Champion", "tbd": "TBD",
           "third": "Third-place match", "pens": "Pens", "aet": "AET", "agg": "Agg",
           "no_scorers": "No goals yet", "no_bracket": "No ties yet",
           "table": "Table", "group": "Group {n}", "table_note": "Standings computed from match results"},
}

CUP_CSS = """
<style>
  /* شجرة البطولة (الموجة 1): أعمدة أدوار؛ ≥760px جنباً إلى جنب بتمرير أفقي، أقل = دور واحد ظاهر (أزرار .bkn، BRACKET_SCRIPT) */
  .bkn { display:flex; gap:6px; overflow-x:auto; scrollbar-width:none; margin:0 0 12px; padding-bottom:2px; }
  .bkn::-webkit-scrollbar { display:none; }
  .bkn button { flex:0 0 auto; min-height:40px; padding:0 14px; border-radius:20px; border:1px solid var(--line);
                background:var(--card); color:var(--muted); font:inherit; font-size:13px; font-weight:600; cursor:pointer; white-space:nowrap; }
  .bkn button.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .bkc { display:block; }
  .bkcol { margin:0 0 14px; }
  .bkcol h3 { font-size:14px; margin:0 0 8px; color:var(--muted); font-weight:700; }
  .bkt.js .bkcol { display:none; }
  .bkt.js .bkcol.on { display:block; }
  @media (min-width:760px) {
    .bkn { display:none; }
    .bkc { display:flex; gap:12px; overflow-x:auto; align-items:stretch; padding-bottom:6px; }
    .bkt.js .bkcol, .bkcol { display:flex; flex-direction:column; flex:1 0 210px; max-width:260px; margin:0; }
    .bkcol .bkties { display:flex; flex-direction:column; justify-content:space-around; flex:1; gap:8px; }
  }
  .tie { display:block; position:relative; background:var(--card); border-radius:12px; padding:8px 10px; margin:0 0 8px;
         color:var(--text); text-decoration:none; border:1px solid transparent; }
  a.tie:hover { border-color:var(--line); }
  .tie.ph { opacity:.6; }
  .tr { display:flex; align-items:center; gap:8px; min-height:30px; }
  .tr img { width:22px; height:22px; object-fit:contain; flex:0 0 22px; }
  .tr .tn { flex:1; min-width:0; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tr .ts { font-weight:700; font-size:15px; min-width:18px; text-align:center; font-variant-numeric:tabular-nums; }
  .tr .tp { font-size:11px; color:var(--muted); min-width:22px; text-align:center; }
  .tr.lo .tn, .tr.lo .ts { color:var(--muted); font-weight:400; }
  .tr.w .tn { font-weight:700; }
  .tm { font-size:11px; color:var(--muted); margin-top:2px; }
  .tie.fin { padding:12px 14px; }
  .tie.fin .tr img { width:28px; height:28px; flex-basis:28px; }
  .tie.fin .tr .tn { font-size:16px; }
  .champ { display:flex; align-items:center; gap:10px; background:var(--card); border-radius:12px; padding:10px 14px; margin:0 0 14px;
           border-inline-start:3px solid #d4a017; }
  .champ img { width:32px; height:32px; object-fit:contain; }
  .champ small { display:block; color:var(--muted); font-size:12px; }
  .champ b { font-size:16px; }
  .bkx { margin-top:6px; }
  .bkx h3 { font-size:14px; margin:0 0 8px; color:var(--muted); }
  .cup-sc ol { list-style:none; padding:0; margin:0; }
  /* ركلات الترجيح بسطر صغير تحت نتيجة البطاقة («ترجيح 3-2»، make_site3.match_card) — هنا وحدها: صفوف الكؤوس وحدها تحمل pen_home */
  .match .score .pso { display:block; white-space:nowrap; font-size:10px; font-weight:600; line-height:1.15; margin-top:1px; color:var(--muted); }
</style>"""

# (الموجة 3) لصفحات الكؤوس ذات الجدول وحدها — جدول الدوري نفسه (STYLE)، فقط عناوين المجموعات وخط التأهّل والملاحظة
TABLE_CSS = """
<style>
  .ctbl h3 { font-size:14px; margin:14px 0 8px; color:var(--muted); font-weight:700; }
  .ctbl h3:first-child { margin-top:0; }
  .ctbl table { border-radius:12px; overflow:hidden; }
  .ctbl tr.cut td { border-bottom:2px solid var(--accent); }
  .ctbl .tnote { font-size:12px; color:var(--muted); margin:8px 2px 0; }
</style>"""

BRACKET_SCRIPT = """
<script>
(function(){
  var b=document.querySelector('.bkt'); if(!b) return;
  var btns=b.querySelectorAll('.bkn button'), cols=b.querySelectorAll('.bkcol');
  function show(i){ btns.forEach(function(x,j){ x.classList.toggle('on', j===i); }); cols.forEach(function(c,j){ c.classList.toggle('on', j===i); });
    try{ btns[i].scrollIntoView({inline:'nearest', block:'nearest'}); }catch(e){} }
  btns.forEach(function(x,i){ x.addEventListener('click', function(){ show(i); }); });
  b.classList.add('js'); show(+b.getAttribute('data-cur')||0);
})();
</script>"""


def cup_rows(conn, code, season):
    """كل مباريات الكأس بالموسم مع أسماء الفريقين وشعاريهما وتفصيل النتيجة (للبطاقات والشجرة)"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals, m.league_code, m.season, m.status, m.round,
               m.pen_home, m.pen_away, m.et_home, m.et_away,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en, h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en, a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ?
        ORDER BY m.date, m.match_id
    """, (code, season)).fetchall()


def cup_codes(conn, only=None):
    """الكؤوس التي لها مباريات بموسمها الجاري (بترتيب السجلّ)"""
    out = []
    for code, c in COMPETITIONS.items():
        if only and code not in only:
            continue
        if conn.execute("SELECT 1 FROM matches WHERE league_code = ? AND season = ? LIMIT 1", (code, c["season"])).fetchone():
            out.append(code)
    return out


def _team_row(teams, tid, lang, score, cls, pen=None):
    t = teams.get(tid) if tid else None
    if t is None:
        return (f'<div class="tr"><span class="tn">{S[lang]["tbd"]}</span>'
                f'<span class="ts"></span></div>')
    img = MC.logo_tag(t, lang, 22)
    p = f'<span class="tp">({pen})</span>' if pen is not None else ""
    return (f'<div class="tr{(" " + cls) if cls else ""}">{img}<span class="tn">{escape(MC.tname(t, lang))}</span>{p}'
            f'<span class="ts">{"" if score is None else score}</span></div>')


def tie_html(t, teams, lang, final=False):
    """بطاقة مواجهة: فريقان (الفائز عريض، الخاسر باهت)، النتيجة/المجموع، الترجيح بين قوسين، وسطر الموعد/الحالة"""
    s = S[lang]
    a, b = t["a"], t["b"]
    ga = gb = None
    if t["agg"] is not None:
        ga, gb = t["agg"]
    pa = pb = None
    if t["pens"]:
        pa, pb = t["pens"]
    ca = "w" if t["winner"] and t["winner"] == a else ("lo" if t["winner"] else "")
    cb = "w" if t["winner"] and t["winner"] == b else ("lo" if t["winner"] else "")
    rows = _team_row(teams, a, lang, ga, ca, pa) + _team_row(teams, b, lang, gb, cb, pb)
    meta = ""
    if t["legs"]:
        last = t["legs"][-1]
        if t["pens"]:
            meta = f'{s["pens"]} {pa}-{pb}'
        elif last["status"] == "AET":
            meta = s["aet"]
        elif len(t["legs"]) > 1 and t["agg"] is not None:
            meta = s["agg"]
        elif last["home_goals"] is None:
            parts = str(last["date"]).split()
            day, clock = parts[0], (parts[1][:5] if len(parts) > 1 else "")
            off = off_label(last["status"], T[lang], last["date"])
            if off:
                meta = escape(off)
            elif clock:
                meta = (f'<span data-utcd="{day}T{clock}:00Z">{day}</span> '
                        f'<span data-utc="{day}T{clock}:00Z">{clock} UTC</span>')
            else:
                meta = day
    cls = "tie" + (" fin" if final else "") + (" ph" if t["placeholder"] else "")
    body = rows + (f'<div class="tm">{meta}</div>' if meta else "")
    if len(t["legs"]) == 1:
        return f'<a class="{cls}" href="../matches/{t["legs"][0]["match_id"]}.html">{body}</a>'
    return f'<div class="{cls}">{body}</div>'


def bracket_html(bk, teams, lang):
    """تبويب الشجرة: (البطل إن حُسم) + أزرار الأدوار (جوال) + أعمدة الأدوار + المركز الثالث"""
    s = S[lang]
    if not bk["rounds"]:
        return f'<div class="empty">{s["no_bracket"]}</div>'
    champ = ""
    if bk["champion"] and teams.get(bk["champion"]):
        ct = teams[bk["champion"]]
        champ = (f'<div class="champ">{MC.logo_tag(ct, lang, 32)}<div><small>{s["champion"]}</small>'
                 f'<b>{escape(MC.tname(ct, lang))}</b></div></div>')
    # الدور الظاهر بالجوال: أول دور فيه مواجهة حقيقية لم تُحسم، وإلا آخر دور حقيقي
    real = [i for i, rd in enumerate(bk["rounds"]) if any(not t["placeholder"] for t in rd["ties"])]
    open_ = [i for i in real if any(not t["placeholder"] and t["winner"] is None for t in bk["rounds"][i]["ties"])]
    cur = open_[0] if open_ else (real[-1] if real else 0)
    nav, cols = "", ""
    single = len(bk["rounds"]) == 1 and len(bk["rounds"][0]["ties"]) == 1
    for i, rd in enumerate(bk["rounds"]):
        name = round_label(B.display_round(rd["round"], bk), lang) or rd["round"]
        nav += f'<button type="button"{" class=on" if i == cur else ""}>{escape(name)}</button>'
        ties = "".join(tie_html(t, teams, lang, final=single or rd["round"] == "Final") for t in rd["ties"])
        cols += (f'<section class="bkcol{" on" if i == cur else ""}"><h3>{escape(name)}</h3>'
                 f'<div class="bkties">{ties}</div></section>')
    extra = ""
    if bk["extra"]:
        extra = (f'<div class="bkx"><h3>{s["third"]}</h3>'
                 + "".join(tie_html(t, teams, lang) for t in bk["extra"]) + '</div>')
    navh = f'<div class="bkn">{nav}</div>' if len(bk["rounds"]) > 1 else ""
    return f'{champ}<div class="bkt" data-cur="{cur}">{navh}<div class="bkc">{cols}</div></div>{extra}'


def table_html(tbls, teams, lang, cut=None):
    """تبويب الجدول (الموجة 3): جدول لكل مجموعة (عنوان «المجموعة N») أو جدول واحد، خط تحت المركز cut، وملاحظة الحساب"""
    t, s = T[lang], S[lang]
    if not tbls:
        return f'<div class="empty">{t["empty_combo"]}</div>'
    out = ""
    for g in tbls:
        if CT.group_title(g, lang):     # (الموجة 4) اسم رسمي: «غرب آسيا» / «المجموعة A»
            out += f'<h3>{escape(CT.group_title(g, lang))}</h3>'
        elif g["group"] is not None:
            out += f'<h3>{escape(s["group"].format(n=g["group"]))}</h3>'
        rows = ""
        for r in g["rows"]:
            tm = teams.get(r["team"])
            nm = escape(MC.tname(tm, lang)) if tm else str(r["team"])
            img = MC.logo_tag(tm, lang, 22) if tm else ""
            cls = ' class="cut"' if cut and r["pos"] == cut and len(g["rows"]) > cut else ""
            rows += (f'<tr{cls} data-t="{r["team"]}"><td class="pos">{r["pos"]}</td>'
                     f'<td class="team">{img}<a href="clubs/{r["team"]}.html">{nm}</a></td>'
                     f'<td>{r["played"]}</td><td>{r["won"]}</td><td>{r["drawn"]}</td><td>{r["lost"]}</td>'
                     f'<td><bdi dir="ltr">{r["gd"]:+d}</bdi></td><td class="pts">{r["points"]}</td></tr>')
        out += (f'<table><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th><th>{t["played"]}</th><th>{t["won"]}</th>'
                f'<th>{t["drawn"]}</th><th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>{rows}</table>')
    return f'<div class="ctbl">{out}<p class="tnote">{s["table_note"]}</p></div>'


def scorers_html(conn, code, season, lang, depth):
    t, s = T[lang], S[lang]
    scorers = get_scorers(conn, code, season, limit=1000)
    if not scorers:
        return f'<div class="empty">{s["no_scorers"]}</div>'
    names = scorer_names(scorers, lang)
    li = ""
    for i, sc in enumerate(scorers, 1):
        from make_site3 import tname
        href = player_link(sc["player"], BASE, depth, lang)
        nm = f'<a href="{href}">{names[i - 1]}</a>' if href else names[i - 1]
        li += (f'<li class="{"hidden" if i > 10 else ""}"><span class="num">{i}</span><span class="pname">{nm}</span>'
               f'<span class="pteam">{tname(sc, lang, "team", "team_en")}</span><span class="pgoals">{sc["goals"]}</span></li>')
    more = (f'<button class="more">{t["show_all_scorers"]} ({len(scorers) - 10})</button>' if len(scorers) > 10 else "")
    return f'<div class="cup-sc"><ol>{li}</ol>{more}</div>'


def cup_page(conn, lang, code, logos, teams):
    """صفحة كأس واحدة بلغة واحدة (الموسم الجاري بالسجلّ)"""
    t, s = T[lang], S[lang]
    depth = 1 if lang == "ar" else 2
    c = COMPETITIONS[code]
    season = c["season"]
    code_l = code.lower()
    rows = cup_rows(conn, code, season)
    matches_html, more_m = matches_tab(list(rows), lang, logos)
    how = CT.mode(code)   # (الموجة 3) None = كأس إقصائية: كل ما يلي حرفياً كما كان
    bk = B.build(CT.knockout_rows(rows) if how else rows, c["type"])
    _ll, _lloc = load_league_logos()
    url = _lloc.get(code) or _ll.get(code)
    up = "../" if lang == "ar" else "../../"
    if url and url.startswith("http"):
        # (11 نوفمبر 2026) رأس الكأس 64px: النسخة المحلية -128 بدل PNG المزوّد الكامل (CAF-CL 93 ك.ب)
        url = thumb_src(f"league_{code_l}", up, big=True) or url
    lg_img = (f'<img class="lgbig" src="{url}" alt="">' if url
              else (f'<img class="lgbig flagbig" src="{up}{flag_path(code)}" alt="">' if flag_path(code) else ""))
    country = COUNTRY.get(CP.country_of(code) or "", ("", ""))[0 if lang == "ar" else 1]
    sub = " · ".join(x for x in (country, f'<bdi dir="ltr">{CP.season_label(code, season)}</bdi>') if x)
    if not how:
        tabs = (f'<div class="tabs cattabs">'
                f'<button class="tab active" data-cat="matches">{t["tab_matches"]}</button>'
                f'<button class="tab" data-cat="bracket">{s["bracket"]}</button>'
                f'<button class="tab" data-cat="scorers">{s["scorers"]}</button></div>')
        panels = (f'<section class="panel visible" data-cat="matches">{matches_html}{more_m}</section>'
                  f'<section class="panel" data-cat="bracket">{bracket_html(bk, teams, lang)}</section>'
                  f'<section class="panel" data-cat="scorers">{scorers_html(conn, code, season, lang, depth)}</section>')
    else:
        tbls = CT.tables(rows, how, CT.en_names(conn).get, code)
        tabs = (f'<div class="tabs cattabs">'
                f'<button class="tab active" data-cat="matches">{t["tab_matches"]}</button>'
                f'<button class="tab" data-cat="table">{s["table"]}</button>'
                + (f'<button class="tab" data-cat="bracket">{s["bracket"]}</button>' if bk["rounds"] else "")
                + f'<button class="tab" data-cat="scorers">{s["scorers"]}</button></div>')
        panels = (f'<section class="panel visible" data-cat="matches">{matches_html}{more_m}</section>'
                  f'<section class="panel" data-cat="table">{table_html(tbls, teams, lang, CT.line(code))}</section>'
                  + (f'<section class="panel" data-cat="bracket">{bracket_html(bk, teams, lang)}</section>' if bk["rounds"] else "")
                  + f'<section class="panel" data-cat="scorers">{scorers_html(conn, code, season, lang, depth)}</section>')
    fname = f"{code_l}.html"
    switch = f'../en/leagues/{fname}' if lang == "ar" else f'../../leagues/{fname}'
    name = league_name(code, lang)
    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f'<title>{name} — {t["site_title"]}</title>\n'
        + head_meta(name, t["site_sub"], up, lang, f"leagues/{fname}" if lang == "ar" else f"en/leagues/{fname}")
        + THEME_HEAD + STYLE + LOCAL_STYLE + CUP_CSS + (TABLE_CSS if how else "") +
        '</head>\n<body>\n<div class="wrap">\n'
        + '<div class="lstick">'
        + appbar(t, lang, switch, back=True)
        + f'<header class="lhead"><div class="lh-id">{lg_img}<div class="lh-tx"><h1>{escape(name)}</h1>'
          f'<div class="lh-sub">{sub}</div></div></div></header>\n'
        + push_ui.msg_html()
        + f'{tabs}' + compact_row(t, lang, escape(name), country, CP.season_label(code, season)) + f'</div>\n{panels}\n</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT + BACK_SCRIPT + matchtime_script() + league_days_script(lang)
        + nav_script(t) + pwa_script(lang) + live_script(t, depth)
        + TAB_SCRIPT + BRACKET_SCRIPT + swipe_script() + prefs_script()
        + '</body>\n</html>'
    )
    html = html.replace('href="clubs/', 'href="../clubs/').replace('href="matches/', 'href="../matches/')
    return html.replace('src="logos/', f'src="{up}logos/').replace('src="thumbs/', f'src="{up}thumbs/')


def main():
    only = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
    bad = [a for a in only if not CP.is_cup(a)]
    if bad:
        print(f"ليست كؤوساً بـconfig.COMPETITIONS: {bad}")
        return 2
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    logos = load_overrides()
    teams = MC.load_teams()
    os.makedirs(BASE / "leagues", exist_ok=True)
    os.makedirs(BASE / "en" / "leagues", exist_ok=True)
    codes = cup_codes(conn, set(only) if only else None)
    for code in codes:
        for lang in LANGS:
            out = (BASE / "leagues" if lang == "ar" else BASE / "en" / "leagues") / f"{code.lower()}.html"
            out.write_text(cup_page(conn, lang, code, logos, teams), encoding="utf-8")
    conn.close()
    print(f"  صفحات الكؤوس: {len(codes)} × لغتين — {', '.join(codes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
