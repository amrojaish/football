#!/usr/bin/env python3
"""
صفحة الدوريات — بلغتين
=========================
إعادة تصميم (3 سبتمبر — راجع leagues_spec.md، قرارات محسومة):

    leagues.html              → 3 أعلام فقط (الأردن · العراق · السعودية)
    en/leagues.html           → نفسها بالإنجليزي

    leagues/<code>.html       → صفحة الدوري: الموسم الحالي بأربع
                                تبويبات (الترتيب · المباريات ·
                                إحصائيات اللاعبين · إحصائيات
                                الفرق). لا صفحة بلد منفصلة —
                                بلد واحد = دوري واحد حالياً، فالضغطة
                                على العلم تشيل مباشرة لهنا.
    en/leagues/<code>.html    → نفسها بالإنجليزي

⚠️ **الموسم الحالي فقط يُولَّد افتراضياً** (بلا وسيط) — هذا ما
   تستدعيه الأتمتة كل تشغيلة، ولا يمسّ الأرشيف.
   `python make_leagues.py --all` يبني **كل المواسم** لكل دوري
   دفعة واحدة (أرشفة صريحة يدوية — لا تُستدعى تلقائياً أبداً).
   المنسدلة أعلى الصفحة تُبنى من الملفات الموجودة فعلاً على القرص
   (`season_files()`) لا من قائمة ثابتة، فلا رابط ميت.

⚠️ **الكأس مستقبلاً:** ملف شقيق `leagues/<code>-cup.html`، ومعنى
   `leagues/<code>.html` (= الدوري) لا يتغيّر أبداً. الاختيار بين
   بطولتين يُحلّ بصفحة الأعلام (`leagues.html`) لا بصفحة وسيطة.

⚠️ **خطوة أرشفة إجبارية عند كل تدوير موسم** — راجع البند 6 بقائمة
   "عند بداية موسم جديد" بالـREADME. نسيانها يُضيّع محتوى الموسم
   الخارج بلا رابط يعود له أبداً (لا حذف — الملف ببساطة ما تولّد).

⚠️ **يستورد الدوال المشتركة من `make_site3.py`** لا ينسخها.

⚠️ **الروابط داخل `leagues/` نسبية بعمق 1** (مثل `matches/` و
   `clubs/`): `../clubs/x.html`، `../logos/...`. الإنجليزية بعمق 2
   (`en/leagues/` تحت `en/`).

⚠️ **`make_sitemap.py` لا يحتاج تعديلاً** — يمسح كل `.html` تحت
   المجلد فعلياً (`os.walk`)، فأي ملف بـ`leagues/` يدخل الخريطة
   تلقائياً بأول تشغيلة بعد التوليد. تحقّقت من الكود قبل الافتراض.

⚠️ **`clean_orphans.py` لا يحتاج تعديلاً حالياً** — لا يكنس
   `leagues/` أصلاً (يقتصر على players/clubs/matches)، وصفحات
   الدوري الثلاث دائماً موجودة بالضبط (مرتبطة بـ`LEAGUES` بـ
   `config.py` لا بكيان يُدمَج أو يُحذف مثل اللاعبين). أرشيف
   المواسم دائم بالتصميم — لا يُعتبر يتيماً أبداً.

صفر طلبات API.

التشغيل:
    python make_leagues.py          الموسم الحالي فقط (الوضع المعتاد)
    python make_leagues.py --all    كل المواسم — أرشفة يدوية صريحة
"""

import sqlite3
import os
import sys

from config import DB_FILE, LEAGUES
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from search_view import search_box, search_script, search_overlay
from navbar import navbar, settings_overlay, nav_script, pwa_script
from theme import THEME_HEAD, THEME_SCRIPT, BACK_SCRIPT, back_button, head_meta
from live_view import live_script

# الدوال والأنماط المشتركة — مصدر واحد لا نسخة
from make_site3 import (STYLE, load_overrides, available, clean,
                        tname, get_table, get_matches, get_scorers,
                        match_card, player_link)
from matchtime import matchtime_script

