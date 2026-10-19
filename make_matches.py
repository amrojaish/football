#!/usr/bin/env python3
"""
توليد صفحة لكل مباراة — بلغتين
==================================
بيولّد نسختين لكل مباراة:
    matches/1538111.html       → العربي (RTL)
    en/matches/1538111.html    → الإنجليزي (LTR)

كل صفحة فيها:
  - الناديان بشعاريهما والنتيجة (روابط لصفحتَي النادي)
  - التاريخ والدوري والموسم
  - قائمة أحداث موحدة مرتبة بالدقيقة (أهداف + بطاقات + تبديلات)
  - خياران: كل الأحداث / الأحداث المهمة
  - ⭐ شارة "نتيجة مصححة" مع السبب والمصدر

⚠️ ملاحظات وأسماء اللاعبين في التصحيحات مكتوبة بالعربية فقط،
   فتظهر كما هي في النسخة الإنجليزية. ترجمتها مؤجلة لجلسة الأسماء.

⚠️ **الأهداف الملغاة** تُقرأ من `cancelled_goals` (ينقلها إليه
   `fix_goals.py` بدل حذفها) وتظهر بأيقونة 🚫 ووسم "هدف ملغى".
   أكثرها بلا اسم لاعب — المزوّد لا يسمّي الملغى — فيظهر السطر
   بالدقيقة والفريق فقط.

⚠️ **أسماء البطاقات والتبديلات** كانت تُعرض بالإنجليزية دائماً
   لأن استعلام `events` لم يكن يجلب `player_ar` أصلاً (بعكس
   قسم الأهداف). صُحِّح 21 أغسطس. واللاعب الداخل بالتبديل
   (`assist_en`) بلا عمود عربي في الجدول، فيُترجَم عبر
   `name_map()` — جدول بحث من كل الجداول المترجَمة.

صفر طلبات API.

التشغيل:
    python make_matches.py
    python make_matches.py JOR      <- دوري محدد فقط
"""

import sqlite3
import csv
import os
import sys
from html import escape as html_escape
from config import DB_FILE, TEAMS_FILE, LEAGUES
from thumbs_util import thumb_src, logo_img
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name, off_label, off_msg
from search_view import SEARCH_CSS
from navbar import (NAV_CSS, navbar, settings_button, settings_overlay,
                    nav_script, pwa_script, pwa_offbar, appbar)
import assets
from lineup_view import LINEUP_CSS, build_lineups
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)
from live_view import LIVE_CSS, live_script
from match_row import ROW_CSS, card_css, match_row
from tabs_view import TABS_CSS
from tiebreak import STANDINGS_EXCLUDED
from matchtime import matchtime_script

BASE = DB_FILE.parent
CORRECTIONS_FILE = BASE / "match_corrections.csv"

# ⚠️ **جدول `events` يحمل `assist_en` بلا `assist_ar` مقابل.**
#    العمود يخصّ التبديلات حصراً (اللاعب الداخل) — 7,408 سجلاً،
#    كلها type='subst'، ولا هدف واحد. الاسم مضلِّل ومصدره المزوّد.
#    بدل تعديل بنية الجدول، نبني جدول بحث من كل الجداول التي
#    تحمل ترجمة: يغطي ~495 من 1,049 اسماً فوراً (درس 66).
_NAME_MAP = None


def name_map(conn):
    """player_en -> player_ar من كل جدول يحمل ترجمة. يُبنى مرة واحدة."""
    global _NAME_MAP
    if _NAME_MAP is not None:
        return _NAME_MAP
    m = {}
    for tbl in ("goals", "lineup_players", "player_stats", "events"):
        try:
            rows = conn.execute(f"""
                SELECT DISTINCT player_en, player_ar FROM {tbl}
                WHERE player_en IS NOT NULL AND player_en != ''
                  AND player_ar IS NOT NULL AND player_ar != ''
            """).fetchall()
        except sqlite3.OperationalError:
            continue
        for en, ar in rows:
            m.setdefault(en, ar)
    _NAME_MAP = m
    return m

ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


MATCH_FOLLOW_CSS = """
  /* نجمة + جرس بشريط التطبيق العلوي (13 أكتوبر): دائريّان 44×44 بنفس إطار .topbtn؛ الجرس مخفي حتى تكشفه البوّابة */
  .mact { width:44px; height:44px; flex:0 0 44px; border-radius:12px; padding:0; cursor:pointer;
          display:inline-flex; align-items:center; justify-content:center;
          background:var(--card); color:var(--muted); border:1px solid var(--line); }
  .mact[hidden] { display:none; }
  .mact:hover { background:var(--card2); color:var(--text); }
  .mact svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.8;
              stroke-linecap:round; stroke-linejoin:round; }
  .mact[aria-pressed="true"] { color:var(--accent); border-color:var(--accent); }
  .mact[aria-pressed="true"] svg { fill:currentColor; }
  .mact:disabled { opacity:.55; cursor:default; }
  .pushmsg { color:var(--muted); font-size:13px; margin:0 0 10px; padding-inline:4px; }
  .pushmsg[hidden] { display:none; }
"""

