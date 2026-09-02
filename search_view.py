#!/usr/bin/env python3
"""
واجهة البحث — أندية ولاعبون
==============================
وحدة مستقلة على نمط `tiebreak.py` و`onboard.py` و`lineup_view.py`.
لا تشغّلها لحالها — سكربتات التوليد بتستوردها.

بتقدّم ثلاثة أشياء:
    SEARCH_CSS              → يُضاف لبلوك STYLE
    search_box(t, big)      → الصندوق أو الزر في الصفحة
    search_script(t, depth) → السكربت + وسم تحميل الفهرس

⚠️ **الفهرس ملف خارجي** `search_data.js` (~103 كيلوبايت) يُحمَّل
   مرة ويُخزَّن في كاش المتصفح. حقنه في كل صفحة كان سينتج
   ~500 ميغابايت. راجع `make_search.py`.

⚠️ **البحث يطابق العربي والإنجليزي معاً.** 3% فقط من اللاعبين
   لهم اسم عربي، فالمطابقة الإنجليزية ليست ترفاً بل شرط عمل
   الميزة. كل اسم يُترجَم يصير قابلاً للبحث بالعربية.

⚠️ **نتيجة اللاعب توديه لصفحة ناديه** — صفحة اللاعب غير موجودة
   بعد (البند 9). اسم النادي معروض بجانبه فلا يُفاجأ الزائر.
   عند بناء صفحة اللاعب: غيّر `_HREF_PLAYER` أسفله فقط.

⚠️ **الروابط تحترم اللغة.** الاعتماد على العمق وحده كان يرسل
   الزائر الإنجليزي إلى الصفحة العربية: من `en/clubs/x.html`
   يصير `../../clubs/y.html` وهو العربي لا `../../en/clubs/y.html`.
   فصار هناك بادئتان (مصيدة 8):
       UP  → الأصول المشتركة بالجذر (search_data.js · logos/)
       UPL → الصفحات المترجَمة (clubs/ · players/)

⚠️ `depth` = عمق الصفحة من جذر الموقع:
       الرئيسية · about        → 0
       clubs/ · matches/ · en/ → 1
       en/clubs/ · en/matches/ → 2

الاستخدام:
    from search_view import SEARCH_CSS, search_box, search_script
"""

# عند بناء صفحة اللاعب، غيّر هذا السطر فقط
_HREF_PLAYER = "clubs/{club_id}.html"

MAX_RESULTS = 40


SEARCH_CSS = """
  .sbtn { background:var(--card); color:var(--muted);
          border:1px solid var(--line); padding:6px 12px;
          border-radius:8px; font-size:14px; cursor:pointer;
          font-family:inherit; line-height:1; }
  .sbtn:hover { background:var(--card2); color:var(--text); }

  .sbig { width:100%; max-width:520px; margin:0 auto 22px;
          display:block; position:relative; }
  .sbig input { width:100%; background:var(--card);
          border:1px solid var(--line); border-radius:11px;
          padding:13px 44px 13px 16px; color:var(--text);
          font-size:16px; font-family:inherit; }
  .sbig input:focus { outline:none; border-color:var(--accent); }
  .sbig .ico { position:absolute; top:50%; inset-inline-end:15px;
          transform:translateY(-50%); color:var(--muted);
          font-size:15px; pointer-events:none; }

  .sovl { position:fixed; inset:0; background:rgba(0,0,0,.72);
          display:none; align-items:flex-start;
          justify-content:center; z-index:950; padding:60px 16px 16px; }
  .sovl.on { display:flex; }
  .sbox { background:var(--card); border:1px solid var(--line);
          border-radius:14px; width:100%; max-width:540px;
          max-height:80vh; display:flex; flex-direction:column;
          overflow:hidden; }
  .sbox .top { display:flex; gap:8px; padding:14px;
          border-bottom:1px solid var(--line); }
  .sbox input { flex:1; background:var(--bg);
          border:1px solid var(--line); border-radius:9px;
          padding:11px 14px; color:var(--text); font-size:16px;
          font-family:inherit; }
  .sbox input:focus { outline:none; border-color:var(--accent); }
  .sclose { background:none; border:none; color:var(--muted);
          font-size:22px; cursor:pointer; padding:0 6px;
          font-family:inherit; line-height:1; }
  .sclose:hover { color:var(--text); }

  .sres { overflow-y:auto; padding:8px; }
  .sgrp { color:var(--muted); font-size:11px; padding:8px 8px 4px;
          font-weight:600; }
  .sitem { display:flex; align-items:center; gap:10px;
           padding:9px 10px; border-radius:9px; cursor:pointer;
           text-decoration:none; color:var(--text); font-size:14px; }
  .sitem:hover, .sitem.sel { background:var(--card2); }
  .sitem img { width:24px; height:24px; object-fit:contain;
               flex-shrink:0; }
  .sitem .meta { color:var(--muted); font-size:12px;
                 margin-inline-start:auto; white-space:nowrap; }
  .sempty { color:var(--muted); font-size:14px; text-align:center;
            padding:26px 10px; }
  .shint { color:var(--muted); font-size:12px; text-align:center;
           padding:20px 10px; line-height:1.8; }
"""


