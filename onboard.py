#!/usr/bin/env python3
"""
معالج الترحيب والتفضيلات
===========================
نافذة تظهر **مرة واحدة** عند أول زيارة:
    1. الاسم                    [تخطي]
    2. الدوريات — متعدد          [تخطي] [رجوع]
    3. الأندية — متعدد + بحث     [تخطي] [رجوع]

كل شيء في localStorage — **لا حساب ولا سيرفر**. الموقع ملفات
ثابتة على GitHub Pages، والتفضيلات تخصّ الجهاز وحده.

المفاتيح:
    fbUser · fbLeagues · fbClubs · fbSetup

⚠️ الأندية تُمرَّر من بايثون وقت التوليد — الصفحة لا تستطيع
   الاستعلام من قاعدة البيانات.

⚠️ عند عدم اختيار أي دوري، تُعرض **كل** الأندية لا لا شيء.

الاستخدام:
    from onboard import wizard_html, wizard_style, wizard_script
"""


def wizard_style():
    """يعتمد على متغيرات theme.py"""
    return """
  .ovl { position:fixed; inset:0; background:rgba(0,0,0,.78);
         display:none; align-items:center; justify-content:center;
         z-index:980; padding:16px; }  /* فوق نافذة الإعدادات (950)
            — كان 900 فيظهر المعالج خلفها ويبدو معطّلاً */
  .ovl.on { display:flex; }
  .wiz { background:var(--card); border:1px solid var(--line);
         border-radius:14px; padding:20px; width:100%;
         max-width:520px; max-height:88vh; display:flex;
         flex-direction:column; }
  .wtop { display:flex; justify-content:space-between;
          align-items:center; margin-bottom:16px; }
  .wlang { background:var(--bg); color:var(--muted);
           border:1px solid var(--line); padding:5px 12px;
           border-radius:8px; font-size:12px; text-decoration:none;
           font-family:inherit; }
  .wlang:hover { color:var(--text); }
  .dots { display:flex; gap:6px; }
  .dot { width:7px; height:7px; border-radius:50%;
         background:var(--line); }
  .dot.on { background:var(--accent); }
  .wbody { overflow-y:auto; flex:1; min-height:0; }
  .wiz h3 { font-size:24px; margin-bottom:18px; line-height:1.4; }
  .wiz input[type=text] { width:100%; background:var(--bg);
         border:1px solid var(--line); border-radius:9px;
         padding:14px 16px; color:var(--text); font-size:17px;
         font-family:inherit; }
  .wiz input[type=text]:focus { outline:none;
         border-color:var(--accent); }
  .wsearch { margin-bottom:14px; }
  .pick { display:flex; flex-wrap:wrap; gap:8px; }
  .chip { background:var(--bg); border:1px solid var(--line);
          border-radius:9px; padding:10px 15px; cursor:pointer;
          font-family:inherit; font-size:15px; color:var(--text);
          display:flex; align-items:center; gap:9px; }
  .chip:hover { border-color:var(--accent); }
  .chip.on { background:var(--accent); color:#fff;
             border-color:var(--accent); }
  .chip img { width:22px; height:22px; object-fit:contain; }
  .lgroup { color:var(--muted); font-size:12px;
            margin:14px 0 8px; }
  .lgroup:first-child { margin-top:0; }
  .nores { color:var(--muted); font-size:14px; padding:14px 0; }
  .wrow { display:flex; justify-content:space-between;
          align-items:center; margin-top:18px; gap:10px;
          padding-top:16px; border-top:1px solid var(--line); }
  .wleft { display:flex; gap:6px; }
  .wskip, .wback { background:none; border:none; color:var(--muted);
           font-size:14px; cursor:pointer; font-family:inherit;
           padding:9px 8px; }
  .wskip:hover, .wback:hover { color:var(--text); }
  .wback[hidden] { display:none; }
  .wnext { background:var(--accent); color:#fff; border:none;
           border-radius:9px; padding:12px 30px; font-size:16px;
           cursor:pointer; font-family:inherit; }
  .wnext:hover { filter:brightness(1.1); }
  .hello { color:var(--muted); font-size:13px; }
"""