BASE = DB_FILE.parent
LEAGUES_DIR = BASE / "leagues"

# ⚠️ الوضع الافتراضي (بلا --all) هو ما تستدعيه الأتمتة كل تشغيلة:
#    الموسم الحالي فقط لكل دوري — سريع، ولا يمسّ الأرشيف أبداً.
#    --all أرشفة صريحة يدوية لكل المواسم — لا تُستدعى تلقائياً.
ALL_SEASONS = "--all" in sys.argv

# ── أنماط وسكربت محليّان — لا يوجدان بـSTYLE المشتركة ──
LOCAL_STYLE = """
<style>
  .more { display:block; width:100%; margin:10px 0 4px; padding:10px;
          border-radius:9px; border:1px solid var(--line);
          background:var(--card); color:var(--muted); cursor:pointer;
          font-family:inherit; font-size:13px; }
  .more:hover { background:var(--card2); }
  li.hidden, .match.hidden { display:none; }
  .season-sel { width:100%; padding:10px; margin:12px 0; border-radius:9px;
                border:1px solid var(--line); background:var(--card);
                color:var(--text); font-family:inherit; font-size:14px; }
  .cattabs .tab { flex:1; }
</style>
"""

TAB_SCRIPT = """
<script>
(function(){
  var tabs = document.querySelectorAll('.cattabs .tab');
  var panels = document.querySelectorAll('.panel[data-cat]');
  tabs.forEach(function(b){
    b.addEventListener('click', function(){
      var cat = this.dataset.cat;
      tabs.forEach(function(x){ x.classList.toggle('active', x===b); });
      panels.forEach(function(p){
        p.classList.toggle('visible', p.dataset.cat === cat);
      });
    });
  });
  document.querySelectorAll('.more').forEach(function(btn){
    btn.addEventListener('click', function(){
      var box = btn.previousElementSibling;
      if(!box) return;
      box.querySelectorAll('.hidden').forEach(function(el){
        el.classList.remove('hidden');
      });
      btn.style.display = 'none';
    });
  });
})();
</script>
"""


def compute_streaks(conn, code, season):
    """
    لكل فريق: أطول سلسلة انتصارات وأطول سلسلة بلا هزيمة، بالتسلسل
    الزمني الفعلي — لا يوجد عمود جاهز لهذا، فيُحسب بحلقة بايثون
    على مباريات الفريق مرتّبة بالتاريخ.
    """
    rows = conn.execute("""
        SELECT home_id AS team, date, home_goals AS gf, away_goals AS ga
        FROM matches WHERE league_code=? AND season=? AND home_goals IS NOT NULL
        UNION ALL
        SELECT away_id AS team, date, away_goals AS gf, home_goals AS ga
        FROM matches WHERE league_code=? AND season=? AND home_goals IS NOT NULL
        ORDER BY team, date
    """, (code, season, code, season)).fetchall()

    by_team = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)

    win_streak, unbeaten_streak = {}, {}
    for team, games in by_team.items():
        cur_w = max_w = cur_u = max_u = 0
        for g in games:
            if g["gf"] > g["ga"]:
                cur_w += 1
                cur_u += 1
            elif g["gf"] == g["ga"]:
                cur_w = 0
                cur_u += 1
            else:
                cur_w = 0
                cur_u = 0
            max_w = max(max_w, cur_w)
            max_u = max(max_u, cur_u)
        win_streak[team] = max_w
        unbeaten_streak[team] = max_u
    return win_streak, unbeaten_streak


def leader_teams(table, value_of, best="max"):
    """
    الفرق المتساوية على القيمة القصوى/الدنيا لمقياس معيّن.
    ⚠️ **يرجع كل المتساويين لا واحداً عشوائياً** — اختيار فريق
       واحد بالتخمين عند تعادل قيمتين كذب بصورة رقم صحيح.
    """
    if not table:
        return [], None
    vals = [(value_of(r), r) for r in table]
    target = (max(v for v, _ in vals) if best == "max"
             else min(v for v, _ in vals))
    return [r for v, r in vals if v == target], target


