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
import json
import collections
from datetime import datetime, timezone
from html import escape
from config import DB_FILE, TEAMS_FILE, BASE_DIR
from thumbs_util import thumb_src, logo_img
from live_view import LIVE_CSS, live_script
from match_row import ROW_CSS, match_row
from player_slug import slug as _pslug
from tiebreak import sort_table, STANDINGS_EXCLUDED
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name, off_label
from search_view import SEARCH_CSS
from live_view import LIVE_CSS, live_script
from navbar import (NAV_CSS, navbar, settings_button, settings_overlay,
                    nav_script, pwa_script, pwa_offbar, appbar)
import assets
from matchtime import matchtime_script
from tabs_view import TABS_CSS, NOSCRIPT, tabs_html
from swipe_view import TOUCH_CSS
from zones import ZONE_CSS, zone_list, row_class, data_attr as zone_attr, legend as zone_legend
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)

BASE = DB_FILE.parent


def _push_css():
    import push_ui
    return push_ui.CSS


CSS_TYPE = VARS + """
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
  .club-head img { width:64px; height:64px; object-fit:contain; flex:0 0 auto; }
  /* الاسم الطويل: سطران كحد أقصى ثم «…»؛ «متابعة»+الجرس (.hdract) لا ينكسران ولا ينزلان تحت الاسم (13 أكتوبر) */
  .club-head > div:not(.hdract) { min-width:0; flex:1 1 0; }
  .club-head h1 { font-size:24px; line-height:1.3; overflow-wrap:anywhere;
                  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  @media (max-width:480px) {
    .club-head { gap:10px; padding:14px; }
    .club-head img { width:48px; height:48px; }
    .club-head h1 { font-size:17px; }
    .hdract { gap:6px; }
    .fclubbtn { padding:0 12px; font-size:13px; }
  }
  .club-head .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  /* رأس النادي (13 أكتوبر): «متابعة» + جرس تنبيهات الأهداف جنباً لجنب بطرف الرأس (مكان واحد بدل صف التنبيهات القديم).
     الجرس مخفي حتى يكشفه السكربت (?push=1 / التطبيق المثبَّت / PUSH_PUBLIC)؛ رسالته القصيرة تظهر تحت الرأس عند الحاجة فقط. */
  .hdract { margin-inline-start:auto; flex:0 0 auto; display:flex; align-items:center; gap:8px; }
  .fclubbtn { flex:0 0 auto; min-height:44px; padding:0 16px;
              border-radius:22px; font:inherit; font-size:14px; font-weight:700; cursor:pointer;
              background:var(--accent); color:#fff; border:1px solid var(--accent); white-space:nowrap; }
  .fclubbtn.on { background:transparent; color:var(--muted); border-color:var(--line); }
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
  .match { background:var(--card); border-radius:10px; padding:12px 10px;
           margin-bottom:7px; display:grid;
           grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);
           align-items:center; gap:7px 7px; }
  .match.filt { display:none; }
  .side { display:flex; align-items:center; gap:8px;
          font-size:clamp(13px,3.7vw,14px); min-width:0; }
  .side.away { justify-content:flex-end; }
  a.side { text-decoration:none; color:var(--text); }
  a.side:hover span { color:var(--accent); }
  .side img { width:24px; height:24px; object-fit:contain; flex:0 0 24px; }
  /* أسماء طويلة: سطران كحد أقصى ثم «…»، والشعار ثابت (نفس قاعدة الرئيسية بـmake_site3) */
  .side span { min-width:0; overflow:hidden; line-height:1.25; overflow-wrap:break-word;
               display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
  .side.away span { text-align:end; }
  .score { font-size:17px; font-weight:700; padding:4px 11px;
           background:var(--deep); border-radius:6px; white-space:nowrap; }
  .score.pst { font-size:13px; padding:4px 8px; color:var(--muted); }
  .date { grid-column:1/-1; text-align:center; color:var(--muted);
          font-size:11px; margin-top:4px; }
  .date a { color:var(--muted); text-decoration:none; }
  .date a:hover { color:var(--accent); }
  .rw { border-inline-start:3px solid var(--green); }
  .rd { border-inline-start:3px solid var(--muted); }
  .rl { border-inline-start:3px solid var(--red); }
  .rn { border-inline-start:3px solid var(--accent); }
  /* (28 أكتوبر 2026، دفعة التصميم A بند 4 — FotMob) كل قائمة (آخر المباريات / القادمة) كتلة مدوّرة واحدة بخط 1px بين الصفوف بدل
     بطاقة لكل مباراة؛ شريط النتيجة الملوّن بالبداية يبقى لكل صف. نفس ارتفاع الصف وحشوه. */
  .mbox { background:var(--card); border-radius:12px; overflow:hidden; margin-bottom:8px; }
  .mbox .match { background:none; border-radius:0; margin:0; }
  .mbox .match:not(:first-child) { border-top:1px solid var(--line); }
  .mbox .match:hover { background:var(--card2); }
  ol { list-style:none; background:var(--card); border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid var(--line); font-size:14px; }
  ol li:last-child { border-bottom:none; }
  ol li.hidden { display:none; }
  .num { color:var(--muted); width:20px; }
  .pname { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .pname a { color:var(--text); text-decoration:none; }
  .pname a:hover { color:var(--accent); }
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
               display:flex; align-items:center; gap:7px; min-height:44px; }
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
          padding:10px 18px; cursor:pointer; min-height:44px;
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
  .match { --scw:84px; }
""" + TABS_CSS + TOUCH_CSS + ZONE_CSS + """
  /* ═══ صفحة النادي على نمط FotMob (29 أكتوبر 2026، دفعة 2 C1–C7) ═══ */
  /* C1: رأس بلا بطاقة — الشعار + الاسم + المدينة/البلد؛ مجموعة الجرس + «متابعة» كبسولة واحدة مدوّرة بطرف الشريط العلوي */
  .club-head { background:none; padding:4px 2px 0; margin-bottom:4px; }
  .fgrp { display:inline-flex; align-items:center; gap:2px; padding:3px; border:1px solid var(--line);
          border-radius:999px; background:var(--card); }
  .fgrp .pbwrap { display:inline-flex; }
  .fgrp .fgbell { width:38px; height:38px; border:none; background:none; color:var(--text); border-radius:50%; }
  .fgrp .fgbell[aria-pressed="true"] { background:var(--accent); color:#fff; }
  .fgrp .fclubbtn { min-height:38px; padding:0 16px; font-size:14px; border-radius:999px; }
  .fgrp .fclubbtn.on { background:var(--card2); color:var(--text); border-color:var(--card2); }
  /* C2: شريط التبويبات يتمرّر أفقياً، النشط عريض */
  .mtabs { margin-top:10px; }
  .mtab { flex:0 0 auto; padding:10px 12px; font-size:14px; }
  .mtab.on { font-weight:800; }
  .mp { padding-top:4px; }
  .card { background:var(--card); border-radius:12px; padding:12px; }
  h3.ct { font-size:14px; color:var(--text); font-weight:700; margin:18px 2px 8px; }
  .mp > h3.ct:first-child { margin-top:12px; }
  .lchip { display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); min-width:0;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .lchip img { width:16px; height:16px; object-fit:contain; flex:0 0 16px; }
  /* C3: المباراة القادمة */
  a.nxt { display:block; color:var(--text); text-decoration:none; }
  a.nxt:hover { background:var(--card2); }
  .nxh { display:flex; align-items:center; justify-content:space-between; gap:10px; font-size:13px; color:var(--muted); }
  .nxh .dl { color:var(--text); font-weight:700; }
  .nxb { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); align-items:center; gap:8px; margin-top:12px; }
  .nxt-t { display:flex; flex-direction:column; align-items:center; gap:6px; min-width:0; text-align:center; font-size:13px; }
  .nxt-t img { width:40px; height:40px; object-fit:contain; }
  .nxtime { font-size:22px; font-weight:800; font-variant-numeric:tabular-nums; }
  /* C3: فورمة الفريق — الأحدث يميناً بالاتجاهين */
  .frow { display:flex; direction:ltr; justify-content:space-between; gap:6px; }
  .fp { display:flex; flex-direction:column; align-items:center; gap:6px; text-decoration:none; min-width:0; flex:1 1 0; }
  .fsc { min-width:46px; text-align:center; padding:3px 6px; border-radius:6px; font-size:13px; font-weight:700; color:#fff;
         white-space:nowrap; font-variant-numeric:tabular-nums; }
  .fsc.w { background:#17803a; } .fsc.d { background:#6b7280; } .fsc.l { background:#c62828; }
  .fp img { width:22px; height:22px; object-fit:contain; }
  /* C3: الملعب */
  .stad { display:flex; align-items:center; gap:12px; }
  .stad .mic { width:22px; height:22px; color:var(--muted); flex:0 0 22px; }
  .stad .mic svg { width:22px; height:22px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
  .stad .sn { font-size:14px; font-weight:600; }
  .stad .sub { color:var(--muted); font-size:12px; }
  /* C4: قائمة مباريات واحدة متصلة */
  .mlist { background:var(--card); border-radius:12px; overflow:hidden; margin-top:12px; }
  .mli + .mli { border-top:1px solid var(--line); }
  .mlh { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 12px 0;
         font-size:12px; color:var(--muted); }
  .mlh .dl { font-weight:600; color:var(--text); }
  .mlist .match { background:none; border-radius:0; margin:0; }
  .mlist .match:hover { background:var(--card2); }
  .score.kt { background:none; font-size:15px; }
  /* C5/C6: منسدلة الموسم */
  .ssel { position:relative; margin:12px 0 10px; display:inline-block; max-width:100%; }
  .sselect { appearance:none; -webkit-appearance:none; background:var(--card); color:var(--text); border:1px solid var(--line);
             border-radius:999px; padding:0 40px 0 16px; min-height:40px; font:inherit; font-size:14px; font-weight:700;
             max-width:100%; cursor:pointer; }
  [dir="rtl"] .sselect { padding:0 16px 0 40px; }
  .ssel .cv { position:absolute; inset-inline-end:16px; top:50%; width:7px; height:7px; margin-top:-6px;
              border-inline-end:2px solid var(--muted); border-bottom:2px solid var(--muted); transform:rotate(45deg);
              pointer-events:none; }
  .spane[hidden] { display:none; }
  /* C5: الجدول (نفس جدول تبويب المباراة) */
  .lgt { width:100%; border-collapse:collapse; background:var(--card); border-radius:10px; overflow:hidden; table-layout:fixed; }
  .lgt th, .lgt td { padding:9px 2px; text-align:center; font-size:13px; }
  .lgt th { background:var(--card2); color:var(--muted); font-size:12px; }
  .lgt th.r { text-align:start; padding-inline-start:6px; }
  .lgt tr { border-bottom:1px solid var(--line); }
  .lgt tr:last-child { border-bottom:none; }
  .lgt .ps { width:26px; color:var(--muted); }
  .lgt td.gd { direction:ltr; unicode-bidi:isolate; }
  .lgt th:nth-child(n+3), .lgt td:nth-child(n+3) { width:32px; }
  .lgt td.tm { text-align:start; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .lgt td.tm img { width:20px; height:20px; object-fit:contain; vertical-align:middle; margin-inline-end:6px; }
  .lgt td.tm a { color:var(--text); text-decoration:none; vertical-align:middle; }
  .lgt .pt { font-weight:700; color:var(--accent); }
  .lgt tr.hl { background:rgba(47,129,247,.16); }
  .lgt tr.hl td.tm a { font-weight:700; }
  /* C6: الإحصائيات */
  .scard2 + .scard2 { margin-top:12px; }
  .sch { display:flex; align-items:center; justify-content:space-between; gap:10px; font-size:14px; font-weight:700; margin-bottom:6px; }
  .srk { font-size:12px; color:var(--muted); font-weight:400; }
  .srk b { color:var(--text); }
  .hat { width:100%; border-collapse:collapse; table-layout:fixed; }
  .hat th, .hat td { padding:8px 2px; text-align:center; font-size:13px; }
  .hat th { color:var(--muted); font-size:11px; font-weight:600; }
  .hat .r { text-align:start; width:76px; }
  .hat tr + tr td { border-top:1px solid var(--line); }
  .hat .ltr { direction:ltr; unicode-bidi:isolate; }
  .hat .pt { font-weight:700; color:var(--accent); }
  .gl { display:flex; justify-content:space-between; align-items:center; min-height:38px; font-size:14px; }
  .gl + .gl { border-top:1px solid var(--line); }
  .gl b { font-variant-numeric:tabular-nums; }
  /* C7: اللاعبون */
  .sqc { padding:2px 12px; }
  .sqr { display:flex; align-items:center; gap:12px; min-height:44px; font-size:14px; }
  .sqr + .sqr { border-top:1px solid var(--line); }
  .sqn { width:26px; text-align:center; color:var(--muted); font-variant-numeric:tabular-nums; flex:0 0 26px; }
  .sqp { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sqp a { color:var(--text); text-decoration:none; }
  .sqa { color:var(--muted); font-size:13px; white-space:nowrap; }
  .sqa small { font-size:11px; }
  .noday { text-align:center; color:var(--muted); padding:30px 16px; background:var(--card); border-radius:12px; font-size:14px; margin-top:12px; }
""" + _push_css() + ROW_CSS   # صف المباراة المشترك (دفعة C) — آخر شيء ليعلو .side/.match أعلاه

