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

import json
import sqlite3
import csv
import os
from datetime import datetime, date, timedelta
from config import DB_FILE, TEAMS_FILE, LEAGUES, BASE_DIR
from tiebreak import sort_table, STANDINGS_EXCLUDED
from i18n import T, LANGS, DIR, league_name, off_label
from search_view import SEARCH_CSS
from navbar import (NAV_CSS, navbar, settings_button, settings_overlay,
                    nav_script, pwa_script, appbar)
from live_view import LIVE_CSS, live_script
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   head_meta)
from prefs import prefs_script
from matchtime import matchtime_script
from player_slug import slug as _pslug

BASE = DB_FILE.parent

# ملفات الأعلام في flags/*.svg — أعلام دائرية أصلاً من circle-flags (HatScripts، MIT)
# ولا تُقصّ بالـCSS (كانت PNG 4:3 بـobject-fit:cover فتضيع الأطراف)
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



# ⚠️ **أيام الرئيسية بتوقيت الزائر (6 أكتوبر 2026 — بند 21، البند "ب").** الصفحة تُبنى
#    بـ`date.today()` على خادم CI (UTC): التبويب النشط وتسميات اليوم/أمس/غداً كانت UTC.
#    الآن بعد التحميل: (1) نقل كل بطاقة تحمل `data-utc` للوحة تاريخها المحلي (ضمن قسم
#    دوريها بترتيب الوقت)، (2) تسميات اليوم/أمس/غداً وأسماء الأيام من تاريخ الزائر،
#    (3) التبويب الافتراضي = اليوم المحلي. بلا JS تبقى الصفحة كما بُنيت (UTC) بلا تغيير.
#    بطاقة بلا `data-utc` (بلا وقت فعلي) تبقى بيومها. يجب أن يسبق follow_section_script
#    (قسم Following يُبنى من اللوحات بعد إعادة التجميع). يُستبدل __CFG__ بـJSON.
DAY_SCRIPT = """
<script>
(function(){
  var CFG=__CFG__;
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

  function p2(n){ return (n<10?'0':'')+n; }
  function ymd(d){ return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate()); }
  function utcOf(c){ var u=c.querySelector&&c.querySelector('[data-utc]'); return u?u.dataset.utc:''; }

  // (1) إعادة التجميع: بطاقة يومها المحلي غير يوم لوحتها تنتقل للوحة يومها المحلي
  function regroup(){
    var moves=[], touched=[];
    document.querySelectorAll('.daypanel .match').forEach(function(c){
      var u=utcOf(c); if(!u)return;
      var d=new Date(u); if(isNaN(d.getTime()))return;
      var panel=c.closest('.daypanel');
      var tgt=document.getElementById('d'+ymd(d));
      if(!panel||!tgt||tgt===panel)return;
      moves.push([c,panel,tgt]);
    });
    moves.forEach(function(mv){
      var c=mv[0], tgt=mv[2];
      var sec=c.closest('.lgsec'); if(!sec)return;
      var code=sec.getAttribute('data-sec');
      var secs=[].filter.call(tgt.children,function(x){ return x.classList.contains('lgsec'); });
      var tsec=null;
      secs.forEach(function(x){ if(x.getAttribute('data-sec')===code) tsec=x; });
      if(!tsec){
        var nd=tgt.querySelector('.noday'); if(nd) nd.parentNode.removeChild(nd);
        tsec=document.createElement('details');
        tsec.className='lgsec'; tsec.setAttribute('data-sec',code); tsec.open=true;
        tsec.innerHTML=sec.querySelector('summary').outerHTML+'<div class="lgbody"></div>';
        var idx=CFG.leagues.indexOf(code), before=null;
        for(var i=0;i<secs.length;i++){
          if(CFG.leagues.indexOf(secs[i].getAttribute('data-sec'))>idx){ before=secs[i]; break; }
        }
        tgt.insertBefore(tsec,before);
      }
      var tb=tsec.querySelector('.lgbody'), key=utcOf(c), ref=null;
      for(var k=0;k<tb.children.length;k++){
        var o=utcOf(tb.children[k]);
        if(o&&o>key){ ref=tb.children[k]; break; }
      }
      tb.insertBefore(c,ref);
      touched.push(mv[1],tgt);
    });
    touched.forEach(function(panel){
      var left=0;
      [].slice.call(panel.querySelectorAll('.lgsec')).forEach(function(sec){
        var n=sec.querySelectorAll('.match').length;
        if(!n){ sec.parentNode.removeChild(sec); return; }
        var num=sec.querySelector('.lgnum'); if(num) num.textContent=n;
        left+=n;
      });
      if(!left&&!panel.querySelector('.noday')){
        var nd=document.createElement('div'); nd.className='noday'; nd.textContent=CFG.none;
        panel.appendChild(nd);
      }
    });
  }

  // (2)+(3) تسميات اليوم/أمس/غداً وأسماء الأيام + التبويب الافتراضي من تاريخ الزائر
  function relabel(){
    var now=new Date(), ty=now.getFullYear(), tm=now.getMonth()+1, td=now.getDate();
    var t0=Date.UTC(ty,tm-1,td), todayKey=ymd(now), hit=null;
    tabs.forEach(function(b){
      var p=b.dataset.day.split('-'), u=Date.UTC(+p[0],+p[1]-1,+p[2]);
      var diff=Math.round((u-t0)/864e5), name;
      if(diff===0) name=CFG.today; else if(diff===-1) name=CFG.yesterday;
      else if(diff===1) name=CFG.tomorrow;
      else name=CFG.weekdays[(new Date(u).getUTCDay()+6)%7];
      var dn=b.querySelector('.dn'); if(dn) dn.textContent=name;
      if(b.dataset.day===todayKey) hit=b;
    });
    if(hit) show(hit.dataset.day);
  }

  try{ regroup(); }catch(e){}
  try{ relabel(); }catch(e){}

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

# ⚠️ **يخلف MYCLUBS_SORT_SCRIPT (ترتيب صامت بـCSS order)** —
#    استُبدل بقصد (بند 5، 22 سبتمبر) بقسم "⭐ Following" **ظاهر**
#    أعلى كل يوم، لا مجرد إعادة ترتيب. نقل DOM حقيقي هذه المرة
#    لا `order` — القسم القديم يرتّب فقط ضمن نفس الحاوية، ولا
#    يُنشئ قسماً منفصلاً مرئياً كما طُلب هنا صراحة.
#
# ⚠️ **الفرق/اللاعبون معاً من أول يوم** — لا "نضيف اللاعبين لاحقاً".
#    follow_data.js (بند 4، جزء ب) يحمل أصلاً team_id الحالي لكل
#    لاعب متابَع (مستدَل من آخر هدف)، فإدراجه هنا إعادة استخدام
#    كاملة لبيانات موجودة أصلاً لغرض آخر — صفر استعلام جديد.
#    ⚠️ محدودية مقبولة بقصد: "النادي الحالي" للاعب استدلال من آخر
#       هدف، قد يتأخر عن انتقال حديث فعلي — نفس محدودية `club_line`
#       بصفحة اللاعب نفسها، لا جديدة هنا.
#
# ⚠️ **نقل حقيقي — إفراغ `.lgbody` يُخفي `.lgsec` كاملاً** ويحدّث
#    عدّاده (`.lgnum`)، تجنّباً لقسم دوري فارغ الشكل بعد سحب كل
#    مبارياته للقسم الجديد.
#
# ⚠️ **لا قسم إطلاقاً لو لا مطابقة بذلك اليوم** — لا رسالة فارغة
#    (نفس مبدأ `.noday`/`.sempty` بكل الموقع).
FOLLOW_SECTION_SCRIPT = """
<script>
(function(){
  var FB=window.FBPrefs;
  if(!FB)return;
  var TITLE="__TITLE__";
  var STAR='<svg class="fstar" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9-4.3-4.1 5.9-.8z"/></svg>';

  function run(){
    var data=window.FBFollowData;
    var teamSet={};
    FB.getClubs().forEach(function(c){ teamSet[c]=true; });
    if(data){
      var byId={};
      data.players.forEach(function(r){ byId[r[0]]=r; });
      FB.getPlayers().forEach(function(slug){
        var r=byId[slug];
        if(r) teamSet[r[3]]=true;
      });
    }
    if(!Object.keys(teamSet).length)return;

    document.querySelectorAll('.daypanel').forEach(function(panel){
      var hits=[];
      panel.querySelectorAll('.match').forEach(function(m){
        if(teamSet[m.dataset.h]||teamSet[m.dataset.a]) hits.push(m);
      });
      if(!hits.length)return;

      var sec=document.createElement('details');
      sec.className='lgsec followsec';
      sec.setAttribute('data-sec','follow');
      sec.open=true;
      sec.innerHTML='<summary>'+STAR+'<span class="lgname"></span>'+
        '<span class="lgnum">'+hits.length+'</span><span class="chev"></span></summary>'+
        '<div class="lgbody"></div>';
      sec.querySelector('.lgname').textContent=TITLE;
      var fbody=sec.querySelector('.lgbody');

      hits.forEach(function(m){
        var body=m.parentElement;
        fbody.appendChild(m);
        if(body&&body.classList.contains('lgbody')){
          var lgsec=body.closest('.lgsec');
          var left=body.querySelectorAll('.match').length;
          if(lgsec){
            var num=lgsec.querySelector('.lgnum');
            if(num) num.textContent=left;
            if(!left) lgsec.style.display='none';
          }
        }
      });

      panel.insertBefore(sec, panel.firstChild);
    });
  }

  /* follow_data.js لا يُحمَّل إلا لمن يتابع لاعباً — البيانات تُستخدم
     فقط لاستنتاج نادي اللاعب. متابع الأندية فقط (أو لا شيء) لا يدفع
     بايتاً. التحميل يبدأ فوراً (بدل defer) ثم run بعد load/error
     (error: الأندية تعمل بلا ملف البيانات كما كان). */
  function go(){
    if(document.readyState==='complete') run();
    else window.addEventListener('load', run);
  }
  if(!FB.getPlayers().length){
    if(FB.getClubs().length) go();
    return;
  }
  var sc=document.createElement('script');
  sc.src="__UP__follow_data.js";
  sc.onload=go; sc.onerror=go;
  document.head.appendChild(sc);
})();
</script>"""


SEC_STATE_SCRIPT = """
<script>
(function(){
  var K='fbSecClosed';
  function load(){ try{ var v=JSON.parse(localStorage.getItem(K)||'{}'); return v&&typeof v==='object'?v:{}; }catch(e){ return {}; } }
  function save(o){ try{ localStorage.setItem(K,JSON.stringify(o)); }catch(e){} }
  function key(d){ return d.getAttribute('data-sec'); }
  function apply(){
    var st=load();
    document.querySelectorAll('details.lgsec[data-sec]').forEach(function(d){
      if(st[key(d)]) d.open=false;
    });
  }
  /* نحفظ عند ضغط المستخدم فقط (لا عند الفتح/الإغلاق البرمجي) */
  document.addEventListener('click',function(e){
    var sm=e.target.closest&&e.target.closest('details.lgsec[data-sec] > summary');
    if(!sm)return;
    var d=sm.parentElement;
    setTimeout(function(){
      var st=load(), k=key(d);
      if(d.open) delete st[k]; else st[k]=1;
      save(st);
    },0);
  });
  window.addEventListener('load',function(){ setTimeout(apply,0); });
})();
</script>"""


def follow_section_script(t, depth):
    """قسم "⭐ Following" — راجع FOLLOW_SECTION_SCRIPT أعلاه للتصميم
    الكامل. UP بنفس صيغة make_search_page.page_js() حرفياً (follow_data.js
    بجذر الموقع). لا UPL هنا — العناصر المنقولة روابطها جاهزة
    أصلاً من match_card()، لا نبني روابط جديدة بهذا السكربت."""
    up = "../" * depth
    title = t["following"]
    return (FOLLOW_SECTION_SCRIPT
            .replace("__UP__", up)
            .replace("__TITLE__", title.replace('"', '\\"'))
            + SEC_STATE_SCRIPT)


def follow_card_html(t, lang):
    """
    بطاقة صغيرة قابلة للإغلاق أعلى الرئيسية — تظهر بـJS فقط لمن
    `!isSetupDone()` ولم يغلقها، وتربط بـ`following.html`.

    ⚠️ **لا تحويل (`location.href`) من الرئيسية بأي حال.** كان
       `follow_redirect_script()` يحوّل زائر أول مرة إلى `following.html`
       (noindex)، وجوجل زائر أول مرة دائماً فرأى الرئيسية تحويلاً لصفحة
       noindex (canonical = following.html). والهدف الإنجليزي
       'en/following.html' كان نسبياً من /en/ فيُحَلّ إلى
       /en/en/following.html (404). الرابط هنا نسبي سليم: العربي
       `following.html` من الجذر، والإنجليزي `following.html` داخل `en/`.
    ⚠️ الإغلاق يُحفَظ بمفتاح مستقل (`fbFollowCardX`) لا بـFBPrefs —
       `isSetupDone()` يبقى false حتى يُكمل الزائر الإعداد فعلاً.
    """
    return (
        '<div class="followcard" id="fcard" hidden>'
        f'<span class="fct">{t["follow_card_text"]}</span>'
        f'<a class="fcb" href="following.html">{t["follow_card_btn"]}</a>'
        f'<button class="fcx" id="fcardx" type="button" '
        f'aria-label="{t["follow_card_close"]}">\u00d7</button>'
        '</div>\n'
    )


def follow_card_script():
    return """
