#!/usr/bin/env python3
"""
الصفحة الرئيسية — بلغتين
===========================
بيولّد نسختين:
    index.html       → العربي (RTL)
    en/index.html    → الإنجليزي (LTR)

بنية الصفحة:
    شريط أيام أفقي (30 للخلف · اليوم · 90 للأمام = 121 يوماً)
    ولكل يوم: الدوريات أقساماً قابلة للطي، بعلم دائري واسم
    الدوري وعدد مبارياته. اليوم الفارغ يعرض "لا مباريات".

⚠️ **كل الأيام تُرسَم في HTML** والتبديل بإظهار/إخفاء — لا طلبات
   شبكة عند تغيير اليوم. النافذة ~252 مباراة والصفحة ~175 ك.ب.

⚠️ **الأقسام `<details>` لا JavaScript** — الطي يعمل بلا سكربت،
   والسكربت للتبديل بين الأيام فقط.

⚠️ **بطاقات الدوريات والجداول والهدافون انتقلوا لـ`leagues.html`**
   (21 أغسطس) — الرئيسية صارت للمباريات فقط، وزر "الدوريات"
   بالشريط السفلي صار يشير لصفحة مستقلة بدل مرساة `#tables`.
   تبقى `SCRIPT` و`render_panel` و`get_table` معرَّفة هنا لأن
   `make_leagues.py` يستوردها من هذا الملف.

كل النصوص من i18n.py.

⚠️ المباريات القادمة (home_goals = NULL) مستثناة من حساب الجدول
   ومن قسم "آخر النتائج".

التشغيل:
    python make_site3.py
"""

import sqlite3
import csv
import os
from datetime import datetime, date, timedelta
from config import DB_FILE, TEAMS_FILE, LEAGUES, BASE_DIR
from tiebreak import sort_table, STANDINGS_EXCLUDED
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from search_view import (SEARCH_CSS, search_box, search_script,
                         search_overlay)
from navbar import (NAV_CSS, navbar, settings_overlay,
                    nav_script, WIZ_ROW_SCRIPT, pwa_script)
from live_view import LIVE_CSS, live_script
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   head_meta)
from onboard import wizard_html, wizard_style, wizard_script
from prefs import prefs_script
from player_slug import slug as _pslug

BASE = DB_FILE.parent

# ملفات الأعلام في flags/ — 256×192 تُقصّ دائرةً بالـCSS
FLAG = {"JOR": "jo", "IRQ": "iq", "SAU": "sa", "EGY": "eg", "UAE": "ae",
        "QAT": "qa", "MAR": "ma"}

# شيفرونات أسهم شريط الأيام — الاتجاه فيزيائي ومحسوم هنا
CHEV_L = '<svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>'
CHEV_R = '<svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>'


SCRIPT = """
<script>
  const leagueTabs  = document.querySelectorAll('.tab-league');
  const seasonTabs  = document.querySelectorAll('.tab-season');
  const sections    = document.querySelectorAll('.panel');

  let current = { league: null, season: null };

  function render() {
    sections.forEach(s => s.classList.remove('visible'));

    const id = current.season + '_' + current.league;
    const target = document.getElementById(id);

    if (target) {
      target.classList.add('visible');
      document.getElementById('empty').style.display = 'none';
    } else {
      document.getElementById('empty').style.display = 'block';
    }

    leagueTabs.forEach(t =>
      t.classList.toggle('active', t.dataset.league === current.league));
    seasonTabs.forEach(t =>
      t.classList.toggle('active', t.dataset.season === current.season));
  }

  leagueTabs.forEach(t => {
    t.addEventListener('click', function () {
      current.league = this.dataset.league;
      render();
    });
  });

  seasonTabs.forEach(t => {
    t.addEventListener('click', function () {
      current.season = this.dataset.season;
      render();
    });
  });

  if (seasonTabs.length && leagueTabs.length) {
    current.season = seasonTabs[0].dataset.season;
    current.league = leagueTabs[0].dataset.league;
    render();
  }

  document.querySelectorAll('.jump').forEach(function (b) {
    b.addEventListener('click', function () {
      current.season = this.dataset.s;
      current.league = this.dataset.l;
      render();
      document.getElementById('tables').scrollIntoView({behavior:'smooth'});
    });
  });
</script>
"""