# ⚠️ STYLE الكامل (inline) لم يعد يُستعمل بالصفحات — راجع assets.py
STYLE = ("\n<style>" + CSS_TYPE + SEARCH_CSS + NAV_CSS + LIVE_CSS
         + "\n</style>")

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
                "id": int(tid),
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


def logo_url(t, lang, big=False):
    """
    الشعار — النسخة المصغّرة thumbs/ أولاً (thumbs_util)، ثم logo_local، ثم رابط المزوّد.
    المسار النسبي يعتمد على عمق الصفحة:
      clubs/x.html      → ../thumbs/
      en/clubs/x.html   → ../../thumbs/
    big=True: نسخة 128px لرأس الصفحة (يُعرض 64px).
    """
    up = "../" if lang == "ar" else "../../"
    th = thumb_src(t.get("id"), up, big) if t.get("id") else None
    if th:
        return th
    if t["logo_local"]:
        return up + t["logo_local"]
    return t["logo"] or ""


def logo_tag(t, lang, px, big=False, eager=False):
    """<img> بأبعاد ثابتة؛ eager لرأس الصفحة فقط، غيره lazy"""
    return logo_img(t.get("id"), logo_url(t, lang, big), "../" if lang == "ar" else "../../",
                    px, big=big, eager=eager)


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
               m.home_goals, m.away_goals, m.status
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


