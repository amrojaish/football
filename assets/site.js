/* theme */
try{
(function(){
  var b=document.getElementById('themebtn');
  if(!b)return;
  function icon(){
    var l=document.documentElement.getAttribute('data-theme')==='light';
    b.textContent=l?'\u2600':'\u263E';
  }
  icon();
  b.addEventListener('click',function(){
    var h=document.documentElement;
    var l=h.getAttribute('data-theme')==='light';
    if(l){h.removeAttribute('data-theme');}
    else{h.setAttribute('data-theme','light');}
    try{localStorage.setItem('theme',l?'dark':'light');}catch(e){}
    icon();
  });
})();
}catch(e){console.error('theme',e);}
;
/* back */
try{
(function(){
  var b=document.getElementById('backbtn');
  if(!b)return;
  // يظهر فقط إن كان في تاريخ تصفّح داخل الموقع
  if(history.length<=1){b.style.display='none';return;}
  b.addEventListener('click',function(){history.back();});
})();
}catch(e){console.error('back',e);}
;
/* matchtime */
try{
(function(){
  var els = document.querySelectorAll('[data-utc]');
  if (!els.length) return;
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
})();
}catch(e){console.error('matchtime',e);}
;
/* nav */
try{
(function(){
  var ns=document.getElementById('navsearch');
  var ovl=document.getElementById('sovl');
  if(ns&&ovl){ns.addEventListener('click',function(){
    ovl.classList.add('on');
    if(window.__navOn)window.__navOn(ns);
    var i=document.getElementById('sinput');
    if(i)setTimeout(function(){i.focus();},50);
  });}

  var so=document.getElementById('sovl2');
  var sb=document.getElementById('navset');
  var sc=document.getElementById('sclose2');

  // تلوين الأيقونة النشطة — الرابط الافتراضي يبقى ملوّناً
  // عند إغلاق النافذة
  function navOn(el){
    document.querySelectorAll('.nav a,.nav button')
      .forEach(function(x){
        x.classList.remove('on');
        x.querySelectorAll('.ic,span').forEach(function(s){
          s.classList.remove('on');});
      });
    if(el){el.classList.add('on');
      el.querySelectorAll('.ic,span').forEach(function(s){
        s.classList.add('on');});}
  }
  var defaultOn=document.querySelector('.nav a.on');
  function navReset(){navOn(defaultOn);}
  window.__navOn=navOn;
  window.__navReset=navReset;

  // ⚠️ "الدوريات" صار صفحة مستقلة (leagues.html) لا مرساة —
  //    فالتلوين يأتي من active عند التوليد، ولا حاجة لمراقبة
  //    التمرير التي كانت ضرورية حين كان القسم داخل الرئيسية.

  if(ovl){ovl.addEventListener('click',function(e){
    if(e.target===ovl)navReset();});}
  var sc1=document.getElementById('sclose');
  if(sc1)sc1.addEventListener('click',navReset);

  if(sb&&so){sb.addEventListener('click',function(){
    so.classList.add('on');navOn(sb);});}
  if(sc&&so){sc.addEventListener('click',function(){
    so.classList.remove('on');navReset();});}
  if(so){so.addEventListener('click',function(e){
    if(e.target===so){so.classList.remove('on');navReset();}});}

  // أزرار الوضع — تطابق منطق theme.py حرفياً:
  // المفتاح "theme"، والداكن = إزالة السمة لا قيمة "dark"
  function setTheme(light){
    var h=document.documentElement;
    if(light){h.setAttribute('data-theme','light');}
    else{h.removeAttribute('data-theme');}
    try{localStorage.setItem('theme',light?'light':'dark');}catch(e){}
    mark();
  }
  function mark(){
    var light=document.documentElement
              .getAttribute('data-theme')==='light';
    var d=document.getElementById('thdark');
    var l=document.getElementById('thlight');
    if(d)d.classList.toggle('act',!light);
    if(l)l.classList.toggle('act',light);
  }
  var d=document.getElementById('thdark');
  var l=document.getElementById('thlight');
  if(d)d.addEventListener('click',function(){setTheme(false);});
  if(l)l.addEventListener('click',function(){setTheme(true);});
  mark();
})();
}catch(e){console.error('nav',e);}
