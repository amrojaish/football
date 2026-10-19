#!/usr/bin/env python3
"""
عرض النتائج المباشرة
======================
وحدة مستقلة على نمط `search_view.py` و`navbar.py`.
لا تشغّلها لحالها — سكربتات التوليد بتستوردها.

تقرأ `live.json` (يكتبه `fetch_live.py`) وتحدّث بطاقات المباريات
**في المتصفح مباشرة** — بلا إعادة توليد أي صفحة.

⚠️ **لماذا هذا الحل:** الحالة المباشرة تتغيّر كل دقيقة. حفظها
   في الديتابيس يعني إعادة توليد 9,000 صفحة ورفع 12 ميغابايت
   كل مرة. هنا: ملف 0.1 كيلوبايت + سكربت يقرأه دورياً.

⚠️ **المصدر Cloudflare Worker لا ملف محلي** (2 سبتمبر).
   `live.json` كان يُكتب عبر GitHub Actions، وGitHub يخنق
   الجدولة الدورية: `*/5` كان ينفَّذ مرة كل ~7 ساعات فعلياً.
   الآن Worker يسحب من المزوّد كل دقيقة ويقدّمها مباشرة.

⚠️ **لا رجوع إلى `live.json` عند الفشل — عمداً.** الملف صار
   جامداً بعد تعطيل `live.yml`، فالرجوع إليه يعرض نتيجة
   **خاطئة** لا قديمة. لا شيء أصدق من رقم كاذب (مبدأ 17).

⚠️ **الفشل بهدوء محلياً** — `fetch()` ممنوع على `file://`،
   فالاختبار المحلي لا يُظهر النتائج المباشرة. هذا متوقَّع.

⚠️ **يتطلب أن تحمل بطاقة المباراة `data-mid`** بمعرّف المباراة
   — وإلا لا يعرف السكربت أي بطاقة يحدّث.

⚠️ **التحديث كل 60 ثانية** أثناء وجود مباريات جارية فقط،
   ويتوقف تلقائياً حين تنتهي كلها — لا استهلاك بلا داعٍ.

⚠️ **النتيجة النهائية بعد الصافرة (4 أكتوبر 2026):** الـWorker يضيف `f` =
   {id: {h, a, s, ft}} للمباريات التي انتهت للتو (12 ساعة). إن كانت
   البطاقة لسا تعرض الموعد (لا نمط نتيجة `n - n` بمحتواها الأصلي) نعرض
   النتيجة + «انتهت» بلا النقطة الحمراء (FT/AET/PEN)، أو حالة المباراة
   (SUSP/ABD/PST/INT). بطاقة فيها نتيجة أصلاً لا تُمسّ. الـWorker القديم
   بلا `f` لا يغيّر شيئاً.

الاستخدام:
    from live_view import LIVE_CSS, live_script
"""

import hashlib
import json
from pathlib import Path

