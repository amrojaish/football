/* prefs */
try{
window.FBPrefs = (function(){
  // ⚠️ fbPlayers تخزّن slugs (نصوص، مثل 'cristiano-ronaldo') لا
  //    player_id — لا معرّف رقمي مستقر يصل للمتصفح إطلاقاً
  //    (player_id الحقيقي داخلي بـmake_players.py::gather() فقط،
  //    الـslug هو الهوية الوحيدة المُصدَّرة لأي HTML/JS. جزء أ،
  //    22 سبتمبر).
  var K = {l:'fbLeagues', c:'fbClubs', s:'fbSetup', p:'fbPlayers'};

  function get(k, d) {
    try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; }
    catch(e) { return d; }
  }
  function set(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch(e) {}
  }

  function getLeagues() { return get(K.l, []); }
  function setLeagues(arr) { set(K.l, arr); }

  function getClubs() { return get(K.c, []); }
  function setClubs(arr) { set(K.c, arr); }

  function getPlayers() { return get(K.p, []); }
  function setPlayers(arr) { set(K.p, arr); }

  function isSetupDone() { return !!get(K.s, null); }
  function markSetupDone() { set(K.s, '1'); }

  // يزيل من fbClubs أي نادٍ دوريه غير موجود بـfbLeagues.
  // ⚠️ fbLeagues فاضية = كل الدوريات ضمنياً (سلوك onboard.py
  //    الحالي) — لا يُحذف شيء وقتها.
  // ⚠️ الخريطة (window.FBClubLeagueMap) من club_map_script()
  //    منفصلة وقد تكون غائبة عن هذه الصفحة — غيابها = لا تنظيف
  //    (فشل آمن)، لا حذف كل شيء.
  function cleanClubs() {
    var map = window.FBClubLeagueMap;
    if (!map) return getClubs();
    var leagues = getLeagues();
    if (!leagues.length) return getClubs();
    var kept = getClubs().filter(function(tid){
      var lg = map[String(tid)];
      return !lg || leagues.indexOf(lg) >= 0;
    });
    setClubs(kept);
    return kept;
  }

  return {
    getLeagues: getLeagues, setLeagues: setLeagues,
    getClubs: getClubs, setClubs: setClubs,
    getPlayers: getPlayers, setPlayers: setPlayers,
    isSetupDone: isSetupDone, markSetupDone: markSetupDone,
    cleanClubs: cleanClubs
  };
})();
}catch(e){console.error('prefs',e);}
;
/* search */
try{
(function(){
  var UP="/", UPL="/en/";
  var L_CLUBS="Clubs", L_PLAYERS="Players",
      L_NONE="No results", L_HINT="Type a club or player name", L_PH="Search for a club or player";
  var MAX=40;
  var LANG="en";

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
/* goals */
var GA="▼ Show all",GL="▲ Show less";
document.querySelectorAll(".shead").forEach(function(h){
h.addEventListener("click",function(){
var s=this.parentElement;
var b=s.querySelector(".sbody");
var op=s.classList.toggle("open");
b.classList.toggle("hidden",!op);});});
document.querySelectorAll(".gmore").forEach(function(b){
b.dataset.open="0";
b.addEventListener("click",function(){
var box=this.previousElementSibling;
var kids=box.querySelectorAll(".g");
var op=this.dataset.open==="1";
var n=0;
kids.forEach(function(g,i){
if(i>=10){g.classList.toggle("hidden",op);n++;}});
this.dataset.open=op?"0":"1";
this.textContent=op?GA+" ("+n+")":GL;});});
;
/* follow */
var FL="Follow player",UFL="Unfollow player";
(function(){
var b=document.getElementById("followbtn");
var FB=window.FBPrefs;
if(!b||!FB)return;
var slug=b.dataset.slug;
function mark(on){
b.classList.toggle("on",on);
b.title=on?UFL:FL;
b.setAttribute("aria-pressed",on?"true":"false");}
mark(FB.getPlayers().indexOf(slug)>=0);
b.addEventListener("click",function(){
var p=FB.getPlayers();
var i=p.indexOf(slug);
if(i>=0){p.splice(i,1);}else{p.push(slug);}
FB.setPlayers(p);
mark(i<0);});
})();