def wizard_html(t, leagues, clubs, switch_url, switch_label):
    """
    leagues: [(code, name), ...]
    clubs:   [(team_id, name, logo, league_code, popular), ...]
             popular = 1 لأشهر 4 أندية بكل دوري
    """
    lg = "".join(
        f'<button class="chip" data-lg="{c}">{n}</button>'
        for c, n in leagues)

    # مجمّعة حسب الدوري
    names = dict(leagues)
    cl = ""
    for code, lname in leagues:
        rows = [c for c in clubs if c[3] == code]
        if not rows:
            continue
        cl += f'<div class="lgroup" data-grp="{code}">{lname}</div>'
        for tid, nm, logo, lgc, pop in rows:
            cl += (f'<button class="chip" data-cl="{tid}" '
                   f'data-lgc="{lgc}" data-pop="{pop}" '
                   f'data-nm="{nm.lower()}">'
                   f'<img src="{logo}" alt=""><span>{nm}</span></button>')

    return (
        f'<div class="ovl" id="ovl"><div class="wiz">'

        f'<div class="wtop">'
        f'<div class="dots">'
        f'<span class="dot on" data-d="1"></span>'
        f'<span class="dot" data-d="2"></span>'
        f'<span class="dot" data-d="3"></span></div>'
        f'<a class="wlang" href="{switch_url}">{switch_label}</a>'
        f'</div>'

        f'<div class="wbody">'

        # 1 — الاسم
        f'<div class="wstep" data-s="1">'
        f'<h3>{t["welcome"]}</h3>'
        f'<input type="text" id="wname" placeholder="{t["w_name_ph"]}">'
        f'</div>'

        # 2 — الدوريات
        f'<div class="wstep" data-s="2" style="display:none">'
        f'<h3>{t["w_leagues"]}</h3>'
        f'<div class="pick" id="wlg">{lg}</div>'
        f'</div>'

        # 3 — الأندية
        f'<div class="wstep" data-s="3" style="display:none">'
        f'<h3>{t["w_clubs"]}</h3>'
        f'<input type="text" id="wsearch" class="wsearch" '
        f'placeholder="{t["search_club"]}">'
        f'<div id="wcl">{cl}</div>'
        f'<div class="nores" id="nores" style="display:none">'
        f'{t["no_results"]}</div>'
        f'</div>'

        f'</div>'

        f'<div class="wrow">'
        f'<div class="wleft">'
        f'<button class="wback" id="wback" hidden>{t["back"]}</button>'
        f'<button class="wskip" id="wskip">{t["skip"]}</button>'
        f'</div>'
        f'<button class="wnext" id="wnext">{t["next"]}</button>'
        f'</div>'

        f'</div></div>'
    )