def player_link(player_en, team_id=None):
    from player_pages import resolve_slug
    s = resolve_slug(player_en, _pslug(player_en), team_id)    # صفحة المعرّف إن دُمج الاسم بها (لا رابط لـstub)
    if s not in _player_pages():
        return ""
    return f"../players/{s}.html"


def render_stats_lists(conn, tid, code, season, lang):
    """قوائم اللاعبين بالموسم (هدافون · صناعات · بطاقات) — كما كانت بتبويب «الإحصائيات» القديم"""
    t = T[lang]
    sec = SEC[lang]

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
            href = player_link(r["en"], tid)
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
    out = ""
    for rows, title in (
            (scorers_rows, t["club_scorers"]),
            (club_assists(conn, tid, code, season), sec["assists"]),
            (club_cards(conn, tid, code, season, "Yellow Card"), sec["yellow"]),
            (club_cards(conn, tid, code, season, "Red Card"), sec["red"])):
        blk = player_list(rows)
        if blk:
            out += f'<h3>{title}</h3>{blk}'
    return out


# ═══ صفحة النادي على نمط FotMob (29 أكتوبر 2026، دفعة 2 C1–C7) ═══
# تبويبات: نظرة عامة | المباريات | الترتيب | الإحصائيات | اللاعبون — شريط .mtabs ولوحات .mp (tabs_view.py) فيسحب بينها
# محرّك السحب المشترك (swipe_view.py، مجموعة .mtabs) بمتابعة الإصبع. كل البيانات من قاعدتنا — صفر طلبات API.

COUNTRY = {  # (عربي، إنجليزي) — نفس make_leagues.COUNTRY (سطر البلد تحت اسم النادي)
    "SAU": ("السعودية", "Saudi Arabia"), "EGY": ("مصر", "Egypt"), "UAE": ("الإمارات", "United Arab Emirates"),
    "QAT": ("قطر", "Qatar"), "JOR": ("الأردن", "Jordan"), "IRQ": ("العراق", "Iraq"), "MAR": ("المغرب", "Morocco"),
    "TUN": ("تونس", "Tunisia"), "ALG": ("الجزائر", "Algeria"), "KUW": ("الكويت", "Kuwait"),
}

CL = {
    "ar": {"ov": "نظرة عامة", "mt": "المباريات", "tb": "الترتيب", "st": "الإحصائيات", "sq": "اللاعبون",
           "next": "المباراة القادمة", "form": "فورمة الفريق", "stadium": "الملعب",
           "today": "اليوم", "tomorrow": "غداً", "yesterday": "أمس",
           "pr": "النقاط / المركز", "home": "على أرضه", "away": "خارج أرضه",
           "goals": "الأهداف", "scored": "سجّل", "conceded": "استقبل", "pens": "ركلات جزاء",
           "og": "عكسية لصالحه", "other": "أهداف أخرى", "cs": "شباك نظيفة", "fts": "لم يسجّل",
           "coach": "المدرب", "gk": "حراس المرمى", "df": "المدافعون", "mf": "لاعبو الوسط", "fw": "المهاجمون",
           "ot": "مراكز غير معروفة", "apps": "مشاركة", "season_sel": "الموسم", "pl": "لعب", "gfga": "له-عليه"},
    "en": {"ov": "Overview", "mt": "Matches", "tb": "Table", "st": "Stats", "sq": "Squad",
           "next": "Next match", "form": "Team form", "stadium": "Stadium",
           "today": "Today", "tomorrow": "Tomorrow", "yesterday": "Yesterday",
           "pr": "Points / Rank", "home": "Home", "away": "Away",
           "goals": "Goals", "scored": "Scored", "conceded": "Conceded", "pens": "Penalties",
           "og": "Own goals for", "other": "Other goals", "cs": "Clean sheets", "fts": "Failed to score",
           "coach": "Coach", "gk": "Goalkeepers", "df": "Defenders", "mf": "Midfielders", "fw": "Attackers",
           "ot": "Position unknown", "apps": "apps", "season_sel": "Season", "pl": "PL", "gfga": "GF-GA"},
}

