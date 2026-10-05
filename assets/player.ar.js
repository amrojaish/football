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
/* goals */
var GA="▼ عرض الكل",GL="▲ عرض أقل";
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
var FL="متابعة اللاعب",UFL="إلغاء متابعة اللاعب";
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