DAY_SCRIPT = """
<script>
(function(){
  var tabs=document.querySelectorAll('.daytab');
  var strip=document.getElementById('daytabs');
  if(!tabs.length)return;

  function show(day){
    document.querySelectorAll('.daypanel').forEach(function(p){
      p.classList.toggle('visible', p.id === 'd' + day);
    });
    tabs.forEach(function(b){
      b.classList.toggle('active', b.dataset.day === day);
    });
  }

  // ⚠️ الضغط على يوم **يمرّر الشريط لتمركزه** فيظهر اليوم التالي
  //    والسابق حوله. بدونه، الضغط على آخر تبويب ظاهر يُبقي ما
  //    بعده مخفياً فيبدو الشريط كأنه انتهى.
  tabs.forEach(function(b,i){
    b.addEventListener('click',function(){
      show(this.dataset.day);
      center(i, 1);
    });
  });

  // ⚠️ اليوم يبدأ نشطاً من التوليد — نمرّر الشريط ليظهر بالوسط.
  //    scrollIntoView وحده يمرّر الصفحة كلها للأسفل على الجوال،
  //    فنحسب الإزاحة داخل الشريط يدوياً.
  // ⚠️ scrollLeft يدوياً يكسر مع RTL — المتصفحات تعطي قيماً
  //    سالبة أو معكوسة. scrollIntoView مع inline:'center' يتولّاها
  //    صحيحاً بالاتجاهين، و block:'nearest' يمنع تمرير الصفحة
  //    كلها للأسفل على الجوال.
  // ⚠️ التنقل بمؤشّر على مصفوفة التبويبات لا بـscrollLeft —
  //    قيم scrollLeft معكوسة أو سالبة مع RTL حسب المتصفح،
  //    بينما scrollIntoView صحيح بالاتجاهين دائماً.
  var view = 0;
  tabs.forEach(function(b,i){ if(b.classList.contains('active')) view=i; });

  var prev=document.getElementById('dayprev');
  var next=document.getElementById('daynext');
  var STEP=5;

  function center(i, smooth){
    view = Math.max(0, Math.min(tabs.length-1, i));
    var el = tabs[view];
    if(el&&el.scrollIntoView){
      try{ el.scrollIntoView({inline:'center', block:'nearest',
                              behavior: smooth ? 'smooth' : 'auto'}); }
      catch(e){ el.scrollIntoView(); }
    }
    if(prev) prev.disabled = (view <= 0);
    if(next) next.disabled = (view >= tabs.length-1);
  }

  // inline-start = الأيام الأقدم بالاتجاهين
  if(prev) prev.addEventListener('click',function(){ center(view-STEP,1); });
  if(next) next.addEventListener('click',function(){ center(view+STEP,1); });

  // ⚠️ استدعاء واحد لا يكفي: السكربت ينفَّذ قبل أن تستقر أعرض
  //    التبويبات (الخطوط والصور)، فيُحسب الموضع على عرض خاطئ
  //    ويقف الشريط على أيام بعيدة عن اليوم. نعيده بعد التخطيط.
  center(view, 0);
  if(window.requestAnimationFrame){
    requestAnimationFrame(function(){ center(view, 0); });
  }
  window.addEventListener('load', function(){ center(view, 0); });
})();
</script>"""

