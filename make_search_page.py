#!/usr/bin/env python3
"""
صفحة البحث — search.html / en/search.html
=============================================
البحث صفحة كاملة لا نافذة فوق الصفحة الحالية (دفعة 5، 5 أكتوبر 2026):
زر «بحث» بالشريط السفلي رابط عادي إلى هنا، وزر الرجوع (`history.back()`
عبر BACK_SCRIPT) يعيد الزائر مكانه.

    - خانة بحث عليها `autofocus`
    - شارات فلترة: الكل / أندية / لاعبون
    - «عمليات البحث الأخيرة» قبل الكتابة: آخر 10 أندية/لاعبين فُتحوا **من
      هذه الصفحة**، بشعار أو صورة + اسم + سطر صغير (الدوري أو النادي) وزر ×
      للحذف. التخزين `localStorage` (`fbSearchRecent`) داخل try/catch؛ بلا
      تخزين تعمل الصفحة بسجلّ بالذاكرة فقط (يضيع بإعادة التحميل).

⚠️ **كل صف بالسجل مكتفٍ بنفسه** (الاسمان العربي والإنجليزي، الشعار، رمز
   الدوري، معرّف الصورة…) فيُعرض فوراً بلا انتظار `search_data.js`، ويبقى
   صحيحاً لو بدّل الزائر اللغة.

⚠️ **`search_data.js` يُحمَّل هنا وحده** — لا يُحمَّل بأي صفحة أخرى
   (حُذف من الرئيسية والدوريات والأندية والمباريات واللاعبين والثابتة
   والمتابَعة وحزم /assets).

⚠️ **noindex**: صفحة بلا محتوى ثابت (مستبعدة من sitemap.xml أيضاً).

صفر طلبات API.

التشغيل:
    python make_search_page.py
"""

import json
import os

from config import DB_FILE, LEAGUES
from i18n import T, LANGS, DIR, league_name
from theme import VARS, THEME_HEAD, THEME_SCRIPT, BACK_SCRIPT, head_meta
from navbar import (NAV_CSS, navbar, settings_overlay, nav_script,
                    pwa_script, appbar)

BASE = DB_FILE.parent

RECENT_MAX = 10

