#!/usr/bin/env python3
"""
تحويل وقت المباريات للمنطقة الزمنية المحلية — عرض فقط
=========================================================
`matches.date` مخزَّن UTC خام بلا أي علامة منطقة زمنية (بند
مفتوح بالـREADME — درس التوقيت 6 سبتمبر). التحويل **بجافاسكربت
وقت العرض لا وقت التوليد** — المتصفح يعرف منطقة الزائر الزمنية
تلقائياً، بلا اختيار يدوي من أحد.

الآلية: أي عنصر HTML يحمل `data-utc="2026-09-08T18:00:00Z"`
(ISO صريح، `Z` = UTC بلا لبس) يُمسَح بعد التحميل ويُستبدَل نصّه
بالوقت المحلي عبر `Intl.DateTimeFormat`.

⚠️ **بلا JS يبقى النص الأولي المولَّد ظاهراً كما هو** — موسوم
   صراحة `"18:00 UTC"` لا رقماً عارياً. زائر بلا JS يعرف على
   الأقل أنه UTC ويقدر يحسب فرقه بنفسه (درس 1: لا صمت — الوضع
   السابق كان UTC خام بلا تسمية، يُقرأ خطأً كأنه محلي).

⚠️ **لا يُضاف `data-utc` إلا لصفوف فيها وقت فعلي فعلاً.** مباريات
   منتهية مخزَّنة بتاريخ بلا وقت (`fetch_matches2.py` يخزّن
   `date[:10]` فقط — بند مفتوح منفصل) تبقى بلا السمة كلياً،
   فيتخطاها هذا السكربت بلا أي تعديل — لا اختراع `00:00`.

⚠️ **التاريخ النصي:** `data-utcd="<ISO UTC>"` على span يلفّ `YYYY-MM-DD` فقط
   فيُستبدل بالتاريخ المحلي بنفس الصيغة (بلا JS يبقى تاريخ UTC كما كان).
   أما إعادة تجميع أيام الرئيسية (تبويبات اليوم/أمس/غداً) فتتم بـDAY_SCRIPT
   بـ`make_site3.py` (بند 21 — طُبّق 6 أكتوبر).

⚠️ **مستقل عن `prefs.py` عمداً** — المنطقة الزمنية معلومة من
   المتصفح لا تفضيل مخزَّن، فلا علاقة لها بـ`localStorage`/
   `FBPrefs`. خلطهما يخالف فصل المسؤوليات المعتمَد هالجلسة.

يُستهلَك بأربعة مولّدات — أي صفحة تعرض وقت مباراة:
    make_site3.py    (كروت أيام الرئيسية + سطور "أنديتي")
    make_leagues.py  (تبويب مباريات صفحة الدوري — match_card نفسها)
    make_clubs.py    (قائمة مباريات صفحة النادي)
    make_matches.py  (صفحة المباراة)

الاستخدام:
    from matchtime import matchtime_script
    ... + matchtime_script() + ...
"""


def matchtime_script():
    return """
<script>
(function(){
  var els = document.querySelectorAll('[data-utc]');
  var dels = document.querySelectorAll('[data-utcd]');
  if (!els.length && !dels.length) return;
  var cdEls = document.querySelectorAll('[data-cd]');
  var fmt;
  try {
    fmt = new Intl.DateTimeFormat(undefined,
      {hour: '2-digit', minute: '2-digit', hour12: false});
  } catch(e) { return; }
  els.forEach(function(el){
    try {
      var d = new Date(el.dataset.utc);
      if (isNaN(d.getTime())) return;
      el.textContent = fmt.format(d);
    } catch(e) {}
  });
  // التاريخ النصي (YYYY-MM-DD) بجانب الوقت: يتبع يوم الزائر المحلي بنفس الصيغة
  function p2(n){ return (n < 10 ? '0' : '') + n; }
  dels.forEach(function(el){
    try {
      var d = new Date(el.dataset.utcd);
      if (isNaN(d.getTime())) return;
      el.textContent = d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
    } catch(e) {}
  });

  // ── عدّ تنازلي للموعد (10 أكتوبر) — جافاسكربت فقط، بلا API ──
  // [data-cd="page"] (صفحة المباراة، تحت الوقت الكبير): أبعد من 24س → التاريخ المحلي؛ ≤24س → HH:MM:SS؛ عند 0 → «بلشت».
  // [data-cd="card"] (بطاقة القائمة، نفس عنصر الوقت): أبعد من ساعة → الوقت فقط؛ ≤ساعة → «بعد N د» / "in N min"،
  //   <دقيقة → «بعد أقل من دقيقة»؛ عند 0 → «بلشت». (لا MM:SS: يُقرأ كساعة.)
  // لا سالب أبداً. بعد 3 ساعات من الموعد بلا نتيجة (البيانات متأخرة) نرجع للتاريخ/الوقت بدل «بلشت» للأبد.
  // حين يتولّى البث المباشر (live_view: data-lvOrig على البطاقة) أو تظهر النتيجة لا نلمس العنصر.
  // ⚠️ مؤقّت واحد يعيد استعلام الـDOM كل نبضة (لا مراجع محفوظة): بطاقات تُنقل/تُستنسخ/تُضاف لاحقاً تعمل تلقائياً.
  //    النبضة ثانية واحدة إن وُجد عدّاد صفحة، وإلا 30 ث (البطاقات بالدقيقة).
  if (document.querySelector('[data-cd]')) {
    var AR = (document.documentElement.lang || '').indexOf('ar') === 0;
    var STARTING = AR ? 'بلشت' : 'Starting';
    var LESS = AR ? 'بعد أقل من دقيقة' : 'in <1 min';
    var inMin = function(n){ return AR ? 'بعد ' + n + ' د' : 'in ' + n + ' min'; };
    var HOUR = 3600000, DAY = 86400000, GRACE = 3 * HOUR;
    var setT = function(el, txt, cls){
      if (el.textContent !== txt) el.textContent = txt;
      if (cls != null && el.className !== cls) el.className = cls;
    };
    var hms = function(ms){
      var s = Math.max(0, Math.floor(ms / 1000));
      return p2(Math.floor(s / 3600)) + ':' + p2(Math.floor(s % 3600 / 60)) + ':' + p2(s % 60);
    };
    var tick = function(){
      var now = Date.now(), live = false, pageEl = false;
      document.querySelectorAll('[data-cd]').forEach(function(el){
        var ko = new Date(el.dataset.ko).getTime();
        if (isNaN(ko)) return;
        var card = el.closest('[data-mid]');
        if (card && card.dataset.lvOrig != null) return;           // البث المباشر/النتيجة تولّت
        var diff = ko - now, d = new Date(ko);
        var date = d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
        if (diff > -GRACE) live = true;
        if (el.dataset.cd === 'page') {
          pageEl = true;
          if (diff > DAY || diff <= -GRACE) { setT(el, date, 'kick dt'); el.style.direction = ''; }
          else { setT(el, diff > 0 ? hms(diff) : STARTING, 'kick'); el.style.direction = 'ltr'; }
        } else {
          var base = fmt.format(d);
          if (diff > 0 && diff <= HOUR) setT(el, diff < 60000 ? LESS : inMin(Math.floor(diff / 60000)));
          else if (diff <= 0 && -diff < GRACE) setT(el, STARTING);
          else setT(el, base);
        }
      });
      return {live: live, page: pageEl};
    };
    var run = function(){
      var s = tick();
      if (!s.live) return;
      setTimeout(run, s.page ? 1000 : 30000);
    };
    run();
  }
})();
</script>"""