_LG_SRC = None


def league_logo_src(code, up):
    """شعار الدوري — نفس make_matches.league_logo_src (المحلي ثم المزوّد ثم العلم)"""
    global _LG_SRC
    if _LG_SRC is None:
        from make_site3 import load_league_logos, FLAG
        logos, local = load_league_logos()
        _LG_SRC = {c: (local.get(c) or logos.get(c) or f"flags/{FLAG[c]}.svg") for c in FLAG}
    src = _LG_SRC.get(code, "")
    return src if src.startswith("http") else (up + src if src else "")


def league_chip(code, lang):
    up = "../" if lang == "ar" else "../../"
    src = league_logo_src(code, up)
    img = f'<img src="{src}" alt="" width="16" height="16" loading="lazy" decoding="async">' if src else ""
    return f'<span class="lchip">{img}<span>{league_name(code, lang)}</span></span>'


def season_label(code, season, lang):
    return f'{league_name(code, lang)} - {season}/{season + 1}'


def iso(d):
    """matches.date (UTC خام) → ISO بـZ، أو "" لو بلا وقت"""
    p = str(d).split()
    return f"{p[0]}T{p[1][:5]}:00Z" if len(p) > 1 else ""


def _blank(tid):
    return {"id": None, "short": str(tid), "name_en": str(tid), "name_ar": "", "logo": "", "logo_local": "", "city": "", "league": ""}


def next_match_card(cur_ms, teams, tid, lang):
    """أقرب مباراة قادمة بالموسم الحالي (بلا مؤجّلة/ملغاة). "" إن لم توجد."""
    t, s = T[lang], CL[lang]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    up = [m for m in cur_ms if m["home_goals"] is None and not off_label(m["status"], t, m["date"])
          and str(m["date"]) >= now[:10]]
    if not up:
        return ""
    m = up[0]
    h, a = teams.get(m["home_id"], _blank(m["home_id"])), teams.get(m["away_id"], _blank(m["away_id"]))
    k = iso(m["date"])
    when = (f'<span class="dl" data-kdl="{k}">{str(m["date"])[:10]}</span>' if k else str(m["date"])[:10])
    clock = (f'<span data-utc="{k}">{str(m["date"]).split()[1][:5]} UTC</span>' if k else "—")
    return (f'<h3 class="ct">{s["next"]}</h3>'
            f'<a class="nxt card" href="../matches/{m["match_id"]}.html">'
            f'<div class="nxh">{when}{league_chip(m["league_code"], lang)}</div>'
            f'<div class="nxb"><span class="nxt-t">{logo_tag(h, lang, 40)}<span>{tname(h, lang)}</span></span>'
            f'<span class="nxtime">{clock}</span>'
            f'<span class="nxt-t">{logo_tag(a, lang, 40)}<span>{tname(a, lang)}</span></span></div></a>')


def form_card(conn, tid, code, teams, lang):
    """آخر 5 نتائج بالدوري (كل المواسم): كبسولة النتيجة ملوّنة + شعار الخصم، الأحدث يميناً بالاتجاهين؛ النقر = المباراة"""
    rows = conn.execute("""
        SELECT match_id, date, home_id, away_id, home_goals, away_goals FROM matches
        WHERE league_code = ? AND (home_id = ? OR away_id = ?) AND home_goals IS NOT NULL
        ORDER BY date DESC LIMIT 5""", (code, tid, tid)).fetchall()
    if not rows:
        return ""
    out = ""
    for m in reversed(rows):   # الأقدم أولاً (يساراً) → الأحدث آخراً (يميناً): الحاوية direction:ltr
        mine = m["home_goals"] if m["home_id"] == tid else m["away_goals"]
        theirs = m["away_goals"] if m["home_id"] == tid else m["home_goals"]
        cls = "w" if mine > theirs else ("l" if mine < theirs else "d")
        opp = m["away_id"] if m["home_id"] == tid else m["home_id"]
        ot = teams.get(opp, _blank(opp))
        out += (f'<a class="fp" href="../matches/{m["match_id"]}.html" aria-label="{str(m["date"])[:10]}">'
                f'<span class="fsc {cls}">{m["home_goals"]}-{m["away_goals"]}</span>{logo_tag(ot, lang, 22)}</a>')
    return f'<h3 class="ct">{CL[lang]["form"]}</h3><div class="card fcard"><div class="frow">{out}</div></div>'


PIN_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11z"/>'
           '<circle cx="12" cy="10" r="2.3"/></svg>')


def stadium_card(conn, tid, lang):
    """الملعب من matches.venue_name/venue_city لمباريات النادي على أرضه فقط (الأكثر تكراراً، الأحدث عند التعادل). "" إن لم يوجد."""
    try:
        r = conn.execute("""
            SELECT venue_name, venue_city, COUNT(*) n, MAX(date) d FROM matches
            WHERE home_id = ? AND venue_name IS NOT NULL AND TRIM(venue_name) != ''
            GROUP BY venue_name, venue_city ORDER BY n DESC, d DESC LIMIT 1""", (tid,)).fetchone()
    except sqlite3.OperationalError:   # الأعمدة غير موجودة (قبل ترحيل match_venue)
        return ""
    if not r:
        return ""
    city = clean(r["venue_city"])
    return (f'<h3 class="ct">{CL[lang]["stadium"]}</h3><div class="card stad"><span class="mic">{PIN_SVG}</span>'
            f'<div><div class="sn">{escape(clean(r["venue_name"]))}</div>'
            + (f'<div class="sub">{escape(city)}</div>' if city else "") + '</div></div>')


