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

import json

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
  .scl { margin-top:2px; max-width:100%; }
  .scl div { font-size:12px; line-height:1.5; color:var(--muted); text-align:center; unicode-bidi:plaintext;
             overflow-wrap:anywhere; }
  .lvfin { font-weight:700; }
  .lvend { display:inline-block; color:var(--muted); font-size:12px;
           font-weight:600; white-space:nowrap; }
"""


# مصدر النتائج المباشرة — Cloudflare Worker
# ⚠️ تغييره هنا يكفي؛ لا مسار نسبي ولا اعتماد على العمق.
LIVE_SRC = "https://saffara-live.abujaishamr.workers.dev/"


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
              "AR": 1 if t.get("lv_ht") == "بين الشوطين" else 0}

    return """
<script>
(function(){
  var SRC="__SRC__", HT="__HT__", LB=__LB__;
  var timer=null;

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

  function paint(data){
    var m=(data&&data.m)||{}, f=(data&&data.f)||{}, S=(data&&data.s)||{};
    var any=false;

    document.querySelectorAll('[data-mid]').forEach(function(card){
      var d=m[card.getAttribute('data-mid')];
      var slot=card.querySelector('.time,.score,.min');
      if(!slot)return;
      // صفحة المباراة: لا موعد انطلاق تحت النتيجة أثناء البث، ولا «لم تبدأ بعد» بصندوق الأحداث
      // (حالة حيّة = 1H/HT/2H/ET/BT/P/LIVE؛ ردّ m لا يحوي سواها). تُستعاد عند خروجها من m.
      var kick=card.querySelector('.kick'), em=card.classList.contains('big')?document.getElementById('evempty'):null;
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
        "__LB__", json.dumps(labels, ensure_ascii=False))