def leader_card(label, teams, value, lang, logos, unit=""):
    """بطاقة إحصائية على نمط lcard/lead الموجودة أصلاً — صفر CSS جديد"""
    if not teams or value is None:
        return ""
    suffix = f' {unit}' if unit else ''
    if len(teams) == 1:
        r = teams[0]
        lead = (f'<div class="lead">'
                f'<img src="{logos.get(str(r["team_id"]), r["logo"])}" alt="">'
                f'<span>{tname(r, lang)}</span>'
                f'<span class="pts">{value}{suffix}</span></div>')
    elif len(teams) <= 3:
        sep = "، " if lang == "ar" else ", "
        names = sep.join(tname(r, lang) for r in teams)
        lead = (f'<div class="lead"><span>{names}</span>'
                f'<span class="pts">{value}{suffix}</span></div>')
    else:
        lead = f'<div class="lead"><span class="pts">{value}{suffix}</span></div>'
    return f'<div class="lcard"><div class="ln">{label}</div>{lead}</div>'


def top_player_stat(conn, code, season, column, min_apps=1):
    """
    أعلى قيمة إجمالية بعمود من player_stats — أي دوري وموسم
    (كانت 'SAU' حرفياً، درس 1: القيد بالداتا لا بقائمة أسماء) —
    مُجمَّعة بـplayer_id لا player_en (درس 5: تشابه الاسم ليس هوية).
    ترجع ([], None) طبيعياً لو الدوري/الموسم بلا صفوف — القيد
    الحقيقي (توفّر الداتا) يظهر بالنتيجة نفسها بلا فحص منفصل.
    """
    rows = conn.execute(f"""
        SELECT ps.player_id, ps.player_en, ps.player_ar,
               t.short_name_ar AS team,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS team_en,
               SUM(ps.{column}) AS val, COUNT(*) AS apps
        FROM player_stats ps
        JOIN matches m ON m.match_id = ps.match_id
        JOIN teams t ON t.team_id = ps.team_id
        WHERE m.league_code=? AND m.season=? AND ps.{column} IS NOT NULL
        GROUP BY ps.player_id
        HAVING apps >= ? AND val > 0
        ORDER BY val DESC LIMIT 20
    """, (code, season, min_apps)).fetchall()
    if not rows:
        return [], None
    target = rows[0]["val"]
    return [r for r in rows if r["val"] == target], target


def top_rating(conn, code, season, min_apps=3):
    """
    أعلى معدّل تقييم موسمي — أي دوري وموسم (كانت 'SAU' حرفياً).
    بحدّ أدنى مباريات لتفادي شذوذ مباراة واحدة. ⚠️ 3 لا 5: أول
    الموسم أقصى عدد ظهورات لأي لاعب = عدد الجولات المُلعَبة (4
    حالياً) — حدّ أعلى كان يُفرغ البطاقة كلياً لأسابيع. يرتفع
    أثره تلقائياً مع تقدّم الموسم لأنه نسبي لا مطلق.
    """
    rows = conn.execute("""
        SELECT ps.player_id, ps.player_en, ps.player_ar,
               t.short_name_ar AS team,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS team_en,
               AVG(ps.rating) AS val, COUNT(*) AS apps
        FROM player_stats ps
        JOIN matches m ON m.match_id = ps.match_id
        JOIN teams t ON t.team_id = ps.team_id
        WHERE m.league_code=? AND m.season=? AND ps.rating IS NOT NULL
        GROUP BY ps.player_id
        HAVING apps >= ?
        ORDER BY val DESC LIMIT 20
    """, (code, season, min_apps)).fetchall()
    if not rows:
        return [], None
    target = round(rows[0]["val"], 1)
    return [r for r in rows if round(r["val"], 1) == target], target