def matches_list(cur_ms, teams, tid, lang):
    """قائمة واحدة متصلة بترتيب التاريخ (المنتهية والقادمة معاً). كل عنصر: سطر التاريخ + شارة الدوري ثم صف المباراة المشترك.
    data-ko لكل عنصر — page_script يمرّر الصفحة لأول مباراة لم تبدأ عند فتح التبويب."""
    t = T[lang]
    out = ""
    for m in cur_ms:
        h, a = m["home_id"], m["away_id"]
        hg, ag = m["home_goals"], m["away_goals"]
        ht, at = teams.get(h, _blank(h)), teams.get(a, _blank(a))
        off = off_label(m["status"], t, m["date"])
        k = iso(m["date"])
        if hg is None or ag is None:
            cls = "rn"
            if off:
                score = f'<div class="score pst">{off}</div>'
            elif k:
                score = f'<div class="score kt"><span data-utc="{k}">{str(m["date"]).split()[1][:5]} UTC</span></div>'
            else:
                score = '<div class="score">—</div>'
        else:
            mine, theirs = (hg, ag) if h == tid else (ag, hg)
            cls = "rw" if mine > theirs else ("rd" if mine == theirs else "rl")
            score = f'<div class="score">{hg} - {ag}</div>'
        when = (f'<span class="dl" data-kdl="{k}">{str(m["date"])[:10]}</span>' if k else str(m["date"])[:10])
        ko = k or (str(m["date"])[:10] + "T23:59:00Z")
        up = ' data-up="1"' if (hg is None and not off) else ""
        out += (f'<div class="mli" data-ko="{ko}"{up}><div class="mlh">{when}{league_chip(m["league_code"], lang)}</div>'
                + match_row(m["match_id"], f'../matches/{m["match_id"]}.html',
                            (tname(ht, lang), logo_tag(ht, lang, 24), f"{h}.html"),
                            (tname(at, lang), logo_tag(at, lang, 24), f"{a}.html"),
                            score, cls=f"match {cls}", attrs=' data-m="1"')
                + '</div>')
    return f'<div class="mlist">{out}</div>' if out else ""


def table_block(conn, tid, teams, code, season, lang):
    """جدول الدوري للموسم: النادي مظلَّل، أشرطة المناطق بالبداية ومفتاحها تحته (zones.py، مكدَّس كـB2)"""
    t = T[lang]
    rows = standings(conn, code, season)
    if not rows:
        return ""
    n = len(rows)
    zl = zone_list(conn, code, season)
    body = ""
    for i, r in enumerate(rows, 1):
        rt = teams.get(r["team_id"], _blank(r["team_id"]))
        cls = " ".join(x for x in ("hl" if r["team_id"] == tid else "",
                                   row_class(zl, i) if zl else "") if x)
        attr = f' class="{cls}"' if cls else ""
        body += (f'<tr data-t="{r["team_id"]}"{attr}><td class="ps">{i}</td>'
                 f'<td class="tm">{logo_tag(rt, lang, 20)}<a href="{r["team_id"]}.html">{tname(rt, lang)}</a></td>'
                 f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td><td>{r["losses"]}</td>'
                 f'<td class="gd">{r["diff"]:+d}</td><td class="pt">{r["points"]}</td></tr>')
    return (f'<table class="lgt"{zone_attr(zl, n)}><tr><th class="ps">{t["pos"]}</th><th class="r">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th><th>{t["lost"]}</th>'
            f'<th>{t["gd"]}</th><th>{t["points"]}</th></tr>{body}</table>' + zone_legend(zl, lang, n))


def stats_block(conn, tid, code, season, lang):
    """بطاقة «النقاط / المركز» (على أرضه / خارج أرضه) وبطاقة «الأهداف» — من مبارياتنا وجدول goals فقط"""
    t, s = T[lang], CL[lang]
    excl = STANDINGS_EXCLUDED
    ms = [m for m in conn.execute("""
        SELECT match_id, home_id, away_id, home_goals, away_goals FROM matches
        WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL AND (home_id = ? OR away_id = ?)""",
                                  (code, season, tid, tid)) if m["match_id"] not in excl]
    if not ms:
        return ""
    agg = {"h": [0] * 6, "a": [0] * 6}   # لعب ف ت خ له عليه
    cs = fts = 0
    for m in ms:
        side = "h" if m["home_id"] == tid else "a"
        gf, ga = (m["home_goals"], m["away_goals"]) if side == "h" else (m["away_goals"], m["home_goals"])
        r = agg[side]
        r[0] += 1
        r[1 if gf > ga else (2 if gf == ga else 3)] += 1
        r[4] += gf
        r[5] += ga
        cs += ga == 0
        fts += gf == 0
    table = standings(conn, code, season)
    rank = next((i for i, r in enumerate(table, 1) if r["team_id"] == tid), "—")
    pts = sum(3 * agg[k][1] + agg[k][2] for k in agg)
    rows = ""
    for k in ("h", "a"):
        pl, w, d, l, gf, ga = agg[k]
        rows += (f'<tr><td class="r">{s["home" if k == "h" else "away"]}</td><td>{pl}</td><td>{w}</td><td>{d}</td><td>{l}</td>'
                 f'<td class="ltr">{gf}-{ga}</td><td class="ltr">{gf - ga:+d}</td><td class="pt">{3 * w + d}</td></tr>')
    pr = (f'<div class="card scard2"><div class="sch"><span>{s["pr"]}</span>'
          f'<span class="srk">{t["rank"]} <b>{rank}</b> · {t["points"]} <b>{pts}</b></span></div>'
          f'<table class="hat"><tr><th class="r"></th><th>{s["pl"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
          f'<th>{t["lost"]}</th><th>{s["gfga"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>{rows}</table></div>')
    scored = agg["h"][4] + agg["a"][4]
    conceded = agg["h"][5] + agg["a"][5]
    ids = [m["match_id"] for m in ms]
    q = ",".join("?" * len(ids))
    det = dict(conn.execute(f"SELECT detail, COUNT(*) FROM goals WHERE team_id = ? AND match_id IN ({q}) GROUP BY detail",
                            (tid, *ids)).fetchall())
    lines = [(s["scored"], scored), (s["conceded"], conceded)]
    # التفصيل فقط إن غطّى جدول goals كل أهداف النادي بالموسم (الأردني/العراقي/الكويتي قد ينقصها هدّافون) — لا أرقام جزئية
    if sum(det.values()) == scored and scored:
        lines += [(s["pens"], det.get("Penalty", 0)), (s["og"], det.get("Own Goal", 0)),
                  (s["other"], det.get("Normal Goal", 0))]
    lines += [(s["cs"], cs), (s["fts"], fts)]
    gl = "".join(f'<div class="gl"><span>{k}</span><b>{v}</b></div>' for k, v in lines)
    return pr + f'<div class="card scard2"><div class="sch"><span>{s["goals"]}</span></div>{gl}</div>'


POS_GROUPS = (("G", "gk"), ("D", "df"), ("M", "mf"), ("F", "fw"), ("", "ot"))
_INFO_POS = {"Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Attacker": "F"}
_PID_SLUG = None


