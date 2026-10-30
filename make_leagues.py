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

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
import os
import sys

from config import DB_FILE, LEAGUES
import push_ui
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from navbar import (navbar, settings_button, settings_overlay,
                    nav_script, pwa_script, appbar)
from theme import THEME_HEAD, THEME_SCRIPT, BACK_SCRIPT, back_button, head_meta
from live_view import live_script

# الدوال والأنماط المشتركة — مصدر واحد لا نسخة
from swipe_view import TOUCH_CSS, swipe_script, head_html as swipe_head
from seasons_view import SEASONS_CSS, STR as SV_STR, seasons_tab_html
from zones import ZONE_CSS, zone_list, row_class, data_attr as zone_attr, legend as zone_legend
from search_view import search_field
import league_player_cards as lpc
import league_team_cards as ltc
from tiebreak import STANDINGS_EXCLUDED
from league_player_cards import CARDS_CSS
from make_site3 import (STYLE, load_overrides, available, clean,
                        tname, get_table, get_matches, get_scorers,
                        match_card, player_link, FLAG, thumb_of,
                        load_league_logos, league_badge)
from matchtime import matchtime_script
from prefs import prefs_script

BASE = DB_FILE.parent
LEAGUES_DIR = BASE / "leagues"

# ⚠️ الوضع الافتراضي (بلا --all) هو ما تستدعيه الأتمتة كل تشغيلة:
#    الموسم الحالي فقط لكل دوري — سريع، ولا يمسّ الأرشيف أبداً.
#    --all أرشفة صريحة يدوية لكل المواسم — لا تُستدعى تلقائياً.
ALL_SEASONS = "--all" in sys.argv

# ── أنماط وسكربت محليّان — لا يوجدان بـSTYLE المشتركة ──
LOCAL_STYLE = """
<style>
""" + SEASONS_CSS + """
""" + TOUCH_CSS + """
  /* «متابعة» الدوري (27 أكتوبر 2026، طلب عمرو #4) بجانب الجرس: إطار، ومتابَع = ممتلئ بلون التمييز. ليست تنبيهات — fbLeagues فقط */
  .lfol { flex:0 0 auto; min-height:44px; padding:0 16px; border-radius:22px; font:inherit; font-size:14px; font-weight:700;
          cursor:pointer; background:transparent; color:var(--text); border:1px solid var(--line); white-space:nowrap; }
  .lfol:hover { border-color:var(--accent); }
  .lfol.on { background:var(--accent); color:#fff; border-color:var(--accent); }
""" + ZONE_CSS + """
  /* (14 أكتوبر) ترويسة الدوري بنمط FotMob: شعار كبير + الاسم والدولة تحته + زر موسم واحد منسدل + الجرس بنفس الصف */
  .lhead { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:6px; }
  .lh-id { display:flex; align-items:center; gap:14px; min-width:0; }
  .lgbig { width:64px; height:64px; object-fit:contain; flex:0 0 64px; border-radius:12px; padding:6px; background:var(--card); }
  .lgbig.flagbig { padding:0; background:none; }
  .lh-tx { min-width:0; }
  .lh-tx h1 { font-size:clamp(19px,5.6vw,24px); line-height:1.25; margin:0; }
  .lh-sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .sdwrap { position:relative; margin:4px 0 14px; }
  .sdd { display:inline-block; }
  .sdd summary { list-style:none; cursor:pointer; display:inline-flex; align-items:center; gap:10px; min-height:44px;
                 padding:0 14px; border-radius:10px; border:1px solid var(--line); background:var(--card); color:var(--text);
                 font-size:15px; font-weight:600; user-select:none; }
  .sdd summary::-webkit-details-marker { display:none; }
  .sdd summary::after { content:""; width:7px; height:7px; border:solid currentColor; border-width:0 2px 2px 0;
                        transform:rotate(45deg) translateY(-2px); opacity:.7; }
  .sdd[open] summary { border-color:var(--accent); }
  .sdd[open] summary::after { transform:rotate(-135deg) translateY(-2px); }
  .sdl { position:absolute; z-index:40; inset-inline-start:0; top:calc(100% + 4px); min-width:190px; max-height:60vh; overflow:auto;
         background:var(--card); border:1px solid var(--line); border-radius:12px; padding:4px; box-shadow:0 8px 24px rgba(0,0,0,.35); }
  .sdl a { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:44px; padding:0 12px; border-radius:8px;
           color:var(--text); text-decoration:none; font-size:14px; }
  .sdl a:hover { background:var(--card2); }
  .sdl a.cur { color:var(--accent); font-weight:700; }
  .sdl a small { color:var(--muted); font-size:11px; font-weight:400; }
  .more { display:block; width:100%; margin:10px 0 4px; padding:10px;
          border-radius:9px; border:1px solid var(--line);
          background:var(--card); color:var(--muted); cursor:pointer;
          font-family:inherit; font-size:13px; }
  .more:hover { background:var(--card2); }
  li.hidden, .match.hidden, .mday.hidden { display:none; }
  /* (27 أكتوبر 2026، دفعة التصميم D) مباريات اليوم الواحد = بطاقة واحدة عنوانها اليوم («غداً»، «Thursday, 29 Oct»)، والمباريات
     صفوف داخلها بفواصل (كانت ترويسة عرضية فوق بطاقة لكل مباراة) */
  .mday { background:var(--card); border-radius:12px; margin:0 0 12px; overflow:hidden; }
  .mdh { font-size:14px; font-weight:700; color:var(--text); margin:0; padding:11px 14px 9px; }
  .mdays .mday .match { background:none; border-radius:0; margin:0; border-top:1px solid var(--line); }
  .more[data-mdir="past"] { margin:0 0 10px; }
  /* (25 أكتوبر 2026، دفعة UI 3) الأقسام صفّ واحد من تبويبات نصية مسطَّرة قابل للتمرير أفقياً (نمط .mtabs بصفحة المباراة) —
     كانت أزراراً مربّعة تلتفّ لسطرين. الأصناف cattabs/tab/active باقية: يعتمد عليها TAB_SCRIPT وLEAGUE_DAYS_SCRIPT. */
  .tabs.cattabs { display:flex; flex-wrap:nowrap; justify-content:flex-start; gap:2px; margin:6px 0 14px;
                  overflow-x:auto; border-bottom:1px solid var(--line); scrollbar-width:none; }
  .tabs.cattabs::-webkit-scrollbar { display:none; }
  .cattabs .tab { flex:1 0 auto; background:none; border:none; border-bottom:2px solid transparent; border-radius:0;
                  margin-bottom:-1px; padding:10px 10px; min-height:44px; color:var(--muted); font-size:14px; font-weight:600;
                  white-space:nowrap; }
  .cattabs .tab:hover { background:none; color:var(--text); }
  .cattabs .tab.active { background:none; color:var(--text); border-color:transparent; border-bottom-color:var(--accent); }
  /* منسدلة الموسم بالصف العلوي: بلا هامش، والقائمة تنفتح نحو داخل الشاشة (الزر عند نهاية الصف) */
  .appbar .sdwrap { margin:0; }
  .appbar .sdd summary { min-height:40px; padding:0 12px; font-size:14px; }
  .appbar .sdl { inset-inline-start:auto; inset-inline-end:0; }
  .lhead { margin:2px 0 4px; }
  /* (26 أكتوبر 2026، دفعة UI 3 إصلاح 2، نمط FotMob) الترويسة كلها ثابتة أعلى الشاشة: الرجوع + الموسم + الجرس، الشعار والاسم والدولة،
     ثم صف التبويبات تحتها — لا تتمرر بعيداً ولا تقفز عند تبديل التبويب (TAB_SCRIPT يعيد المحتوى لأوله، والمباريات لمرساة «اليوم» تحتها).
     تمتد لعرض الشاشة (هامش body 16px) بخلفية الصفحة فيختفي المحتوى تحتها؛ z-index تحت الشريط السفلي والأوراق (900+). */
  .lstick { position:sticky; top:0; z-index:40; background:var(--bg); margin:-8px -16px 0; padding:8px 16px 0; }
  .lstick .tabs.cattabs { margin-bottom:0; }
  .lstick ~ .panel { padding-top:12px; }
  /* (30 أكتوبر 2026، دفعة 3 بند 4) طيّ الترويسة: نزولاً تنزلق الترويسة الكبيرة (الصف العلوي، الشعار والاسم والدولة) للأعلى خارج الشاشة
     ويبقى صف التبويبات ثابتاً بأعلاها؛ صعوداً تعود. transform فقط (لا تغيير تخطيط = لا قفز)؛ --lhh = ارتفاع ما فوق التبويبات (LHEAD_SCRIPT) */
  .lstick { transition:transform .25s ease; }
  .lstick.hid { transform:translateY(calc(-1 * var(--lhh, 0px))); }
  @media (prefers-reduced-motion: reduce) { .lstick { transition:none; } }
  /* (بند 6a) الشريط يتمرّر أفقياً فقط: لا سحب عمودي ولا ارتداد عند لمسه */
  .tabs.cattabs { touch-action:pan-x; overscroll-behavior:contain; }
  /* (بند 3) صفوف تبويب المباريات بمقاس FotMob: شعار 32px واسم 17px (خلية الوقت/النتيجة كما هي)؛ الاسم الطويل يلتف لسطرين (ROW_CSS) */
  .mdays .match { min-height:60px; }
  .mdays .match { padding-inline:6px; column-gap:6px; }
  .mdays .match .side img { width:clamp(28px, 8.2vw, 32px); height:clamp(28px, 8.2vw, 32px); flex:0 0 auto; }
  .mdays .match .side span { font-size:clamp(15px, 4.4vw, 17px); }   /* 390px ≈ 17px، 360px ≈ 16px */
""" + CARDS_CSS + """</style>
"""