LIVE_CSS = """
  .lv { display:inline-flex; align-items:center; gap:5px;
        background:var(--red); color:#fff; border-radius:6px;
        padding:2px 8px; font-size:12px; font-weight:600;
        white-space:nowrap; }
  .lv .dot { width:6px; height:6px; border-radius:50%;
             background:#fff; animation:lvp 1.4s infinite; }
  @keyframes lvp { 0%,100%{opacity:1} 50%{opacity:.25} }
  .lvscore { color:var(--red) !important; font-weight:700; }
  /* بطاقة قائمة أثناء البث (10 أكتوبر، شكل FotMob): [كبسولة الدقيقة الخضراء] اسم·شعار · نتيجة · شعار·اسم، النتيجة غامقة بيضاء */
  .match.live { grid-template-columns:auto minmax(0,1fr) auto minmax(0,1fr); }
  .lvpill, .lv { direction:ltr; unicode-bidi:isolate; }
  .lvpill { background:var(--green); color:#04170a; border-radius:6px; padding:2px 7px; font-size:12px;
            font-weight:700; white-space:nowrap; min-width:30px; text-align:center; position:relative; z-index:2;
            pointer-events:none; }
  :root[data-theme="light"] .lvpill { color:#fff; }
  .match.live .side { flex-direction:row-reverse; margin-inline-start:auto; }
  .match.live .side.away { margin-inline-start:0; justify-content:flex-start; }
  .match.live .side span { text-align:end; }
  .match.live .side.away span { text-align:start; }
  .match.live .score { background:none; padding:4px 4px; }
  .match.live .score .lvscore { color:var(--text) !important; }
  .match.live .score .lv { display:none; }
  /* صفحة المباراة أثناء البث: النتيجة كبيرة بالمنتصف بالنص الأبيض، تحتها الدقيقة بنقطة نابضة، وتحت كل فريق هدّافوه */
  .big .lvscore { display:block; text-align:center; color:var(--text) !important; }
  .big .lv { display:flex; justify-content:center; background:none; color:var(--green); font-size:15px;
             padding:0; margin-top:4px; }
  .big .lv .dot { background:var(--green); }
  /* شارة نهاية المباراة بصفحة المباراة (12 أكتوبر): بحجم وموضع دقيقة البث لكن رمادية بلا نقطة */
  .big .ftb { display:block; text-align:center; color:var(--muted); font-size:15px; font-weight:600;
              letter-spacing:0; margin-top:4px; direction:ltr; unicode-bidi:isolate; }
  /* الترتيب المباشر (12 أكتوبر): شارة «مباشر» فوق الجدول، نقطة بجانب الفريقين اللاعبين، سهم تغيّر المركز */
  .ltlive { display:flex; align-items:center; gap:7px; font-size:12px; font-weight:700; color:var(--green);
            margin:8px 2px 6px; }
  .ltlive .lvdot { width:7px; height:7px; border-radius:50%; background:var(--green); animation:lvp 1.4s infinite;
                   flex:0 0 auto; }
  .ltlive .ltn { color:var(--muted); font-weight:500; }
  tr.lvrow td:nth-child(2) a::after { content:"●"; color:var(--green); font-size:9px; margin-inline-start:5px;
                                      vertical-align:middle; }
  td.ps, td.pos { position:relative; }
  .chg { position:absolute; top:1px; inset-inline-start:3px; font-size:8px; line-height:1; font-weight:700; }
  .chg.up { color:var(--green); }
  .chg.dn { color:var(--red); }
  .mtab.lvt::after { content:"●"; color:var(--green); font-size:9px; margin-inline-start:5px; }
  .scl { margin-top:2px; max-width:100%; }
  .scl div { font-size:12px; line-height:1.5; color:var(--muted); text-align:center; unicode-bidi:plaintext;
             overflow-wrap:anywhere; }
  .lvfin { font-weight:700; }
  .lvend { display:inline-block; color:var(--muted); font-size:12px;
           font-weight:600; white-space:nowrap; }
"""


def live_table_ver():
    """hash (8) لـassets_src/live_table.js — نفس صيغة make_assets.py (sha1 للبايتات، أول 8) كي يطابق ?v= بالمانيفست."""
    p = Path(__file__).resolve().parent / "assets_src" / "live_table.js"
    try:
        return hashlib.sha1(p.read_bytes().decode("utf-8").encode("utf-8")).hexdigest()[:8]
    except OSError:
        return "0"


# مصدر النتائج المباشرة — Cloudflare Worker
# ⚠️ تغييره هنا يكفي؛ لا مسار نسبي ولا اعتماد على العمق.
LIVE_SRC = "https://saffara-live.abujaishamr.workers.dev/"
EVENTS_SRC = LIVE_SRC + "events"


def ev_live_json(m):
    """#evlive لصفحة مباراة بلا أحداث محفوظة: {id, ko, src} — يجلب منه سكربت live أحداث ev:<id> بعد خروجها من m (19 أكتوبر 2026)."""
    parts = str(m["date"] or "").split()
    if len(parts) < 2 or not parts[1][:5]:
        return ""
    data = {"id": m["match_id"], "ko": f"{parts[0]}T{parts[1][:5]}:00Z", "src": EVENTS_SRC}
    return f'<script type="application/json" id="evlive">{json.dumps(data, separators=(",", ":"))}</script>'