STYLE = """
<style>""" + VARS + """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:900px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:6px; }
  .lang { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:var(--card2); color:var(--text); }
  header { text-align:center; margin-bottom:26px; }
  h1 { font-size:26px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  h2 { font-size:17px; margin:28px 0 12px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  h2.hero { margin-top:0; }

  /* بطاقات الدوريات */
  .lgrid { display:flex; gap:10px; flex-wrap:wrap; }
  .lcard { flex:1; min-width:200px; background:var(--card);
           border:1px solid var(--line); border-radius:11px; padding:16px;
           cursor:pointer; font-family:inherit; text-align:start;
           transition:.15s; color:var(--text); }
  .lcard:hover { background:var(--card2); border-color:var(--accent); }
  .lcard .ln { font-size:15px; font-weight:600; }
  .lcard .ls { color:var(--muted); font-size:12px; margin-top:2px; }
  .lcard .lead { display:flex; align-items:center; gap:9px;
                 margin-top:12px; font-size:14px; }
  .lcard .lead img { width:26px; height:26px; object-fit:contain; }
  .lcard .pts { color:var(--accent); font-weight:700; margin-inline-start:auto; }

  /* شريط الأيام */
  .daynav { display:flex; align-items:stretch; gap:2px;
            margin-bottom:6px; }
  .dayarrow { flex:0 0 30px; background:var(--card); border:none;
              border-radius:9px; cursor:pointer; color:var(--muted);
              display:flex; align-items:center; justify-content:center;
              padding:0; transition:background .15s, color .15s; }
  .dayarrow:hover { background:var(--card2); color:var(--text); }
  .dayarrow:disabled { opacity:.3; cursor:default;
                       background:var(--card); }
  /* ⚠️ **SVG لا حدود CSS.** حيلة الحدّين + rotate(45deg) تنكسر
     مع RTL: الحدود المنطقية تنعكس والدوران لا ينعكس معها فيصير
     السهم عمودياً. والقلب اليدوي عبر [dir="rtl"] يعتمد على
     ترتيب القواعد والتخزين المؤقت. الاتجاه هنا يُحسم في بايثون
     لأننا نولّد ملفاً لكل لغة أصلاً — لا التباس ممكن. */
  .dayarrow svg { width:15px; height:15px; display:block;
                  fill:none; stroke:currentColor; stroke-width:2.2;
                  stroke-linecap:round; stroke-linejoin:round; }

  .daytabs { display:flex; gap:4px; overflow-x:auto; padding:4px 0 10px;
             scrollbar-width:none; -ms-overflow-style:none;
             scroll-behavior:smooth; flex:1; min-width:0; }
  .daytabs::-webkit-scrollbar { display:none; }
  /* ⚠️ خمسة تبويبات بالعرض بالضبط — الباقي بالتمرير يميناً
     ويساراً. flex:0 0 auto كان يعرض 13 يوماً على الشاشة العريضة
     فيضيع تمركز اليوم ويصعب التصفّح. */
  .daytab { flex:0 0 calc((100% - 16px) / 5);
            background:none; border:none;
            border-bottom:2px solid transparent; cursor:pointer;
            font-family:inherit; color:var(--muted); padding:7px 14px;
            display:flex; flex-direction:column; align-items:center;
            gap:1px; line-height:1.25; transition:color .15s; }
  .daytab .dn { font-size:14px; font-weight:600; white-space:nowrap; }
  .daytab .dd { font-size:11px; opacity:.75; }
  .daytab:hover { color:var(--text); }
  .daytab.active { color:var(--accent); border-bottom-color:var(--accent); }

  .daypanel { display:none; }
  .daypanel.visible { display:block; }
  .noday { text-align:center; color:var(--muted); padding:44px 20px;
           background:var(--card); border-radius:12px; font-size:14px; }

  /* أقسام الدوريات القابلة للطي */
  .lgsec { background:var(--card); border-radius:12px; margin-bottom:10px;
           overflow:hidden; }
  .lgsec > summary { display:flex; align-items:center; gap:11px;
           padding:13px 14px; cursor:pointer; list-style:none;
           user-select:none; }
  .lgsec > summary::-webkit-details-marker { display:none; }
  .lgsec > summary:hover { background:var(--card2); }
  .flag { width:26px; height:26px; border-radius:50%; object-fit:cover;
          flex:0 0 auto; }
  .lgname { font-size:14px; font-weight:600; flex:1; min-width:0;
            overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .lgnum { background:var(--deep); color:var(--muted); font-size:12px;
           min-width:24px; text-align:center; padding:2px 7px;
           border-radius:20px; }
  .chev { width:9px; height:9px; border-inline-end:2px solid var(--muted);
          border-bottom:2px solid var(--muted); transform:rotate(45deg);
          margin-inline-start:2px; transition:transform .18s; }
  .lgsec[open] > summary .chev { transform:rotate(-135deg); }
  .lgbody { padding:0 10px 10px; }
  .lgbody .match { background:var(--deep); }

  /* المباريات */
  /* ═══ بطاقة نادٍ في "أنديتي" ═══
     ⚠️ **ضاعت هذه الأنماط عند إضافتها أول مرة** (27 أغسطس)،
     فظهرت البطاقة نصاً خاماً بلا تنسيق. البنية كانت سليمة
     والكلاسات موجودة — الناقص كان الـCSS وحده. */
  .myc { background:var(--card); border-radius:12px;
         margin-bottom:10px; overflow:hidden; }
  .mhead { display:flex; align-items:center; gap:10px;
           padding:13px 14px; text-decoration:none; color:var(--text);
           border-bottom:1px solid var(--line); }
  .mhead img { width:30px; height:30px; object-fit:contain;
               flex-shrink:0; }
  .mnm { font-size:15px; font-weight:600; flex:1; min-width:0;
         overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .mpos { font-size:12px; color:var(--muted); white-space:nowrap; }
  .mpts { font-size:12px; color:var(--accent); font-weight:700;
          margin-inline-start:8px; white-space:nowrap; }
  .mrow { display:flex; align-items:center; gap:10px;
          padding:11px 14px; text-decoration:none; color:var(--text);
          font-size:13px; }
  .mrow + .mrow { border-top:1px solid var(--line); }
  .mrow:hover { background:var(--card2); }
  .ml { color:var(--muted); font-size:11px; min-width:62px;
        flex-shrink:0; }
  .mm { flex:1; min-width:0; display:flex; align-items:center;
        justify-content:center; gap:9px; overflow:hidden;
        white-space:nowrap; }
  .mm b { color:var(--accent); font-size:14px; white-space:nowrap; }
  .md { color:var(--muted); font-size:11px; white-space:nowrap;
        flex-shrink:0; }

  .match { background:var(--card); border-radius:10px; padding:13px;
           margin-bottom:8px; display:grid;
           grid-template-columns:1fr auto 1fr; align-items:center; gap:10px;
           position:relative; }
  /* الرابط الغامر: يغطي البطاقة كلها تحت المحتوى */
  .match .open { position:absolute; inset:0; z-index:1;
                 border-radius:10px; }
  .match:hover { background:var(--card2); }
  /* الروابط الفعلية تعلو الغامر فتبقى قابلة للضغط */
  .match .side, .match .date { position:relative; z-index:2; }
  .match.soon { border-inline-start:3px solid var(--accent); }
  /* ⚠️ `.side` يملأ عموده كاملاً بشبكة 1fr، فالضغط على الفراغ
     يمين النادي أو يساره كان يفتح صفحة النادي لا المباراة.
     `width:max-content` يقصره على الشعار والاسم فقط، ويبقى
     الفراغ حوله للرابط الغامر. */
  .side { display:inline-flex; align-items:center; gap:8px;
          font-size:14px; min-width:0; max-width:100%;
          width:max-content; text-decoration:none; color:var(--text); }
  .side.away { justify-content:flex-end; margin-inline-start:auto; }
  .side img { width:26px; height:26px; object-fit:contain; }
  .side span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  a.side:hover span { color:var(--accent); }
  .score { font-size:18px; font-weight:700; padding:4px 13px;
           background:var(--deep); border-radius:6px; white-space:nowrap; }
  .score.time { font-size:14px; color:var(--accent); }
  .date { grid-column:1/-1; text-align:center; color:var(--muted);
          font-size:11px; margin-top:5px; }
  .date a { color:var(--muted); text-decoration:none; }
  .date a:hover { color:var(--accent); }
  .lg { color:var(--muted); font-size:11px; }

  /* التبويبات */
  .divider { border:none; border-top:1px solid var(--line); margin:38px 0 24px; }
  .tabs { display:flex; gap:8px; justify-content:center;
          margin-bottom:12px; flex-wrap:wrap; }
  .tabs.seasons { margin-bottom:20px; }
  .tab { background:var(--card); color:var(--muted); border:1px solid var(--line);
         padding:8px 18px; border-radius:8px; cursor:pointer;
         font-family:inherit; font-size:14px; transition:.15s; }
  .tab:hover { background:var(--card2); color:var(--text); }
  .tab.active { background:var(--accent); color:var(--bg); border-color:var(--accent); }
  .tab-season { padding:6px 14px; font-size:13px; }
  .tab-season.active { background:var(--green); border-color:var(--green); }
  .panel { display:none; }
  .panel.visible { display:block; }
  #empty { display:none; text-align:center; color:var(--muted);
           padding:50px 20px; background:var(--card); border-radius:10px; }

  /* الجدول */
  table { width:100%; border-collapse:collapse; background:var(--card);
          border-radius:10px; overflow:hidden; }
  th,td { padding:10px 8px; text-align:center; font-size:14px; }
  th { background:var(--card2); color:var(--muted); font-size:12px; }
  th.r { text-align:start; }
  tr { border-bottom:1px solid var(--line); }
  tr:last-child { border-bottom:none; }
  .team { text-align:start; display:flex; align-items:center; gap:9px;
          min-width:0; }
  .team img { width:22px; height:22px; object-fit:contain; }
  .team a { color:var(--text); text-decoration:none; overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap; }
  .team a:hover { color:var(--accent); }
  .pos { color:var(--muted); width:34px; }
  .pts { font-weight:700; color:var(--accent); }
  .top .pos { color:var(--green); font-weight:700; }
  .bottom .pos { color:var(--red); }

  /* الهدافون */
  ol { list-style:none; background:var(--card); border-radius:10px; padding:6px; }
  ol li { display:flex; align-items:center; gap:12px; padding:9px 12px;
          border-bottom:1px solid var(--line); font-size:14px; }
  ol li:last-child { border-bottom:none; }
  .num { color:var(--muted); width:20px; }
  .pname { flex:1; min-width:0; overflow:hidden;
           text-overflow:ellipsis; white-space:nowrap; }
  .pname a { color:var(--text); text-decoration:none; }
  .pname a:hover { color:var(--accent); }
  .pteam { color:var(--muted); font-size:12px; }
  .pgoals { font-weight:700; color:var(--accent); min-width:22px;
            text-align:end; }
  .meta { color:var(--muted); font-size:12px; text-align:center;
          margin-top:14px; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }
""" + wizard_style() + """
""" + SEARCH_CSS + NAV_CSS + """
""" + SEARCH_CSS + NAV_CSS + LIVE_CSS + """
</style>"""