# ── أيام تبويب المباريات (18 أكتوبر 2026، دفعة C) ──
# matches.date مخزَّن UTC خام. التوليد يجمّع بتوقيت عمّان (UTC+3 ثابت منذ 2022 بلا توقيت صيفي؛ بلا tzdata على ويندوز المحلي)،
# فزائر الأردن يرى الترويسات صحيحة حتى بلا JS. LEAGUE_DAYS_SCRIPT ينقل البطاقات (data-k) ليوم الزائر المحلي ويعيد التسميات
# (اليوم/أمس/غداً من تاريخ الزائر) — نفس مبدأ DAY_SCRIPT بالرئيسية. بطاقة بلا وقت فعلي تبقى بتاريخها المخزَّن.
AMMAN = timezone(timedelta(hours=3))
# النافذة الظاهرة حول «اليوم» (شكل FotMob، ترتيب زمني): أيام كاملة حتى ≥ PAST_CAP مباراة قبله و≥ NEXT_CAP من يومه فصاعداً؛
# الباقي وراء «مباريات سابقة (N)» أعلى القائمة و«مباريات لاحقة (N)» أسفلها.
PAST_CAP = 10
NEXT_CAP = 15


def match_day(m):
    """(يوم عمّان، مفتاح ترتيب UTC) لمباراة"""
    parts = str(m["date"]).split()
    if len(parts) > 1 and parts[1][:5].count(":") == 1:
        dt = datetime.strptime(f"{parts[0]} {parts[1][:5]}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        return dt.astimezone(AMMAN).date(), dt.isoformat()
    return date.fromisoformat(parts[0]), parts[0]


def match_days(matches):
    """[(يوم، [مباريات])] بترتيب زمني: الأيام تصاعدياً، وداخل اليوم بترتيب الانطلاق"""
    days = {}
    for m in matches:
        d, k = match_day(m)
        days.setdefault(d, []).append((k, m))
    return [(d, [m for _, m in sorted(days[d], key=lambda x: x[0])]) for d in sorted(days)]


def day_months(t):
    """أشهر عنوان اليوم: الإنجليزي مختصر («29 Oct»، دفعة التصميم D)، والعربي كامل"""
    return t["MONTHS"] if t is T["ar"] else [x[:3] for x in t["MONTHS"]]


def day_label(d, today, t):
    """«اليوم/أمس/غداً» (نفس كلمات شريط الرئيسية) وإلا «الاثنين 12 أكتوبر» / "Monday, 12 October" """
    diff = (d - today).days
    if diff == 0:
        return t["d_today"]
    if diff == -1:
        return t["d_yesterday"]
    if diff == 1:
        return t["d_tomorrow"]
    wd, mo = t["WEEKDAYS_FULL"][d.weekday()], day_months(t)[d.month - 1]
    return f"{wd} {d.day} {mo}" if t is T["ar"] else f"{wd}, {d.day} {mo}"


def get_upcoming(conn, code, season):
    """مباريات الموسم غير المُلعوبة (القادمة + المؤجّلة/الملغاة) بحالتها، تصاعدياً"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals, m.league_code, m.status,
               h.team_id AS home_id, h.short_name_ar AS home,
               COALESCE(NULLIF(h.name_en_official,''), h.name_en) AS home_en, h.logo AS home_logo,
               a.team_id AS away_id, a.short_name_ar AS away,
               COALESCE(NULLIF(a.name_en_official,''), a.name_en) AS away_en, a.logo AS away_logo
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ? AND m.season = ? AND m.home_goals IS NULL
        ORDER BY m.date ASC
    """, (code, season)).fetchall()