def wizard_script(t):
    def esc(x):
        return t[x].replace('"', '\\"')

    js = """<script>
(function(){
  var K={u:'fbUser',l:'fbLeagues',c:'fbClubs',s:'fbSetup'};
  function get(k,d){try{var v=localStorage.getItem(k);
    return v?JSON.parse(v):d;}catch(e){return d;}}
  function set(k,v){try{localStorage.setItem(k,JSON.stringify(v));
    }catch(e){}}

  var ovl=document.getElementById('ovl');
  if(!ovl)return;

  var step=1;
  var NXT="__NXT__", DONE="__DONE__", HI="__HI__";
  var bNext=document.getElementById('wnext');
  var bBack=document.getElementById('wback');
  var search=document.getElementById('wsearch');

  function show(n){
    step=n;
    document.querySelectorAll('.wstep').forEach(function(x){
      x.style.display=(x.dataset.s==String(n))?'':'none';});
    document.querySelectorAll('.dot').forEach(function(x){
      x.classList.toggle('on',+x.dataset.d<=n);});
    bNext.textContent=(n===3)?DONE:NXT;
    bBack.hidden=(n===1);
    if(n===3)clubView();
  }

  // عرض الأندية: البحث أولاً، وإلا أشهر 4 من الدوريات المختارة
  function clubView(){
    var q=(search.value||'').trim().toLowerCase();
    var picked=[];
    document.querySelectorAll('#wlg .chip.on').forEach(function(x){
      picked.push(x.dataset.lg);});

    var shown=0;
    document.querySelectorAll('#wcl .chip').forEach(function(x){
      var inLg=picked.length===0||picked.indexOf(x.dataset.lgc)>=0;
      var ok;
      if(q){ ok=inLg && x.dataset.nm.indexOf(q)>=0; }
      else { ok=inLg && (x.dataset.pop==='1'||x.classList.contains('on')); }
      x.style.display=ok?'':'none';
      if(ok)shown++;
    });

    // عناوين الدوريات: تظهر فقط إن كان تحتها نادٍ ظاهر
    document.querySelectorAll('#wcl .lgroup').forEach(function(g){
      var any=false, n=g.nextElementSibling;
      while(n&&n.classList.contains('chip')){
        if(n.style.display!=='none'){any=true;break;}
        n=n.nextElementSibling;
      }
      g.style.display=any?'':'none';
    });

    document.getElementById('nores').style.display=shown?'none':'';
  }

  if(search)search.addEventListener('input',clubView);

  document.querySelectorAll('.chip').forEach(function(x){
    x.addEventListener('click',function(){
      this.classList.toggle('on');});
  });

  function save(){
    var n=document.getElementById('wname').value.trim();
    if(n)set(K.u,n);
    var L=[];document.querySelectorAll('#wlg .chip.on').forEach(
      function(x){L.push(x.dataset.lg);});
    set(K.l,L);
    var C=[];document.querySelectorAll('#wcl .chip.on').forEach(
      function(x){C.push(+x.dataset.cl);});
    set(K.c,C);
    set(K.s,'1');
  }

  bNext.addEventListener('click',function(){
    if(step<3){show(step+1);}else{save();ovl.classList.remove('on');render();}
  });
  document.getElementById('wskip').addEventListener('click',function(){
    if(step<3){show(step+1);}else{save();ovl.classList.remove('on');render();}
  });
  bBack.addEventListener('click',function(){
    if(step>1)show(step-1);
  });

  // إعادة الفتح من الإعدادات — مع تحميل المحفوظ
  var open=document.getElementById('openwiz');
  if(open)open.addEventListener('click',function(e){
    e.preventDefault();
    var n=get(K.u,'');
    if(n)document.getElementById('wname').value=n;
    var L=get(K.l,[]), C=get(K.c,[]);
    document.querySelectorAll('#wlg .chip').forEach(function(x){
      x.classList.toggle('on',L.indexOf(x.dataset.lg)>=0);});
    document.querySelectorAll('#wcl .chip').forEach(function(x){
      x.classList.toggle('on',C.indexOf(+x.dataset.cl)>=0);});
    show(1);ovl.classList.add('on');
  });

  if(!get(K.s,null)){ovl.classList.add('on');}

  function render(){
    var name=get(K.u,null);
    var h=document.getElementById('hello');
    if(h)h.textContent=name?(HI+' '+name):'';

    var clubs=get(K.c,[]);
    var box=document.getElementById('myclubs');
    if(!box)return;
    if(!clubs.length){box.style.display='none';return;}

    var any=false;
    document.querySelectorAll('#myclubs [data-club]').forEach(
      function(x){
        var on=clubs.indexOf(+x.dataset.club)>=0;
        x.style.display=on?'':'none';
        if(on)any=true;});
    box.style.display=any?'':'none';
  }
  render();
})();
</script>"""

    return (js.replace("__NXT__", esc("next"))
              .replace("__DONE__", esc("done"))
              .replace("__HI__", esc("hi")))