CSS_TYPE = VARS + """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:760px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:14px; }
  .back { display:inline-block; color:var(--accent); text-decoration:none;
          font-size:14px; }
  .back:hover { text-decoration:underline; }
  .lang { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:var(--card2); color:var(--text); }
  .meta-top { text-align:center; color:var(--muted); font-size:13px;
              margin-bottom:12px; }
  .head { background:var(--card); border-radius:12px; padding:24px 16px;
          display:grid; grid-template-columns:1fr auto 1fr;
          align-items:center; gap:12px; }
  .team { display:flex; flex-direction:column; align-items:center;
          gap:10px; min-width:0; text-decoration:none; color:var(--text); }
  .team img { width:60px; height:60px; object-fit:contain; }
  .team span { font-size:15px; text-align:center; }
  .team:hover span { color:var(--accent); }
  .kick { display:block; font-size:15px; font-weight:600;
          color:var(--text); margin-top:6px; }
  .big { font-size:29px; font-weight:700; letter-spacing:2px;
         white-space:nowrap; }
  /* عدّ تنازلي (10 أكتوبر): الوقت كبير بـ.score والتاريخ/العدّاد تحته بـ.kick (matchtime.py: data-cd) */
  .big.cd { font-size:24px; letter-spacing:1px; }
  .big.cd .kick { font-size:13px; font-weight:600; letter-spacing:1px; font-variant-numeric:tabular-nums;
                  color:var(--muted); text-align:center; unicode-bidi:isolate; }
  .big.cd .kick.dt { font-size:13px; letter-spacing:0; color:var(--muted); }
  .big.soon { font-size:15px; font-weight:600; letter-spacing:0;
              color:var(--accent); white-space:normal; text-align:center; }
  /* المواجهات المباشرة */
  .h2h { background:var(--card); border-radius:12px; padding:16px; }
  .h2hn { text-align:center; color:var(--muted); font-size:13px;
          margin-bottom:12px; }
  .h2hbar { display:flex; height:34px; border-radius:8px;
            overflow:hidden; font-size:13px; font-weight:700; }
  .h2hbar span { display:flex; align-items:center;
                 justify-content:center; color:#fff; min-width:22px; }
  .h2hbar .w { background:#2ea043; }
  .h2hbar .d { background:#484f58; }
  .h2hbar .l { background:#8957e5; }
  .h2hleg { display:flex; margin-top:7px; font-size:12px;
            color:var(--muted); }
  .h2hleg span { flex:1; text-align:center; }
  .h2hleg span:first-child { text-align:start; }
  .h2hleg span:last-child { text-align:end; }
  .h2hlist { margin-top:14px; }
  .h2hlist a { display:flex; align-items:center;
               justify-content:space-between; padding:10px 4px;
               border-top:1px solid var(--line); text-decoration:none;
               color:var(--text); }
  .h2hlist a:hover { background:var(--card2); }
  .h2hlist a.hidden { display:none; }
  .hd { color:var(--muted); font-size:12px; }
  .hm { display:flex; align-items:center; gap:9px; font-size:14px; }
  .hm img { width:21px; height:21px; object-fit:contain; }
  .h2hmore { width:100%; margin-top:10px; background:var(--card2);
             color:var(--accent); border:1px solid var(--line);
             border-radius:9px; padding:10px; font-size:13px;
             cursor:pointer; font-family:inherit; min-height:44px; }

  .fixed { background:var(--card2); border:1px solid var(--accent);
           border-radius:10px; padding:14px 16px; margin-top:12px;
           font-size:13px; }
  .fixed b { color:var(--accent); }
  .fixed .row { color:var(--muted); margin-top:4px; }
  h2 { font-size:16px; margin:26px 0 10px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  .goals { background:var(--card); border-radius:10px; padding:6px; }
  /* خط الأحداث (12 أكتوبر): [مضيف] دقيقة [ضيف] — عمود المضيف أول عمود فيتبع اتجاه الصفحة (يمين بالعربي ويسار بالإنجليزي) */
  .min { color:var(--accent); font-weight:700; text-align:center; }
  .who { min-width:0; overflow-wrap:anywhere; }
  .kind { color:var(--muted); font-size:12px; }
  .who.cancelled { text-decoration:line-through; opacity:.6; }
  .ev { display:grid; grid-template-columns:minmax(0,1fr) 40px minmax(0,1fr); align-items:center;
        column-gap:6px; padding:10px 8px; border-bottom:1px solid var(--line); font-size:14px; }
  .ev:last-child { border-bottom:none; }
  .evc { display:flex; align-items:center; gap:6px; min-width:0; }
  .ev.h .evc.on { justify-content:flex-end; text-align:end; }
  .ev.a .evc.on { justify-content:flex-start; text-align:start; }
  .evt { display:flex; flex-direction:column; min-width:0; }
  .ic { font-size:13px; flex:none; }
  .out { color:var(--red); font-size:12px; }
  .in { color:var(--green); font-size:12px; }
  .vtabs { display:flex; gap:8px; margin:26px 0 10px; }
  .vtab { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:8px 16px; border-radius:8px; cursor:pointer;
          font-family:inherit; font-size:14px; min-height:44px; }
  .vtab:hover { background:var(--card2); color:var(--text); }
  .vtab.on { background:var(--accent); color:var(--bg); border-color:var(--accent); }
  .minor.off { display:none; }
""" + TABS_CSS + """  .mp > h2:first-child { display:none; }
  .mp > .vtabs { margin-top:12px; }
  .mp > .goals, .mp > .empty, .mp > .lu, .mp > .h2h, .lgt { margin-top:12px; }
  /* ترتيب الدوري داخل التبويب: الفريقان مظلَّلان */
  .lgt { width:100%; border-collapse:collapse; background:var(--card); border-radius:10px; overflow:hidden;
         table-layout:fixed; }
  .lgt th, .lgt td { padding:9px 2px; text-align:center; font-size:13px; }
  .lgt th { background:var(--card2); color:var(--muted); font-size:12px; }
  .lgt th.r { text-align:start; padding-inline-start:6px; }
  .lgt tr { border-bottom:1px solid var(--line); }
  .lgt tr:last-child { border-bottom:none; }
  .lgt .ps { width:26px; color:var(--muted); }
  .lgt td:nth-child(7) { direction:ltr; unicode-bidi:isolate; }   /* فارق الأهداف +8 لا 8+ بالعربي */
  .lgt th:nth-child(n+3), .lgt td:nth-child(n+3) { width:32px; }
  .lgt td.tm { text-align:start; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .lgt td.tm img { width:20px; height:20px; object-fit:contain; vertical-align:middle; margin-inline-end:6px; }
  .lgt td.tm a { color:var(--text); text-decoration:none; vertical-align:middle; }
  .lgt .pt { font-weight:700; color:var(--accent); }
  .lgt tr.top .ps { color:var(--green); font-weight:700; }
  .lgt tr.bottom .ps { color:var(--red); }
  .lgt tr.hl { background:rgba(47,129,247,.16); }
  .lgt tr.hl td.tm a { font-weight:700; }
  .st { display:grid; grid-template-columns:52px 1fr 52px;
        align-items:center; gap:10px; padding:9px 12px;
        border-bottom:1px solid var(--line); font-size:13px; }
  .st:last-child { border-bottom:none; }
  .st .v { font-weight:700; }
  .st .v.a { text-align:start; }
  .st .v.b { text-align:end; }
  .st .mid { text-align:center; }
  .st .lbl { color:var(--muted); font-size:12px; display:block; }
  .bar { display:flex; height:5px; border-radius:3px;
         overflow:hidden; background:var(--line); margin-top:3px; }
  .bar i { display:block; height:100%; }
  .bar .x { background:var(--accent); }
  .bar .y { background:var(--muted); }
  .empty { background:var(--card); border-radius:10px; padding:20px;
           text-align:center; color:var(--muted); font-size:13px; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }
""" + MATCH_FOLLOW_CSS + """""" + LINEUP_CSS

# ⚠️ STYLE الكامل (inline) لم يعد يُستعمل بالصفحات — الأنماط بملفات /assets
#    (راجع assets.py/make_assets.py): CSS_TYPE → match.css والباقي → site.css
CSS_TYPE += """
  /* فورمة الفريقين (14 أكتوبر): عمودان بترتيب DOM (المضيف أولاً = جهة المضيف بالعربي والإنجليزي)، آخر 5 نتائج، الأحدث بالأعلى */
  .tfcard { background:var(--card); border-radius:12px; padding:12px 10px 8px; margin-top:16px; }
  .tfcard h3 { font-size:14px; text-align:center; margin-bottom:8px; color:var(--text); }
  .tfcols { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:10px; }
  .tfh { text-align:center; color:var(--muted); font-size:12px; margin-bottom:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tfr { display:flex; align-items:center; justify-content:center; gap:6px; min-height:44px; text-decoration:none; color:var(--text); }
  .tfr img, .tfr .tfnl { width:22px; height:22px; flex:0 0 22px; object-fit:contain; }
  .tfpw { display:inline-flex; flex-direction:column; align-items:center; gap:2px; }
  .tfp { min-width:48px; text-align:center; padding:2px 8px; border-radius:6px; font-size:13px; font-weight:700; color:#fff; white-space:nowrap; }
  .tfp.w { background:#17803a; } .tfp.d { background:#6b7280; } .tfp.l { background:#c62828; }
  .tfmk { width:18px; height:3px; border-radius:2px; background:var(--accent); }
""" + card_css(".fxc") + ROW_CSS + """
  /* تبويب المواجهات (18 أكتوبر، دفعة D2): بطاقة هذه المباراة أعلاه دائماً، ثم الملخص والقائمة أو سطر «لا مواجهات سابقة» */
  .fxc { margin:4px 0 12px; }
  .h2hnone { background:var(--card); border-radius:12px; padding:14px; text-align:center; color:var(--muted); font-size:13px; }
  /* «الموسم حتى الآن»: صف لكل مؤشر [قيمة المضيف][التسمية][قيمة الضيف]، المضيف بجهة البداية (ترتيب DOM) */
  .ssf { background:var(--card); border-radius:12px; padding:12px 12px 6px; margin-top:16px; }
  .ssf h3 { font-size:14px; text-align:center; margin-bottom:6px; color:var(--text); }
  .ssfh, .ssfr { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); align-items:center; gap:8px; min-height:40px; }
  .ssfh { color:var(--muted); font-size:12px; min-height:28px; }
  .ssfh span, .ssfr .v { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ssfr { border-top:1px solid var(--line); font-size:14px; }
  .ssfr .k { color:var(--muted); font-size:12px; text-align:center; }
  .ssfh span:first-child, .ssfr .v:first-child { text-align:start; }
  .ssfh span:last-child, .ssfr .v:last-child { text-align:end; }
  .ssfr .v { font-weight:700; }
  .ssfr .v a { color:var(--text); text-decoration:none; }
  .ssfr .v a:hover { color:var(--accent); }
  .ssfr .v small { color:var(--muted); font-weight:400; font-size:11px; }
  /* مركزا الفريقين بالنظرة العامة (دفعة D2): واحد تحت الآخر؛ live_view (ltPaint) يحدّث المركز والنقاط والمباريات أثناء البث */
  .ltpos { background:var(--card); border-radius:12px; padding:10px 12px 4px; margin-top:16px; }
  .ltpos h3 { font-size:14px; text-align:center; margin-bottom:4px; color:var(--text); }
  .lph, .lprow { display:grid; grid-template-columns:32px 22px minmax(0,1fr) 40px 40px; align-items:center; gap:8px; }
  .lph { color:var(--muted); font-size:11px; min-height:24px; }
  .lprow { min-height:44px; border-top:1px solid var(--line); font-size:14px; text-decoration:none; color:var(--text); }
  .lprow img, .lprow .tfnl { width:22px; height:22px; object-fit:contain; }
  .lpr { font-weight:700; text-align:center; }
  .lpn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .lpp, .lpm, .lph .c { text-align:center; }
  .lpp { font-weight:700; }
  .lprow.lvrow .lpr { color:var(--green); }
"""
STYLE = ("\n<style>" + CSS_TYPE + SEARCH_CSS + NAV_CSS + LIVE_CSS
         + "\n</style>")

