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

الاستخدام:
    from live_view import LIVE_CSS, live_script
"""

LIVE_CSS = """
  .lv { display:inline-flex; align-items:center; gap:5px;
        background:var(--red); color:#fff; border-radius:6px;
        padding:2px 8px; font-size:12px; font-weight:600;
        white-space:nowrap; }
  .lv .dot { width:6px; height:6px; border-radius:50%;
             background:#fff; animation:lvp 1.4s infinite; }
  @keyframes lvp { 0%,100%{opacity:1} 50%{opacity:.25} }
  .lvscore { color:var(--red) !important; font-weight:700; }
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

    return """
<script>
(function(){
  var SRC="__SRC__", HT="__HT__";
  var timer=null;

  function paint(data){
    var m=(data&&data.m)||{};
    var any=false;

    document.querySelectorAll('[data-mid]').forEach(function(card){
      var d=m[card.getAttribute('data-mid')];
      var slot=card.querySelector('.time,.score,.min');
      if(!slot)return;

      if(!d){
        // انتهت أو لم تبدأ — نعيد الأصل إن كنا غيّرناه
        if(card.dataset.lvOrig){
          slot.innerHTML=card.dataset.lvOrig;
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
</script>""".replace("__SRC__", LIVE_SRC).replace("__HT__", ht)