def search_box(t, big=False):
    """
    big=True  → صندوق كبير بالصفحة الرئيسية
    big=False → زر صغير بالشريط العلوي
    """
    if big:
        return (
            f'<div class="sbig" id="sbig">'
            f'<input type="text" id="sbiginput" '
            f'placeholder="{t["search_ph"]}" readonly>'
            f'<span class="ico">⌕</span></div>'
        )
    return (f'<button class="sbtn" id="sbtn" '
            f'title="{t["search"]}">⌕</button>')


def search_script(t, depth=0, lang="ar"):
    """السكربت + وسم تحميل الفهرس. depth = عمق الصفحة"""
    up = "../" * depth
    # ⚠️ بادئة الصفحات المترجَمة — الأصول تبقى على `up`
    upl = up + ("en/" if lang == "en" else "")

    def esc(k):
        return t[k].replace('"', '\\"')

    js = """
<script src="__UP__search_data.js" defer></script>
<script>
(function(){
  var UP="__UP__", UPL="__UPL__";
  var L_CLUBS="__CLUBS__", L_PLAYERS="__PLAYERS__",
      L_NONE="__NONE__", L_HINT="__HINT__", L_PH="__PH__";
  var MAX=__MAX__;
  var LANG="__LANG__";

  var ovl=document.getElementById('sovl');
  if(!ovl)return;
  var inp=document.getElementById('sinput');
  var res=document.getElementById('sres');
  var idx=null, sel=-1;

  function norm(s){
    if(!s)return '';
    s=(''+s).toLowerCase();
    // توحيد الألف والهمزات والتاء المربوطة والياء
    s=s.replace(/[\\u0623\\u0625\\u0622\\u0671]/g,'\\u0627')
       .replace(/\\u0629/g,'\\u0647')
       .replace(/\\u0649/g,'\\u064a')
       .replace(/[\\u064b-\\u0652\\u0640]/g,'');
    // تجاهل ال التعريف بالبداية
    s=s.replace(/^\\u0627\\u0644/,'');
    // تجاهل الشرطات والنقاط بالإنجليزي
    s=s.replace(/[-'.\\u2019]/g,' ').replace(/\\s+/g,' ').trim();
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
      +'onerror="this.style.visibility=\\'hidden\\'">'
      +'<span>'+esc(name)+'</span></a>';
  }

  function playerHtml(p){
    var name=(LANG==='ar'? (p[0]||p[1]) : (p[1]||p[0]));
    var club=(LANG==='ar'? (p[3]||p[4]) : (p[4]||p[3]));
    var href = p[5] ? (UPL+'players/'+p[5]+'.html')
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
    if(ovl.classList.contains('on'))render(inp.value);
  });
})();
</script>"""

    return (js.replace("__UPL__", upl)
              .replace("__UP__", up)
              .replace("__CLUBS__", esc("s_clubs"))
              .replace("__PLAYERS__", esc("s_players"))
              .replace("__NONE__", esc("no_results"))
              .replace("__HINT__", esc("s_hint"))
              .replace("__PH__", esc("search_ph"))
              .replace("__MAX__", str(MAX_RESULTS))
              .replace("__LANG__", lang))


def search_overlay(t):
    """الطبقة — تُوضع قبل </body> في كل صفحة فيها بحث"""
    return (
        f'<div class="sovl" id="sovl"><div class="sbox">'
        f'<div class="top">'
        f'<input type="text" id="sinput" '
        f'placeholder="{t["search_ph"]}">'
        f'<button class="sclose" id="sclose">×</button></div>'
        f'<div class="sres" id="sres"></div>'
        f'</div></div>'
    )