def _pid_slug():
    """{player_id: slug} لصفحات اللاعبين ذات المعرّف (player_pages.get_plan) — الصفحة يجب أن توجد فعلاً كملف"""
    global _PID_SLUG
    if _PID_SLUG is None:
        from player_pages import get_plan
        _PID_SLUG = {pg["pid"]: pg["slug"] for pg in get_plan()["pages"] if pg.get("pid")}
    return _PID_SLUG


def squad_block(conn, tid, code, season, lang):
    """اللاعبون من تشكيلاتنا فقط (أساسيون + بدلاء) بالموسم الحالي، مجمَّعين بمركزهم الأكثر تكراراً. "" = بلا تشكيلات (التبويب يُخفى)."""
    s = CL[lang]
    rows = conn.execute("""
        SELECT lp.player_id, lp.player_en, lp.player_ar, lp.number, lp.pos, m.date, m.match_id
        FROM lineup_players lp JOIN matches m ON m.match_id = lp.match_id
        WHERE lp.team_id = ? AND m.league_code = ? AND m.season = ?
        ORDER BY m.date""", (tid, code, season)).fetchall()
    if not rows:
        return ""
    pl = {}
    for r in rows:
        # معرّف المزوّد > 0؛ بلا معرّف تحمل التشكيلة معرّفاً سالباً مؤقتاً لكل مباراة (-<مباراة><رقم>) — يُجمَّع بالاسم
        pid = r["player_id"] if (r["player_id"] or 0) > 0 else 0
        key = pid or ("n", clean(r["player_en"]))
        p = pl.setdefault(key, {"pid": pid, "en": "", "ar": "", "num": None, "apps": set(), "pc": collections.Counter()})
        p["apps"].add(r["match_id"])
        if r["pos"] in ("G", "D", "M", "F"):
            p["pc"][r["pos"]] += 1
        if clean(r["player_en"]):
            p["en"] = clean(r["player_en"])
        if clean(r["player_ar"]):
            p["ar"] = clean(r["player_ar"])
        if r["number"] not in (None, ""):
            p["num"] = r["number"]   # الأحدث يغلب (الترتيب بالتاريخ)
    # المركز: الأكثر تكراراً بكل التشكيلات (كل المواسم)، ثم player_stats، ثم player_info — وإلا «غير معروف»
    pids = [p["pid"] for p in pl.values() if p["pid"]]
    pos = {}
    if pids:
        q = ",".join("?" * len(pids))
        for src in (f"SELECT player_id, pos, COUNT(*) FROM lineup_players WHERE player_id IN ({q}) AND pos IN ('G','D','M','F') GROUP BY 1, 2",
                    f"SELECT player_id, pos, COUNT(*) FROM player_stats WHERE player_id IN ({q}) AND pos IN ('G','D','M','F') GROUP BY 1, 2"):
            best = {}
            for pid, ps, n in conn.execute(src, pids):
                if pid not in pos and n > best.get(pid, ("", 0))[1]:
                    best[pid] = (ps, n)
            for pid, (ps, _) in best.items():
                pos.setdefault(pid, ps)
        try:
            for pid, ps in conn.execute(f"SELECT player_id, position FROM player_info WHERE player_id IN ({q})", pids):
                if pid not in pos and _INFO_POS.get(ps):
                    pos[pid] = _INFO_POS[ps]
        except sqlite3.OperationalError:
            pass
    coach = conn.execute("""
        SELECT l.coach_en, l.coach_ar FROM lineups l JOIN matches m ON m.match_id = l.match_id
        WHERE l.team_id = ? AND m.league_code = ? AND m.season = ? AND COALESCE(l.coach_en, '') != ''
        ORDER BY m.date DESC LIMIT 1""", (tid, code, season)).fetchone()
    pages = _player_pages()
    out = ""
    if coach:
        cn = (clean(coach["coach_ar"]) if lang == "ar" else "") or clean(coach["coach_en"])
        out += (f'<h3 class="ct">{s["coach"]}</h3><div class="card sqc"><div class="sqr"><span class="sqn"></span>'
                f'<span class="sqp">{escape(cn)}</span></div></div>')
    for p in pl.values():   # بلا معرّف أو بلا مركز عام: مركزه الأكثر تكراراً بتشكيلات الموسم نفسها
        p["pos"] = pos.get(p["pid"]) or (p["pc"].most_common(1)[0][0] if p["pc"] else "")
    for code_p, key in POS_GROUPS:
        grp = [p for p in pl.values() if p["pos"] == code_p]
        if not grp:
            continue
        grp.sort(key=lambda p: (-len(p["apps"]), p["en"]))
        li = ""
        for p in grp:
            name = (p["ar"] if lang == "ar" else "") or p["en"]
            slug = _pid_slug().get(p["pid"]) if p["pid"] else None
            # ../players/ من clubs/ = /players/، ومن en/clubs/ = /en/players/ — نفس الرابط النسبي باللغتين (كـplayer_link)
            href = f"../players/{slug}.html" if slug and slug in pages else player_link(p["en"], tid)
            nm = f'<a href="{href}">{escape(name)}</a>' if href else escape(name)
            li += (f'<div class="sqr"><span class="sqn">{p["num"] if p["num"] is not None else ""}</span>'
                   f'<span class="sqp">{nm}</span><span class="sqa">{len(p["apps"])} <small>{s["apps"]}</small></span></div>')
        out += f'<h3 class="ct">{s[key]}</h3><div class="card sqc">{li}</div>'
    return out


def season_select(opts, cur, lang):
    """منسدلة الموسم («<الدوري> - 2026/2027» + سهم) أعلى تبويبَي الترتيب والإحصائيات — المنسدلتان متزامنتان (page_script)"""
    o = "".join(f'<option value="{k}"{" selected" if k == cur else ""}>{lab}</option>' for k, lab in opts)
    return (f'<div class="ssel"><select class="sselect" aria-label="{CL[lang]["season_sel"]}">{o}</select>'
            f'<span class="cv" aria-hidden="true"></span></div>')


PUSH_WORKER = "https://saffara-live.abujaishamr.workers.dev"

