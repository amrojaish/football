#!/usr/bin/env python3
"""
تصويت «مين رح يفوز؟» / "Who will win?" — بطاقة أعلى «نظرة عامة» بصفحة المباراة القادمة (27 أكتوبر 2026)
=========================================================================================================
الواجهة فقط؛ الخادم = worker saffara-live (POST /vote، GET /votes، جدول votes بـD1 saffara-push، الهجرة 0010_votes.sql).

    • قبل التصويت: العنوان + «مجموع الأصوات: N» + ثلاثة أزرار بإطار: شعار المضيف / «تعادل» / شعار الضيف.
    • بعد التصويت (أو جهاز صوّت سابقاً — fbVotes بـlocalStorage، أو ردّ 409 من الخادم): الأزرار تُستبدل بالنتيجة —
      شعار المضيف + %، «تعادل %»، شعار الضيف + %؛ اختيار الجهاز مظلَّل بالأخضر. النسب تجمع 100 (أكبر باقٍ).
    • بعد الانطلاق (data-ko بساعة الزائر، أو 403 started من الخادم): بلا أزرار، النتيجة فقط؛ صفر أصوات = البطاقة مخفية.
    • أي فشل بالـworker (شبكة/خطأ/حدّ IP 429): البطاقة تُخفى بصمت. بلا JS تبقى مخفية (hidden بالبناء).

الجهاز = UUID عشوائي بـlocalStorage (fbDevice) — لا بيانات شخصية. لا كوكيز.
"""
from html import escape

from push_ui import PUSH_WORKER

STR = {
    "ar": {"title": "مين رح يفوز؟", "total": "مجموع الأصوات", "draw": "تعادل"},
    "en": {"title": "Who will win?", "total": "Total votes", "draw": "Draw"},
}

VOTE_CSS = """
  /* تصويت «مين رح يفوز؟» (27 أكتوبر 2026، vote_view.py) */
  .vote { background:var(--card); border-radius:12px; padding:12px 12px 14px; margin-top:12px; }
  .vote[hidden] { display:none; }
  .vote .vth { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:10px; }
  .vote .vtt { font-size:15px; font-weight:700; }
  .vote .vtot { color:var(--muted); font-size:12px; white-space:nowrap; }
  .vote .vrow { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }
  .vote .vrow[hidden] { display:none; }
  .vote .vb { min-height:52px; border:1px solid var(--line); border-radius:10px; background:var(--card2); color:var(--text);
              font:inherit; font-size:14px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center;
              gap:8px; padding:6px 8px; }
  .vote button.vb:hover { border-color:var(--accent); }
  .vote button.vb:disabled { opacity:.6; cursor:default; }
  .vote .vb img { width:30px; height:30px; object-fit:contain; }
  .vote .vres .vb { cursor:default; }
  .vote .vres .vb.me { border-color:var(--green); background:color-mix(in srgb, var(--green) 16%, var(--card2)); }
  .vote .vres .vb.me .vp { color:var(--green); }
  .vote .vp { font-variant-numeric:tabular-nums; unicode-bidi:isolate; }
"""


def vote_card(mid, ko_iso, home_logo, away_logo, home_name, away_name, lang):
    """البطاقة مخفية بالبناء؛ vote_script يكشفها بعد ردّ /votes. data-ko بـUTC (ISO)."""
    s = STR[lang]
    hn, an = escape(home_name, quote=True), escape(away_name, quote=True)
    img = lambda src: f'<img src="{escape(src, quote=True)}" alt="" width="30" height="30" decoding="async">' if src else ""  # noqa: E731

    def row(cls, tag):
        attr = ' type="button"' if tag == "button" else ""
        return (f'<div class="vrow {cls}"{" hidden" if cls == "vres" else ""}>'
                f'<{tag}{attr} class="vb" data-c="h" aria-label="{hn}">{img(home_logo)}<span class="vp"></span></{tag}>'
                f'<{tag}{attr} class="vb" data-c="d"><span>{s["draw"]}</span><span class="vp"></span></{tag}>'
                f'<{tag}{attr} class="vb" data-c="a" aria-label="{an}">{img(away_logo)}<span class="vp"></span></{tag}></div>')

    return (f'<div class="vote" id="vote" data-fx="{mid}" data-ko="{ko_iso}" hidden>'
            f'<div class="vth"><span class="vtt">{s["title"]}</span>'
            f'<span class="vtot">{s["total"]}: <span class="vn">0</span></span></div>'
            + row("vbtns", "button") + row("vres", "div") + '</div>')


