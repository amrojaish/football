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
  /* ترويسة يوم بتبويب المباريات (دفعة C): عرض كامل فوق بطاقات اليوم */
  .mdh { font-size:13px; font-weight:700; color:var(--muted); margin:14px 0 6px; padding:0 2px 6px;
         border-bottom:1px solid var(--line); }
  .mday:first-child .mdh, .mday.hidden + .mday:not(.hidden) .mdh { margin-top:2px; }
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
</style>
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


def day_label(d, today, t):
    """«اليوم/أمس/غداً» (نفس كلمات شريط الرئيسية) وإلا «الاثنين 12 أكتوبر» / "Monday, 12 October" """
    diff = (d - today).days
    if diff == 0:
        return t["d_today"]
    if diff == -1:
        return t["d_yesterday"]
    if diff == 1:
        return t["d_tomorrow"]
    wd, mo = t["WEEKDAYS_FULL"][d.weekday()], t["MONTHS"][d.month - 1]
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
  function toAnchor(){ var a=anchor(); if(a) window.scrollTo(0, Math.max(0, a.getBoundingClientRect().top + window.pageYOffset - 8)); }
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
})();
</script>"""


def league_days_script(lang):
    t = T[lang]
    cfg = {"today": t["d_today"], "yesterday": t["d_yesterday"], "tomorrow": t["d_tomorrow"],
           "wd": t["WEEKDAYS_FULL"], "mo": t["MONTHS"], "ar": lang == "ar"}
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
    b.addEventListener('click', function(){ activate(b); });
  });
  // استرجاع التبويب عند الرجوع: بلا click (فلا تمرير toAnchor لتبويب المباريات — المتصفح يستعيد موضع التمرير بنفسه)
  try{
    var sv = history.state && history.state.cat;
    tabs.forEach(function(b){ if(sv && b.dataset.cat === sv && !b.classList.contains('active')) activate(b); });
  }catch(e){}
  // سحب أفقي على المحتوى = التبويب المجاور (نفس قاعدة سحب الأيام بالرئيسية: ≥ 60px، أفقي ضعف العمودي، < 700ms؛ الاتجاه حسب dir)
  var RTL = document.documentElement.dir === 'rtl', sx = 0, sy = 0, t0 = 0, on = false;
  document.addEventListener('touchstart', function(e){
    on = !!(e.touches.length === 1 && e.target.closest
            && !e.target.closest('.appbar,.cattabs,.sdd,.nav,.psheet,.ptoast'));
    if(!on) return;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; t0 = Date.now();
  }, {passive:true});
  document.addEventListener('touchend', function(e){
    if(!on) return; on = false;
    var t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
    if(Math.abs(dx) < 60 || Math.abs(dx) < 2*Math.abs(dy) || Date.now() - t0 > 700) return;
    var cur = 0; tabs.forEach(function(b, i){ if(b.classList.contains('active')) cur = i; });
    var i = cur + ((dx < 0) !== RTL ? 1 : -1);
    if(i >= 0 && i < tabs.length) tabs[i].click();
  }, {passive:true});
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


# ⚠️ **لا شعارات بطولات رسمية بالمشروع** (فُحص فعلاً 6 سبتمبر —
#    صفر ملف "لوجو دوري"/"شارة بطولة"، راجع بند مفتوح بالـREADME).
#    نستعمل أعلام الدول (FLAG/flags/) كبديل — نفس النمط المطبَّق
#    فعلياً بـday_view (make_site3.py)، مستورَد لا مكرَّر.
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
        '</head>\n<body>\n<div class="wrap">\n'
        # ⚠️ leagues.html لم تكن تملك .topbar إطلاقاً — أُضيفت الآن
        #    فقط لحمل أيقونة الإعدادات العلوية (بند 1، 22 سبتمبر).
        # (25 أكتوبر 2026، دفعة UI 3) عنوان الصف = اسم التبويب؛ الترويسة الوسطى صارت h1 مخفياً للفهرسة والقارئات
        + appbar(t, lang, switch, title=t["nv_leagues"]) +
        f'<h1 class="vh">{t["leagues"]}</h1>\n'
        # ⚠️ بند 3 — صندوق محلي لتصفية الدوريات (`lgsearch`)، مستقل عن
        #    صفحة البحث العامة (`search.html`). يعيد استخدام كلاسات
        #    `.sbig`/`.sempty` الموجودة بـSEARCH_CSS بلا CSS جديد.
        f'<div class="sbig" id="lgsearch">'
        f'<input type="text" id="lgsearchinput" '
        f'placeholder="{t["leagues_search_ph"]}">'
        f'<span class="ico">⌕</span></div>\n'
        f'<div class="lgrid">{cards}</div>\n'
        f'<div class="sempty" id="lgnores" style="display:none">'
        f'{t["no_results"]}</div>\n'
        '</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT
        + prefs_script() + LEAGUES_SORT_SCRIPT + LEAGUES_SEARCH_SCRIPT
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
    for i, r in enumerate(table, 1):
        cls = "top" if i <= 3 else ("bottom" if i > len(table) - 2 else "")
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
            f'<table{lt}><tr><th>{t["pos"]}</th><th class="r">{t["team"]}</th>'
            f'<th>{t["played"]}</th><th>{t["won"]}</th><th>{t["drawn"]}</th>'
            f'<th>{t["lost"]}</th><th>{t["gd"]}</th><th>{t["points"]}</th></tr>'
            f'{rows}</table>'
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
        + appbar(t, lang, switch, back=True, extra=season_dd + push_ui.bell_html("l", LEAGUES[code]["id"], lang)) +
        f'<header class="lhead"><div class="lh-id">{lg_img}<div class="lh-tx"><h1>{league_name(code, lang)}</h1>'
        f'<div class="lh-sub">{country}</div></div></div></header>\n'
        + push_ui.msg_html() +
        f'{tabs_html}\n'
        f'{panels_html}\n'
        '</div>\n'
        + navbar(t, depth, "leagues", lang)
        + THEME_SCRIPT + BACK_SCRIPT + matchtime_script() + league_days_script(lang)
        + nav_script(t) + pwa_script(lang)
        + live_script(t, depth)
        + TAB_SCRIPT + SDD_SCRIPT
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