SEARCH_PAGE_CSS = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:720px; margin:0 auto; padding-bottom:84px; }
  .sp-box { position:relative; margin:6px 0 12px; }
  .sp-box input { width:100%; background:var(--card); color:var(--text);
         border:1px solid var(--line); border-radius:12px;
         padding:13px 16px; padding-inline-end:46px; font-size:16px;
         font-family:inherit; -webkit-appearance:none; appearance:none; }
  .sp-box input:focus { outline:none; border-color:var(--accent); }
  .sp-box .ico { position:absolute; top:50%; inset-inline-end:15px;
         transform:translateY(-50%); color:var(--muted); font-size:16px;
         pointer-events:none; }
  .sp-chips { display:flex; gap:8px; margin-bottom:14px; }
  .sp-chip { background:var(--card); color:var(--muted);
         border:1px solid var(--line); padding:8px 16px; min-height:40px;
         border-radius:20px; cursor:pointer; font-family:inherit;
         font-size:14px; }
  .sp-chip:hover { background:var(--card2); color:var(--text); }
  .sp-chip.on { background:var(--accent); color:#fff;
         border-color:var(--accent); }
  .sp-h { color:var(--muted); font-size:12.5px; font-weight:600;
         padding:6px 4px; }
  .sp-list { display:flex; flex-direction:column; gap:2px; }
  .sp-row { display:flex; align-items:center; border-radius:12px; }
  .sp-row:hover, .sp-row.sel { background:var(--card2); }
  .sp-item { flex:1; min-width:0; display:flex; align-items:center; gap:12px;
         padding:9px 8px; text-decoration:none; color:var(--text); }
  .sp-av { width:40px; height:40px; flex:0 0 auto; border-radius:50%;
         background:#fff; border:1px solid var(--line); overflow:hidden;
         display:flex; align-items:center; justify-content:center;
         color:#333; font-weight:700; font-size:16px; }
  .sp-av img { width:100%; height:100%; object-fit:contain; }
  .sp-av.ph img { object-fit:cover; }
  .sp-av.ph { position:relative; }
  .sp-txt { min-width:0; display:flex; flex-direction:column; }
  .sp-nm { font-size:15px; font-weight:600; white-space:nowrap;
         overflow:hidden; text-overflow:ellipsis; }
  .sp-sub { font-size:12.5px; color:var(--muted); white-space:nowrap;
         overflow:hidden; text-overflow:ellipsis; }
  .sp-x { flex:0 0 auto; width:44px; height:44px; background:none;
         border:none; color:var(--muted); font-size:22px; line-height:1;
         cursor:pointer; font-family:inherit; border-radius:50%; }
  .sp-x:hover { color:#e5484d; }
  .sp-empty { color:var(--muted); font-size:14px; text-align:center;
         padding:34px 10px; }
"""

SEARCH_PAGE_JS = r"""
<script src="__UP__search_data.js" defer></script>
<script>
(function(){
  var UP="__UP__", UPL="__UPL__", LANG="__LANG__";
  var LG=__LG__;
  var L_ALL="__ALL__", L_CLUBS="__CLUBS__", L_PLAYERS="__PLAYERS__",
      L_NONE="__NONE__", L_RECENT="__RECENT__", L_NORECENT="__NORECENT__",
      L_REMOVE="__REMOVE__";
  var MAX=__MAX__, RMAX=__RMAX__, KEY='fbSearchRecent';
  var PHOTO='https://media.api-sports.io/football/players/';

  var inp=document.getElementById('q');
  var body=document.getElementById('sbody');
  var chips=document.querySelectorAll('.sp-chip');
  var filter='all', idx=null, clubsById=null, mem=[], sel=-1;

  function norm(s){
    if(!s)return '';
    s=(''+s).toLowerCase();
    s=s.replace(/[أإآٱ]/g,'ا')
       .replace(/ة/g,'ه')
       .replace(/ى/g,'ي')
       .replace(/[ً-ْـ]/g,'');
    s=s.replace(/^ال/,'');
    s=s.replace(/[-'.’]/g,' ').replace(/\s+/g,' ').trim();
    return s;
  }
  function esc(s){
    return (''+s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                 .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function pick(ar,en){ return LANG==='ar' ? (ar||en||'') : (en||ar||''); }
  function logoSrc(l){
    return (l && l.indexOf('http')===0) ? l : (UP + (l||''));
  }

  /* ---- السجل (localStorage داخل try/catch، وإلا ذاكرة الصفحة) ---- */
  function loadRecent(){
    try{
      var v=JSON.parse(localStorage.getItem(KEY)||'[]');
      return Array.isArray(v) ? v : [];
    }catch(e){ return mem.slice(); }
  }
  function saveRecent(list){
    mem=list.slice();
    try{ localStorage.setItem(KEY, JSON.stringify(list)); }catch(e){}
  }
  function rkey(r){ return r.k+':'+(r.k==='c' ? r.id : (r.s||('c'+r.c+r.a+r.e))); }
  function addRecent(r){
    var list=loadRecent().filter(function(x){ return rkey(x)!==rkey(r); });
    list.unshift(r);
    saveRecent(list.slice(0,RMAX));
  }
  function delRecent(key){
    saveRecent(loadRecent().filter(function(x){ return rkey(x)!==key; }));
  }

  /* ---- عناصر العرض (نفس الشكل للنتيجة وللسجل) ---- */
  function avatar(r){
    if(r.k==='c'){
      return '<span class="sp-av">'+(r.l
        ? '<img loading="lazy" alt="" src="'+esc(logoSrc(r.l))+'" '
          +'onerror="this.style.visibility=\'hidden\'">' : '')+'</span>';
    }
    var nm=pick(r.a,r.e), ini=esc((nm.trim().charAt(0)||'?').toUpperCase());
    if(!r.i) return '<span class="sp-av">'+ini+'</span>';
    return '<span class="sp-av ph"><span>'+ini+'</span>'
      +'<img loading="lazy" alt="" src="'+PHOTO+r.i+'.png" '
      +'style="position:absolute;inset:0;background:#fff" '
      +'onerror="this.remove()"></span>';
  }
  function subline(r){
    if(r.k==='c') return LG[r.g]||'';
    return pick(r.ca,r.ce);
  }
  function href(r){
    if(r.k==='c') return UPL+'clubs/'+r.id+'.html';
    return r.s ? (UPL+'players/'+r.s+'.html') : (UPL+'clubs/'+r.c+'.html');
  }
  function row(r, withX){
    var key=rkey(r);
    return '<div class="sp-row" data-key="'+esc(key)+'">'
      +'<a class="sp-item" href="'+esc(href(r))+'" data-rec="'+esc(JSON.stringify(r))+'">'
      +avatar(r)+'<span class="sp-txt"><span class="sp-nm">'+esc(pick(r.a,r.e))
      +'</span><span class="sp-sub">'+esc(subline(r))+'</span></span></a>'
      +(withX ? '<button class="sp-x" type="button" aria-label="'+esc(L_REMOVE)
        +'" title="'+esc(L_REMOVE)+'">×</button>' : '')+'</div>';
  }
  function fromClub(c){ return {k:'c', id:c[0], a:c[1], e:c[2], g:c[3], l:c[4]||''}; }
  function fromPlayer(p){
    var c=clubsById && clubsById[p[2]];
    return {k:'p', s:p[3]||'', a:p[0], e:p[1], c:p[2], i:p[4]||0,
            ca:c?c[1]:'', ce:c?c[2]:''};
  }

  /* ---- العرض ---- */
  function render(){
    sel=-1;
    var q=norm(inp.value), h='';
    if(!q){
      var rec=loadRecent().filter(function(r){
        return filter==='all' || (filter==='clubs' ? r.k==='c' : r.k==='p');
      });
      if(!rec.length){
        body.innerHTML='<div class="sp-empty">'+esc(L_NORECENT)+'</div>';
        return;
      }
      h='<div class="sp-h">'+esc(L_RECENT)+'</div><div class="sp-list">';
      rec.forEach(function(r){ h+=row(r,true); });
      body.innerHTML=h+'</div>';
      return;
    }
    if(!idx){ body.innerHTML='<div class="sp-empty">…</div>'; return; }
    var cs=[], ps=[], i, c, p;
    if(filter!=='players'){
      for(i=0;i<idx.c.length;i++){
        c=idx.c[i];
        if(norm(c[1]).indexOf(q)>=0 || norm(c[2]).indexOf(q)>=0) cs.push(c);
      }
    }
    if(filter!=='clubs'){
      for(i=0;i<idx.p.length && ps.length<MAX;i++){
        p=idx.p[i];
        if(norm(p[0]).indexOf(q)>=0 || norm(p[1]).indexOf(q)>=0) ps.push(p);
      }
    }
    if(!cs.length && !ps.length){
      body.innerHTML='<div class="sp-empty">'+esc(L_NONE)+'</div>';
      return;
    }
    if(cs.length){
      if(filter==='all') h+='<div class="sp-h">'+esc(L_CLUBS)+'</div>';
      h+='<div class="sp-list">';
      cs.forEach(function(x){ h+=row(fromClub(x),false); });
      h+='</div>';
    }
    if(ps.length){
      if(filter==='all') h+='<div class="sp-h">'+esc(L_PLAYERS)+'</div>';
      h+='<div class="sp-list">';
      ps.forEach(function(x){ h+=row(fromPlayer(x),false); });
      h+='</div>';
    }
    body.innerHTML=h;
  }

  /* ---- تفاعل ---- */
  chips.forEach(function(b){
    b.addEventListener('click',function(){
      filter=this.dataset.f;
      chips.forEach(function(x){ x.classList.toggle('on', x===b); });
      render();
    });
  });
  inp.addEventListener('input', render);

  body.addEventListener('click',function(e){
    var x=e.target.closest('.sp-x');
    if(x){
      e.preventDefault();
      delRecent(x.closest('.sp-row').dataset.key);
      render();
      return;
    }
    var a=e.target.closest('.sp-item');
    if(a){
      try{ addRecent(JSON.parse(a.dataset.rec)); }catch(err){}
    }
  });

  function items(){ return body.querySelectorAll('.sp-row'); }
  function move(d){
    var it=items(); if(!it.length)return;
    if(sel>=0&&it[sel]) it[sel].classList.remove('sel');
    sel+=d; if(sel<0)sel=it.length-1; if(sel>=it.length)sel=0;
    it[sel].classList.add('sel'); it[sel].scrollIntoView({block:'nearest'});
  }
  inp.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){ e.preventDefault(); move(1); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); }
    else if(e.key==='Enter'){
      var it=items(), a=(sel>=0&&it[sel]) ? it[sel].querySelector('.sp-item')
                       : (it[0] && it[0].querySelector('.sp-item'));
      if(a){ e.preventDefault(); a.click(); }
    }
  });

  function ready(){
    idx=window.FBSEARCH||null;
    if(idx){
      clubsById={};
      for(var k=0;k<idx.c.length;k++) clubsById[idx.c[k][0]]=idx.c[k];
    }
    render();
  }
  window.addEventListener('load', ready);
  // رجوع من نتيجة (bfcache): نُحدّث السجل
  window.addEventListener('pageshow',function(e){ if(e.persisted) render(); });
  render();
  inp.focus();
})();
</script>"""


def page_js(t, lang, depth):
    up = "../" * depth
    upl = up + ("en/" if lang == "en" else "")
    lg = {c: league_name(c, lang) for c in LEAGUES}

    def esc(k):
        return t[k].replace('"', '\\"')

    return (SEARCH_PAGE_JS
            .replace("__UPL__", upl).replace("__UP__", up)
            .replace("__LANG__", lang)
            .replace("__LG__", json.dumps(lg, ensure_ascii=False))
            .replace("__ALL__", esc("s_all"))
            .replace("__CLUBS__", esc("s_clubs"))
            .replace("__PLAYERS__", esc("s_players"))
            .replace("__NONE__", esc("no_results"))
            .replace("__RECENT__", esc("s_recent"))
            .replace("__NORECENT__", esc("s_recent_none"))
            .replace("__REMOVE__", esc("s_remove"))
            .replace("__MAX__", "40")
            .replace("__RMAX__", str(RECENT_MAX)))


def search_page(lang):
    t = T[lang]
    depth = 0 if lang == "ar" else 1
    rel = "search.html" if lang == "ar" else "en/search.html"
    switch = "en/search.html" if lang == "ar" else "../search.html"
    title = f'{t["search"]} — {t["site_title"]}'

    chips = "".join(
        f'<button class="sp-chip{" on" if f == "all" else ""}" '
        f'data-f="{f}" type="button">{label}</button>'
        for f, label in (("all", t["s_all"]), ("clubs", t["s_clubs"]),
                         ("players", t["s_players"])))

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        '<meta name="robots" content="noindex">\n'
        + head_meta(title, t["site_sub"], "" if lang == "ar" else "../",
                    lang, rel)
        + THEME_HEAD
        + "<style>" + VARS + SEARCH_PAGE_CSS + NAV_CSS + "</style>\n"
        '</head>\n<body>\n<div class="wrap">\n'
        + appbar(t, lang, switch, back=True)
        + '<div class="sp-box">'
          f'<input type="text" id="q" autofocus autocomplete="off" '
          f'autocapitalize="off" spellcheck="false" enterkeyhint="search" '
          f'placeholder="{t["search_ph"]}" aria-label="{t["search"]}">'
          '<span class="ico">⌕</span></div>\n'
        f'<div class="sp-chips" role="group">{chips}</div>\n'
        '<div id="sbody" aria-live="polite"></div>\n'
        '</div>\n'
        + navbar(t, depth, "search", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT + BACK_SCRIPT
        + nav_script(t) + pwa_script(lang)
        + page_js(t, lang, depth) +
        '</body>\n</html>'
    )


def main():
    os.makedirs(BASE / "en", exist_ok=True)
    made = []
    for lang in LANGS:
        path = BASE / ("search.html" if lang == "ar" else "en/search.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(search_page(lang))
        made.append(str(path.relative_to(BASE)).replace(os.sep, "/"))
    print("\n  تم توليد:")
    for m in made:
        print(f"      {m}")


if __name__ == "__main__":
    main()