def vote_script():
    return """<script>
(function(){
  var box=document.getElementById('vote'); if(!box||!window.fetch)return;
  var W="__W__", ID=parseInt(box.getAttribute('data-fx'),10), KO=Date.parse(box.getAttribute('data-ko'))||0;
  var btns=box.querySelector('.vbtns'), res=box.querySelector('.vres'), num=box.querySelector('.vn');
  function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(e){return null;}}
  function device(){
    var d=ls('fbDevice');
    if(!d||!/^[0-9a-f-]{36}$/i.test(d)){
      if(window.crypto&&crypto.randomUUID)d=crypto.randomUUID();
      else{var b=new Uint8Array(16);crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
        var h=[].map.call(b,function(x){return(x<16?'0':'')+x.toString(16);}).join('');
        d=h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);}
      ls('fbDevice',d);}
    return d;}
  function mine(){try{var v=JSON.parse(ls('fbVotes')||'{}');return v&&v[ID]||'';}catch(e){return '';}}
  function save(c){try{var v=JSON.parse(ls('fbVotes')||'{}')||{};v[ID]=c;var k=Object.keys(v);
    if(k.length>200)k.slice(0,k.length-200).forEach(function(x){delete v[x];});ls('fbVotes',JSON.stringify(v));}catch(e){}}
  function started(){return KO>0&&Date.now()>=KO;}
  function hide(){box.hidden=true;}
  // نسب تجمع 100 بالضبط: أكبر باقٍ
  function pct(t){var keys=['h','d','a'],n=t.total||0,base={},rem=[],sum=0;
    keys.forEach(function(k){var x=n?(t[k]||0)*100/n:0;base[k]=Math.floor(x);sum+=base[k];rem.push([x-base[k],k]);});
    if(n){rem.sort(function(p,q){return q[0]-p[0];});for(var i=0;i<100-sum;i++)base[rem[i%3][1]]++;}
    return base;}
  function show(t,c,withBtns){
    num.textContent=t.total||0;
    if(withBtns){btns.hidden=false;res.hidden=true;}
    else{var p=pct(t);btns.hidden=true;res.hidden=false;
      [].forEach.call(res.querySelectorAll('.vb'),function(el){var k=el.getAttribute('data-c');
        el.querySelector('.vp').textContent=p[k]+'%';el.classList.toggle('me',k===c);});}
    box.hidden=false;}
  function paint(t){
    var c=mine();
    if(started()){if(!t.total)return hide();return show(t,c,false);}
    show(t,c,!c);}
  function valid(t){return t&&typeof t==='object'&&Number.isFinite(t.total);}
  fetch(W+'/votes?id='+ID).then(function(r){return r.ok?r.json():Promise.reject(r.status);})
    .then(function(t){if(!valid(t))return hide();paint(t);
      // الانطلاق أثناء فتح الصفحة: الأزرار تختفي وتبقى النتيجة (أو تُخفى البطاقة بلا أصوات)
      var left=KO-Date.now();if(left>0&&left<864e5)setTimeout(function(){paint(t);},left+500);})
    .catch(hide);
  [].forEach.call(btns.querySelectorAll('button.vb'),function(b){
    b.addEventListener('click',function(){
      var c=b.getAttribute('data-c');
      if(started())return;
      [].forEach.call(btns.querySelectorAll('button'),function(x){x.disabled=true;});
      fetch(W+'/vote',{method:'POST',headers:{'Content-Type':'application/json'},
                       body:JSON.stringify({fixture:ID,choice:c,device:device()})})
        .then(function(r){return r.json().then(function(j){return [r.status,j];});})
        .then(function(x){var st=x[0],j=x[1];
          if(st===200&&valid(j)){save(j.choice||c);return show(j,j.choice||c,false);}
          if(st===409&&valid(j)){if(j.choice)save(j.choice);return show(j,j.choice||'',false);}
          if(st===403&&valid(j)){KO=Math.min(KO||Date.now(),Date.now());return paint(j);}
          hide();})
        .catch(hide);
    });
  });
})();
</script>""".replace("__W__", PUSH_WORKER)