# سكربت الصفحة المحدَّد بالمباراة (يُضمَّن بحزمة match.<lang>.js)
# ── متابعة المباراة + جرس تنبيهات أهدافها (13 أكتوبر 2026) ──
MATCH_STAR = {
    "ar": {"f": "متابعة المباراة", "u": "إلغاء متابعة المباراة"},
    "en": {"f": "Follow match", "u": "Unfollow match"},
}
def push_ui_msg():
    import push_ui
    return push_ui.msg_html()


def match_actions_html(mid, ko_iso, lang, label=""):
    """نجمة المتابعة + جرس تنبيهات المباراة لشريط التطبيق العلوي بصفحة المباراة (دفعة B: بلا «تعديل» تحته — الإشعار السفلي يحمل الرابط؛ خط مائل مطفأً)."""
    import push_ui
    st = MATCH_STAR[lang]
    star = (f'<button class="mact" id="mstar" type="button" aria-pressed="false" data-mid="{mid}" data-ko="{ko_iso}" '
            f'data-f="{st["f"]}" data-u="{st["u"]}" aria-label="{st["f"]}" title="{st["f"]}">'
            f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9-4.3-4.1 5.9-.8z"/></svg></button>')
    return star + push_ui.bell_html("m", mid, lang, ko_iso, bell_class="mact", label=label, edit=False, strike=True)


def match_follow_script(lang):
    """نجمة متابعة المباراة (fbMatches عبر FBPrefs) + المحرّك المشترك لتنبيهات المباراة (push_ui.py). يتطلب prefs_script() قبله بنفس الحزمة."""
    import push_ui
    star = """
var star=document.getElementById('mstar'),FB=window.FBPrefs;
if(star&&FB){
  var MID=parseInt(star.getAttribute('data-mid'),10),KO=Date.parse(star.getAttribute('data-ko'))||0,
      L1=star.getAttribute('data-f'),L2=star.getAttribute('data-u');
  var paint=function(){var on=FB.hasMatch(MID);star.setAttribute('aria-pressed',on?'true':'false');
    star.setAttribute('aria-label',on?L2:L1);star.title=on?L2:L1;};
  star.addEventListener('click',function(){if(FB.hasMatch(MID))FB.removeMatch(MID);else FB.addMatch(MID,KO);paint();});
  window.addEventListener('storage',paint);paint();
}
if(window.FBPush)window.FBPush.bind(document.getElementById('pushbtn'),null,document.getElementById('pushmsg'),{toast:true});
"""
    return "<script>" + push_ui.engine_body(lang) + "\n(function(){" + star + "})();</script>"


MATCH_PAGE_JS = (
        # زر "عرض المزيد" بقائمة المواجهات — يكشف الكل دفعة واحدة
        # (القوائم قصيرة: 7 مواجهات كحد أقصى بالداتا الحالية)
        'var hb=document.querySelector(".h2hmore");\n'
        'if(hb)hb.addEventListener("click",function(){\n'
        'document.querySelectorAll(".h2hlist a.hidden")\n'
        '.forEach(function(x){x.classList.remove("hidden");});\n'
        'this.style.display="none";});\n'
        'document.querySelectorAll(".vtab").forEach(function(t){\n'
        't.addEventListener("click",function(){\n'
        'var key=this.dataset.v==="key";\n'
        'document.querySelectorAll(".vtab").forEach(function(x){\n'
        'x.classList.toggle("on",x===t);});\n'
        'document.querySelectorAll(".ev.minor").forEach(function(e){\n'
        'e.classList.toggle("off",key);});\n'
        '});});\n'
        # تبويبات الصفحة: تبديل لوحة بلا إعادة تحميل ولا تخزين (الحالة بالـDOM فقط)
        'var mtb=document.querySelectorAll(".mtab");\n'
        'mtb.forEach(function(b){\n'
        'b.addEventListener("click",function(){\n'
        'var k=b.getAttribute("data-tab");\n'
        'mtb.forEach(function(x){var on=x===b;x.classList.toggle("on",on);\n'
        'x.setAttribute("aria-selected",on?"true":"false");});\n'
        'document.querySelectorAll(".mp").forEach(function(p){\n'
        'p.classList.toggle("on",p.getAttribute("data-tab")===k);});\n'
        '});});\n'
        # رابط مباشر لتبويب: #lineups (إشعار «التشكيلة الرسمية»، 19 أكتوبر 2026)؛ تبويب غائب = يبقى الافتراضي
        'var mh=location.hash.slice(1);\n'
        'if(/^[a-z0-9]+$/.test(mh)){var mtg=document.querySelector(\'.mtab[data-tab="\'+mh+\'"]\');if(mtg)mtg.click();}\n'
)


CARD_ICON = {
    "Yellow Card": "🟨",
    "Red Card": "🟥",
    "Second Yellow card": "🟨🟥",
}


def clean(t):
    return (t or "").strip()


def t_cancelled(lang):
    """وسم الهدف الملغى — نص محلي هنا بدل إضافة مفتاح لـi18n"""
    return "هدف ملغى" if lang == "ar" else "Disallowed goal"


def goal_kind(detail, lang):
    """نوع الهدف مترجَم"""
    t = T[lang]
    return {
        "Normal Goal": "",
        "Penalty": t["penalty"],
        "Own Goal": t["own_goal"],
    }.get(detail, clean(detail))


def load_teams():
    teams = {}
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "id": int(tid),
                "short": clean(r.get("short_name_ar")),
                "name_en": (clean(r.get("name_en_official"))
                            or clean(r.get("name_en"))),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


def tname(t, lang):
    """اسم النادي حسب اللغة"""
    if lang == "ar":
        return t["short"] or t["name_en"]
    return t["name_en"] or t["short"]


def logo_url(t, lang, big=False):
    """
    الشعار: النسخة المصغّرة thumbs/ أولاً (thumbs_util)، ثم logo_local، ثم رابط المزوّد.
    matches/x.html      → ../thumbs/
    en/matches/x.html   → ../../thumbs/
    big=True: نسخة 128px لرأس الصفحة (يُعرض 60px).
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


def load_corrections():
    """التصحيحات — عشان نعرض الشارة"""
    fixes = {}
    if not CORRECTIONS_FILE.exists():
        return fixes
    with open(CORRECTIONS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            mid = clean(r.get("match_id"))
            if not mid:
                continue
            fixes[int(mid)] = {
                "note": clean(r.get("note")),
                "source": clean(r.get("source")),
            }
    return fixes


def build_items(conn, mid, lang):
    """كل أحداث المباراة بقائمة واحدة مرتبة بالدقيقة"""
    items = []

    for g in conn.execute("""
        SELECT team_id, minute, player_en, player_ar, detail
        FROM goals WHERE match_id = ? ORDER BY minute
    """, (mid,)):
        who = (clean(g["player_ar"]) if lang == "ar" else "")
        who = who or clean(g["player_en"]) or "—"
        items.append({
            "min": g["minute"] if g["minute"] is not None else 999,
            "team": g["team_id"], "icon": "⚽", "major": True,
            "body": f'<span class="who">{who}</span>',
            "kind": goal_kind(g["detail"], lang),
            "plain": "" if who == "—" else who,
        })

    # ⚠️ الأهداف الملغاة — منقولة إلى cancelled_goals لا محذوفة
    #    (fix_goals.py، 21 أغسطس). الجدول قد لا يكون موجوداً في
    #    نسخة أقدم من الديتابيس، فالفشل يُتجاهَل بصمت.
    #    ⚠️ أغلبها بلا اسم لاعب — المزوّد لا يسمّي الملغى عادةً،
    #    فيظهر السطر بالدقيقة والفريق فقط، وهذا مقصود.
    try:
        for c in conn.execute("""
            SELECT team_id, minute, player_en, player_ar
            FROM cancelled_goals
            WHERE match_id = ? AND reason = 'zero_zero_match'
              AND TRIM(COALESCE(player_en, '')) != ''   -- الشبح (بلا اسم) ليس هدفاً ملغى فلا يُعرض
            ORDER BY minute
        """, (mid,)):
            nm = (clean(c["player_ar"]) if lang == "ar" else "")
            nm = nm or clean(c["player_en"])
            items.append({
                "min": c["minute"] if c["minute"] is not None else 999,
                "team": c["team_id"], "icon": "🚫", "major": False,
                "body": (f'<span class="who cancelled">{nm}</span>'
                         if nm else ""),
                "kind": t_cancelled(lang),
            })
    except Exception:
        pass

    try:
        evs = conn.execute("""
            SELECT team_id, minute, type, detail,
                   player_en, player_ar, assist_en
            FROM events WHERE match_id = ? AND type != 'none'
            ORDER BY minute
        """, (mid,)).fetchall()
    except Exception:
        evs = []

    sub_arrow = "←" if lang == "ar" else "→"

    names = name_map(conn) if lang == "ar" else {}

    for e in evs:
        # ⚠️ كان يعرض player_en دائماً — فترجمات البطاقات
        #    والتبديلات في `events` لم تكن تظهر إطلاقاً رغم
        #    تطبيقها على الجدول (بعكس قسم الأهداف أعلاه).
        player = ""
        if lang == "ar":
            player = clean(e["player_ar"]) or names.get(clean(e["player_en"]), "")
        player = player or clean(e["player_en"]) or "—"
        mn = e["minute"] if e["minute"] is not None else 999

        if e["type"] == "Card":
            red = e["detail"] in ("Red Card", "Second Yellow card")
            items.append({
                "min": mn, "team": e["team_id"],
                "icon": CARD_ICON.get(e["detail"], "🟨"),
                "major": red,
                "body": f'<span class="who">{player}</span>',
                "kind": "",
            })
        elif e["type"] == "subst":
            inn_en = clean(e["assist_en"])
            inn = (names.get(inn_en, "") if lang == "ar" else "") or inn_en
            items.append({
                "min": mn, "team": e["team_id"], "icon": "🔄",
                "major": False,
                "body": (f'<span class="who">'
                         f'<span class="in">{inn}</span> {sub_arrow} '
                         f'<span class="out">{player}</span></span>'),
                "kind": "",
            })
        else:
            items.append({
                "min": mn, "team": e["team_id"], "icon": "📺",
                "major": False,
                "body": f'<span class="who">{clean(e["detail"])}</span>',
                "kind": "",
            })

    items.sort(key=lambda x: x["min"])
    return items


STAT_ROWS = [
    ("possession", "possession", "%"),
    ("shots_total", "shots", ""),
    ("shots_on", "shots_on", ""),
    ("corners", "corners", ""),
    ("fouls", "fouls", ""),
    ("offsides", "offsides", ""),
    ("saves", "saves", ""),
    ("passes_total", "passes", ""),
    ("passes_pct", "pass_acc", "%"),
    ("xg", "xg", ""),
]


def build_stats(conn, mid, home_id, away_id, lang):
    """قسم إحصائيات المباراة — فارغ إن لم توجد داتا"""
    t = T[lang]
    try:
        rows = conn.execute("""
            SELECT * FROM match_stats WHERE match_id = ?
        """, (mid,)).fetchall()
    except Exception:
        return ""

    if len(rows) < 2:
        return ""

    data = {r["team_id"]: r for r in rows}
    A = data.get(home_id)
    B = data.get(away_id)
    if A is None or B is None:
        return ""

    out = ""
    for col, key, unit in STAT_ROWS:
        va, vb = A[col], B[col]
        if va is None and vb is None:
            continue
        va = va or 0
        vb = vb or 0
        tot = va + vb
        pa = (va / tot * 100) if tot else 50
        pb = 100 - pa

        # الأرقام العشرية (xG) تُعرض برقمين
        fa = f"{va:.2f}" if isinstance(va, float) else str(va)
        fb = f"{vb:.2f}" if isinstance(vb, float) else str(vb)

        out += (
            f'<div class="st">'
            f'<span class="v a">{fa}{unit}</span>'
            f'<span class="mid"><span class="lbl">{t[key]}</span>'
            f'<span class="bar"><i class="x" style="width:{pa:.0f}%"></i>'
            f'<i class="y" style="width:{pb:.0f}%"></i></span></span>'
            f'<span class="v b">{fb}{unit}</span>'
            f'</div>'
        )

    if not out:
        return ""

    return f'<h2>{t["stats"]}</h2><div class="goals">{out}</div>'
# ⚠️ نصوص محلية لا في i18n — تخصّ هذا القسم وحده.
H2H = {
    "ar": {"title": "المواجهات المباشرة", "met": "تواجها",
           "times": "مرة", "draw": "تعادل", "recent": "آخر المواجهات",
           "more": "عرض المزيد", "none": "لا مواجهات سابقة"},
    "en": {"title": "Head to head", "met": "Met",
           "times": "times", "draw": "Draws", "recent": "Recent meetings",
           "more": "Show more", "none": "No previous meetings"},
}

# «الموسم حتى الآن» + مركزا الفريقين (18 أكتوبر 2026، دفعة D2) — نصوص محلية لا في i18n
SSF = {
    "ar": {"title": "الموسم حتى الآن", "pos": "المركز", "wdl": "فوز - تعادل - خسارة", "gpm": "أهداف بالمباراة",
           "cpm": "استقبل بالمباراة", "cs": "شباك نظيفة", "bw": "أكبر فوز", "bl": "أكبر خسارة", "vs": "ضد",
           "tbl": "الترتيب", "pts": "نقاط", "pl": "لعب"},
    "en": {"title": "Season so far", "pos": "Position", "wdl": "W - D - L", "gpm": "Goals per match",
           "cpm": "Conceded per match", "cs": "Clean sheets", "bw": "Biggest win", "bl": "Biggest loss", "vs": "vs",
           "tbl": "Table", "pts": "Pts", "pl": "P"},
}


def fixture_card(m, h, a, lang):
    """بطاقة هذه المباراة (match_row المشتركة) أعلى تبويب المواجهات: الوقت/العدّ التنازلي للقادمة، التسمية للمؤجّلة، النتيجة للمنتهية.
    data-mid نفسه فيحدّثها live_view كبطاقة قائمة (كبسولة الدقيقة + النتيجة) أثناء البث."""
    t = T[lang]
    parts = str(m["date"]).split()
    day, clock = parts[0], (parts[1][:5] if len(parts) > 1 else "")
    upcoming = m["home_goals"] is None
    off = off_label(m["status"], t) if upcoming else ""
    if not upcoming:
        score = f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>'
    elif off:
        score = f'<div class="score pst">{off}</div>'
    elif clock:
        score = (f'<div class="score time" data-utc="{day}T{clock}:00Z" data-cd="card" data-ko="{day}T{clock}:00Z">'
                 f'{clock} UTC</div>')
    else:
        score = '<div class="score time">—</div>'
    card = match_row(m["match_id"], f'{m["match_id"]}.html',
                     (html_escape(tname(h, lang)), logo_tag(h, lang, 22), None),
                     (html_escape(tname(a, lang)), logo_tag(a, lang, 22), None),
                     score, cls="match soon" if upcoming else "match")
    return f'<div class="fxc">{card}</div>'


# مباريات (دوري، موسم) المنتهية لكل فريق — استعلام واحد لكل (دوري، موسم) يتشاركه كل صفحات التوليد؛ نفس استثناءات جدول الترتيب
_SSF = {}


def season_games(conn, code, season):
    k = (code, season)
    if k not in _SSF:
        per = {}
        for r in conn.execute(
                "SELECT match_id, date, home_id, away_id, home_goals, away_goals FROM matches "
                "WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL AND away_goals IS NOT NULL ORDER BY date, match_id",
                (code, season)):
            if r["match_id"] in STANDINGS_EXCLUDED:
                continue
            for tid, gf, ga, opp in ((r["home_id"], r["home_goals"], r["away_goals"], r["away_id"]),
                                     (r["away_id"], r["away_goals"], r["home_goals"], r["home_id"])):
                per.setdefault(tid, []).append((r["date"], r["match_id"], gf, ga, opp))
        _SSF[k] = per
    return _SSF[k]


def season_so_far(conn, m, tid):
    """مؤشرات الفريق بموسم المباراة ومسابقتها (كل المنتهية المحسوبة بالترتيب): المركز (get_table + كسر التعادل)، ف/ت/خ،
    أهداف/استقبل بالمباراة، شباك نظيفة، أكبر فوز/خسارة (الفارق الأكبر، ثم الأهداف الأكثر، ثم الأحدث)."""
    games = season_games(conn, m["league_code"], m["season"]).get(tid, [])
    rows = table_rows(conn, m["league_code"], m["season"])
    pos = next((i for i, r in enumerate(rows, 1) if r["team_id"] == tid), None)
    p = len(games)
    out = {"pos": pos, "p": p, "w": 0, "d": 0, "l": 0, "gpm": None, "cpm": None, "cs": 0, "win": None, "loss": None}
    if not p:
        return out
    out["w"] = sum(1 for g in games if g[2] > g[3])
    out["d"] = sum(1 for g in games if g[2] == g[3])
    out["l"] = sum(1 for g in games if g[2] < g[3])
    out["gpm"] = sum(g[2] for g in games) / p
    out["cpm"] = sum(g[3] for g in games) / p
    out["cs"] = sum(1 for g in games if g[3] == 0)
    out["win"] = max((g for g in games if g[2] > g[3]), key=lambda g: (g[2] - g[3], g[2], g[0]), default=None)
    out["loss"] = max((g for g in games if g[2] < g[3]), key=lambda g: (g[3] - g[2], g[3], g[0]), default=None)
    return out


def build_season_card(conn, m, h, a, teams, lang):
    """بطاقة «الموسم حتى الآن»: صف لكل مؤشر [المضيف][التسمية][الضيف]. "" إن لم يلعب أي من الفريقين بالموسم."""
    S = SSF[lang]
    d = [season_so_far(conn, m, m["home_id"]), season_so_far(conn, m, m["away_id"])]
    if not (d[0]["p"] or d[1]["p"]):
        return ""

    def big(g):
        if not g:
            return "—"
        opp = teams.get(g[4])
        on = html_escape(tname(opp, lang)) if opp else ""
        return f'<a href="{g[1]}.html">{g[2]} - {g[3]}</a>' + (f' <small>{S["vs"]} {on}</small>' if on else "")

    def num(v):
        return "—" if v is None else f"{v:.1f}"

    vals = [
        ("pos", lambda x: str(x["pos"]) if x["pos"] else "—"),
        ("wdl", lambda x: f'{x["w"]} - {x["d"]} - {x["l"]}' if x["p"] else "—"),
        ("gpm", lambda x: num(x["gpm"])),
        ("cpm", lambda x: num(x["cpm"])),
        ("cs", lambda x: str(x["cs"]) if x["p"] else "—"),
        ("bw", lambda x: big(x["win"])),
        ("bl", lambda x: big(x["loss"])),
    ]
    rows = "".join(f'<div class="ssfr" data-k="{k}"><span class="v">{f(d[0])}</span><span class="k">{S[k]}</span>'
                   f'<span class="v">{f(d[1])}</span></div>' for k, f in vals)
    return (f'<div class="ssf"><h3>{S["title"]}</h3><div class="ssfh"><span>{html_escape(tname(h, lang))}</span><span></span>'
            f'<span>{html_escape(tname(a, lang))}</span></div>{rows}</div>')


def build_positions(conn, m, teams, lang):
    """مركزا الفريقين واحداً تحت الآخر (النظرة العامة للقادمة، دفعة D2): المركز · الشعار · الاسم · النقاط · المباريات.
    سمات data-lt/ss/lid لموسم الدوري الحالي (بلا JOR، كجدول تبويب الترتيب) فيحدّثها live_view.ltPaint أثناء البث. "" بلا جدول."""
    rows = table_rows(conn, m["league_code"], m["season"])
    idx = {r["team_id"]: (i, r) for i, r in enumerate(rows, 1)}
    if m["home_id"] not in idx and m["away_id"] not in idx:
        return ""
    S = SSF[lang]
    code = m["league_code"]
    lt = (f' data-lt="{code}" data-ss="{m["season"]}" data-lid="{LEAGUES[code]["id"]}"'
          if m["season"] == LATEST_SEASON and code in LEAGUES and code != "JOR" else "")
    out = ""
    for tid in (m["home_id"], m["away_id"]):
        if tid not in idx:
            continue
        i, r = idx[tid]
        tm = teams.get(tid)
        lg = logo_tag(tm, lang, 22) if tm and logo_url(tm, lang) else '<span class="tfnl"></span>'
        nm = html_escape(tname(tm, lang)) if tm else str(tid)
        out += (f'<a class="lprow" data-t="{tid}" href="../clubs/{tid}.html"><span class="lpr">{i}</span>{lg}'
                f'<span class="lpn">{nm}</span><span class="lpp">{r["points"]}</span><span class="lpm">{r["played"]}</span></a>')
    return (f'<div class="ltpos"{lt}><h3>{S["tbl"]}</h3><div class="lph"><span class="c">#</span><span></span><span></span>'
            f'<span class="c">{S["pts"]}</span><span class="c">{S["pl"]}</span></div>{out}</div>')


def build_h2h(conn, m, h, a, lang, tname_fn, logo_fn, teams=None):
    """
    المواجهات المباشرة بين الفريقين — من كل المواسم المخزّنة.

    ⚠️ **التبويب ظاهر دائماً (18 أكتوبر، دفعة D2، قرار عمرو):** بطاقة هذه المباراة أعلاه، ثم الملخص والقائمة، أو سطر
       «لا مواجهات سابقة» (كان يُخفى كلياً بلا مواجهة: 22% من القادمة)، ثم «الموسم حتى الآن» للفريقين.

    ⚠️ **تُستثنى المباراة الحالية** — عرضها ضمن تاريخ نفسها خطأ
       منطقي، ويحدث لو كانت منتهية.

    ⚠️ **تشمل المنتهية فقط** — المباريات القادمة بلا نتيجة لا
       تُحسب في السجل ولا تُعرض.
    """
    hid, aid = m["home_id"], m["away_id"]
    s = H2H[lang]

    rows = conn.execute("""
        SELECT match_id, date, home_id, away_id, home_goals, away_goals,
               league_code, season
        FROM matches
        WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
          AND match_id != ?
          AND ((home_id = ? AND away_id = ?) OR (home_id = ? AND away_id = ?))
        ORDER BY date DESC
    """, (m["match_id"], hid, aid, aid, hid)).fetchall()

    top = f'<h2>{s["title"]}</h2>' + fixture_card(m, h, a, lang)
    season = build_season_card(conn, m, h, a, teams or {}, lang)
    if not rows:
        return top + f'<div class="h2hnone">{s["none"]}</div>' + season

    hw = aw = dr = 0
    for r in rows:
        hg, ag = r["home_goals"], r["away_goals"]
        if hg == ag:
            dr += 1
        elif (r["home_id"] == hid) == (hg > ag):
            hw += 1
        else:
            aw += 1

    # ⚠️ الأسماء المختصرة — البطاقة ضيّقة على الجوال
    hn, an = tname_fn(h, lang), tname_fn(a, lang)

    li = ""
    for i, r in enumerate(rows, 1):
        rh = h if r["home_id"] == hid else a
        ra = a if r["home_id"] == hid else h
        hide = ' class="hidden"' if i > 5 else ''
        # ⚠️ 7 سبتمبر — وقت اختياري بجانب التاريخ (بند مفتوح 28).
        #    matchtime.py محمَّل أصلاً بهذه الصفحة (matchtime_script()
        #    بأسفل الملف) — HTML فقط، بلا حقن جافاسكربت إضافي.
        #    data-utc فقط لو وقت فعلي — الصفوف بلا وقت (37 مباراة،
        #    بند مفتوح 20) تبقى بتاريخ وحده كما كانت.
        h2h_parts = str(r["date"]).split()
        h2h_clock = h2h_parts[1][:5] if len(h2h_parts) > 1 else ""
        hd_html = (f'<span data-utcd="{h2h_parts[0]}T{h2h_clock}:00Z">'
                   f'{h2h_parts[0]}</span> '
                   f'<span data-utc="{h2h_parts[0]}T{h2h_clock}:00Z">'
                   f'{h2h_clock} UTC</span>'
                   if h2h_clock else h2h_parts[0])
        li += (
            f'<a{hide} href="{r["match_id"]}.html">'
            f'<span class="hd">{hd_html}</span>'
            f'<span class="hm">'
            f'{logo_tag(rh, lang, 21)}'
            f'<b>{r["home_goals"]} - {r["away_goals"]}</b>'
            f'{logo_tag(ra, lang, 21)}'
            f'</span></a>'
        )
    btn = ""
    if len(rows) > 5:
        btn = (f'<button class="h2hmore">'
               f'{s["more"]} ({len(rows) - 5})</button>')

    return (
        top +
        f'<div class="h2h">'
        f'<div class="h2hn">{s["met"]} {len(rows)} {s["times"]}</div>'
        f'<div class="h2hbar">'
        f'<span class="w" style="flex:{hw or 0.001}">{hw}</span>'
        f'<span class="d" style="flex:{dr or 0.001}">{dr}</span>'
        f'<span class="l" style="flex:{aw or 0.001}">{aw}</span>'
        f'</div>'
        f'<div class="h2hleg">'
        f'<span>{hn}</span><span>{s["draw"]}</span><span>{an}</span>'
        f'</div>'
        f'<div class="h2hlist">{li}</div>{btn}'
        f'</div>' + season
    )


# ── تبويبات صفحة المباراة (12 أكتوبر) ──
# ⚠️ نصوص محلية لا في i18n. الترتيب ثابت: أحداث · تشكيلات · إحصائيات · ترتيب · مواجهات. التبويب بلا داتا يُحذف.
MT = {
    "ar": {"events": "الأحداث", "lineups": "التشكيلات", "stats": "الإحصائيات",
           "table": "الترتيب", "h2h": "المواجهات"},
    "en": {"events": "Events", "lineups": "Lineups", "stats": "Stats",
           "table": "Table", "h2h": "H2H"},
}
MT_ORDER = ("events", "lineups", "stats", "table", "h2h")

# ── فورمة الفريقين (14 أكتوبر 2026، قرار عمرو): آخر 5 مباريات منتهية (FT/AET/PEN) لكل فريق، أي مسابقة، قبل انطلاق هذه المباراة
# ⚠️ بلا طلبات API: استعلام واحد لكل التوليد (يُبنى مرة بـmain) ثم bisect بالذاكرة لكل صفحة. الأحدث بالأعلى؛ هذه المباراة لا تدخل أبداً
#    (تاريخها ليس «أصغر قطعاً» من تاريخها). المعرّفات السالبة/الاصطناعية تُهمَل. لون القرص من وجهة نظر هذا الفريق: فوز أخضر · تعادل رمادي · خسارة أحمر.
import bisect

FORM_N = 5
FORM_STATUS = ("FT", "AET", "PEN")
_FORM = None   # {team_id: ([date, ...] تصاعدياً, [row, ...])}؛ row = (date, match_id, home_id, away_id, hg, ag)

MF = {
    "ar": {"preview": "نظرة عامة", "form": "فورمة الفريقين"},
    "en": {"preview": "Preview", "form": "Team form"},
}


def build_form_index(conn):
    global _FORM
    rows = conn.execute(
        "SELECT date, match_id, home_id, away_id, home_goals, away_goals FROM matches "
        "WHERE status IN ('FT','AET','PEN') AND home_goals IS NOT NULL AND away_goals IS NOT NULL "
        "AND home_id > 0 AND away_id > 0 AND date IS NOT NULL AND date <> '' "
        "ORDER BY date, match_id").fetchall()
    per = {}
    for r in rows:
        row = (r[0], r[1], r[2], r[3], r[4], r[5])
        for tid in (r[2], r[3]):
            per.setdefault(tid, ([], []))
            per[tid][0].append(r[0])
            per[tid][1].append(row)
    _FORM = per
    return per


def team_form(tid, date, mid, n=FORM_N):
    """آخر n مباريات منتهية للفريق قبل `date` (تاريخ نصي أصغر قطعاً)، الأحدث أولاً."""
    if _FORM is None or tid not in _FORM or tid <= 0:
        return []
    dates, rows = _FORM[tid]
    i = bisect.bisect_left(dates, str(date))   # كل ما قبل i تاريخه < date قطعاً
    out = [r for r in rows[max(0, i - n - 1):i] if r[1] != mid][-n:]
    return list(reversed(out))


def build_form_card(m, h, a, teams, lang):
    """بطاقة «فورمة الفريقين»: عمودان، المضيف بجهة المضيف (يتبع RTL/LTR تلقائياً بترتيب DOM). "" إن لم يوجد شيء."""
    cols = ""
    total = 0
    for tid, tm in ((m["home_id"], h), (m["away_id"], a)):
        fm = team_form(tid, m["date"], m["match_id"])
        total += len(fm)
        rows = ""
        for k, (d, rid, hid, aid, hg, ag) in enumerate(fm):
            mine = hg if hid == tid else ag
            theirs = ag if hid == tid else hg
            cls = "w" if mine > theirs else ("l" if mine < theirs else "d")
            lh, la = teams.get(hid), teams.get(aid)
            ih = logo_tag(lh, lang, 22) if lh and logo_url(lh, lang) else '<span class="tfnl"></span>'
            ia = logo_tag(la, lang, 22) if la and logo_url(la, lang) else '<span class="tfnl"></span>'
            dash = " - " if lang == "ar" else "-"
            mk = '<span class="tfmk"></span>' if k == 0 else ""
            rows += (f'<a class="tfr" href="{rid}.html" aria-label="{html_escape(str(d).split()[0])}">{ih}'
                     f'<span class="tfpw"><span class="tfp {cls}">{hg}{dash}{ag}</span>{mk}</span>{ia}</a>')
        cols += (f'<div class="tfcol" data-ftid="{tid}"><div class="tfh">'
                 f'<span>{html_escape(tname(tm, lang))}</span></div>{rows}</div>')
    if not total:
        return ""
    return f'<div class="tfcard"><h3>{MF[lang]["form"]}</h3><div class="tfcols">{cols}</div></div>'


# جدول الدوري/الموسم يُحسب مرة واحدة لكل (دوري، موسم) — كل صفحات المباريات تتشاركه
_TABLES = {}


def table_rows(conn, code, season):
    k = (code, season)
    if k not in _TABLES:
        try:
            from make_site3 import get_table
            _TABLES[k] = [dict(r) for r in get_table(conn, code, season)]
        except Exception:
            _TABLES[k] = []
    return _TABLES[k]


def build_table_panel(conn, m, teams, lang):
    """
    ترتيب الدوري للموسم نفسه — نفس جدول صفحة الدوري (get_table)، ثابت وقت التوليد، والفريقان مظلَّلان.
    ⚠️ بلا شعارات عمداً: لا طلبات جديدة عند فتح التبويب (الشعارات تُحمَّل 20 صورة).
    يرجع "" إن لم يوجد جدول أو لم يكن أي من الفريقين به (كأس/ملحق).
    """
    rows = table_rows(conn, m["league_code"], m["season"])
    ids = {m["home_id"], m["away_id"]}
    if not rows or not ids & {r["team_id"] for r in rows}:
        return ""
    t = T[lang]
    n = len(rows)
    body = ""
    for i, r in enumerate(rows, 1):
        nm = (clean(r["name"]) or clean(r["name_en"])) if lang == "ar" \
            else (clean(r["name_en"]) or clean(r["name"]))
        cls = " ".join(x for x in (
            "hl" if r["team_id"] in ids else "",
            "top" if i <= 3 else ("bottom" if i > n - 2 else "")) if x)
        attr = f' class="{cls}"' if cls else ""
        body += (
            f'<tr data-t="{r["team_id"]}"{attr}>'
            f'<td class="ps">{i}</td>'
            f'<td class="tm">'
            f'<a href="../clubs/{r["team_id"]}.html">{html_escape(nm)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pt">{r["points"]}</td></tr>'
        )
    # الترتيب المباشر: سمات data-lt/ss/lid لموسم الدوري الحالي فقط (وبلا JOR)؛ راجع live_view.py (ltPaint) وmake_live_tables.py
    code = m["league_code"]
    lt = (f' data-lt="{code}" data-ss="{m["season"]}" data-lid="{LEAGUES[code]["id"]}"'
          if m["season"] == LATEST_SEASON and code in LEAGUES and code != "JOR" else "")
    return (f'<h2>{MT[lang]["table"]}</h2><table class="lgt"{lt}><tr><th class="ps">{t["pos"]}</th>'
            f'<th class="r">{t["team"]}</th><th>{t["played"]}</th><th>{t["won"]}</th>'
            f'<th>{t["drawn"]}</th><th>{t["lost"]}</th><th>{t["gd"]}</th>'
            f'<th>{t["points"]}</th></tr>{body}</table>')


def build_tabs(panels, is_upcoming, lang):
    """
    panels: {tab: html} لما فيه داتا فقط (الأحداث للقادمة تُبقى لأنها تحمل رسالة «لم تبدأ/مباشر» التي يبدّلها live_view).
    الافتراضي: المنتهية → الأحداث إن وُجدت وإلا أول متاح؛ القادمة → التشكيلات إن وُجدت ثم المواجهات ثم الأحداث.
    تبويب واحد أو لا شيء = بلا شريط.
    """
    # (14 أكتوبر) الافتراضي دائماً التبويب الأول: للقادمة «نظرة عامة/Preview» (لوحة الأحداث نفسها)، وللحيّة/المنتهية «الأحداث/Events»
    avail = [k for k in MT_ORDER if panels.get(k)]
    if not avail:
        return ""
    default = avail[0]
    secs = "".join(
        f'<section class="mp{" on" if k == default else ""}" data-tab="{k}">{panels[k]}</section>'
        for k in avail)
    if len(avail) < 2:
        return secs
    def _lbl(k):
        if k == "events" and is_upcoming:
            return f'<button class="mtab{" on" if k == default else ""}" data-tab="events" role="tab" data-live="{MT[lang]["events"]}">{MF[lang]["preview"]}</button>'
        return f'<button class="mtab{" on" if k == default else ""}" data-tab="{k}" role="tab">{MT[lang][k]}</button>'
    bar = "".join(_lbl(k) for k in avail)
    return f'<div class="mtabs" role="tablist">{bar}</div>{secs}'


# ⚠️ أحدث موسم بالداتا — يُملأ في main() مرة واحدة
LATEST_SEASON = None


def build_page(m, h, a, items, fix, lang, stats_html="", lineup_html="",
               h2h_html="", table_html="", form_html=""):
    """صفحة مباراة واحدة بلغة واحدة"""
    t = T[lang]
    mid = m["match_id"]
    season = m["season"]
    lg = league_name(m["league_code"], lang)
    is_upcoming = m["home_goals"] is None or m["away_goals"] is None
    # مؤجّلة/ملغاة: تسمية الحالة بدل الوقت وكلمة «قادمة»
    off = off_label(m["status"], t)

    # الوقت من حقل التاريخ: "2026-09-01 18:00"
    # ⚠️ **الموسم الجاري يُحسب من الداتا لا من `config.SEASON`.**
    #    ذاك ثابت افتراضي للسحب، وربط العرض به هش: من يغيّره
    #    ليسحب موسماً قديماً يغيّر ما يُعرض دون قصد.
    season_txt = ("" if season == LATEST_SEASON
                  else f' · {t["season"]} {season}-{season + 1}')

    # UTC خام — نفس آلية matchtime.py (data-utc + تسمية صريحة)،
    # مصدر واحد للقصّ يخدم كل استخدامات التاريخ/الوقت بهذه الدالة.
    # ⚠️ **`desc` بـhead_meta نص خام لا HTML** — لا data-utc ممكن
    #    هناك (وسم meta لا عنصر DOM)، فيبقى تاريخاً فقط بلا وقت
    #    بقصد — محرك البحث/الروبوت لا يحوّل شيئاً على أي حال.
    date_parts = str(m["date"]).split()
    date_only = date_parts[0]
    clock = (date_parts[1][:5]
             if len(date_parts) > 1 and date_parts[1][:5] and not off
             else "")

    kickoff_html = ""
    # قادمة بوقت فعلي: الوقت كبير بـ.score (data-utc: matchtime يحوّله محلياً) وتحته .kick يملؤه matchtime.py
    # (data-cd): <24س عدّ تنازلي HH:MM:SS ثم «بلشت»، وأبعد من 24س التاريخ. بلا JS يبقى التاريخ (UTC) نصاً ثابتاً.
    countdown = bool(is_upcoming and clock and not off)
    if countdown:
        kickoff_html = (f'<span class="kick dt" data-cd="page" '
                        f'data-ko="{date_only}T{clock}:00Z">{date_only}</span>')

    # ⚠️ **بلا شرط `is_upcoming`** — بعكس `kickoff_html` أعلاه —
    #    بقصد: بمجرد ما تحمل مباراة منتهية وقتاً فعلياً (بعد
    #    إصلاح `fetch_matches2.py`)، هذا الشريط يعرضه تلقائياً
    #    (نفس نمط `make_clubs.py::build_cards`، غير مغلوط، سلوك
    #    مقصود لا أثر جانبي).
    if clock:
        date_html = (f'<span data-utcd="{date_only}T{clock}:00Z">'
                     f'{date_only}</span> '
                     f'<span data-utc="{date_only}T{clock}:00Z">'
                     f'{clock} UTC</span>')
    else:
        date_html = date_only

    up = "../" if lang == "ar" else "../../"

    # شارة نهاية المباراة تحت النتيجة بنمط دقيقة البث (12 أكتوبر): «FT» بالعربي والإنجليزي (AET/PEN كما هي)
    ft_html = (f'<span class="ftb">{m["status"]}</span>'
               if not is_upcoming and m["status"] in ("FT", "AET", "PEN") else "")

    # ⚠️ **عنوان/وصف للفهرسة:** النتيجة والموسم والتاريخ، واللاعبون إن وُجدوا.
    #    الموسم يظهر دائماً هنا (حتى الجاري) بخلاف شريط الصفحة. العربي
    #    بمسافات حول الشرطة ("2 - 0") كما بالصفحة — بدونها يُعرَض "2-0"
    #    كسلسلة LTR واحدة داخل نص RTL فيلتصق الصفر بالمضيف.
    #    الأهداف الملغاة (icon 🚫) وبلا دقيقة (999) تُستثنى؛ نص اللاعبين
    #    يُقتطع عند 90 حرفاً.
    season_lbl = f'{season}-{season + 1}'
    hn, an = tname(h, lang), tname(a, lang)
    if is_upcoming:
        mid_txt = f'{hn} × {an}'
        meta_desc = (f'{lg} · {season_lbl} · {date_only} — {mid_txt}'
                     + (f' ({off})' if off else ''))
    else:
        dash = " - " if lang == "ar" else "-"
        mid_txt = f'{hn} {m["home_goals"]}{dash}{m["away_goals"]} {an}'
        goals_txt = ("، " if lang == "ar" else ", ").join(
            f"{it['plain']} {it['min']}'" for it in items
            if it["icon"] == "⚽" and it["min"] != 999
            and it.get("plain"))[:90]
        meta_desc = (f'{lg} · {season_lbl} · {date_only} — '
                     f'{t["match_result"]}: {mid_txt}'
                     + (f'. {t["match_scorers"]}: {goals_txt}'
                        if goals_txt else ''))
    page_title = html_escape(
        f'{mid_txt} | {lg} {season_lbl} · {date_only} — {t["site_title"]}')
    meta_desc = html_escape(meta_desc)

    # قائمة الأحداث
    if items:
        rows = ""
        for it in items:
            is_home = it["team"] == m["home_id"]
            cls = "" if it["major"] else " minor"
            mn = "؟" if it["min"] == 999 else it["min"]
            kind_html = (f'<span class="kind">{it["kind"]}</span>'
                         if it["kind"] else "")
            # الأيقونة بجانب الدقيقة (وسط الخط) والاسم بعيداً عنها: المضيف [اسم أيقونة] والضيف [أيقونة اسم]
            ic = f'<span class="ic">{it["icon"]}</span>'
            txt = f'<span class="evt">{it["body"]}{kind_html}</span>'
            cell = (f'<span class="evc on">{txt}{ic}</span>' if is_home
                    else f'<span class="evc on">{ic}{txt}</span>')
            blank = '<span class="evc"></span>'
            rows += (
                f'<div class="ev {"h" if is_home else "a"}{cls}">'
                + (cell if is_home else blank)
                + f'<span class="min">{mn}\'</span>'
                + (blank if is_home else cell) + '</div>'
            )

        has_minor = any(not it["major"] for it in items)
        tabs = ""
        if has_minor:
            tabs = (f'<div class="vtabs">'
                    f'<button class="vtab on" data-v="all">'
                    f'{t["view_all_events"]}</button>'
                    f'<button class="vtab" data-v="key">'
                    f'{t["view_key_events"]}</button>'
                    f'</div>')

        events_html = (f'<h2>{t["match_events"]}</h2>{tabs}'
                       f'<div class="goals" id="evbox">{rows}</div>')
        events_html += form_html   # الفورمة أسفل قائمة الأحداث
    else:
        if is_upcoming:
            msg = off_msg(m["status"], t) or t["not_started"]
        else:
            total = (m["home_goals"] or 0) + (m["away_goals"] or 0)
            msg = t["goalless"] if total == 0 else t["no_details"]
        # id=evempty: live_view يستبدل «لم تبدأ بعد» بـ«مباشر — الأحداث بتنزل بعد الماتش» أثناء البث
        events_html = (f'<h2 id="evh" data-live="{MT[lang]["events"]}">{MF[lang]["preview"] if is_upcoming else t["match_events"]}</h2>'
                       f'<div class="empty" id="evempty">{msg}</div>')
        events_html += form_html   # قادمة: تحت رسالة «لم تبدأ»؛ منتهية بلا تفاصيل: تحت الرسالة

    # شارة التصحيح
    fix_block = ""
    if fix:
        fix_block = (
            f'<div class="fixed">'
            f'<b>{t["corrected"]}</b>'
            f'<div class="row">{fix["note"]}</div>'
            f'<div class="row">{t["source"]}: {fix["source"]}</div>'
            f'</div>'
        )

    # تبويبات تحت رأس النتيجة (12 أكتوبر): كل قسم لوحة، تُحذف اللوحة الفارغة؛ لا طلبات جديدة ولا تخزين
    tabs_block = build_tabs({
        "events": events_html if (items or is_upcoming or form_html) else "",
        "lineups": lineup_html, "stats": stats_html,
        "table": table_html, "h2h": h2h_html}, is_upcoming, lang)
    if not tabs_block:   # منتهية بلا أي داتا: رسالة الأحداث وحدها
        tabs_block = events_html

    home = '../index.html'
    switch = (f'../en/matches/{mid}.html' if lang == "ar"
              else f'../../matches/{mid}.html')

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{page_title}</title>\n'
        + head_meta(html_escape(mid_txt), meta_desc,
                    "../" if lang == "ar" else "../../", lang,
                    f"matches/{mid}.html" if lang == "ar"
                    else f"en/matches/{mid}.html")
        + THEME_HEAD + assets.css_links("match") +
        # بلا JS: كل اللوحات ظاهرة بالتسلسل (والشريط مخفي)
        '<noscript><style>.mp{display:block!important}.mp>h2:first-child{display:block!important}'
        '.mtabs{display:none}</style></noscript>\n'
        '</head>\n<body>\n<div class="wrap">\n'
        + appbar(t, lang, switch, back=True,
                 extra=match_actions_html(mid, f"{date_only}T{clock or '23:59'}:00Z", lang, html_escape(f"{hn} \u00d7 {an}", quote=True)))
        + push_ui_msg() +
        # ⚠️ **الموسم يظهر للمواسم القديمة فقط.** الموسم الجاري
        #    بديهي للزائر، لكن من يصل من بحث جوجل لمباراة 2022
        #    يحتاج معرفته. الشريط: الدوري · [الموسم إن كان قديماً]
        #    · التاريخ.
        # ⚠️ سطر التاريخ حُذف (12 أكتوبر): وقت الانطلاق القادم يبقى بـ.big (الوقت + .kick). يبقى التاريخ فقط لقادمة بلا وقت إطلاقاً.
        f'<div class="meta-top">{lg}'
        f'{season_txt}'
        f'{(" · " + date_html) if (is_upcoming and not clock) else ""}</div>\n'
        f'<div class="head">'
        f'<a class="team" href="../clubs/{m["home_id"]}.html">'
        f'{logo_tag(h, lang, 60, big=True, eager=True)}'
        f'<span>{tname(h, lang)}</span><div class="scl" data-sc="h"></div></a>'
        # ⚠️ **وقت المباراة تحت العنوان مباشرة.** كان الوقت في
        #    الشريط الرمادي أعلى الصفحة فقط، فيصعب التقاطه —
        #    والزائر يفتح مباراة قادمة ليعرف متى تُلعب.
        f'<div class="big{" cd" if countdown else (" soon" if is_upcoming else "")}" data-mid="{m["match_id"]}">'
        + (f'<span class="score" data-utc="{date_only}T{clock}:00Z">{clock} UTC</span>' if countdown else
        f'<span class="score">'
        f'{(off or t["upcoming"]) if is_upcoming else str(m["home_goals"]) + " - " + str(m["away_goals"])}'
        f'</span>') +
        ft_html +
        f'{kickoff_html}'
        f'</div>'
        f'<a class="team" href="../clubs/{m["away_id"]}.html">'
        f'{logo_tag(a, lang, 60, big=True, eager=True)}'
        f'<span>{tname(a, lang)}</span><div class="scl" data-sc="a"></div></a>'
        f'</div>\n'
        f'{fix_block}\n'
        f'{tabs_block}\n'
        '</div>\n'
        # ⚠️ **العمق يتبع اللغة:** الصفحة العربية بـ`matches/`
        #    (عمق 1) والإنجليزية بـ`en/matches/` (عمق 2).
        #    تمرير 1 ثابتاً كان يجعل زر "المباريات" يحلّ إلى
        #    `en/matches/index.html` — صفحة غير موجودة (404).
        + navbar(t, 1 if lang == "ar" else 2, "", lang)
        + pwa_offbar(lang)
        + assets.script_tags("match", lang) +
        '</body>\n</html>'
    )


def main():
    global LATEST_SEASON
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    LATEST_SEASON = conn.execute(
        "SELECT MAX(season) FROM matches").fetchone()[0]
    conn.row_factory = sqlite3.Row
    teams = load_teams()
    fixes = load_corrections()
    build_form_index(conn)   # استعلام واحد لفورمة كل الصفحات (بلا طلبات API)

    os.makedirs(BASE / "matches", exist_ok=True)
    os.makedirs(BASE / "en" / "matches", exist_ok=True)

    q = """SELECT match_id, league_code, season, date,
                  home_id, away_id, home_goals, away_goals, status
           FROM matches"""
    params = []
    if ONLY:
        q += " WHERE league_code = ?"
        params.append(ONLY)

    matches = conn.execute(q, params).fetchall()

    made = skipped = fixed_n = 0

    for m in matches:
        mid = m["match_id"]
        h = teams.get(m["home_id"])
        a = teams.get(m["away_id"])

        if not h or not a:
            skipped += 1
            continue

        fix = fixes.get(mid)
        if fix:
            fixed_n += 1

        for lang in LANGS:
            items = build_items(conn, mid, lang)
            stats_html = build_stats(conn, mid, m["home_id"],
                                     m["away_id"], lang)
            h2h_html = build_h2h(conn, m, h, a, lang, tname, logo_url, teams)
            lineup_html = build_lineups(conn, m, h, a, lang, T,
                                        tname, logo_url)
            table_html = build_table_panel(conn, m, teams, lang)
            form_html = build_form_card(m, h, a, teams, lang)
            if m["home_goals"] is None:   # النظرة العامة للقادمة: مركزا الفريقين تحت الفورمة (دفعة D2)
                form_html += build_positions(conn, m, teams, lang)
            html = build_page(m, h, a, items, fix, lang, stats_html,
                              lineup_html, h2h_html, table_html, form_html)
            out = ((BASE / "matches" / f"{mid}.html") if lang == "ar"
                   else (BASE / "en" / "matches" / f"{mid}.html"))
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)

        made += 1

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} مباراة × لغتين")
    print("  matches/  +  en/matches/")
    if fixed_n:
        print(f"  منها {fixed_n} بشارة 'نتيجة مصححة'")
    if skipped:
        print(f"  متخطى: {skipped} (نادٍ غير موجود بجدول teams)")
    print(f"{'=' * 55}")
    print("""
  جرّب:
      start matches\\1252470.html
      start en\\matches\\1252470.html
    """)


if __name__ == "__main__":
    main()