LEAGUE_DAYS_SCRIPT = """
<script>
(function(){
  var box=document.querySelector('[data-mdays]'); if(!box)return;
  var C=__CFG__;
  function p2(n){ return (n<10?'0':'')+n; }
  function ymd(d){ return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate()); }
  function label(key){
    var p=key.split('-'), u=Date.UTC(+p[0],+p[1]-1,+p[2]), n=new Date(),
        diff=Math.round((u-Date.UTC(n.getFullYear(),n.getMonth(),n.getDate()))/864e5);
    if(diff===0) return C.today; if(diff===-1) return C.yesterday; if(diff===1) return C.tomorrow;
    var dt=new Date(u), wd=C.wd[(dt.getUTCDay()+6)%7], mo=C.mo[dt.getUTCMonth()];
    return C.ar ? wd+' '+dt.getUTCDate()+' '+mo : wd+', '+dt.getUTCDate()+' '+mo;
  }
  // مجموعة يوم بعينه (تُنشأ بمكانها: الأيام تصاعدياً)، ترث إخفاء/جهة المجموعة المصدر (خلف «سابقة/لاحقة»)
  function group(key,src){
    var gs=box.querySelectorAll('.mday'), before=null;
    for(var i=0;i<gs.length;i++){ var k=gs[i].getAttribute('data-day'); if(k===key) return gs[i]; if(!before&&k>key) before=gs[i]; }
    var g=document.createElement('div'); g.className='mday'+(src.classList.contains('hidden')?' hidden':''); g.setAttribute('data-day',key);
    if(src.getAttribute('data-side')) g.setAttribute('data-side',src.getAttribute('data-side'));
    var h=document.createElement('h3'); h.className='mdh'; g.appendChild(h); box.insertBefore(g,before); return g;
  }
  try{
    [].slice.call(box.querySelectorAll('.match[data-k]')).forEach(function(c){
      var d=new Date(c.getAttribute('data-k')); if(isNaN(d.getTime())) return;
      var key=ymd(d), g=c.parentNode; if(g.getAttribute('data-day')===key) return;
      var tg=group(key,g), k=c.getAttribute('data-k'), ref=null;
      [].slice.call(tg.querySelectorAll('.match')).some(function(o){ var ok=o.getAttribute('data-k'); if(ok&&ok>k){ ref=o; return true; } return false; });
      tg.insertBefore(c,ref);
    });
    [].slice.call(box.querySelectorAll('.mday')).forEach(function(g){
      if(!g.querySelector('.match')){ g.parentNode.removeChild(g); return; }
      g.querySelector('.mdh').textContent=label(g.getAttribute('data-day'));
    });
  }catch(e){}
  // المرساة: أول يوم ظاهر من «اليوم» المحلي فصاعداً، وإلا آخر يوم ظاهر (موسم منتهٍ/أرشيف)
  function anchor(){
    var t=ymd(new Date()), vis=[].filter.call(box.querySelectorAll('.mday'),function(g){ return !g.classList.contains('hidden'); });
    for(var i=0;i<vis.length;i++) if(vis[i].getAttribute('data-day')>=t) return vis[i];
    return vis[vis.length-1]||null;
  }
  // (26 أكتوبر 2026، إصلاح 2) الترويسة ثابتة (.lstick): المرساة تُوضع تحتها لا تحت حافة الشاشة
  // (30 أكتوبر 2026) الترويسة تُطوى نزولاً بعد ما فوق التبويبات (hh): الهدف بعده = تحت التبويبات وحدها، ونطويها فوراً (لا فجوة)
  function toAnchor(){
    var a=anchor(); if(!a) return;
    var s=document.querySelector('.lstick'), b=s&&s.querySelector('.cattabs');
    var full=s?s.getBoundingClientRect().height:0, hh=(s&&b)?Math.max(0, b.getBoundingClientRect().top - s.getBoundingClientRect().top):0;
    var top=a.getBoundingClientRect().top + window.pageYOffset, y=top - (full - hh) - 8;
    if(y<=hh) y=top - full - 8;
    window.scrollTo(0, Math.max(0, y));
    if(window.FBLeagueHead) window.FBLeagueHead.sync();
  }
  window.FBLeagueDays={anchor:anchor,toAnchor:toAnchor};
  // فتح تبويب المباريات = تمرير «اليوم» لأعلى الشاشة؛ الأيام السابقة فوقه بالتمرير للأعلى
  document.querySelectorAll('.cattabs .tab[data-cat="matches"]').forEach(function(b){ b.addEventListener('click',function(){ setTimeout(toAnchor,0); }); });
  if(box.closest('.panel.visible')) toAnchor();
  // «مباريات سابقة» تكشف ما فوق دون أن تقفز الشاشة (نحفظ موضع المرساة)؛ «لاحقة» تكشف ما تحت
  document.querySelectorAll('.more[data-mdir]').forEach(function(btn){
    btn.addEventListener('click',function(){
      var dir=btn.getAttribute('data-mdir'), a=anchor(), y0=a?a.getBoundingClientRect().top:0;
      box.querySelectorAll('.mday.hidden[data-side="'+dir+'"]').forEach(function(g){ g.classList.remove('hidden'); });
      btn.style.display='none';
      if(dir==='past'&&a) window.scrollBy(0, a.getBoundingClientRect().top - y0);
    });
  });
  // (30 أكتوبر 2026، دفعة 4 بند 10) تغيّر تاريخ الجهاز (منتصف الليل، أو عودة من الخلفية/bfcache بيوم جديد) = إعادة تحميل: «اليوم/أمس/غداً»
  //    والمرساة من التاريخ الجديد (كما بالرئيسية)
  var LOADED=ymd(new Date());
  function rollover(){
    if(document.hidden||ymd(new Date())===LOADED) return;
    LOADED=ymd(new Date());
    location.reload();
  }
  document.addEventListener('visibilitychange', rollover);
  window.addEventListener('pageshow', function(e){ if(e.persisted) rollover(); });
  setInterval(rollover, 60000);
})();
</script>"""


def league_days_script(lang):
    t = T[lang]
    cfg = {"today": t["d_today"], "yesterday": t["d_yesterday"], "tomorrow": t["d_tomorrow"],
           "wd": t["WEEKDAYS_FULL"], "mo": day_months(t), "ar": lang == "ar"}
    return LEAGUE_DAYS_SCRIPT.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))