def player_leader_card(label, rows, value, lang):
    """بطاقة إحصائية لاعب — نفس نمط leader_card بلا شعار"""
    if not rows or value is None:
        return ""

    def pname(r):
        pl = clean(r["player_ar"]) if lang == "ar" else ""
        return pl or clean(r["player_en"])

    if len(rows) == 1:
        r = rows[0]
        tm = tname(r, lang, "team", "team_en")
        lead = (f'<div class="lead"><span>{pname(r)} · {tm}</span>'
                f'<span class="pts">{value}</span></div>')
    elif len(rows) <= 3:
        sep = "، " if lang == "ar" else ", "
        names = sep.join(pname(r) for r in rows)
        lead = (f'<div class="lead"><span>{names}</span>'
                f'<span class="pts">{value}</span></div>')
    else:
        lead = f'<div class="lead"><span class="pts">{value}</span></div>'
    return f'<div class="lcard"><div class="ln">{label}</div>{lead}</div>'


def team_stats_tab_html(conn, code, season, table, logos, lang, t):
    """
    تبويب إحصائيات الفرق — محسوبة من النتائج (leagues_spec.md
    طبقة ١)، تعمل للسبعة كلهم دائماً — صفر اعتماد على player_stats.
    """
    if not table:
        return f'<div class="empty">{t["empty_combo"]}</div>'

    win_streak, unbeaten_streak = compute_streaks(conn, code, season)
    by_id = {r["team_id"]: r for r in table}

    def team_row(tid):
        return by_id.get(tid)

    def streak_teams(streak_map):
        if not streak_map:
            return [], None
        target = max(streak_map.values())
        if target == 0:
            return [], None
        teams = [team_row(tid) for tid, v in streak_map.items()
                if v == target and team_row(tid)]
        return teams, target

    attack_teams, attack_v = leader_teams(table, lambda r: r["scored"])
    defense_teams, defense_v = leader_teams(
        table, lambda r: r["scored"] - r["diff"], best="min")
    diff_teams, diff_v = leader_teams(table, lambda r: r["diff"])
    win_teams, win_v = streak_teams(win_streak)
    unbeaten_teams, unbeaten_v = streak_teams(unbeaten_streak)

    diff_str = f'{diff_v:+d}' if diff_v is not None else None

    layer1 = "".join([
        leader_card(t["top_attack"], attack_teams, attack_v, lang, logos),
        leader_card(t["top_defense"], defense_teams, defense_v, lang, logos),
        leader_card(t["best_diff"], diff_teams, diff_str, lang, logos),
        leader_card(t["win_streak"], win_teams, win_v, lang, logos,
                    unit=t["streak_unit"]),
        leader_card(t["unbeaten_streak"], unbeaten_teams, unbeaten_v, lang,
                    logos, unit=t["streak_unit"]),
    ])

    return f'<div class="lgrid">{layer1}</div>'


def player_stats_layer_html(conn, code, season, lang, t):
    """
    بطاقات لاعبين إضافية (leagues_spec.md طبقة ٢) — تُبنى مباشرة
    من نتيجة الاستعلامات لـ(دوري, موسم) بالضبط، بلا فحص توفّر
    منفصل ولا قائمة دوريات ثابتة (درس 1). ترجع "" تلقائياً لو كل
    القيم فارغة — والسبب حينها توفّر الداتا الفعلي لهذا الموسم
    بالذات، لا اسم الدوري (مثال: الإماراتي عنده صفوف بـ2023/2024
    وصفر بـ2025 — نفس الدالة تُرجع محتوى أو فراغاً حسب الموسم
    المطلوب لا حسب `code` وحده).
    """
    rating_rows, rating_v = top_rating(conn, code, season)
    saves_rows, saves_v = top_player_stat(conn, code, season, "saves")
    kp_rows, kp_v = top_player_stat(conn, code, season, "passes_key")
    layer2 = "".join([
        player_leader_card(t["top_rating"], rating_rows, rating_v, lang),
        player_leader_card(t["top_saves"], saves_rows, saves_v, lang),
        player_leader_card(t["top_keypasses"], kp_rows, kp_v, lang),
    ])
    return f'<div class="lgrid">{layer2}</div>' if layer2 else ""


