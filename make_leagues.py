#!/usr/bin/env python3
"""
صفحة الدوريات — بلغتين
=========================
بيولّد نسختين:
    leagues.html       → العربي (RTL)
    en/leagues.html    → الإنجليزي (LTR)

بنية الصفحة:
    1. بطاقات الدوريات — المتصدر ورابط لجدوله
    2. تبويبات الموسم/الدوري + الجدول + النتائج + الهدافون

⚠️ **هذا المحتوى كان في الرئيسية** ونُقل هنا (21 أغسطس) بعد
   قرار جعل الرئيسية للمباريات القادمة فقط. زر "الدوريات" في
   الشريط السفلي كان مرساة `#tables` داخل الرئيسية، وصار
   يشير لهذه الصفحة.

⚠️ **يستورد الدوال المشتركة من `make_site3.py`** لا ينسخها —
   أي تعديل على منطق الجدول أو بطاقة المباراة يبقى بمكان واحد.

⚠️ الروابط الداخلية (`clubs/x.html`) نسبية من الجذر — تعمل
   من `leagues.html` ومن `en/leagues.html` بنفس الشكل تماماً
   كما تعمل من `index.html`.

صفر طلبات API.

التشغيل:
    python make_leagues.py
"""

import sqlite3
import os

from config import DB_FILE, LEAGUES
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from search_view import (search_box, search_script, search_overlay)
from navbar import navbar, settings_overlay, nav_script, pwa_script
from theme import THEME_HEAD, THEME_SCRIPT, head_meta
from live_view import live_script

# الدوال والأنماط المشتركة — مصدر واحد لا نسخة
from make_site3 import (STYLE, SCRIPT, load_overrides, available,
                        tname, get_table, get_matches, get_scorers,
                        render_panel)

BASE = DB_FILE.parent


def build(conn, lang, combos, seasons, leagues, logos):
    """صفحة الدوريات كاملة بلغة واحدة"""
    t = T[lang]

    # ---- 1. بطاقات الدوريات ----
    newest = {}
    for c in combos:
        code = c["league_code"]
        if code not in newest:
            newest[code] = c["season"]

    lcards = ""
    for code in leagues:
        season = newest.get(code)
        if season is None:
            continue
        tbl = get_table(conn, code, season)
        lead = ""
        if tbl:
            r = tbl[0]
            lg_logo = logos.get(str(r["team_id"]), r["logo"])
            lead = (f'<div class="lead">'
                    f'<img src="{lg_logo}" alt="">'
                    f'<span>{tname(r, lang)}</span>'
                    f'<span class="pts">{r["points"]}</span></div>')
        lcards += (
            f'<button class="lcard jump" data-s="{season}" data-l="{code}">'
            f'<div class="ln">{league_name(code, lang)}</div>'
            f'<div class="ls">{t["season"]} {season}-{season+1}</div>'
            f'{lead}</button>'
        )

    hero_lg = ""
    if lcards:
        hero_lg = (f'<h2 class="hero">{t["leagues"]}</h2>'
                   f'<div class="lgrid">{lcards}</div>')

    # ---- 2. الجداول التفصيلية ----
    panels = ""
    for c in combos:
        table = get_table(conn, c["league_code"], c["season"])
        matches = get_matches(conn, c["league_code"], c["season"])
        scorers = get_scorers(conn, c["league_code"], c["season"])
        if table or matches:
            panels += render_panel(c["league_code"], c["season"],
                                   table, matches, scorers, logos, lang)

    season_tabs = "".join(
        f'<button class="tab tab-season" data-season="{s}">'
        f'{s}-{s+1}</button>' for s in seasons)

    league_tabs = "".join(
        f'<button class="tab tab-league" data-league="{c}">'
        f'{league_name(c, lang)}</button>' for c in leagues)

    switch = ("en/leagues.html" if lang == "ar" else "../leagues.html")
    depth = 0 if lang == "ar" else 1
    title = f'{t["leagues"]} — {t["site_title"]}'

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        + head_meta(title, t["site_sub"],
                    "" if lang == "ar" else "../", lang)
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<header><h1>{t["leagues"]}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'
        f'{search_box(t, big=True)}\n'
        f'{hero_lg}\n'
        '<hr class="divider" id="tables">\n'
        f'<div class="tabs seasons">{season_tabs}</div>\n'
        f'<div class="tabs">{league_tabs}</div>\n'
        f'{panels}\n'
        f'<div id="empty">{t["empty_combo"]}</div>\n'
        f'<footer><a href="about.html" '
        f'style="color:var(--accent);text-decoration:none">{t["about"]}</a>'
        f'<br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + navbar(t, depth, "leagues", lang)
        + settings_overlay(t, switch, lang)
        + SCRIPT + THEME_SCRIPT
        + nav_script(t) + pwa_script(lang)
        + live_script(t, depth)
        + search_script(t, depth, lang) +
        '</body>\n</html>'
    )

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
        path = (BASE / "leagues.html" if lang == "ar"
                else BASE / "en" / "leagues.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    conn.close()

    print(f"\n{'=' * 55}")
    print("  تم: leagues.html  +  en/leagues.html")
    print(f"{'=' * 55}")
    for c in combos:
        print(f"  {league_name(c['league_code'], 'ar'):<18} "
              f"موسم {c['season']}   {c['n']} ماتش")
    print("""
  زر "الدوريات" بالشريط السفلي يشير لهذه الصفحة.
    """)


if __name__ == "__main__":
    main()