# ✅ **التنبيهات عامة (13 أكتوبر 2026، قرار عمرو الصريح):** PUSH_PUBLIC = True → الجرس يظهر للجميع بلا ?push=1، وزوار iPhone بلا تثبيت يرون تلميح
#    «أضف الموقع للشاشة الرئيسية». هذا الثابت هو **البوّابة الوحيدة** بجهة الموقع (يقرؤه push_ui.py لكل الصفحات: النادي والمباراة والدوري والإشعارات)؛
#    للـworker مفتاح GOAL_PUSH فقط. ?push=1 والتطبيق المثبَّت يبقيان يفتحان الجرس لو أُعيد الثابت إلى False (ثم make_assets.py + إعادة بناء الصفحات).
#    أنواع الاشتراك الافتراضية لم تتغيّر (115 للجديد؛ القديم أهداف فقط).
PUSH_PUBLIC = True


def push_bell_html(tid, lang):
    """جرس تنبيهات هذا النادي + رابط «تعديل» تحته بجانب «متابعة» برأس النادي (مخفيان حتى يكشفهما المحرّك المشترك push_ui.py)."""
    import push_ui
    return push_ui.bell_html("t", tid, lang)


def push_msg_html():
    import push_ui
    return push_ui.msg_html()


def push_script(lang):
    """المحرّك المشترك (window.FBPush: أنواع التنبيه، ورقة التعديل، المزامنة) + ربط جرس هذا النادي. الحالة محلية: fbPushTeams (القديم نفسه)
    وfbPushTypes؛ المتابعة (fbClubs) منفصلة تماماً ولا تشترك بالتنبيهات. تفاصيل المحرّك بـpush_ui.py."""
    import push_ui
    return ("<script>" + push_ui.engine_body(lang) + "\n"
            "(function(){var b=document.getElementById('pushbtn');if(!b||!window.FBPush)return;"
            "window.FBPush.bind(b,null,document.getElementById('pushmsg'),"
            "{fallbackTid:parseInt(b.getAttribute('data-id'),10),toast:true});})();</script>")


def follow_club_script():
    """
    زر «متابعة النادي» (12 أكتوبر) — يقرأ/يكتب fbClubs عبر FBPrefs (نفس مفتاح صفحة المتابَعة). متابعة نادٍ من دوري غير مختار بـfbLeagues
    (لو القائمة غير فارغة) تضيف دوريه (كورقة «+» بصفحة المتابَعة) كي لا يزيله cleanClubs، وأول متابعة تعلّم fbSetup. النص/التسميتان بسمات
    الزر (ملف JS مشترك بين كل الأندية واللغتين). يتطلب prefs_script() قبله بنفس الحزمة (make_assets.py).
    """
    return """<script>
(function(){
  var b=document.getElementById('fclubbtn'),FB=window.FBPrefs;
  if(!b||!FB)return;
  var id=+b.getAttribute('data-tid'),lg=b.getAttribute('data-lg'),
      F=b.getAttribute('data-f'),U=b.getAttribute('data-u');
  function paint(){
    var on=FB.getClubs().indexOf(id)>=0;
    b.classList.toggle('on',on);
    b.setAttribute('aria-pressed',on?'true':'false');
    b.textContent=on?U:F;   // (29 أكتوبر 2026، C1) كبسولة نصية «متابعة/متابَع» داخل مجموعة الجرس
  }
  b.addEventListener('click',function(){
    var C=FB.getClubs(),i=C.indexOf(id);
    if(i>=0)C.splice(i,1);
    else{
      C.push(id);
      // (27 أكتوبر 2026) لا يُضاف دوري النادي لـfbLeagues بعد الآن: متابعة الدوري صريحة بزرّها (cleanClubs الذي احتاجها لا يُستدعى)
      if(FB.markSetupDone)FB.markSetupDone();
    }
    FB.setClubs(C);
    paint();
  });
  window.addEventListener('storage',paint);
  paint();
})();
</script>"""


def page_script(t, lang="ar"):
    """الـJS: منسدلتا الموسم المتزامنتان، تسميات التاريخ، التمرير لأول مباراة قادمة، وأزرار «عرض المزيد» بقوائم اللاعبين"""
    s = CL[lang]
    cfg = json.dumps({"t": s["today"], "m": s["tomorrow"], "y": s["yesterday"], "more": SEC[lang]["more"]}, ensure_ascii=False)
    return """<script>
(function(){
  var C=__CFG__, D=document;
  // (1) منسدلتا الموسم (الترتيب + الإحصائيات) متزامنتان: نفس القيمة تُظهر لوحة الموسم بالتبويبين
  var sels=D.querySelectorAll('.sselect');
  function pick(k){
    sels.forEach(function(x){if(x.value!==k)x.value=k;});
    D.querySelectorAll('.spane').forEach(function(p){p.hidden=p.getAttribute('data-k')!==k;});
  }
  sels.forEach(function(x){x.addEventListener('change',function(){pick(x.value);});});
  // (2) تسمية التاريخ بيوم الزائر: اليوم/غداً/أمس، وإلا «الخميس 30 أكتوبر» بلغة الصفحة
  var ar=(D.documentElement.lang||'').indexOf('ar')===0, F;
  try{F=new Intl.DateTimeFormat(ar?'ar-u-nu-latn':'en-GB',{weekday:'short',day:'numeric',month:'short'});}catch(e){}
  D.querySelectorAll('[data-kdl]').forEach(function(el){
    var d=new Date(el.getAttribute('data-kdl')); if(isNaN(d.getTime())||!F)return;
    var n=new Date(), a=Date.UTC(d.getFullYear(),d.getMonth(),d.getDate()), b=Date.UTC(n.getFullYear(),n.getMonth(),n.getDate());
    var df=Math.round((a-b)/864e5);
    el.textContent=df===0?C.t:df===1?C.m:df===-1?C.y:F.format(d);
  });
  // (3) تبويب المباريات: قائمة واحدة، وأول فتح يمرّر الصفحة لأول مباراة لم تبدأ (المنتهية فوقها بالتمرير للأعلى)
  var done=false;
  function toNext(){
    if(done)return; var p=D.querySelector('.mp[data-tab="mt"]'); if(!p||!p.classList.contains('on'))return;
    done=true; var now=Date.now(), hit=null;
    p.querySelectorAll('.mli[data-up]').forEach(function(el){
      if(!hit&&Date.parse(el.getAttribute('data-ko'))>now-2*3600000)hit=el;
    });
    if(!hit)return;
    var bar=D.querySelector('.mtabs'), off=bar?bar.getBoundingClientRect().height+8:8;
    window.scrollTo(0,Math.max(0,hit.getBoundingClientRect().top+window.pageYOffset-off));
  }
  D.querySelectorAll('.mtab[data-tab="mt"]').forEach(function(b){b.addEventListener('click',function(){setTimeout(toNext,0);});});
  toNext();
  // (4) «عرض المزيد»: يكشف خمساً بكل ضغطة ثم يختفي (قوائم الهدافين/الصناعات/البطاقات)
  D.querySelectorAll('.more.step').forEach(function(b){
    b.addEventListener('click',function(){
      var box=this.previousElementSibling, hid=box.querySelectorAll('.hidden');
      for(var i=0;i<5&&i<hid.length;i++)hid[i].classList.remove('hidden');
      var left=box.querySelectorAll('.hidden').length;
      if(left===0)this.style.display='none'; else this.textContent=C.more+' ('+left+')';
    });
  });
})();
</script>""".replace("__CFG__", cfg)