<script>
(function(){
  var c=document.getElementById('fcard'); if(!c) return;
  var x=false;
  try{ x=!!localStorage.getItem('fbFollowCardX'); }catch(e){}
  if(!x && window.FBPrefs && !window.FBPrefs.isSetupDone()) c.hidden=false;
  var b=document.getElementById('fcardx');
  if(b) b.addEventListener('click',function(){
    c.hidden=true;
    try{ localStorage.setItem('fbFollowCardX','1'); }catch(e){}
  });
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
  header { text-align:center; margin-bottom:16px; }
  .followcard { display:flex; align-items:center; gap:10px; margin:0 0 18px;
                padding:10px 12px; border-radius:11px;
                border:1px solid var(--line); background:var(--card); }
  .followcard[hidden] { display:none; }
  .followcard .fct { flex:1; font-size:14px; color:var(--text); }
  .followcard .fcb { padding:6px 14px; border-radius:9px; font-size:13px;
                     background:var(--accent); color:#fff;
                     text-decoration:none; }
  .followcard .fcx { background:none; border:0; color:var(--muted);
                     font-size:20px; line-height:1; cursor:pointer; }
  h1 { font-size:20px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  h2 { font-size:17px; margin:28px 0 12px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }

  /* بطاقات الدوريات */
  .lgrid { display:flex; gap:10px; flex-wrap:wrap; }
  .lcard { flex:1; min-width:200px; background:var(--card);
           border:1px solid var(--line); border-radius:11px; padding:16px;
           cursor:pointer; font-family:inherit; text-align:start;
           transition:.15s; color:var(--text); text-decoration:none; }
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
  /* flex column — يضمن ترتيب `#followsec`/`.lgsec` عمودياً بالضبط
     كما وُلِّدا بالـHTML (قسم "⭐ Following" أولاً لو أُدرِج، بند 5).
     الأطفال `<details>` block أصلاً بعرض كامل، وalign-items:stretch
     الافتراضي يُبقيهم كذلك — صفر تغيير بالمظهر. */
  .daypanel.visible { display:flex; flex-direction:column; }
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
  /* ⚠️ خلفية بيضاء موحَّدة (22 سبتمبر) — شعارا مصر والإمارات
     رسم/نص أسود على شفافية كاملة (87%/73%)، يختفيان كلياً فوق
     var(--card) الداكن بلا خلفية خاصة بهما (تباين WCAG 1.05/1.24
     — تحت الحد الأدنى 3.0 للعناصر غير النصية). خلفية بيضاء ثابتة
     تحل الاثنين بلا استثناء لمصر وحدها، ولا تغيّر شيئاً عملياً
     بالخمسة الباقية (إما معتمة أصلاً أو تباينها كافٍ أصلاً).
     الحدّ الخفيف ضروري بالوضع الفاتح تحديداً — var(--card) هناك
     (#f6f8fa) قريب جداً من الأبيض فتضيع حافة القرص بدونه. */
  .flag { width:26px; height:26px; flex:0 0 auto; display:block; }
  /* شعار الدوري داخل قرص أبيض بهامش، كاملاً (contain) لا مقصوصاً —
     الشعارات مستطيلة/بنصوص على الأطراف فيقطعها cover (مثل IPFL بالعراق). */
  .lgbadge { width:40px; height:40px; flex:0 0 auto; display:block;
             box-sizing:border-box; padding:5px; border-radius:50%;
             object-fit:contain; background:#fff;
             border:1px solid var(--line); }
  .lgname { font-size:14px; font-weight:600; flex:1; min-width:0;
            overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  /* العدّاد: مربع صغير مدوّر، والسهم رفيع (1.5px) — نفس الشريط للدوريات والمتابَعة */
  .lgnum { background:var(--deep); color:var(--muted); font-size:12px;
           font-weight:600; min-width:22px; height:22px; padding:0 6px;
           display:inline-flex; align-items:center; justify-content:center;
           border-radius:7px; font-variant-numeric:tabular-nums; }
  .chev { width:7px; height:7px; border-right:1.5px solid var(--muted);
          border-bottom:1.5px solid var(--muted); transform:rotate(45deg);
          margin-inline:2px 4px; transition:transform .18s; flex:0 0 auto; }
  .lgsec[open] > summary .chev { transform:rotate(-135deg); }
  /* flex column بنفس سبب .daypanel أعلاه */
  .lgbody { padding:0 10px 10px; display:flex; flex-direction:column; }
  .lgbody .match { background:var(--deep); }

  /* المباريات */
  /* ⚠️ **بطاقة "أنديتي" (`.myc`/`.mhead`/`.mnm`/`.mpos`/`.mpts`/
     `.mrow`/`.ml`/`.mm`/`.md`) حُذفت من هنا** (8 سبتمبر) — القسم
     نفسه استُبدل بترتيب CSS `order` بقائمة المباريات العادية
     أولاً، ثم بقسم "⭐ Following" ظاهر ومنقول DOM حقيقياً (بند 5،
     22 سبتمبر — راجع FOLLOW_SECTION_SCRIPT). */

  /* قسم "⭐ Following" — نفس تباعد .lgbody، بلا خلفية/حدود خاصة
     (المباريات المنقولة كروتها العادية `.match` كافية بصرياً). */
  /* شريط المتابَعة: نفس .lgsec، بنجمة رفيعة بدل العلم */
  .fstar { width:26px; height:26px; flex:0 0 auto; padding:3px; display:block;
           fill:none; stroke:var(--accent); stroke-width:1.6;
           stroke-linejoin:round; }

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
  .score.pst { font-size:13px; color:var(--muted); }
  .date { grid-column:1/-1; text-align:center; color:var(--muted);
          font-size:12px; margin-top:5px; }
  .date a { color:var(--muted); text-decoration:none; }
  .date a:hover { color:var(--accent); }
  .lg { color:var(--muted); font-size:12px; }

  /* التبويبات */
  .divider { border:none; border-top:1px solid var(--line); margin:38px 0 24px; }
  .tabs { display:flex; gap:8px; justify-content:center;
          margin-bottom:12px; flex-wrap:wrap; }
  .tabs.seasons { margin-bottom:20px; }
  .tab { background:var(--card); color:var(--muted); border:1px solid var(--line);
         padding:8px 18px; border-radius:8px; cursor:pointer;
         font-family:inherit; font-size:14px; transition:.15s;
         min-height:44px; }
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
  /* ⚠️ جدول الترتيب على الشاشات الضيقة: كان `td.team{display:flex}` يجعل الجدول
     أعرض من الشاشة (438px على 390px) فيمتد سكرول أفقي ويُقطع عمود النقاط.
     تخطيط ثابت: أعمدة الأرقام بعرض ثابت، وعمود الفريق يأخذ الباقي ويقصّ الاسم
     بـ… — كل الأعمدة (والنقاط) ظاهرة بلا سكرول. */
  @media (max-width:480px) {
    table { table-layout:fixed; }
    th,td { padding:10px 2px; }
    th:first-child, td.pos { width:26px; }
    th:nth-child(n+3), td:nth-child(n+3) { width:32px; }
    td.team { display:table-cell; }
    td.team img { display:inline-block; vertical-align:middle;
                  margin-inline-end:6px; }
    td.team a { display:inline-block; vertical-align:middle;
                max-width:calc(100% - 30px); }
  }

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


LEAGUE_LOGOS_FILE = BASE_DIR / "league_logos.csv"


def load_league_logos():
    """
    شعارات الدوريات — نفس نمط load_overrides للأندية، لكن بدون
    جدول DB مقابل (LEAGUES بـconfig.py لا تحمل logo). الملف نفسه
    يحمل الرابط الخام (logo، من fetch_standings.py) والاستثناء
    المحلي (logo_local) معاً، لا فقط الاستثناء.

    ⚠️ **يرجع قاموسين لا واحداً** — logos (خام من المزوّد) و
       local (استثناء يدوي)، كي يقرّر league_badge() الأولوية
       (local أولاً) بلا الحاجة لدمجهما هنا.
    """
    logos, local = {}, {}
    if not LEAGUE_LOGOS_FILE.exists():
        return logos, local
    with open(LEAGUE_LOGOS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = clean(row.get("league_code"))
            if not code:
                continue
            if clean(row.get("logo")):
                logos[code] = clean(row["logo"])
            if clean(row.get("logo_local")):
                local[code] = clean(row["logo_local"])
    return logos, local


def league_badge(code, logos, local, fallback):
    """
    رابط شعار الدوري: استثناء محلي، وإلا الخام من المزوّد، وإلا
    fallback (علم الدولة الحالي بـflags/) — **سقوط آمن دائم**،
    قبل أول سحب أو لو دوري بلا شعار بالاستجابة.
    """
    return local.get(code) or logos.get(code) or fallback


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


def player_link(player_en, base_dir, depth, lang="ar"):
    """
    رابط صفحة اللاعب إن وُجدت فعلاً كملف، وإلا "" .
    depth: عمق الصفحة الحالية من **جذر الموقع** (0=الرئيسية العربية، 1=clubs/matches
           أو en/index.html، 2=en/leagues...).
    lang : لغة الصفحة الحالية — صفحات اللاعبين الإنجليزية بـen/players/ لا players/.
    ⚠️ **بدون lang كانت الصفحات الإنجليزية تربط بصفحة اللاعب العربية** (../../players/
       من en/leagues/ = /players/): الزائر الإنجليزي يقع على صفحة عربية.
    """
    s = _pslug(player_en)
    if s not in _player_pages(base_dir):
        return ""
    return ("../" * depth) + ("en/" if lang == "en" else "") + f"players/{s}.html"


# نافذة الأيام المعروضة بالرئيسية: 30 للخلف + اليوم + 90 للأمام
# ⚠️ التوسيع رخيص: 29 يوماً = 135 مباراة، و121 يوماً = 252 فقط
#    (المباريات لا تتضاعف خطياً — الدوريات فيها فجوات)
DAYS_BACK = 30
DAYS_FWD = 90


def window_matches(conn, start, end):
    """كل مباريات النافذة — منتهية وقادمة معاً، مرتّبة بالوقت"""
    return conn.execute("""
        SELECT m.match_id, m.date, m.home_goals, m.away_goals,
               m.league_code, m.season, m.status,
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


def day_script(t, leagues):
    """DAY_SCRIPT مع نصوص اللغة وترتيب الدوريات (JSON)"""
    cfg = {"today": t["d_today"], "yesterday": t["d_yesterday"],
           "tomorrow": t["d_tomorrow"], "weekdays": list(t["WEEKDAYS"]),
           "none": t["d_none"], "leagues": list(leagues)}
    return DAY_SCRIPT.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))


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
        eager_left = EAGER_CARDS
        if day_leagues:
            body = ""
            for code in leagues:
                ms = day_leagues.get(code)
                if not ms:
                    continue
                cards = ""
                for m in ms:
                    cards += match_card(m, lang, logos, show_league=False,
                                        upcoming=(m["home_goals"] is None),
                                        club_ids=True, thumbs=True,
                                        eager=is_today and eager_left > 0)
                    eager_left -= 1
                body += (
                    f'<details class="lgsec" data-sec="{code}" open>'
                    f'<summary>'
                    f'<img class="flag" src="flags/{FLAG[code]}.svg" alt="">'
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
        SELECT m.match_id, m.date, m.league_code, m.season, m.status,
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


# ⚠️ **`hero_results()` و`MYC` و`club_summary()` حُذفت من هنا**
#    (8 سبتمبر) — كانت تبني `hero_results()`: قائمة "آخر النتائج"
#    (لم تُستخدم فعلياً بـbuild() أصلاً)، و`club_summary()`: بطاقة
#    ملخّص كل نادٍ لقسم "أنديتي" المحذوف (راجع MYCLUBS_SORT_SCRIPT
#    وCSS `.match`/`.lgsec` أعلاه للبديل). `hero_upcoming()` تبقى
#    — تُستخدم بـmain() لعدّاد "مباريات قادمة" بالطباعة فقط.
# ⚠️ شعارات الرئيسية المصغّرة (make_logo_thumbs.py): 64px WebP (~3 ك.ب) بدل صور المزوّد الكاملة
#    (~40 ك.ب، حتى 124) المعروضة بـ26px. بلا نسخة لنادٍ ما => يعود لرابط الأصل (لا شعار مكسور).
THUMBS_DIR = BASE_DIR / "thumbs"
EAGER_CARDS = 8   # بطاقات أول شاشة من لوحة اليوم: شعاراتها تُحمَّل فوراً؛ الباقي lazy


def thumb_of(tid):
    return f"thumbs/{tid}.webp" if (THUMBS_DIR / f"{tid}.webp").exists() else None


def match_card(m, lang, logos, show_league=True, upcoming=False,
               club_ids=False, thumbs=False, eager=False):
    """
    بطاقة مباراة واحدة.

    club_ids: يضيف data-h/data-a (فريقا المباراة) — يُفعَّل فقط من
    day_view() لخدمة MYCLUBS_SORT_SCRIPT. الافتراضي False حفاظاً
    على مخرجات match_card() بلا تغيير بكل مكان آخر يستدعيها
    (leagues.html وأرشيف leagues/*.html عبر make_leagues.py).
    """
    def logo_of(tid, fb):
        return logos.get(str(tid), fb)

    def logo_img(tid, fb):
        """thumbs=True (الرئيسية فقط): نسخة 64px + أبعاد ثابتة (بلا قفزة) + lazy تحت أول شاشة"""
        if not thumbs:
            return f'<img src="{logo_of(tid, fb)}" alt="">'
        src = thumb_of(tid) or logo_of(tid, fb)
        return (f'<img src="{src}" alt="" width="26" height="26" decoding="async"'
                + ('' if eager else ' loading="lazy"') + '>')

    hn = tname(m, lang, "home", "home_en")
    an = tname(m, lang, "away", "away_en")
    arrow = "←" if lang == "ar" else "→"

    if upcoming:
        # التاريخ فيه وقت: 2026-08-15 18:00 — UTC خام (بند مفتوح
        # بالـREADME). data-utc يُضاف فقط لو وقت فعلي موجود —
        # matchtime.py يحوّله محلياً وقت العرض؛ بلا JS يبقى
        # موسوماً "UTC" صراحة لا رقماً عارياً (راجع matchtime.py).
        parts = str(m["date"]).split()
        day = parts[0]
        clock = parts[1] if len(parts) > 1 else ""
        # مؤجّلة/ملغاة: التسمية بدل الوقت (class pst لا time فلا يمسّها
        # matchtime.py ولا يقرأها السكربت المباشر كموعد)
        off = off_label(m["status"] if "status" in m.keys() else None,
                        T[lang])
        if off:
            score = f'<div class="score pst">{off}</div>'
        elif clock:
            score = (f'<div class="score time" data-utc="{day}T{clock}:00Z">'
                     f'{clock} UTC</div>')
        else:
            score = '<div class="score time">—</div>'
        cls = "match soon"
        # التاريخ النصي يتحوّل لتاريخ الزائر المحلي (matchtime.py: data-utcd)
        stamp = (f'<span data-utcd="{day}T{clock}:00Z">{day}</span>'
                 if clock and not off else day)
    else:
        score = f'<div class="score">{m["home_goals"]} - {m["away_goals"]}</div>'
        cls = "match"
        # ⚠️ 7 سبتمبر — وقت اختياري بصف `.date` (منفصل تماماً عن
        #    `.score` — صفر ازدحام مع النتيجة، بند مفتوح 28). نفس
        #    نمط `make_clubs.py::build_cards` حرفياً. `data-utc`
        #    فقط لو وقت فعلي موجود — 37 مباراة لا تزال بلا وقت
        #    (بند مفتوح 20)، تبقى بتاريخ وحده بلا أي تعديل.
        parts = str(m["date"]).split()
        day = parts[0]
        clock = parts[1][:5] if len(parts) > 1 else ""
        stamp = (f'<span data-utcd="{day}T{clock}:00Z">{day}</span> '
                 f'<span data-utc="{day}T{clock}:00Z">{clock} UTC</span>'
                 if clock else day)

    lg = ""
    if show_league:
        lg = f' <span class="lg">· {league_name(m["league_code"], lang)}</span>'

    # ⚠️ رابط يغطي البطاقة كاملة (درس: الضغط على السهم وحده صعب
    #    على الجوال). روابط الأندية والتاريخ تعلوه بـz-index فتبقى
    #    تعمل — فالضغط على شعار نادٍ يفتح النادي، وعلى أي مكان آخر
    #    يفتح المباراة.
    club_attrs = (f' data-h="{m["home_id"]}" data-a="{m["away_id"]}"'
                  if club_ids else "")
    return (
        f'<div class="{cls}" data-mid="{m["match_id"]}"{club_attrs}>'
        f'<a class="open" href="matches/{m["match_id"]}.html"'
        f' aria-label="{hn} - {an}"></a>'
        f'<a class="side" href="clubs/{m["home_id"]}.html">'
        f'{logo_img(m["home_id"], m["home_logo"])}'
        f'<span>{hn}</span></a>'
        f'{score}'
        f'<a class="side away" href="clubs/{m["away_id"]}.html">'
        f'<span>{an}</span>'
        f'{logo_img(m["away_id"], m["away_logo"])}</a>'
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
        href = player_link(s["player"], BASE_DIR, depth, lang)
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

    # ---- 3. بطاقات الدوريات والجداول: انتقلت لـleagues.html ----
    #      (21 أغسطس — قرار "الرئيسية للمباريات فقط")

    # ⚠️ **قسم "أنديتي" حُذف من هنا** (8 سبتمبر) — بدلاً منه
    #    مباريات الأندية المتابَعة تصعد أعلى قائمة المباريات
    #    العادية بـday_view() نفسها (راجع MYCLUBS_SORT_SCRIPT).
    #    معلومة المركز/النقاط تُفقد من الرئيسية — قرار محسوم،
    #    موجودة أصلاً بصفحة كل دوري (leagues.html)، لا تعويض لها
    #    هنا بقصد.

    # ⚠️ **المعالج انتقل لـfollowing.html (6 سبتمبر)** — الرئيسية
    #    لم تعد تبني شرائح دوريات/أندية بنفسها، فقط تعرض بطاقة
    #    اختيارية لزائر أول مرة (follow_card_html أدناه، بلا تحويل). راجع
    #    onboard.py (صار مصدر شرائح مشتركة فقط، لا معالج) و
    #    make_following.py (الوضعان: أول زيارة/عائد بنفس الصفحة).
    switch = "en/index.html" if lang == "ar" else "../index.html"

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
        # ⚠️ **ترس الإعدادات الأعلى عاد من جديد (22 سبتمبر)** — بعد
        #    أن انتقل زر "الإعدادات" من الشريط السفلي (صار أربعة
        #    عناصر فقط) لأيقونة علوية وحيدة بخانة النهاية. راجع
        #    navbar.py::settings_button.
        # ⚠️ (4 أكتوبر) العنوان الكبير والجملة تحته حُذفا: اسم التطبيق صار بشريط
        #    التطبيق العلوي (appbar). `h1` مخفي بصرياً يبقى لقارئات الشاشة ومحركات البحث.
        + appbar(t, lang, switch) +
        f'<h1 class="vh">{t["site_title"]}</h1>\n'
        + follow_card_html(t, lang) +
        # ⚠️ **البحث العلوي حُذف** (1 سبتمبر) — كان يكرّر زر
        #    البحث بالشريط السفلي، والسفلي أوضح وأقرب لليد.
        #    طبقة البحث نفسها (`#sovl`) ما زالت مُدرَجة ويفتحها
        #    الشريط — الحذف للحقل الظاهر فقط.

        f'{days_html}\n'
        '</div>\n'
        + navbar(t, 0 if lang == "ar" else 1, "matches", lang)
        + settings_overlay(t, switch, lang)
        + day_script(t, leagues) + THEME_SCRIPT + matchtime_script()
        + prefs_script()
        + follow_section_script(t, 0 if lang == "ar" else 1)
        + follow_card_script()
        + nav_script(t) + pwa_script(lang)
        + live_script(t, 0 if lang == "ar" else 1)
        +
        '</body>\n</html>'
    )

    # الإنجليزي داخل en/ — الشعارات المحلية فقط تحتاج تصحيحاً
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')
        html = html.replace('src="flags/', 'src="../flags/')
        html = html.replace('src="thumbs/', 'src="../thumbs/')

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