def live_script(t, depth=0):
    """
    depth : غير مستعمل — أُبقي للتوافق مع الاستدعاءات القائمة.
            المصدر رابط مطلق فلا يتأثر بعمق الصفحة.
    """
    ht = t.get("lv_ht", "بين الشوطين")
    # تسميات الحالات بعد الانتهاء (f) — من i18n
    labels = {"END": t.get("lv_end", "انتهت"),
              "SUSP": t.get("lv_susp", "معلّقة"),
              "ABD": t.get("lv_abd", "ملغاة"),
              "PST": t.get("lv_pst", "مؤجَّلة"),
              "INT": t.get("lv_int", "متوقفة مؤقتاً"),
              "EVLIVE": t.get("lv_events", "مباشر — الأحداث بتنزل بعد الماتش"),
              "HTS": t.get("lv_ht_short", "استراحة"), "OG": t.get("lv_og", "ع"), "PEN": t.get("lv_pen", "ج"),
              "PENF": t.get("penalty", "ركلة جزاء"), "OGF": t.get("own_goal", "هدف عكسي"),
              "LT_LIVE": t.get("lt_live", "مباشر"), "LT_NOTE": t.get("lt_note", ""),
              "AR": 1 if t.get("lv_ht") == "بين الشوطين" else 0}

    return """
<script>
(function(){
  var SRC="__SRC__", HT="__HT__", LB=__LB__;
  var timer=null;

  // ── الترتيب المباشر (12 أكتوبر) ──
  // جداول الصفحة بسمة data-lt (دوري) + data-ss (موسم) + data-lid (معرّف المزوّد): إن كان بالدوري مباراة جارية (m) أو انتهت للتو (f، بـlg)
  // نجلب لقطته /assets/table_<CODE>_<season>.json مرة واحدة ونشغّل liveTable() (assets/live_table.js، يُحمَّل كسولاً) ونعيد ترتيب الصفوف
  // الموجودة. أي فشل (لقطة/سكربت) أو دوري مطفأ (لا ملف) = يبقى الثابت. تنتهي المباراة وتُعاد الصفحة = يُستعاد الأصل.
  var LTJS="__LTJS__", LTQ=null, LTSNAP={}, LTLAST=null;
  function ltScript(cb){
    if(window.liveTable){cb();return;}
    if(LTQ){LTQ.push(cb);return;}
    LTQ=[cb];
    var s=document.createElement('script');
    s.src=LTJS;
    s.onload=function(){var q=LTQ;LTQ=null;q.forEach(function(f){f();});};
    s.onerror=function(){LTQ=null;};
    document.head.appendChild(s);
  }
  function ltSnap(code,season,cb){
    var k=code+'_'+season;
    if(LTSNAP[k]===undefined){
      LTSNAP[k]=null;
      fetch('/assets/table_'+k+'.json',{cache:'no-cache'})
        .then(function(r){return r.ok?r.json():false;}).catch(function(){return false;})
        .then(function(j){LTSNAP[k]=j||false;if(LTLAST)ltPaint(LTLAST.m,LTLAST.f);});
      return;
    }
    if(LTSNAP[k])cb(LTSNAP[k]);
  }
  function ltRelevant(lid,m,f){
    var k,e;
    for(k in m){e=m[k];if(e&&e.lg===lid)return true;}
    for(k in f){e=f[k];if(e&&e.lg===lid&&(e.s==='FT'||e.s==='AET'||e.s==='PEN'))return true;}
    return false;
  }
  function ltRestore(tbl){
    var o=tbl._lto;
    if(!o)return;
    var body=o[0].tr.parentNode;
    o.forEach(function(x){x.tr.innerHTML=x.html;x.tr.className=x.cls;body.appendChild(x.tr);});
    tbl._lto=null;
    if(tbl._ltb){tbl._ltb.parentNode.removeChild(tbl._ltb);tbl._ltb=null;}
    var tb=document.querySelector('.mtab[data-tab="table"]');
    if(tb)tb.classList.remove('lvt');
  }
  // كتلة المركزين: المركز/النقاط/المباريات لكل [data-t] من الحساب المباشر؛ الأصل يُحفظ مرة ويُستعاد حين لا شيء مباشر
  function ltPos(el,res){
    var rows={};
    [].forEach.call(el.querySelectorAll('[data-t]'),function(x){rows[x.getAttribute('data-t')]=x;});
    if(!el._lto){el._lto=[];for(var k in rows)el._lto.push({x:rows[k],html:rows[k].innerHTML,cls:rows[k].className});}
    res.rows.forEach(function(r,i){
      var x=rows[String(r.team_id)];
      if(!x)return;
      x.querySelector('.lpr').textContent=i+1;
      x.querySelector('.lpp').textContent=r.points;
      x.querySelector('.lpm').textContent=r.played;
      x.classList.toggle('lvrow',!!r.live);
    });
  }
  function ltPosRestore(el){
    var o=el._lto;
    if(!o)return;
    o.forEach(function(y){y.x.innerHTML=y.html;y.x.className=y.cls;});
    el._lto=null;
  }
  function ltRender(tbl,res){
    var list=[].slice.call(tbl.querySelectorAll('tr[data-t]')),rows={};
    if(!list.length)return;
    list.forEach(function(tr){rows[tr.getAttribute('data-t')]=tr;});
    if(!tbl._lto)tbl._lto=list.map(function(tr){return {tr:tr,html:tr.innerHTML,cls:tr.className};});
    var body=list[0].parentNode,n=res.rows.length;
    res.rows.forEach(function(r,i){
      var tr=rows[String(r.team_id)];
      if(!tr)return;
      var c=tr.children,hl=tr.classList.contains('hl');
      tr.className=(hl?'hl ':'')+(i<3?'top':(i>=n-2?'bottom':''))+(r.live?' lvrow':'');
      c[0].textContent=i+1;
      if(r.base_pos!==r.pos){
        var a=document.createElement('i');
        a.className='chg '+(r.pos<r.base_pos?'up':'dn');
        a.textContent=r.pos<r.base_pos?'▲':'▼';
        c[0].appendChild(a);
      }
      c[2].textContent=r.played;c[3].textContent=r.wins;c[4].textContent=r.draws;c[5].textContent=r.losses;
      c[6].textContent=(r.diff>=0?'+':'')+r.diff;c[7].textContent=r.points;
      body.appendChild(tr);
    });
    if(!tbl._ltb){
      var b=document.createElement('div');
      b.className='ltlive';
      b.innerHTML='<span class="lvdot"></span><span>'+LB.LT_LIVE+'</span><span class="ltn">\u00B7 '+LB.LT_NOTE+'</span>';
      tbl.parentNode.insertBefore(b,tbl);
      tbl._ltb=b;
    }
    var tb=document.querySelector('.mtab[data-tab="table"]');
    if(tb)tb.classList.add('lvt');
  }
  function ltPaint(m,f){
    LTLAST={m:m||{},f:f||{}};
    // جداول الترتيب الكاملة + كتلة «مركزا الفريقين» المدمجة بصفحة المباراة (.ltpos، دفعة D2): نفس اللقطة والحساب
    var tables=document.querySelectorAll('table[data-lt], .ltpos[data-lt]');
    if(!tables.length)return;
    tables.forEach(function(tbl){
      var lid=+tbl.getAttribute('data-lid'), pos=tbl.tagName!=='TABLE';
      var restore=pos?ltPosRestore:ltRestore;
      if(!ltRelevant(lid,LTLAST.m,LTLAST.f)){restore(tbl);return;}
      ltScript(function(){
        ltSnap(tbl.getAttribute('data-lt'),tbl.getAttribute('data-ss'),function(snap){
          var res=window.liveTable(snap,LTLAST.m,LTLAST.f);
          if(!res||(!res.live&&!res.addedF)){restore(tbl);return;}
          if(pos)ltPos(tbl,res);else ltRender(tbl,res);
        });
      });
    });
  }

  // هدّافو الفريقين تحت أسمائهم (صفحة المباراة): [side, دقيقة, إضافي, اسم لاتيني, عربي مؤكَّد أو "", وسم]
  // العربي: الاسم المؤكَّد فقط وإلا الدقيقة وحدها (لا لاتيني داخل نص عربي). textContent: أسماء المزوّد لا تُحقن كـHTML.
  function fillSc(root,list){
    root.querySelectorAll('.scl').forEach(function(box){
      var side=box.getAttribute('data-sc');
      box.textContent='';
      (list||[]).forEach(function(r){
        if(r[0]!==side)return;
        var nm=LB.AR?r[4]:r[3];
        var tag=r[5]==='og'?' ('+LB.OG+')':(r[5]==='p'?' ('+LB.PEN+')':'');
        var d=document.createElement('div');
        d.textContent=(nm?nm+' ':'')+r[1]+(r[2]?'+'+r[2]:'')+"'"+tag;
        box.appendChild(d);
      });
    });
  }

  /* أحداث المباراة الجارية بصفحة المباراة (13 أكتوبر، 3D): حمولة live تحمل v = {id: [[دقيقة، إضافي، نوع g/c/s/v، تفصيل، لاعب، مساعد/داخل، جهة h/a]…]}
     ← نفس صفوف .ev التي يولّدها make_matches.py للمباراة المنتهية. اللاعب بالتبديل = الخارج والمساعد = الداخل (كجدول events). الأسماء كما أعطاها المزوّد. */
  var CARDIC={y:String.fromCodePoint(0x1F7E8),r:String.fromCodePoint(0x1F7E5),yr:String.fromCodePoint(0x1F7E8,0x1F7E5)};
  /* الأسماء العربية (19 أكتوبر 2026): #pidmap = {n: {pid: اسم عربي}} تضمّنه الصفحة العربية بلا أحداث محفوظة؛ الصف [7]/[8] = معرّفا اللاعب
     والمساعد/الداخل. مجهول = اسم المزوّد. */
  var PM=null;
  function arName(id,nm){
    if(!LB.AR||id==null)return nm;
    if(!PM){PM={};try{var pe=document.getElementById('pidmap');if(pe)PM=(JSON.parse(pe.textContent).n)||{};}catch(e){PM={};}}
    return PM[String(id)]||nm;
  }
  function liveEvents(data){
    var V=(data&&data.v)||{}, M=(data&&data.m)||{};
    var big=document.querySelector('.big[data-mid]');
    if(!big)return;
    var id=big.getAttribute('data-mid'), list=V[id];
    if(!list||!M[id]||!list.length)return;
    drawEvents(list);
  }
  /* بعد صافرة النهاية (19 أكتوبر 2026): #evlive = {id, ko, src} تضعه الصفحة حين لا أحداث محفوظة وانطلاقها خلال 36 ساعة. حين تخرج المباراة
     من m (أو تُفتح الصفحة بعدها) نجلب ev:<id> من /events مرة واحدة. الأحداث المحفوظة (جدول events) تغلب دائماً: #evbox ثابت بلا
     data-lvsig ولا data-goalsonly = لا طلب؛ قائمة أهداف فقط (data-goalsonly) تُستبدل بالنسخة الكاملة. */
  var EVDONE=false;
  function evAfter(data){
    if(EVDONE)return;
    var ce=document.getElementById('evlive');
    if(!ce)return;
    var C;try{C=JSON.parse(ce.textContent);}catch(e){return;}
    var M=(data&&data.m)||{};
    if(M[String(C.id)])return;   // جارية: live.v
    var ko=Date.parse(C.ko),now=Date.now();
    if(!(ko>0)||now<ko||now>ko+36*3600000)return;
    var box=document.getElementById('evbox');
    if(box&&!box.hasAttribute('data-lvsig')&&!box.hasAttribute('data-goalsonly'))return;
    EVDONE=true;
    fetch(C.src+'?id='+C.id).then(function(r){return r.ok?r.json():null;})
      .then(function(J){if(J&&Array.isArray(J.l)&&J.l.length)drawEvents(J.l);}).catch(function(){});
  }
  function drawEvents(list){
    var sig=JSON.stringify(list), box=document.getElementById('evbox');
    if(box&&box.getAttribute('data-lvsig')===sig)return;
    if(!box){
      var em=document.getElementById('evempty');
      if(!em)return;
      box=document.createElement('div'); box.className='goals'; box.id='evbox';
      em.parentNode.replaceChild(box,em);
    }
    box.setAttribute('data-lvsig',sig);
    var rows=list.map(function(r){return {min:r[0],extra:r[1],t:r[2],d:r[3],p:arName(r[7],r[4]),a:arName(r[8],r[5]),side:r[6]};})
      .filter(function(r){return !(r.t==='g'&&r.d==='m');})
      .sort(function(x,y){return (x.min*1000+x.extra)-(y.min*1000+y.extra);});
    var arrow=LB.AR?'\u2190':'\u2192';
    box.innerHTML='';
    rows.forEach(function(r){
      var icon=String.fromCodePoint(0x1F4FA), major=false, kind='', body=document.createElement('span'); body.className='who';
      if(r.t==='g'){icon='\u26BD';major=true;body.textContent=r.p||'\u2014';kind=r.d==='p'?LB.PENF:(r.d==='o'?LB.OGF:'');}
      else if(r.t==='c'){icon=CARDIC[r.d]||CARDIC.y;major=(r.d==='r'||r.d==='yr');body.textContent=r.p||'\u2014';}
      else if(r.t==='s'){
        icon=String.fromCodePoint(0x1F504);
        var i=document.createElement('span'); i.className='in'; i.textContent=r.a;
        var o=document.createElement('span'); o.className='out'; o.textContent=r.p;
        body.appendChild(i); body.appendChild(document.createTextNode(' '+arrow+' ')); body.appendChild(o);
      }else{body.textContent=r.d||'VAR';}
      var home=r.side==='h', row=document.createElement('div');
      row.className='ev '+(home?'h':'a')+(major?'':' minor');
      var txt=document.createElement('span'); txt.className='evt'; txt.appendChild(body);
      if(kind){var k=document.createElement('span'); k.className='kind'; k.textContent=kind; txt.appendChild(k);}
      var ic=document.createElement('span'); ic.className='ic'; ic.textContent=icon;
      var cell=document.createElement('span'); cell.className='evc on';
      if(home){cell.appendChild(txt);cell.appendChild(ic);}else{cell.appendChild(ic);cell.appendChild(txt);}
      var blank=document.createElement('span'); blank.className='evc';
      var mn=document.createElement('span'); mn.className='min'; mn.textContent=r.min+(r.extra?'+'+r.extra:'')+"'";
      row.appendChild(home?cell:blank); row.appendChild(mn); row.appendChild(home?blank:cell);
      box.appendChild(row);
    });
  }

  function paint(data){
    var m=(data&&data.m)||{}, f=(data&&data.f)||{}, S=(data&&data.s)||{};
    var any=false;
    try{liveEvents(data);}catch(e){}
    try{evAfter(data);}catch(e){}

    document.querySelectorAll('[data-mid]').forEach(function(card){
      var d=m[card.getAttribute('data-mid')];
      var slot=card.querySelector('.time,.score,.min');
      if(!slot)return;
      // صفحة المباراة: لا موعد انطلاق تحت النتيجة أثناء البث، ولا «لم تبدأ بعد» بصندوق الأحداث
      // (حالة حيّة = 1H/HT/2H/ET/BT/P/LIVE؛ ردّ m لا يحوي سواها). تُستعاد عند خروجها من m.
      var kick=card.querySelector('.kick'), em=card.classList.contains('big')?document.getElementById('evempty'):null;
      /* (14 أكتوبر) بدأت المباراة: تبويب/عنوان «نظرة عامة» ← «الأحداث» (النص بسمة data-live؛ لا يعود لـ«نظرة عامة» بعد البدء) */
      if(card.classList.contains('big')&&(d||(f[card.getAttribute('data-mid')]))){
        ['.mtab[data-tab="events"]','#evh'].forEach(function(sel){
          var el=document.querySelector(sel), lb=el&&el.getAttribute('data-live');
          if(lb&&el.textContent!==lb)el.textContent=lb;
        });
      }
      if(kick)kick.style.display=d?'none':'';
      if(em){
        if(em.dataset.lvOrig==null)em.dataset.lvOrig=em.textContent;
        em.textContent=d?LB.EVLIVE:em.dataset.lvOrig;
      }

      if(!d){
        if(card.classList.contains('live')){
          card.classList.remove('live');
          var op=card.querySelector('.lvpill'); if(op)op.parentNode.removeChild(op);
        }
        if(card.classList.contains('big'))fillSc(card.parentNode,null);
        // انتهت أو لم تبدأ — نعيد الأصل إن كنا غيّرناه
        var orig=card.dataset.lvOrig;
        var e=f[card.getAttribute('data-mid')];
        // النتيجة النهائية: فقط إن كان الأصل (قبل أي تعديل منا) يعرض الموعد
        // لا نتيجة — صفحة فيها النتيجة أصلاً لا تُمسّ
        var base=orig!=null?orig:slot.innerHTML;
        if(e&&!/\\d+\\s*[-–]\\s*\\d+/.test(base.replace(/<[^>]*>/g,''))){
          if(orig==null) card.dataset.lvOrig=slot.innerHTML;
          if(e.s==='FT'||e.s==='AET'||e.s==='PEN'){
            if(card.classList.contains('big')){
              // صفحة المباراة: النتيجة وتحتها شارة «FT» بنمط دقيقة البث (بدل الجملة الكاملة)
              slot.innerHTML='<span class="lvfin">'+(e.h!=null?e.h:0)+' - '+(e.a!=null?e.a:0)+'</span>';
              if(!card.querySelector('.ftb')){
                var fb=document.createElement('span'); fb.className='ftb'; fb.setAttribute('data-lv','1');
                fb.textContent=e.s; card.insertBefore(fb,kick||null);
              }
              if(kick)kick.style.display='none';   // لا عدّ تنازلي لمباراة انتهت
            }else{
              slot.innerHTML='<span class="lvfin">'+(e.h!=null?e.h:0)+' - '
                +(e.a!=null?e.a:0)+'</span> <span class="lvend">'+LB.END+'</span>';
            }
          }else if(LB[e.s]){
            slot.innerHTML='<span class="lvend">'+LB[e.s]+'</span>';
          }
          return;
        }
        if(orig!=null){
          slot.innerHTML=orig;
          delete card.dataset.lvOrig;
          var xb=card.querySelector('.ftb[data-lv]'); if(xb)xb.parentNode.removeChild(xb);
        }
        return;
      }

      any=true;
      var lb=card.querySelector('.ftb'); if(lb)lb.parentNode.removeChild(lb);   // مباشرة الآن: لا شارة FT (ولا قديمة)
      if(!card.dataset.lvOrig) card.dataset.lvOrig=slot.innerHTML;

      var label = d.s==='HT' ? HT
                : (d.e!=null ? d.e+"'" : '');
      var score = (d.h!=null?d.h:0)+' - '+(d.a!=null?d.a:0);

      if(card.classList.contains('big')){
        fillSc(card.parentNode,S[card.getAttribute('data-mid')]);
      }else{
        card.classList.add('live');
        var pill=card.querySelector('.lvpill');
        if(!pill){ pill=document.createElement('span'); pill.className='lvpill'; card.insertBefore(pill,card.querySelector('.side')); }
        pill.textContent = d.s==='HT' ? LB.HTS : (d.e!=null ? d.e+"'" : '•');
      }

      slot.innerHTML='<span class="lvscore">'+score+'</span>'
        +' <span class="lv"><span class="dot"></span>'
        +label+'</span>';
    });

    try{ltPaint(m,f);}catch(e){}   // الترتيب المباشر: فشله لا يمسّ البطاقات

    // نوقف السحب حين لا يبقى شيء جارٍ — لا استهلاك بلا داعٍ
    if(!any&&timer){clearInterval(timer);timer=null;}
  }

  function load(){
    fetch(SRC+'?_='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){if(d)paint(d);})
      .catch(function(){});
  }

  load();
  timer=setInterval(load,60000);

  // إعادة السحب فور عودة التبويب للواجهة
  document.addEventListener('visibilitychange',function(){
    if(!document.hidden)load();
  });
})();
</script>""".replace("__SRC__", LIVE_SRC).replace("__HT__", ht).replace(
        "__LB__", json.dumps(labels, ensure_ascii=False)).replace(
        "__LTJS__", "/assets/live_table.js?v=" + live_table_ver())