def matches_tab(matches, lang, logos, today=None):
    """تبويب المباريات (دفعة C، شكل FotMob): كل مباريات الموسم (المنتهية + القادمة للموسم الجاري) بترتيب زمني تحت ترويسة
    عرضية لكل يوم، بلا سطر تاريخ تحت البطاقة. المرساة = أول يوم من «اليوم» فصاعداً (وإلا آخر يوم)؛ ظاهر حولها أيام كاملة حتى
    ≥ PAST_CAP قبلها و≥ NEXT_CAP من يومها فصاعداً، والباقي وراء «مباريات سابقة (N)» أعلى و«مباريات لاحقة (N)» أسفل.
    يرجع (أعلى: زر السابقة + القائمة، أسفل: زر اللاحقة)."""
    t = T[lang]
    today = today or datetime.now(AMMAN).date()
    days = match_days(matches)
    if not days:
        return f'<div class="empty">{t["empty_combo"]}</div>', ""
    ai = next((i for i, (d, _) in enumerate(days) if d >= today), len(days) - 1)
    lo, n = ai, 0
    while lo > 0 and n < PAST_CAP:
        lo -= 1
        n += len(days[lo][1])
    hi, n = ai, 0
    while hi < len(days) and n < NEXT_CAP:
        n += len(days[hi][1])
        hi += 1
    groups, k, past_n, fut_n = "", 0, 0, 0
    for i, (d, ms) in enumerate(days):
        side = "past" if i < lo else ("future" if i >= hi else "")
        cards = ""
        for m in ms:
            cards += match_card(m, lang, logos, show_league=False, upcoming=m["home_goals"] is None, thumbs=True,
                                eager=not side and k < 6, show_date=False, day_key=True)
            k += 0 if side else 1
        past_n += len(ms) if side == "past" else 0
        fut_n += len(ms) if side == "future" else 0
        groups += (f'<div class="mday{" hidden" if side else ""}" data-day="{d.isoformat()}"'
                   + (f' data-side="{side}"' if side else "") + f'><h3 class="mdh">{day_label(d, today, t)}</h3>{cards}</div>')
    top = f'<button class="more" data-mdir="past">{t["show_earlier"]} ({past_n})</button>' if past_n else ""
    bottom = f'<button class="more" data-mdir="future">{t["show_later"]} ({fut_n})</button>' if fut_n else ""
    return top + f'<div class="mdays" data-mdays>{groups}</div>', bottom


