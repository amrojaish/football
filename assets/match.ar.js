/* live */
try{
(function(){
  var SRC="https://saffara-live.abujaishamr.workers.dev/", HT="بين الشوطين", LB={"END": "انتهت", "SUSP": "معلّقة", "ABD": "ملغاة", "PST": "مؤجَّلة", "INT": "متوقفة مؤقتاً"};
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
        if(e&&!/\d+\s*[-–]\s*\d+/.test(base.replace(/<[^>]*>/g,''))){
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
}catch(e){console.error('live',e);}
;
/* match-page */
var hb=document.querySelector(".h2hmore");
if(hb)hb.addEventListener("click",function(){
document.querySelectorAll(".h2hlist a.hidden")
.forEach(function(x){x.classList.remove("hidden");});
this.style.display="none";});
document.querySelectorAll(".vtab").forEach(function(t){
t.addEventListener("click",function(){
var key=this.dataset.v==="key";
document.querySelectorAll(".vtab").forEach(function(x){
x.classList.toggle("on",x===t);});
document.querySelectorAll(".ev.minor").forEach(function(e){
e.classList.toggle("off",key);});
});});