def clean(t):
    return (t or "").strip()


def load_overrides():
    """الشعارات المحلية"""
    logos = {}
    if not TEAMS_FILE.exists():
        return logos
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = clean(row.get("team_id"))
            if tid and clean(row.get("logo_local")):
                logos[tid] = clean(row.get("logo_local"))
    return logos


def available(conn):
    """تركيبات موسم/دوري فيها مباريات"""
    return conn.execute("""
        SELECT season, league_code, COUNT(*) AS n
        FROM matches
        GROUP BY season, league_code
        ORDER BY season DESC, league_code
    """).fetchall()


def tname(row, lang, ar_key="name", en_key="name_en"):
    if lang == "ar":
        return clean(row[ar_key]) or clean(row[en_key])
    return clean(row[en_key]) or clean(row[ar_key])


def get_table(conn, code, season):
    """جدول الترتيب — المباريات غير المنتهية والمستبعَدة من الترتيب مستثناة"""
    # ⚠️ STANDINGS_EXCLUDED: مباريات حقيقية (ملاحق صعود/هبوط) تبقى
    #    ظاهرة بصفحتها لكن لا تُحسب هنا — راجع standings_exclusions.csv
    excl_ids = STANDINGS_EXCLUDED or {0}   # ⚠️ 0 حارس — لا مباراة بهالمعرّف
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
        SELECT t.team_id, t.short_name_ar AS name,
            COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS name_en,
            t.logo,
            COUNT(*) AS played,
            SUM(CASE WHEN gf > ga THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gf = ga THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN gf < ga THEN 1 ELSE 0 END) AS losses,
            SUM(gf) - SUM(ga) AS diff,
            SUM(gf) AS scored,
            SUM(CASE WHEN gf > ga THEN 3
                     WHEN gf = ga THEN 1 ELSE 0 END) AS points
        FROM all_games
        JOIN teams t ON t.team_id = all_games.team
        GROUP BY t.team_id, t.short_name_ar
        ORDER BY points DESC
    """, (code, season, *excl_ids,
          code, season, *excl_ids)).fetchall()
    return sort_table(conn, code, season, rows)


def get_matches(conn, code, season, limit=10):
    """آخر النتائج المنتهية"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               m.league_code,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en,
               a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ?
          AND m.home_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?
    """, (code, season, limit)).fetchall()


def get_scorers(conn, code, season, limit=10):
    return conn.execute("""
        SELECT g.player_en AS player, g.player_ar AS player_ar,
               t.short_name_ar AS team,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS team_en,
               COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t ON t.team_id = g.team_id
        WHERE g.player_en != ''
          AND m.league_code = ? AND m.season = ?
        GROUP BY g.player_en, t.short_name_ar
        ORDER BY goals DESC LIMIT ?
    """, (code, season, limit)).fetchall()

_PLAYER_PAGES = None
def _player_pages(base_dir):
    """كاش أسماء ملفات players/*.html — يُبنى مرة واحدة فقط"""
    global _PLAYER_PAGES
    if _PLAYER_PAGES is None:
        d = base_dir / "players"
        _PLAYER_PAGES = ({f.stem for f in d.glob("*.html")}
                         if d.exists() else set())
    return _PLAYER_PAGES


def player_link(player_en, base_dir, depth):
    """
    رابط صفحة اللاعب إن وُجدت فعلاً كملف، وإلا "" .
    depth: عمق الصفحة الحالية من الجذر (0=رئيسية، 1=clubs/matches)
    """
    s = _pslug(player_en)
    if s not in _player_pages(base_dir):
        return ""
    return ("../" * depth) + f"players/{s}.html"


# نافذة الأيام المعروضة بالرئيسية: 30 للخلف + اليوم + 90 للأمام
# ⚠️ التوسيع رخيص: 29 يوماً = 135 مباراة، و121 يوماً = 252 فقط
#    (المباريات لا تتضاعف خطياً — الدوريات فيها فجوات)
DAYS_BACK = 30
DAYS_FWD = 90


def window_matches(conn, start, end):
    """كل مباريات النافذة — منتهية وقادمة معاً، مرتّبة بالوقت"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               m.league_code, m.season,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en,
               a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE DATE(m.date) BETWEEN ? AND ?
        ORDER BY m.date ASC
    """, (start.isoformat(), end.isoformat())).fetchall()


def day_label(d, today, t):
    """أمس / اليوم / غداً — وإلا اسم اليوم مع التاريخ"""
    delta = (d - today).days
    if delta == 0:
        return t["d_today"], f'{d.day}/{d.month}'
    if delta == -1:
        return t["d_yesterday"], f'{d.day}/{d.month}'
    if delta == 1:
        return t["d_tomorrow"], f'{d.day}/{d.month}'
    return t["WEEKDAYS"][d.weekday()], f'{d.day}/{d.month}'


def day_view(conn, lang, logos, leagues, t):
    """شريط الأيام + لوحة لكل يوم، الدوريات أقساماً قابلة للطي"""
    today = date.today()
    start = today - timedelta(days=DAYS_BACK)
    end = today + timedelta(days=DAYS_FWD)

    rows = window_matches(conn, start, end)

    # تجميع: يوم -> دوري -> مباريات
    by_day = {}
    for m in rows:
        d = str(m["date"])[:10]
        by_day.setdefault(d, {}).setdefault(m["league_code"], []).append(m)

    tabs = ""
    panels = ""
    cur = start
    while cur <= end:
        key = cur.isoformat()
        name, num = day_label(cur, today, t)
        is_today = (cur == today)
        cls = "daytab" + (" active" if is_today else "")
        tabs += (f'<button class="{cls}" data-day="{key}">'
                 f'<span class="dn">{name}</span>'
                 f'<span class="dd">{num}</span></button>')

        day_leagues = by_day.get(key, {})
        if day_leagues:
            body = ""
            for code in leagues:
                ms = day_leagues.get(code)
                if not ms:
                    continue
                cards = "".join(
                    match_card(m, lang, logos, show_league=False,
                               upcoming=(m["home_goals"] is None))
                    for m in ms)
                body += (
                    f'<details class="lgsec" open>'
                    f'<summary>'
                    f'<img class="flag" src="flags/{FLAG[code]}.png" alt="">'
                    f'<span class="lgname">{league_name(code, lang)}</span>'
                    f'<span class="lgnum">{len(ms)}</span>'
                    f'<span class="chev"></span>'
                    f'</summary>'
                    f'<div class="lgbody">{cards}</div>'
                    f'</details>'
                )
        else:
            body = f'<div class="noday">{t["d_none"]}</div>'

        vis = " visible" if is_today else ""
        panels += f'<section class="daypanel{vis}" id="d{key}">{body}</section>'
        cur += timedelta(days=1)

    # ⚠️ سهمان إجباريان على سطح المكتب — شريط التمرير مخفي
    #    ولا يوجد لمس، فبلا السهمين لا سبيل للتنقل إطلاقاً.
    #    الأول عند inline-start = الأيام الأقدم بالاتجاهين
    #    (العربية والإنجليزية) لأن الخصائص منطقية لا فيزيائية.
    # الزر الأول عند inline-start: يمينُ الشاشة بالعربية،
    # يسارُها بالإنجليزية — فيشير للجهة التي هو عليها.
    ic_first = CHEV_R if lang == "ar" else CHEV_L
    ic_last = CHEV_L if lang == "ar" else CHEV_R
    arrows_wrap = (
        f'<div class="daynav">'
        f'<button class="dayarrow" id="dayprev" aria-label="prev">'
        f'{ic_first}</button>'
        f'<div class="daytabs" id="daytabs">{tabs}</div>'
        f'<button class="dayarrow" id="daynext" aria-label="next">'
        f'{ic_last}</button>'
        f'</div>'
    )
    return f'{arrows_wrap}{panels}'


def hero_upcoming(conn, limit=8):
    """أقرب المباريات القادمة عبر كل الدوريات"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.league_code, m.season,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en,
               a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NULL
        ORDER BY m.date ASC LIMIT ?
    """, (limit,)).fetchall()


def hero_results(conn, limit=8):
    """آخر النتائج عبر كل الدوريات"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               m.league_code, m.season,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en,
               a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?
    """, (limit,)).fetchall()


# ⚠️ نصوص محلية لا في i18n — تخصّ هذا القسم وحده.
MYC = {
    "ar": {"pos": "المركز", "pts": "نقطة", "last": "آخر مباراة",
           "next": "القادمة", "none": "لا مباريات قادمة"},
    "en": {"pos": "Pos", "pts": "pts", "last": "Last match",
           "next": "Next", "none": "No upcoming matches"},
}


def club_summary(conn, row, lang, logos):
    """
    بطاقة ملخّص لنادٍ: مركزه بالجدول · آخر نتيجة · المباراة القادمة.

    ⚠️ **تُبنى لكل نادٍ مسبقاً** ويخفيها المتصفح حسب اختيار
       المستخدم — الموقع ساكن ولا خادم له، فالتخصيص يحدث
       بالمتصفح لا بالتوليد.

    ⚠️ **المركز من الموسم الجاري فقط.** إن لم يبدأ الموسم بعد
       (لا مباريات منتهية) يُخفى السطر بدل عرض صفر مضلِّل.
    """
    s = MYC[lang]
    tid = row["team_id"]

    last_season = conn.execute("""
        SELECT league_code, season FROM matches
        WHERE (home_id = ? OR away_id = ?)
        ORDER BY season DESC LIMIT 1
    """, (tid, tid)).fetchone()
    if not last_season:
        return ""
    code, season = last_season["league_code"], last_season["season"]

    # ── المركز والنقاط — من المباريات المنتهية بالموسم الجاري
    pos_html = ""
    played = conn.execute("""
        SELECT COUNT(*) FROM matches
        WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL
    """, (code, season)).fetchone()[0]
    if played:
        table = get_table(conn, code, season)
        for i, r in enumerate(table, 1):
            if r["team_id"] == tid:
                pos_html = (f'<span class="mpos">{s["pos"]} {i}</span>'
                            f'<span class="mpts">{r["points"]} '
                            f'{s["pts"]}</span>')
                break

    # ── آخر نتيجة والمباراة القادمة
    Q = """
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en,
               a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE (m.home_id = ? OR m.away_id = ?) AND m.home_goals IS %s NULL
        ORDER BY m.date %s LIMIT 1
    """
    last = conn.execute(Q % ("NOT", "DESC"), (tid, tid)).fetchone()
    nxt = conn.execute(Q % ("", "ASC"), (tid, tid)).fetchone()

    def line(r, label, score=True):
        if not r:
            return ""
        hn = tname(r, lang, "home", "home_en")
        an = tname(r, lang, "away", "away_en")
        if score and r["home_goals"] is not None:
            mid = f'{r["home_goals"]} - {r["away_goals"]}'
        else:
            d = str(r["date"]).split()
            mid = d[1][:5] if len(d) > 1 else "—"
        return (
            f'<a class="mrow" href="matches/{r["match_id"]}.html">'
            f'<span class="ml">{label}</span>'
            f'<span class="mm">{hn}<b>{mid}</b>{an}</span>'
            f'<span class="md">{str(r["date"])[:10]}</span></a>'
        )

    body = line(last, s["last"]) + line(nxt, s["next"], score=False)
    if not body:
        return ""

    logo = logos.get(str(tid), row["logo"])
    return (
        f'<div class="myc" data-club="{tid}">'
        f'<a class="mhead" href="clubs/{tid}.html">'
        f'<img src="{logo}" alt="">'
        f'<span class="mnm">{tname(row, lang, "short", "name_en")}</span>'
        f'{pos_html}</a>'
        f'{body}</div>'
    )


def match_card(m, lang, logos, show_league=True, upcoming=False):
    """بطاقة مباراة واحدة"""
    def logo_of(tid, fb):
        return logos.get(str(tid), fb)

    hn = tname(m, lang, "home", "home_en")
    an = tname(m, lang, "away", "away_en")
    arrow = "←" if lang == "ar" else "→"

    if upcoming:
        # التاريخ فيه وقت: 2026-08-15 18:00
        parts = str(m["date"]).split()
        day = parts[0]
        clock = parts[1] if len(parts) > 1 else ""
        score = f'<div class="score time">{clock or "—"}</div>'
        cls = "match soon"
        stamp = day
    else:
        score = f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>'
        cls = "match"
        stamp = str(m["date"])[:10]

    lg = ""
    if show_league:
        lg = f' <span class="lg">· {league_name(m["league_code"], lang)}</span>'

    # ⚠️ رابط يغطي البطاقة كاملة (درس: الضغط على السهم وحده صعب
    #    على الجوال). روابط الأندية والتاريخ تعلوه بـz-index فتبقى
    #    تعمل — فالضغط على شعار نادٍ يفتح النادي، وعلى أي مكان آخر
    #    يفتح المباراة.
    return (
        f'<div class="{cls}" data-mid="{m["match_id"]}">'
        f'<a class="open" href="matches/{m["match_id"]}.html"'
        f' aria-label="{hn} - {an}"></a>'
        f'<a class="side" href="clubs/{m["home_id"]}.html">'
        f'<img src="{logo_of(m["home_id"], m["home_logo"])}" alt="">'
        f'<span>{hn}</span></a>'
        f'{score}'
        f'<a class="side away" href="clubs/{m["away_id"]}.html">'
        f'<span>{an}</span>'
        f'<img src="{logo_of(m["away_id"], m["away_logo"])}" alt=""></a>'
        f'<div class="date">'
        f'<a href="matches/{m["match_id"]}.html">{stamp} {arrow}</a>'
        f'{lg}</div></div>'
    )


def render_panel(code, season, table, matches, scorers, logos, lang):
    t = T[lang]

    def logo_of(tid, fb):
        return logos.get(str(tid), fb)

    rows = ""
    for i, r in enumerate(table, 1):
        cls = "top" if i <= 3 else ("bottom" if i > len(table) - 2 else "")
        rows += (
            f'<tr class="{cls}"><td class="pos">{i}</td>'
            f'<td class="team">'
            f'<img src="{logo_of(r["team_id"], r["logo"])}" alt="">'
            f'<a href="clubs/{r["team_id"]}.html">{tname(r, lang)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )

    cards = "".join(match_card(m, lang, logos, show_league=False)
                    for m in matches)

    sc = ""
    depth = 0 if lang == "ar" else 1
    for i, s in enumerate(scorers, 1):
        pl = clean(s["player_ar"]) if lang == "ar" else ""
        pl = pl or clean(s["player"])
        tm = tname(s, lang, "team", "team_en")
        href = player_link(s["player"], BASE_DIR, depth)
        name_html = (f'<a href="{href}">{pl}</a>' if href else pl)
        sc += (
            f'<li><span class="num">{i}</span>'
            f'<span class="pname">{name_html}</span>'
            f'<span class="pteam">{tm}</span>'
            f'<span class="pgoals">{s["goals"]}</span></li>'
        )

    same = len({r["played"] for r in table}) == 1 if table else True
    warn = "" if same else f' · {t["incomplete"]}'

    table_html = ""
    if table:
        table_html = (
            f'<h2>{t["standings"]}</h2>'
            f'<table><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
            f'<th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>'
            f'{rows}</table>'
            f'<div class="meta">{t["season"]} {season}-{season+1}{warn}</div>'
        )

    res_html = f'<h2>{t["results"]}</h2>{cards}' if cards else ""
    sc_html = f'<h2>{t["scorers"]}</h2><ol>{sc}</ol>' if sc else ""

    return (f'<section class="panel" id="{season}_{code}">'
            f'{table_html}{res_html}{sc_html}</section>')


def build(conn, lang, combos, seasons, leagues, logos):
    """صفحة كاملة بلغة واحدة"""
    t = T[lang]

    # ---- عرض الأيام: شريط أفقي + لوحة لكل يوم ----
    #      (21 أغسطس — استبدل "أقرب 8 قادمة" و"آخر 8 نتائج")
    days_html = day_view(conn, lang, logos, leagues, t)

    # ⚠️ لا تزال مطلوبة لقسم "أنديتي" أدناه
    up = hero_upcoming(conn)
    res = hero_results(conn)

    # ---- 3. بطاقات الدوريات والجداول: انتقلت لـleagues.html ----
    #      (21 أغسطس — قرار "الرئيسية للمباريات فقط")

    # ---- قسم "أنديتي" — يظهر بالمتصفح حسب اختيار المستخدم ----
    # ⚠️ **أُعيد بناؤه 27 أغسطس.** كان يسرد بطاقات مباريات من
    #    نافذتَي "القادمة" و"النتائج" فقط — أي أن نادياً بلا
    #    مباراة قريبة يختفي تماماً من "أنديتي". الآن **بطاقة
    #    ملخّص لكل نادٍ** تعرض مركزه ونتيجته الأخيرة ومباراته
    #    القادمة، فيظهر دائماً ويعطي سبباً للعودة.
    my_cards = ""
    for row in conn.execute("""
            SELECT team_id, short_name_ar AS short, logo,
                   COALESCE(NULLIF(name_en_official,''), name_en) AS name_en
            FROM teams ORDER BY team_id"""):
        my_cards += club_summary(conn, row, lang, logos)

    hero_my = ""
    if my_cards:
        hero_my = (f'<div id="myclubs" style="display:none">'
                   f'<h2 class="hero">{t["my_clubs"]}</h2>'
                   f'{my_cards}</div>')

    # ---- بيانات المعالج ----
    wiz_leagues = [(c, league_name(c, lang)) for c in leagues]

    # أشهر 4 أندية بكل دوري — الأعلى نقاطاً بآخر موسم مكتمل
    popular = set()
    for code in leagues:
        done_season = conn.execute("""
            SELECT MAX(season) FROM matches
            WHERE league_code = ? AND home_goals IS NOT NULL
              AND season < (SELECT MAX(season) FROM matches)
        """, (code,)).fetchone()[0]
        if done_season is None:
            continue
        tbl = get_table(conn, code, done_season)
        for r in tbl[:4]:
            popular.add(r["team_id"])

    # ⚠️ بلا فلتر موسم (حُذف 6 سبتمبر) — نفس مصدر my_cards أعلاه
    #    بالضبط (كل نادٍ له مباراة واحدة على الأقل تاريخياً)، حتى
    #    تتطابق شرائح المعالج مع ما يظهر فعلياً بـ"أنديتي" بالرئيسية.
    #    الأثر: أندية هابطة/غير نشطة صارت تظهر كشرائح، مقبول ومتّسق.
    wiz_clubs = []
    for r in conn.execute("""
        SELECT DISTINCT t.team_id, t.short_name_ar AS name,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS name_en,
               t.logo, t.league_code AS lg
        FROM teams t
        WHERE EXISTS (
            SELECT 1 FROM matches m
            WHERE (m.home_id = t.team_id OR m.away_id = t.team_id)
        )
        ORDER BY t.league_code, t.short_name_ar
    """):
        nm = (clean(r["name"]) or clean(r["name_en"])) if lang == "ar" \
            else (clean(r["name_en"]) or clean(r["name"]))
        logo = logos.get(str(r["team_id"]), r["logo"])
        pop = 1 if r["team_id"] in popular else 0
        wiz_clubs.append((r["team_id"], nm, logo, r["lg"], pop))

    switch = "en/index.html" if lang == "ar" else "../index.html"
    wiz = wizard_html(t, wiz_leagues, wiz_clubs,
                      switch, SWITCH_LABEL[lang])

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{t["site_title"]}</title>\n'
        + head_meta(t["site_title"], t["site_sub"],
                    "" if lang == "ar" else "../", lang,
                    "index.html" if lang == "ar" else "en/index.html")
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        # ⚠️ **ترس الإعدادات الأعلى حُذف** (26 أغسطس) — كان يكرّر
        #    زر "الإعدادات" بالشريط السفلي بلا فائدة. المعالج
        #    (`openwiz`) يُفتح الآن من الشريط السفلي وحده.
        f'<div class="topbar">'
        f'<span></span>'
        f'<span class="hello" id="hello"></span></div>\n'
        f'<header><h1>{t["site_title"]}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'
        # ⚠️ **البحث العلوي حُذف** (1 سبتمبر) — كان يكرّر زر
        #    البحث بالشريط السفلي، والسفلي أوضح وأقرب لليد.
        #    طبقة البحث نفسها (`#sovl`) ما زالت مُدرَجة ويفتحها
        #    الشريط — الحذف للحقل الظاهر فقط.

        f'{hero_my}\n{days_html}\n'
        f'<footer><a href="about.html" style="color:var(--accent);text-decoration:none">{t["about"]}</a><br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        f'{wiz}\n'
                + search_overlay(t)
        + navbar(t, 0 if lang == "ar" else 1, "matches", lang)
        + settings_overlay(t, switch, lang)
        + DAY_SCRIPT + THEME_SCRIPT + WIZ_ROW_SCRIPT
        + prefs_script() + wizard_script(t)
        + nav_script(t) + pwa_script(lang)
        + live_script(t, 0 if lang == "ar" else 1)
        + search_script(t, 0 if lang == "ar" else 1, lang) +
        '</body>\n</html>'
    )

    # الإنجليزي داخل en/ — الشعارات المحلية فقط تحتاج تصحيحاً
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')
        html = html.replace('src="flags/', 'src="../flags/')

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

    n_up = len(hero_upcoming(conn, 999))

    for lang in LANGS:
        html = build(conn, lang, combos, seasons, leagues, logos)
        path = (BASE / "index.html" if lang == "ar"
                else BASE / "en" / "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    conn.close()

    print(f"\n{'=' * 55}")
    print("  تم: index.html  +  en/index.html")
    print(f"{'=' * 55}")
    for c in combos:
        print(f"  {league_name(c['league_code'], 'ar'):<18} "
              f"موسم {c['season']}   {c['n']} ماتش")
    print(f"\n  مباريات قادمة: {n_up}")
    print("""
  الرئيسية: شريط أيام (121 يوماً) ← دوريات قابلة للطي
  الجداول والهدافون: شغّل make_leagues.py
    """)


if __name__ == "__main__":
    main()