def season_files(code):
    """
    مواسم مؤرشفة موجودة فعلاً على القرص لهذا الدوري —
    ('leagues/jor-2025.html' → (2025, 'jor-2025.html')).
    المنسدلة تُبنى من هذا لا من قائمة ثابتة (درس الرابط الميت).
    """
    code_l = code.lower()
    if not LEAGUES_DIR.is_dir():
        return []
    out = []
    for f in LEAGUES_DIR.glob(f"{code_l}-*.html"):
        tail = f.stem[len(code_l) + 1:]
        if tail.isdigit():
            out.append((int(tail), f.name))
    return sorted(out, reverse=True)


def flags_page(lang, leagues):
    """leagues.html — ثلاثة أعلام فقط، بلا جداول"""
    t = T[lang]
    depth = 0 if lang == "ar" else 1

    cards = "".join(
        f'<a class="lcard" href="leagues/{code.lower()}.html">'
        f'<div class="ln">{league_name(code, lang)}</div></a>'
        for code in leagues
    )

    switch = ("en/leagues.html" if lang == "ar" else "../leagues.html")
    title = f'{t["leagues"]} — {t["site_title"]}'

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        + head_meta(title, t["site_sub"],
                    "" if lang == "ar" else "../", lang,
                    "leagues.html" if lang == "ar" else "en/leagues.html")
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<header><h1>{t["leagues"]}</h1>'
        f'<div class="sub">{t["choose_country"]}</div></header>\n'
        f'{search_box(t, big=True)}\n'
        f'<div class="lgrid">{cards}</div>\n'
        f'<footer><a href="about.html" '
        f'style="color:var(--accent);text-decoration:none">{t["about"]}</a>'
        f'<br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + navbar(t, depth, "leagues", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT
        + nav_script(t) + pwa_script(lang)
        + search_script(t, depth, lang) +
        '</body>\n</html>'
    )
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')
    return html