def follow_group(tid, team, lang):
    """C1: مجموعة واحدة مدوّرة بطرف الشريط العلوي — الجرس + كبسولة «متابعة/متابَع» (بدل الزر الكبير + الجرس + «تعديل»)"""
    import push_ui
    t = T[lang]
    return (f'<div class="fgrp">'
            + push_ui.bell_html("t", tid, lang, bell_class="bellbtn fgbell", edit=False,
                              label=escape(tname(team, lang), quote=True)) +
            f'<button class="fclubbtn" id="fclubbtn" type="button" aria-pressed="false" '
            f'data-tid="{tid}" data-lg="{team["league"]}" data-f="{t["f_follow"]}" data-u="{t["f_followed"]}">'
            f'{t["f_follow"]}</button></div>')


def build_page(conn, tid, teams, lang):
    """صفحة نادٍ واحدة بلغة واحدة — None لو ما في محتوى"""
    t, s = T[lang], CL[lang]
    team = teams[tid]
    seasons = [(r["league_code"], r["season"]) for r in club_seasons(conn, tid)]
    if not seasons:
        return None
    code, season = seasons[0]   # الموسم الحالي = الأحدث (club_seasons مرتّبة تنازلياً)
    cur_ms = conn.execute("""
        SELECT match_id, league_code, date, home_id, away_id, home_goals, away_goals, status FROM matches
        WHERE season = ? AND (home_id = ? OR away_id = ?) ORDER BY date, match_id""", (season, tid, tid)).fetchall()

    ov = next_match_card(cur_ms, teams, tid, lang) + form_card(conn, tid, code, teams, lang) + stadium_card(conn, tid, lang)
    mt = matches_list(cur_ms, teams, tid, lang)

    opts, tb_panes, st_panes = [], "", ""
    cur_key = f"{code}_{season}"
    for c, ss in seasons:
        k = f"{c}_{ss}"
        tbl = table_block(conn, tid, teams, c, ss, lang)
        st = stats_block(conn, tid, c, ss, lang) + render_stats_lists(conn, tid, c, ss, lang)
        if not tbl and not st:
            continue
        opts.append((k, season_label(c, ss, lang)))
        hid = "" if k == cur_key else " hidden"
        tb_panes += f'<div class="spane" data-k="{k}"{hid}>{tbl}</div>'
        st_panes += f'<div class="spane" data-k="{k}"{hid}>{st}</div>'
    if opts and cur_key not in [k for k, _ in opts]:   # الموسم الحالي بلا مباريات منتهية بعد: أول موسم بالقائمة ظاهراً
        cur_key = opts[0][0]
        tb_panes = tb_panes.replace(f'data-k="{cur_key}" hidden', f'data-k="{cur_key}"', 1)
        st_panes = st_panes.replace(f'data-k="{cur_key}" hidden', f'data-k="{cur_key}"', 1)
    tb = (season_select(opts, cur_key, lang) + tb_panes) if opts else ""
    stt = (season_select(opts, cur_key, lang) + st_panes) if opts else ""
    sq = squad_block(conn, tid, code, season, lang)   # C2: تبويب اللاعبين يُخفى فقط إن لم تكن للنادي تشكيلات بالموسم الحالي

    if not (ov or mt or tb or stt or sq):
        return None
    tabs = tabs_html([("ov", ov or f'<div class="noday">{t["no_results"]}</div>'), ("mt", mt), ("tb", tb),
                      ("st", stt), ("sq", sq)],
                     {"ov": s["ov"], "mt": s["mt"], "tb": s["tb"], "st": s["st"], "sq": s["sq"]}, "ov")

    country = COUNTRY.get(team["league"] or code, ("", ""))[0 if lang == "ar" else 1]
    sub = " · ".join(x for x in (team["city"], country) if x)
    switch = (f'../en/clubs/{tid}.html' if lang == "ar" else f'../../clubs/{tid}.html')

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{tname(team, lang, full=True)} — {t["site_title"]}</title>\n'
        + head_meta(tname(team, lang, full=True), t["site_sub"],
                    "../" if lang == "ar" else "../../", lang,
                    f"clubs/{tid}.html" if lang == "ar"
                    else f"en/clubs/{tid}.html")
        + THEME_HEAD + assets.css_links("club") + NOSCRIPT +
        '</head>\n<body>\n<div class="wrap">\n'
        # C1: الرجوع بجهة، ومجموعة الجرس + «متابعة» بالجهة الأخرى (لا منسدلة موسم بالأعلى)
        + appbar(t, lang, switch, back=True, extra=follow_group(tid, team, lang))
        + push_msg_html() +
        f'<div class="club-head">'
        f'{logo_tag(team, lang, 64, big=True, eager=True)}'
        f'<div><h1>{tname(team, lang, full=True)}</h1>'
        + (f'<div class="sub">{escape(sub)}</div>' if sub else '') +
        f'</div></div>\n'
        f'{tabs}\n'
        '</div>\n'
        # ⚠️ **العمق يتبع اللغة:** الصفحة العربية بـ`matches/`
        #    (عمق 1) والإنجليزية بـ`en/matches/` (عمق 2).
        + navbar(t, 1 if lang == "ar" else 2, "", lang)
        + pwa_offbar(lang)
        + assets.script_tags("club", lang) +
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
