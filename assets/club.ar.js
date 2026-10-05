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
/* club-page */
const T=document.querySelectorAll(".stab");
const P=document.querySelectorAll(".spanel");
function go(k){P.forEach(p=>p.classList.toggle("on",p.id==="s_"+k));
T.forEach(t=>t.classList.toggle("active",t.dataset.k===k));
var a=document.querySelector(".stab.active");
var l=document.getElementById("seasonlbl");
if(a&&l)l.textContent=a.textContent;}
T.forEach(t=>t.addEventListener("click",function(){
go(this.dataset.k);
var b=document.getElementById("seasonbox");if(b)b.classList.remove("on");
}));
if(T.length)go(T[0].dataset.k);
document.querySelectorAll(".itab").forEach(function(b){
b.addEventListener("click",function(){
var sec=this.closest(".spanel");
sec.querySelectorAll(".itab").forEach(function(x){
x.classList.toggle("on",x===b);});
sec.querySelectorAll(".iview").forEach(function(v){
v.classList.toggle("on",v.id===b.dataset.i);});
});});
document.querySelectorAll(".more.step").forEach(function(b){
b.addEventListener("click",function(){
var box=this.previousElementSibling;
var hid=box.querySelectorAll(".hidden");
for(var i=0;i<5&&i<hid.length;i++)hid[i].classList.remove("hidden");
var left=box.querySelectorAll(".hidden").length;
if(left===0){this.style.display="none";}
else{this.textContent=MORE+" ("+left+")";}
});});
var sb=document.getElementById("seasonbox");
var st=document.getElementById("seasonbtn");
if(st&&sb){st.addEventListener("click",function(e){
e.stopPropagation();sb.classList.toggle("on");});
document.addEventListener("click",function(){sb.classList.remove("on");});
sb.addEventListener("click",function(e){e.stopPropagation();});}
var SA="▼ عرض الكل",SL="▲ عرض أقل";
var MORE="عرض المزيد";
document.querySelectorAll(".more:not(.step)").forEach(function(b){
b.dataset.open="0";
b.addEventListener("click",function(){
var box=this.previousElementSibling;
var kids=box.children;
var lim=box.tagName==="OL"?5:3;
var op=this.dataset.open==="1";
var vis=[];
for(var i=0;i<kids.length;i++){
if(!kids[i].classList.contains("filt")){vis.push(kids[i]);}}
var lm=box.tagName==="OL"?5:(vis.length<kids.length?5:lim);
vis.forEach(function(m,j){
if(j>=lm){m.classList.toggle("hidden",op);}});
this.dataset.open=op?"0":"1";
this.textContent=(op?SA+" ("+(vis.length-lm)+")":SL);
});});
document.querySelectorAll(".stat.click").forEach(function(s){
s.addEventListener("click",function(){
var p=this.closest(".spanel");
var f=this.dataset.f;
var was=this.classList.contains("act");
p.querySelectorAll(".stat.click").forEach(function(x){
x.classList.remove("act");});
var box=p.querySelector(".mbox");
var btn=p.querySelector(".mbox+.more");
if(was){
box.querySelectorAll(".match").forEach(function(m,i){
m.classList.remove("filt");
m.classList.toggle("hidden",i>=3);});
if(btn){btn.style.display="";btn.dataset.open="0";
btn.textContent=SA+" ("+(box.children.length-3)+")";}
return;}
this.classList.add("act");
var k=0;
box.querySelectorAll(".match").forEach(function(m){
var ok=m.classList.contains(f);
m.classList.toggle("filt",!ok);
if(ok){k++;m.classList.toggle("hidden",k>5);}
else{m.classList.remove("hidden");}});
if(btn){if(k>5){btn.style.display="";btn.dataset.open="0";
btn.textContent=SA+" ("+(k-5)+")";}
else{btn.style.display="none";}}
});});
