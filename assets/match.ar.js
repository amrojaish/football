/* live */
try{
(function(){
  var SRC="https://saffara-live.abujaishamr.workers.dev/", HT="بين الشوطين";
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
}catch(e){console.error('live',e);}
;
/* search */
try{
(function(){
  var UP="/", UPL="/";
  var L_CLUBS="الأندية", L_PLAYERS="اللاعبون",
      L_NONE="ما في نتائج", L_HINT="اكتب اسم نادٍ أو لاعب", L_PH="ابحث عن نادٍ أو لاعب";
  var MAX=40;
  var LANG="ar";

  var ovl=document.getElementById('sovl');
  if(!ovl)return;
  var inp=document.getElementById('sinput');
  var res=document.getElementById('sres');
  var idx=null, sel=-1, clubsById=null;

  function norm(s){
    if(!s)return '';
    s=(''+s).toLowerCase();
    // توحيد الألف والهمزات والتاء المربوطة والياء
    s=s.replace(/[\u0623\u0625\u0622\u0671]/g,'\u0627')
       .replace(/\u0629/g,'\u0647')
       .replace(/\u0649/g,'\u064a')
       .replace(/[\u064b-\u0652\u0640]/g,'');
    // تجاهل ال التعريف بالبداية
    s=s.replace(/^\u0627\u0644/,'');
    // تجاهل الشرطات والنقاط بالإنجليزي
    s=s.replace(/[-'.\u2019]/g,' ').replace(/\s+/g,' ').trim();
    return s;
  }

  function open(){
    ovl.classList.add('on');
    setTimeout(function(){inp.focus();},50);
    render('');
  }
  function close(){ ovl.classList.remove('on'); inp.value=''; sel=-1; }

  function esc(s){
    return (''+s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                 .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function clubHtml(c){
    var id=c[0], name=(LANG==='ar'? (c[1]||c[2]) : (c[2]||c[1]));
    return '<a class="sitem" href="'+UPL+'clubs/'+id+'.html">'
            +'<img src="'+(c[4]&&c[4].indexOf('http')===0?c[4]:UP+(c[4]||'logos/'+id+'.png'))+'" alt="" '
      +'onerror="this.style.visibility=\'hidden\'">'
      +'<span>'+esc(name)+'</span></a>';
  }

  function playerHtml(p){
    var name=(LANG==='ar'? (p[0]||p[1]) : (p[1]||p[0]));
    var c=clubsById&&clubsById[p[2]];
    var club=c ? (LANG==='ar'? (c[1]||c[2]) : (c[2]||c[1])) : '';
    var href = p[3] ? (UPL+'players/'+p[3]+'.html')
                     : (UPL+'clubs/'+p[2]+'.html');
    return '<a class="sitem" href="'+href+'">'
      +'<span>'+esc(name)+'</span>'
      +'<span class="meta">'+esc(club)+'</span></a>';
  }
  function render(q){
    if(!idx){ res.innerHTML='<div class="shint">…</div>'; return; }
    var nq=norm(q);
    if(!nq){ res.innerHTML='<div class="shint">'+L_HINT+'</div>';
             return; }

    var cs=[], ps=[];
    for(var i=0;i<idx.c.length;i++){
      var c=idx.c[i];
      if(norm(c[1]).indexOf(nq)>=0 || norm(c[2]).indexOf(nq)>=0)
        cs.push(c);
    }
    for(var j=0;j<idx.p.length && ps.length<MAX;j++){
      var p=idx.p[j];
      if(norm(p[0]).indexOf(nq)>=0 || norm(p[1]).indexOf(nq)>=0)
        ps.push(p);
    }

    if(!cs.length && !ps.length){
      res.innerHTML='<div class="sempty">'+L_NONE+'</div>';
      return;
    }

    var h='';
    if(cs.length){
      h+='<div class="sgrp">'+L_CLUBS+'</div>';
      for(var a=0;a<cs.length;a++) h+=clubHtml(cs[a]);
    }
    if(ps.length){
      h+='<div class="sgrp">'+L_PLAYERS+'</div>';
      for(var b=0;b<ps.length;b++) h+=playerHtml(ps[b]);
    }
    res.innerHTML=h; sel=-1;
  }

  function items(){ return res.querySelectorAll('.sitem'); }
  function move(d){
    var it=items(); if(!it.length)return;
    if(sel>=0 && it[sel]) it[sel].classList.remove('sel');
    sel+=d;
    if(sel<0)sel=it.length-1;
    if(sel>=it.length)sel=0;
    it[sel].classList.add('sel');
    it[sel].scrollIntoView({block:'nearest'});
  }

  inp.addEventListener('input',function(){render(this.value);});
  inp.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){e.preventDefault();move(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();move(-1);}
    else if(e.key==='Enter'){
      var it=items();
      if(sel>=0&&it[sel]){e.preventDefault();it[sel].click();}
    }
    else if(e.key==='Escape'){close();}
  });

  ovl.addEventListener('click',function(e){
    if(e.target===ovl)close();
  });
  var cb=document.getElementById('sclose');
  if(cb)cb.addEventListener('click',close);

  var b=document.getElementById('sbtn');
  if(b)b.addEventListener('click',open);
  var bg=document.getElementById('sbig');
  if(bg)bg.addEventListener('click',open);

  document.addEventListener('keydown',function(e){
    if(e.key==='/' && !/^(INPUT|TEXTAREA)$/.test(
        document.activeElement.tagName)){
      e.preventDefault(); open();
    }
  });

  window.addEventListener('load',function(){
    idx=window.FBSEARCH||null;
    // ⚠️ اسم النادي عاد ما يترافق مع كل لاعب (3 سبتمبر) —
    //    خريطة بحث وحدة بمعرّف النادي بدل تكراره بكل صفّ لاعب
    if(idx) {
      clubsById={};
      for(var k=0;k<idx.c.length;k++) clubsById[idx.c[k][0]]=idx.c[k];
    }
    if(ovl.classList.contains('on'))render(inp.value);
  });
})();
}catch(e){console.error('search',e);}
;
/* pwa */
(function(){
if("serviceWorker" in navigator){
window.addEventListener("load",function(){
navigator.serviceWorker.register("/sw.js")
.catch(function(){});});}
var bar=document.getElementById("offbar");
function upd(){
var off=!navigator.onLine;
if(bar)bar.classList.toggle("on",off);
document.body.classList.toggle("offline",off);}
window.addEventListener("online",upd);
window.addEventListener("offline",upd);
upd();
})();
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

