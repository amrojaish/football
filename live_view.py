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
              "INT": t.get("lv_int", "متوقفة مؤقتاً")}

    return """
<script>
(function(){
  var SRC="__SRC__", HT="__HT__", LB=__LB__;
  var timer=null;

  function paint(data){
    var m=(data&&data.m)||{}, f=(data&&data.f)||{};
    var any=false;

    document.querySelectorAll('[data-mid]').forEach(function(card){
      var d=m[card.getAttribute('data-mid')];
      var slot=card.querySelector('.time,.score,.min');
      if(!slot)return;

      if(!d){
        // انتهت أو لم تبدأ — نعيد الأصل إن كنا غيّرناه
        var orig=card.dataset.lvOrig;
        var e=f[card.getAttribute('data-mid')];
        // النتيجة النهائية: فقط إن كان الأصل (قبل أي تعديل منا) يعرض الموعد
        // لا نتيجة — صفحة فيها النتيجة أصلاً لا تُمسّ
        var base=orig!=null?orig:slot.innerHTML;
        if(e&&!/\\d+\\s*[-–]\\s*\\d+/.test(base.replace(/<[^>]*>/g,''))){
          if(orig==null) card.dataset.lvOrig=slot.innerHTML;
          if(e.s==='FT'||e.s==='AET'||e.s==='PEN'){
            slot.innerHTML='<span class="lvfin">'+(e.h!=null?e.h:0)+' - '
              +(e.a!=null?e.a:0)+'</span> <span class="lvend">'+LB.END+'</span>';
          }else if(LB[e.s]){
            slot.innerHTML='<span class="lvend">'+LB[e.s]+'</span>';
          }
          return;
        }
        if(orig!=null){
          slot.innerHTML=orig;
          delete card.dataset.lvOrig;
        }
        return;
      }

      any=true;
      if(!card.dataset.lvOrig) card.dataset.lvOrig=slot.innerHTML;

      var label = d.s==='HT' ? HT
                : (d.e!=null ? d.e+"'" : '');
      var score = (d.h!=null?d.h:0)+' - '+(d.a!=null?d.a:0);

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