def league_page(conn, lang, code, season, logos, newest_season):
    """
    leagues/<code>.html أو leagues/<code>-<season>.html — صفحة
    موسم واحد بأربع تبويبات.

    newest_season: الموسم الحالي الفعلي لهذا الدوري — لازم
    ⚠️ **لا يُستنتَج من `season`** — `season` هو موسم الصفحة
       المطلوب توليدها الآن (قد يكون أرشيفاً)، و`newest_season`
       ثابت لكل استدعاءات الدوري بنفس الدفعة. الخلط بينهما كان
       يُنتج خياراً بالمنسدلة يدّعي أن أي أرشيف "الموسم الحالي"
       ويشاور خطأً على `<code>.html` — مصيدة أعمدة مقلوبة بثوب
       جديد (مصيدة 23)، أُمسكت بفحص المنسدلة قبل الرفع لا بعده.
    """
    t = T[lang]
    depth = 1 if lang == "ar" else 2
    code_l = code.lower()

    table = get_table(conn, code, season)
    matches = get_matches(conn, code, season, limit=500)
    scorers = get_scorers(conn, code, season, limit=1000)

    # ---- تبويب الترتيب ----
    rows = ""
    for i, r in enumerate(table, 1):
        cls = "top" if i <= 3 else ("bottom" if i > len(table) - 2 else "")
        rows += (
            f'<tr class="{cls}"><td class="pos">{i}</td>'
            f'<td class="team">'
            f'<img src="{logos.get(str(r["team_id"]), r["logo"])}" alt="">'
            f'<a href="clubs/{r["team_id"]}.html">{tname(r, lang)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )
    standings_html = ""
    if table:
        standings_html = (
            f'<table><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
            f'<th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>'
            f'{rows}</table>'
        )
    else:
        standings_html = f'<div class="empty">{t["empty_combo"]}</div>'

    # ---- تبويب المباريات — أول 10 ظاهرة، الباقي وراء "عرض الكل" ----
    cards = ""
    for i, m in enumerate(matches):
        card = match_card(m, lang, logos, show_league=False)
        if i >= 10:
            card = card.replace('class="match"', 'class="match hidden"', 1)
        cards += card
    more_m = ""
    if len(matches) > 10:
        more_m = (f'<button class="more">'
                  f'{t["show_all_matches"]} ({len(matches) - 10})</button>')
    matches_html = cards or f'<div class="empty">{t["empty_combo"]}</div>'

    # ---- تبويب الهدافين — نفس نمط أول 10 + عرض الكل ----
    sc = ""
    for i, s in enumerate(scorers, 1):
        pl = clean(s["player_ar"]) if lang == "ar" else ""
        pl = pl or clean(s["player"])
        tm = tname(s, lang, "team", "team_en")
        href = player_link(s["player"], BASE, depth)
        name_html = f'<a href="{href}">{pl}</a>' if href else pl
        hide = " hidden" if i > 10 else ""
        sc += (f'<li class="{hide.strip()}"><span class="num">{i}</span>'
               f'<span class="pname">{name_html}</span>'
               f'<span class="pteam">{tm}</span>'
               f'<span class="pgoals">{s["goals"]}</span></li>')
    more_s = ""
    if len(scorers) > 10:
        more_s = (f'<button class="more">'
                  f'{t["show_all_scorers"]} ({len(scorers) - 10})</button>')
    scorers_html = f'<ol>{sc}</ol>{more_s}' if sc else \
        f'<div class="empty">{t["empty_combo"]}</div>'

    # ---- تبويب "إحصائيات اللاعبين" — الهدافون + بطاقات لاعبين ----
    player_layer = player_stats_layer_html(conn, code, season, lang, t)
    player_stats_html = scorers_html
    if player_layer:
        player_stats_html += f'<hr class="divider">{player_layer}'

    # ---- منسدلة الموسم — من الملفات الموجودة فعلاً على القرص ----
    # ⚠️ خيار "الحالي" ثابت الوجهة والتسمية بـnewest_season دائماً؛
    #    "selected" هو الفرق الوحيد بين توليد الصفحة الحالية
    #    وتوليد أرشيف — season قد يساوي أو لا يساوي newest_season.
    cur_sel = ' selected' if season == newest_season else ''
    opts = (f'<option value="{code_l}.html"{cur_sel}>'
            f'{newest_season}-{newest_season + 1} · '
            f'{t["current_season"]}</option>')
    for s, fname in season_files(code):
        sel = ' selected' if s == season else ''
        opts += f'<option value="{fname}"{sel}>{s}-{s + 1}</option>'
    season_sel = (f'<select class="season-sel" '
                  f'onchange="location.href=this.value">{opts}</select>')

    team_stats_html = team_stats_tab_html(conn, code, season, table, logos,
                                          lang, t)

    tabs_html = (
        f'<div class="tabs cattabs">'
        f'<button class="tab active" data-cat="standings">'
        f'{t["tab_standings"]}</button>'
        f'<button class="tab" data-cat="matches">{t["tab_matches"]}</button>'
        f'<button class="tab" data-cat="player-stats">'
        f'{t["tab_player_stats"]}</button>'
        f'<button class="tab" data-cat="team-stats">'
        f'{t["tab_team_stats"]}</button>'
        f'</div>'
    )
    panels_html = (
        f'<section class="panel visible" data-cat="standings">'
        f'{standings_html}</section>'
        f'<section class="panel" data-cat="matches">'
        f'{matches_html}{more_m}</section>'
        f'<section class="panel" data-cat="player-stats">'
        f'{player_stats_html}</section>'
        f'<section class="panel" data-cat="team-stats">'
        f'{team_stats_html}</section>'
    )

    switch = (f'../en/leagues/{code_l}.html' if lang == "ar"
              else f'../../leagues/{code_l}.html')
    title = f'{league_name(code, lang)} — {t["site_title"]}'

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        + head_meta(league_name(code, lang), t["site_sub"],
                    "../" if lang == "ar" else "../../", lang,
                    (f"leagues/{code_l}.html" if season == newest_season
                     else f"leagues/{code_l}-{season}.html")
                    if lang == "ar" else
                    (f"en/leagues/{code_l}.html" if season == newest_season
                     else f"en/leagues/{code_l}-{season}.html"))
        + THEME_HEAD + STYLE + LOCAL_STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<span style="display:flex;gap:8px;align-items:center">'
        f'{back_button(t["back"])}</span></div>\n'
        f'<header><h1>{league_name(code, lang)}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'
        f'{season_sel}\n'
        f'{tabs_html}\n'
        f'{panels_html}\n'
        f'<footer><a href="../about.html" '
        f'style="color:var(--accent);text-decoration:none">{t["about"]}</a>'
        f'<br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + navbar(t, depth, "leagues", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT + BACK_SCRIPT + matchtime_script()
        + nav_script(t) + pwa_script(lang)
        + live_script(t, depth)
        + search_script(t, depth, lang)
        + TAB_SCRIPT +
        '</body>\n</html>'
    )

    # ⚠️ عمق 1: كل روابط clubs/matches كُتبت بلا "../" (زي match_card
    #    وصفوف الجدول أعلاه) — نزيحها هنا دفعة واحدة، وبنفس القدر
    #    للغتين لأن clubs/ و matches/ مرآتان تحت en/ (بعكس logos/).
    html = html.replace('href="clubs/', 'href="../clubs/')
    html = html.replace('href="matches/', 'href="../matches/')
    logo_prefix = "../" if lang == "ar" else "../../"
    html = html.replace('src="logos/', f'src="{logo_prefix}logos/')

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

    newest = {}
    for c in combos:
        code = c["league_code"]
        if code not in newest or c["season"] > newest[code]:
            newest[code] = c["season"]

    leagues = [c for c in LEAGUES if c in newest]

    os.makedirs(BASE / "en", exist_ok=True)
    os.makedirs(LEAGUES_DIR, exist_ok=True)
    os.makedirs(BASE / "en" / "leagues", exist_ok=True)

    # 1) صفحة الأعلام
    for lang in LANGS:
        html = flags_page(lang, leagues)
        path = (BASE / "leagues.html" if lang == "ar"
                else BASE / "en" / "leagues.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    # 2) صفحة كل دوري
    #    ⚠️ --all يبني كل المواسم بمرّتين: الأولى تكتب المحتوى،
    #    الثانية تُعيد التوليد بعد ما كل الملفات صارت موجودة على
    #    القرص — المنسدلة تُبنى من season_files() (فحص قرص فعلي)،
    #    فبمرة وحدة كانت أول صفحة تُكتب ترى إخوتها الأحدث فقط لا
    #    الأقدم. تكلفة إضافية بسيطة (30 صفحة) مقابل صحة مضمونة.
    written = []

    def build_pass():
        for code in leagues:
            all_seasons = sorted(
                {c["season"] for c in combos if c["league_code"] == code},
                reverse=True)
            build_seasons = all_seasons if ALL_SEASONS else [newest[code]]
            for season in build_seasons:
                for lang in LANGS:
                    html = league_page(conn, lang, code, season, logos,
                                       newest[code])
                    folder = (LEAGUES_DIR if lang == "ar"
                             else BASE / "en" / "leagues")
                    fname = (f"{code.lower()}.html"
                             if season == newest[code]
                             else f"{code.lower()}-{season}.html")
                    path = folder / fname
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(html)
                    written.append((code, season, lang, fname))

    build_pass()
    if ALL_SEASONS:
        build_pass()  # تصحيح المنسدلات بعد اكتمال القرص

    conn.close()

    print(f"\n{'=' * 55}")
    print("  تم: leagues.html + en/leagues.html")
    n_pages = len({(c, s, l) for c, s, l, _ in written})
    print(f"       + {n_pages} صفحة دوري/موسم")
    print(f"{'=' * 55}")
    if ALL_SEASONS:
        for code in leagues:
            seasons = sorted({s for c, s, l, f in written if c == code},
                             reverse=True)
            print(f"  {league_name(code, 'ar'):<18} "
                  f"{', '.join(str(s) for s in seasons)}")
    else:
        for code in leagues:
            print(f"  {league_name(code, 'ar'):<18} موسم {newest[code]}")
    print("""
  زر "الدوريات" بالشريط السفلي يشير لـleagues.html كما هو.
    """)


if __name__ == "__main__":
    main()