TAB_SCRIPT = """
<script>
(function(){
  var tabs = document.querySelectorAll('.cattabs .tab');
  var panels = document.querySelectorAll('.panel[data-cat]');
  function activate(b){
    var cat = b.dataset.cat;
    tabs.forEach(function(x){ x.classList.toggle('active', x===b); });
    panels.forEach(function(p){
      p.classList.toggle('visible', p.dataset.cat === cat);
    });
    // (25 أكتوبر 2026، دفعة UI 3) الشريط سطر واحد قابل للتمرير: التبويب المختار يُمرَّر لمجال الرؤية (بلا تمرير الصفحة)
    try{ b.scrollIntoView({inline:'nearest', block:'nearest'}); }catch(e){}
    // التبويب المختار بـhistory.state (replaceState: بلا مدخل تاريخ) — الرجوع من مباراة/نادٍ يعيده بدل «الترتيب» دائماً
    try{ history.replaceState(Object.assign({}, history.state||{}, {cat:cat}), ''); }catch(e){}
  }
  tabs.forEach(function(b){
    b.addEventListener('click', function(){
      activate(b);
      // (26 أكتوبر 2026، إصلاح 2) الترويسة ثابتة: التبويب الجديد يبدأ من أوله فلا يقفز موضع قصير بعد جدول طويل
      // (المباريات: LEAGUE_DAYS_SCRIPT يمرّر لمرساة «اليوم» بعد هذا)
      if(b.dataset.cat !== 'matches') window.scrollTo(0, 0);
    });
  });
  // استرجاع التبويب عند الرجوع: بلا click (فلا تمرير toAnchor لتبويب المباريات — المتصفح يستعيد موضع التمرير بنفسه)
  try{
    var sv = history.state && history.state.cat;
    tabs.forEach(function(b){ if(sv && b.dataset.cat === sv && !b.classList.contains('active')) activate(b); });
  }catch(e){}
  // (30 أكتوبر 2026، دفعة 3 بند 4) طيّ الترويسة: --lhh = ارتفاع ما فوق صف التبويبات؛ نزولاً (بعد تجاوزه) تُطوى، صعوداً تعود.
  //   مستمع scroll سلبي + requestAnimationFrame (بلا تخطيط قسري بكل حدث)، وإعادة قياس عند تغيّر المقاس.
  (function(){
    var st=document.querySelector('.lstick'), bar=st&&st.querySelector('.cattabs');
    if(!st||!bar) return;
    var H=0, last=window.pageYOffset, hid=false, tick=false;
    function measure(){ H=Math.max(0, Math.round(bar.getBoundingClientRect().top - st.getBoundingClientRect().top)); st.style.setProperty('--lhh', H+'px'); }
    function set(h){ if(h!==hid){ hid=h; st.classList.toggle('hid', h); } }
    function onScroll(){
      tick=false;
      var y=window.pageYOffset, dy=y-last;
      if(y<=H) set(false);
      else if(dy>4) set(true);
      else if(dy<-4) set(false);
      last=y;
    }
    measure();
    // تمرير برمجي (مرساة المباريات): الحالة من الموضع لا من الاتجاه
    function sync(){ last=window.pageYOffset; set(last>H); }
    window.FBLeagueHead={sync:sync};
    sync();
    window.addEventListener('scroll', function(){ if(!tick){ tick=true; requestAnimationFrame(onScroll); } }, {passive:true});
    window.addEventListener('resize', measure, {passive:true});
    window.addEventListener('load', measure);
    if(window.ResizeObserver) try{ new ResizeObserver(measure).observe(st); }catch(e){}
  })();
  // السحب بين التبويبات: swipe_view.py (اللوحة تتبع الإصبع، 27 أكتوبر 2026) — حلّ محلّ سحب النقرة السريعة القديم هنا
  document.querySelectorAll('.more:not([data-mdir])').forEach(function(btn){   // أزرار المباريات (data-mdir) يتولاها LEAGUE_DAYS_SCRIPT
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
                f'<img src="{thumb_of(r["team_id"]) or logos.get(str(r["team_id"]), r["logo"])}" alt="" loading="lazy">'
                f'<span>{tname(r, lang)}</span>'
                f'<span class="pts">{value}{suffix}</span></div>')
    else:
        # (27 أكتوبر 2026، دفعة التصميم F) تعادل فريقين أو أكثر: كل فريق بشعاره بجانب اسمه (كانت أسماء بلا شعارات حتى 3،
        #    ورقماً وحده لأكثر من 3)
        items = "".join(
            f'<span class="ti"><img src="{thumb_of(r["team_id"]) or logos.get(str(r["team_id"]), r["logo"])}" alt="" loading="lazy">'
            f'<span>{tname(r, lang)}</span></span>' for r in teams)
        lead = (f'<div class="lead"><span class="tlist">{items}</span>'
                f'<span class="pts">{value}{suffix}</span></div>')
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
          AND ps.player_id IS NOT NULL AND ps.player_id != 0
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
          AND ps.player_id IS NOT NULL AND ps.player_id != 0
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


def team_stats_tab_html(conn, code, season, table, logos, lang, t, newest_season=None):
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

    win_teams, win_v = streak_teams(win_streak)
    unbeaten_teams, unbeaten_v = streak_teams(unbeaten_streak)

    # (30 أكتوبر 2026، دفعة 4 بند 1) بطاقات FotMob (league_team_cards): أهداف/استقبال بالمباراة، شباك نظيفة، استحواذ (تغطية ≥90%)
    #    بدل بطاقات «أقوى هجوم/دفاع/فارق» (نفس المعلومة بصيغة إجمالية)؛ السلسلتان تبقيان تحتها
    depth = 1 if lang == "ar" else 2
    team_of, logo_of, _h = stat_ctx(conn, lang, logos, depth)
    cards, _l, _c = ltc.cards_html(conn, code, season, newest_season or season, lang, team_of, logo_of,
                                   tuple(STANDINGS_EXCLUDED))

    layer1 = "".join([
        leader_card(t["win_streak"], win_teams, win_v, lang, logos,
                    unit=t["streak_unit"]),
        leader_card(t["unbeaten_streak"], unbeaten_teams, unbeaten_v, lang,
                    logos, unit=t["streak_unit"]),
    ])

    return cards + (f'<div class="lgrid" style="margin-top:12px">{layer1}</div>' if layer1 else "")


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


# ⚠️ **لا شعارات بطولات رسمية بالمشروع** (فُحص فعلاً 6 سبتمبر —
#    صفر ملف "لوجو دوري"/"شارة بطولة"، راجع بند مفتوح بالـREADME).
#    نستعمل أعلام الدول (FLAG/flags/) كبديل — نفس النمط المطبَّق
#    فعلياً بـday_view (make_site3.py)، مستورَد لا مكرَّر.
# زر «متابعة» الدوري (27 أكتوبر 2026، طلب عمرو #4): يقرأ/يكتب fbLeagues عبر FBPrefs (نفس مفتاح ترتيب صفحة الدوريات وقسم «الدوريات» بصفحة
# المتابَعة). متابعة ≠ تنبيهات: الجرس بجانبه مستقل (ورقة «كل الدوريات» بصفحة الإشعارات تطبّق الأنواع على كل الدوريات المتابَعة).
LEAGUE_FOLLOW_SCRIPT = """
<script>
(function(){
  var b=document.getElementById('lfolbtn'),FB=window.FBPrefs;
  if(!b||!FB)return;
  var code=b.getAttribute('data-lg'),F=b.getAttribute('data-f'),U=b.getAttribute('data-u');
  function on(){return (FB.getLeagues()||[]).indexOf(code)>=0;}
  function paint(){var o=on();b.classList.toggle('on',o);b.setAttribute('aria-pressed',o?'true':'false');b.textContent=o?U:F;}
  b.addEventListener('click',function(){
    var L=(FB.getLeagues()||[]).slice(),i=L.indexOf(code);
    if(i>=0)L.splice(i,1);else{L.push(code);if(FB.markSetupDone)FB.markSetupDone();}
    FB.setLeagues(L);paint();
  });
  window.addEventListener('storage',paint);
  window.addEventListener('pageshow',paint);
  paint();
})();
</script>"""

LEAGUES_SORT_SCRIPT = """
<script>
(function(){
  var FB=window.FBPrefs;
  if(!FB)return;
  var followed=FB.getLeagues();
  // ⚠️ بلا اختيار = الترتيب الافتراضي كما وُلِّد، بلا فصل ولا
  //    قسم "متابَعة" — نفس المحتوى، صفر تغيير (قرار محسوم).
  if(!followed.length)return;
  var grid=document.querySelector('.lgrid');
  if(!grid)return;
  var fi=0, oi=1000;
  grid.querySelectorAll('.lcard').forEach(function(c){
    c.style.order = followed.indexOf(c.dataset.lg)>=0 ? fi++ : oi++;
  });
})();
</script>"""

# ⚠️ بند 3 (22 سبتمبر) — صندوق بحث مستقل خاص بالسبعة دوريات فقط،
#    لا يفتح طبقة `#sovl` (بحث الأندية/اللاعبين العامة) إطلاقاً.
#    كانت `search_box(t, big=True)` تُستخدم هنا سابقاً — حقل
#    readonly يفتح تلك الطبقة، وهي لا تعرف شيئاً عن الدوريات
#    (search_data.js يحوي أندية ولاعبين فقط)، فالكتابة لم تكن
#    تُرجع أي دوري إطلاقاً. الحل هنا فلترة محلية صرفة — 7 عناصر
#    فقط، لا حاجة لفهرس خارجي.
#
# ⚠️ **نفس دالة norm() من search_view.py حرفياً** (توحيد الألف/
#    الهمزة/التاء المربوطة/الياء + حذف "ال" التعريف) — منسوخة لا
#    مستوردة، لأن search_view.py سكربت مضمَّن بالكامل (نص) لا
#    وحدة JS منفصلة يمكن استدعاء دالة منها.
#
# ⚠️ **كل بطاقة تحمل الاسمين معاً** (data-nm-ar/data-nm-en) بصرف
#    النظر عن لغة الصفحة — "Jordan" يجب أن يُظهر "الدوري الأردني"
#    حتى بالصفحة العربية، تماماً كمطابقة بحث الأندية/اللاعبين
#    العامة (3% فقط من اللاعبين لهم اسم عربي فالمطابقة الإنجليزية
#    شرط عمل لا ترفاً هناك أيضاً).
LEAGUES_SEARCH_SCRIPT = """
<script>
(function(){
  var inp=document.getElementById('lgsearchinput');
  var grid=document.querySelector('.lgrid');
  var empty=document.getElementById('lgnores');
  if(!inp||!grid)return;

  function norm(s){
    if(!s)return '';
    s=(''+s).toLowerCase();
    s=s.replace(/[\\u0623\\u0625\\u0622\\u0671]/g,'\\u0627')
       .replace(/\\u0629/g,'\\u0647')
       .replace(/\\u0649/g,'\\u064a')
       .replace(/[\\u064b-\\u0652\\u0640]/g,'');
    s=s.replace(/^\\u0627\\u0644/,'');
    s=s.replace(/[-'.\\u2019]/g,' ').replace(/\\s+/g,' ').trim();
    return s;
  }

  var cards=grid.querySelectorAll('.lcard');
  cards.forEach(function(c){
    c.dataset.nm = norm(c.dataset.nmAr)+'|'+norm(c.dataset.nmEn);
  });

  inp.addEventListener('input', function(){
    var q=norm(this.value);
    var shown=0;
    cards.forEach(function(c){
      var ok = !q || c.dataset.nm.indexOf(q)>=0;
      c.style.display = ok ? '' : 'none';
      if(ok)shown++;
    });
    if(empty)empty.style.display = shown ? 'none' : '';
  });
})();
</script>"""


COUNTRY = {  # (عربي، إنجليزي) — تحت اسم الدوري بترويسة صفحة الدوري
    "SAU": ("السعودية", "Saudi Arabia"), "EGY": ("مصر", "Egypt"), "UAE": ("الإمارات", "United Arab Emirates"),
    "QAT": ("قطر", "Qatar"), "JOR": ("الأردن", "Jordan"), "IRQ": ("العراق", "Iraq"), "MAR": ("المغرب", "Morocco"),
    "TUN": ("تونس", "Tunisia"), "ALG": ("الجزائر", "Algeria"), "KUW": ("الكويت", "Kuwait"),
}

SDD_SCRIPT = """
<script>
(function(){var d=document.getElementById('sdd');if(!d)return;
document.addEventListener('click',function(e){if(d.open&&!d.contains(e.target))d.open=false;});
document.addEventListener('keydown',function(e){if(e.key==='Escape')d.open=false;});})();
</script>"""


def league_img(code, logos, local):
    """شعار الدوري كاملاً على بلاطة بلون السطح (.lgbadge، + lg-<code> للبلاطات البديلة)، وإلا العلم الدائري (.flag)"""
    url = local.get(code) or logos.get(code)
    if url:
        return f'<img class="lgbadge lg-{code.lower()}" src="{url}" alt="">'
    return f'<img class="flag" src="flags/{FLAG[code]}.svg" alt="">'


def flags_page(lang, leagues, league_logos=None, league_logos_local=None):
    """
    leagues.html — بطاقة لكل دوري (شعار البطولة إن توفّر، وإلا علم
    الدولة كسقوط آمن + الاسم)، بلا جداول. الترتيب افتراضياً كما
    وُلِّد (ثابت). لو للزائر دوريات متابَعة محفوظة (`fbLeagues`)،
    جافاسكربت وقت العرض (`LEAGUES_SORT_SCRIPT`) يرفعها لأعلى
    الشبكة عبر CSS `order` — بلا نقل عناصر DOM، بلا تغيير بالمحتوى
    نفسه. زائر بلا تفضيلات يرى نفس الترتيب الافتراضي دائماً، صفر
    رسالة أو حالة فارغة.

    ⚠️ **شعار البطولة يستبدل علم الدولة فقط حيث توفّر** (`league_badge`
       — `logo_local` استثناء يدوي، وإلا `logo` من fetch_standings.py،
       وإلا العلم كما كان). قبل أول سحب فعلي، أو لدوري بلا شعار
       بالاستجابة، تبقى النتيجة علماً — صفر كسر، صفر صورة مفقودة.
    """
    t = T[lang]
    depth = 0 if lang == "ar" else 1
    league_logos = league_logos or {}
    league_logos_local = league_logos_local or {}

    # ⚠️ `.lcard` نفسها ليست flex لمحتواها المباشر (مستخدَمة أيضاً
    #    لبطاقات "leader" بتبويب إحصائيات الفرق، `.lcard .lead` هي
    #    الصف flex هناك) — لفّة سطر واحدة محلية هنا بلا لمس الكلاس
    #    المشترك، تحقّق "اللوجو بجانب الاسم" لا فوقه.
    cards = "".join(
        f'<a class="lcard" href="leagues/{code.lower()}.html" '
        f'data-lg="{code}" data-nm-ar="{league_name(code, "ar")}" '
        f'data-nm-en="{league_name(code, "en")}">'
        f'<div style="display:flex;align-items:center;gap:9px">'
        f'{league_img(code, league_logos, league_logos_local)}'
        f'<div class="ln">{league_name(code, lang)}</div>'
        f'</div></a>'
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
        swipe_head() +   # فارغ منذ 28 أكتوبر 2026 (أُزيل السحب بين صفحات الشريط السفلي، swipe_view.py)
        '</head>\n<body>\n<div class="wrap">\n'
        # ⚠️ leagues.html لم تكن تملك .topbar إطلاقاً — أُضيفت الآن
        #    فقط لحمل أيقونة الإعدادات العلوية (بند 1، 22 سبتمبر).
        # (25 أكتوبر 2026، دفعة UI 3) عنوان الصف = اسم التبويب؛ الترويسة الوسطى صارت h1 مخفياً للفهرسة والقارئات
        + appbar(t, lang, switch, title=t["nv_leagues"]).replace('class="appname"', 'class="appname lgbig"', 1) +
        f'<h1 class="vh">{t["leagues"]}</h1>\n'
        # ⚠️ بند 3 — صندوق محلي لتصفية الدوريات (`lgsearch`)، مستقل عن
        #    صفحة البحث العامة (`search.html`). يعيد استخدام كلاسات
        #    `.sbig`/`.sempty` الموجودة بـSEARCH_CSS بلا CSS جديد.
        # (30 أكتوبر 2026، دفعة 3 بند 1) خانة البحث المشتركة search_field (كبسولة، العدسة بجهة البداية)
        + search_field(f'<input type="search" id="lgsearchinput" autocomplete="off" '
                       f'placeholder="{t["leagues_search_ph"]}" aria-label="{t["leagues_search_ph"]}">', wrap_id="lgsearch") + '\n' +
        f'<div class="lgrid">{cards}</div>\n'
        f'<div class="sempty" id="lgnores" style="display:none">'
        f'{t["no_results"]}</div>\n'
        '</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT
        + prefs_script() + LEAGUES_SORT_SCRIPT + LEAGUES_SEARCH_SCRIPT + swipe_script()
        + nav_script(t) + pwa_script(lang)
        +
        '</body>\n</html>'
    )
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')
        html = html.replace('src="flags/', 'src="../flags/')
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
    # مناطق التأهّل/الهبوط من وصف المزوّد لكل مركز (zones.py، 27 أكتوبر 2026): شريط ملوَّن + مفتاح؛ بلا أوصاف = تلوين المركز القديم
    zl = zone_list(conn, code, season)
    for i, r in enumerate(table, 1):
        cls = row_class(zl, i) if zl else ("top" if i <= 3 else ("bottom" if i > len(table) - 2 else ""))
        rows += (
            f'<tr class="{cls}" data-t="{r["team_id"]}"><td class="pos">{i}</td>'
            f'<td class="team">'
            f'<img src="{thumb_of(r["team_id"]) or logos.get(str(r["team_id"]), r["logo"])}" alt="" '
            f'width="22" height="22" decoding="async"{"" if i <= 10 else " loading=lazy"}>'
            f'<a href="clubs/{r["team_id"]}.html">{tname(r, lang)}</a></td>'
            f'<td>{r["played"]}</td><td>{r["wins"]}</td><td>{r["draws"]}</td>'
            f'<td>{r["losses"]}</td><td>{r["diff"]:+d}</td>'
            f'<td class="pts">{r["points"]}</td></tr>'
        )
    standings_html = ""
    if table:
        # الترتيب المباشر: سمات لموسم الدوري الحالي فقط (وبلا JOR) — راجع live_view.py (ltPaint)
        lt = (f' data-lt="{code}" data-ss="{season}" data-lid="{LEAGUES[code]["id"]}"'
              if season == newest_season and code != "JOR" else "")
        standings_html = (
            f'<table{lt}{zone_attr(zl, len(table))}><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
            f'<th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>'
            f'{rows}</table>' + zone_legend(zl, lang, len(table))
        )
    else:
        standings_html = f'<div class="empty">{t["empty_combo"]}</div>'

    # الموسم الجاري: المنتهية + القادمة (والمؤجّلة) معاً بترتيب زمني؛ الأرشيف: المنتهية فقط
    upcoming = get_upcoming(conn, code, season) if season == newest_season else []
    matches_html, more_m = matches_tab(list(matches) + list(upcoming), lang, logos)

    # ---- تبويب الهدافين — نفس نمط أول 10 + عرض الكل ----
    sc = ""
    for i, s in enumerate(scorers, 1):
        pl = clean(s["player_ar"]) if lang == "ar" else ""
        pl = pl or clean(s["player"])
        tm = tname(s, lang, "team", "team_en")
        href = player_link(s["player"], BASE, depth, lang)
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

    # ---- تبويب "إحصائيات اللاعبين" — بطاقات FotMob (league_player_cards.py) إن غطّت player_stats الموسم، وإلا الهدافون من goals ----
    player_layer = player_stats_layer_html(conn, code, season, lang, t)
    cards, _lists = lpc.cards_html(conn, code, season, newest_season, lang, *stat_ctx(conn, lang, logos, depth))
    player_stats_html = cards or scorers_html
    if player_layer:
        player_stats_html += f'<hr class="divider">{player_layer}'

    # ---- منسدلة الموسم — من الملفات الموجودة فعلاً على القرص ----
    # ⚠️ خيار "الحالي" ثابت الوجهة والتسمية بـnewest_season دائماً؛
    #    "selected" هو الفرق الوحيد بين توليد الصفحة الحالية
    #    وتوليد أرشيف — season قد يساوي أو لا يساوي newest_season.
    cur_sel = ' selected' if season == newest_season else ''
    # ⚠️ (14 أكتوبر) زر موسم واحد منسدل («2026/27 ▾») يفتح قائمة الروابط: <details> بلا JS، والروابط <a href> عادية فتبقى
    #    صفحات المواسم القديمة مكشوفة لمحركات البحث (حلّ محل <select> وصفّ الشرائح المكرَّرين). كل رابط من season_files() (فحص قرص).
    def _sl(s):
        return f'{s}/{str(s + 1)[-2:]}'
    items = (f'<a href="{code_l}.html"{" class=cur" if season == newest_season else ""}>'
             f'<bdi dir="ltr">{_sl(newest_season)}</bdi><small>{t["current_season"]}</small></a>')
    for s_, fname in season_files(code):
        items += f'<a href="{fname}"{" class=cur" if s_ == season else ""}><bdi dir="ltr">{_sl(s_)}</bdi></a>'
    season_dd = (f'<div class="sdwrap"><details class="sdd" id="sdd"><summary aria-label="{t["season"]}">'
                 f'<bdi dir="ltr">{_sl(season)}</bdi></summary>'
                 f'<nav class="sdl" aria-label="{t["season"]}">{items}</nav></details></div>')

    # شعار الدوري الكبير (نفس مصدر leagues.html: استثناء محلي ثم رابط المزوّد ثم علم الدولة) + الدولة تحت الاسم
    _ll, _lloc = load_league_logos()
    _url = _lloc.get(code) or _ll.get(code)
    lg_img = (f'<img class="lgbig" src="{_url}" alt="">' if _url
              else f'<img class="lgbig flagbig" src="{"../" if lang == "ar" else "../../"}flags/{FLAG[code]}.svg" alt="">')
    country = COUNTRY.get(code, ("", ""))[0 if lang == "ar" else 1]

    team_stats_html = team_stats_tab_html(conn, code, season, table, logos,
                                          lang, t, newest_season)

    tabs_html = (
        f'<div class="tabs cattabs">'
        f'<button class="tab active" data-cat="standings">'
        f'{t["tab_standings"]}</button>'
        f'<button class="tab" data-cat="matches">{t["tab_matches"]}</button>'
        f'<button class="tab" data-cat="player-stats">'
        f'{t["tab_player_stats"]}</button>'
        f'<button class="tab" data-cat="team-stats">'
        f'{t["tab_team_stats"]}</button>'
        f'<button class="tab" data-cat="seasons">{SV_STR[lang]["tab"]}</button>'
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
        # تبويب «المواسم» (27 أكتوبر 2026، seasons_view.py): بطل ووصيف كل موسم مكتمل، النقر = صفحة الموسم
        f'<section class="panel" data-cat="seasons">'
        + seasons_tab_html(conn, code, lang, season, newest_season,
                           lambda r: thumb_of(r["team_id"]) or logos.get(str(r["team_id"]), r["logo"]), tname)
        + '</section>'
    )

    # ⚠️ نفس ملف الموسم بالنسخة الأخرى (leagues/<code>-<season>.html لأرشيف المواسم) —
    #    كان يذهب دائماً لصفحة الدوري الحالية فيضيع الموسم المعروض.
    fname = (f"{code_l}.html" if season == newest_season
             else f"{code_l}-{season}.html")
    switch = (f'../en/leagues/{fname}' if lang == "ar"
              else f'../../leagues/{fname}')
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
        # (25 أكتوبر 2026، دفعة UI 3) الصف العلوي: سهم الرجوع … منسدلة الموسم + الجرس (كانا تحت الترويسة وبجانبها)
        + '<div class="lstick">'   # (26 أكتوبر 2026، إصلاح 2) الترويسة + التبويبات ثابتة أعلى الشاشة
        + appbar(t, lang, switch, back=True, extra=season_dd
                 + f'<button class="lfol" id="lfolbtn" type="button" aria-pressed="false" data-lg="{code}" '
                   f'data-f="{t["f_follow"]}" data-u="{t["f_followed"]}">{t["f_follow"]}</button>'
                 + push_ui.bell_html("l", LEAGUES[code]["id"], lang)) +
        f'<header class="lhead"><div class="lh-id">{lg_img}<div class="lh-tx"><h1>{league_name(code, lang)}</h1>'
        f'<div class="lh-sub">{country}</div></div></div></header>\n'
        + push_ui.msg_html() +
        f'{tabs_html}</div>\n'
        f'{panels_html}\n'
        '</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT + BACK_SCRIPT + matchtime_script() + league_days_script(lang)
        + nav_script(t) + pwa_script(lang)
        + live_script(t, depth)
        + TAB_SCRIPT + SDD_SCRIPT + swipe_script()
        + prefs_script() + LEAGUE_FOLLOW_SCRIPT
        + push_ui.page_script(lang) +
        '</body>\n</html>'
    )

    # ⚠️ عمق 1: كل روابط clubs/matches كُتبت بلا "../" (زي match_card
    #    وصفوف الجدول أعلاه) — نزيحها هنا دفعة واحدة، وبنفس القدر
    #    للغتين لأن clubs/ و matches/ مرآتان تحت en/ (بعكس logos/).
    html = html.replace('href="clubs/', 'href="../clubs/')
    html = html.replace('href="matches/', 'href="../matches/')
    logo_prefix = "../" if lang == "ar" else "../../"
    html = html.replace('src="logos/', f'src="{logo_prefix}logos/')
    html = html.replace('src="thumbs/', f'src="{logo_prefix}thumbs/')

    return html


_TEAMS = None


def stat_ctx(conn, lang, logos, depth):
    """(team_of, logo_of, href_of) لبطاقات/قوائم league_player_cards: اسم النادي باللغة، شعاره (thumbs/ نسبي للجذر — يُزاح مع بقية
    الصفحة)، ورابط صفحة اللاعب بمعرّفه إن وُجدت فعلاً (وإلا بالاسم كبقية الموقع، وإلا بلا رابط)"""
    global _TEAMS
    if _TEAMS is None:
        _TEAMS = {r[0]: (clean(r[1]) or clean(r[2]), clean(r[2]) or clean(r[1]), r[3]) for r in conn.execute(
            "SELECT team_id, short_name_ar, COALESCE(NULLIF(name_en_official,''), name_en), logo FROM teams")}
    from make_clubs import _pid_slug, _player_pages
    pages = _player_pages()
    up = "../" * depth + ("en/" if lang == "en" else "")

    def team_of(tid):
        x = _TEAMS.get(tid)
        return (x[0] if lang == "ar" else x[1]) if x else ""

    def logo_of(tid):
        x = _TEAMS.get(tid)
        return thumb_of(tid) or logos.get(str(tid), x[2] if x else "") or ""

    def href_of(p):
        s = _pid_slug().get(p["pid"])
        if s and s in pages:
            return f"{up}players/{s}.html"
        return player_link(p["en"], BASE, depth, lang) if p["en"] else ""
    return team_of, logo_of, href_of


def _list_page(lang, code, season, fname, heading, body):
    """صفحة قائمة كاملة (noindex) لبطاقة إحصائية بصفحة الدوري — لاعبين (دفعة 3) أو فرق (دفعة 4)"""
    t = T[lang]
    depth = 1 if lang == "ar" else 2
    sl = f'{season}/{str(season + 1)[-2:]}'
    title = f'{heading} · {league_name(code, lang)} {sl}'
    switch = (f'../en/leagues/{fname}' if lang == "ar" else f'../../leagues/{fname}')
    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title} — {t["site_title"]}</title>\n'
        '<meta name="robots" content="noindex">\n'
        + head_meta(title, t["site_sub"], "../" if lang == "ar" else "../../", lang,
                    (f"leagues/{fname}" if lang == "ar" else f"en/leagues/{fname}"))
        + THEME_HEAD + STYLE + LOCAL_STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        + appbar(t, lang, switch, back=True, title=heading)
        + f'<div class="lh-sub" style="margin:0 2px 12px">{league_name(code, lang)} · <bdi dir="ltr">{sl}</bdi></div>\n'
        + body +
        '\n</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT + BACK_SCRIPT + nav_script(t) + pwa_script(lang) +
        '</body>\n</html>'
    )
    html = html.replace('href="clubs/', 'href="../clubs/').replace('href="matches/', 'href="../matches/')
    logo_prefix = "../" if lang == "ar" else "../../"
    return html.replace('src="logos/', f'src="{logo_prefix}logos/').replace('src="thumbs/', f'src="{logo_prefix}thumbs/')


def stat_list_pages(conn, lang, code, season, logos, newest_season):
    """{اسم الملف: html} لصفحات القوائم الكاملة: بطاقات اللاعبين (فقط حيث تظهر) وبطاقات الفرق (30 أكتوبر 2026، دفعة 4 بند 1)"""
    depth = 1 if lang == "ar" else 2
    ctx = stat_ctx(conn, lang, logos, depth)
    out = {}
    _c, lists = lpc.cards_html(conn, code, season, newest_season, lang, *ctx)
    for stat, lst in lists.items():
        out[lpc.list_fname(code, season, newest_season, stat)] = _list_page(
            lang, code, season, lpc.list_fname(code, season, newest_season, stat), lpc.STR[lang][stat],
            lpc.list_body(stat, lst, lang, *ctx))
    team_of, logo_of, _h = ctx
    _c, tlists, _cov = ltc.cards_html(conn, code, season, newest_season, lang, team_of, logo_of, tuple(STANDINGS_EXCLUDED))
    for stat, lst in tlists.items():
        fn = ltc.list_fname(code, season, newest_season, stat)
        out[fn] = _list_page(lang, code, season, fn, ltc.STR[lang][stat], ltc.list_body(lst, team_of, logo_of))
    return out


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    logos = load_overrides()
    league_logos, league_logos_local = load_league_logos()

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
        html = flags_page(lang, leagues, league_logos, league_logos_local)
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
                    # (30 أكتوبر 2026، دفعة 3 بند 5) صفحات القوائم الكاملة لبطاقات إحصائيات اللاعبين (فقط حيث تظهر البطاقات)
                    #    (30 أكتوبر 2026، دفعة 4 بند 1) + قوائم بطاقات الفرق (<code>-team-<stat>.html)
                    for fn, page in stat_list_pages(conn, lang, code, season, logos, newest[code]).items():
                        with open(folder / fn, "w", encoding="utf-8") as f:
                            f.write(page)

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
