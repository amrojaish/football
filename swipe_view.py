#!/usr/bin/env python3
"""
السحب بين التبويبات وبين صفحات الشريط السفلي بمتابعة الإصبع (27 أكتوبر 2026، طلب عمرو #3 دفعة 2)
=====================================================================================================
سكربت واحد مكتفٍ بنفسه (`swipe_script()`) يُضمَّن بكل صفحة فيها مجموعة تبويبات أو هي من صفحات الشريط السفلي:

1) **التبويبات داخل الصفحة** (المباراة/اللاعب `.mtabs`، الدوري `.cattabs`، المتابَعة `.ftabs`، الإشعارات `.ntabs`) — تُكتشف تلقائياً
   من جدول SETS: اللوحة الحالية واللوحة المجاورة تتحرّكان مع الإصبع 1:1 (transform)، والمجاورة تُعرض مؤقتاً بجانبها (absolute بنفس
   العرض)؛ الإفلات بعد 30% من العرض أو بنقرة سريعة (≥ 0.3 px/ms بآخر 150ms) = التبويب المجاور، وإلا ترجع. الإنهاء = نقرة التبويب الأصلية
   نفسها (`btn.click()`) فيبقى كل منطق الصفحة كما هو: تحميل اللوحات الكسولة (التشكيلة الحية، الترتيب المباشر…)، history.state، التمرير.
   ارتفاع الحاوية = اللوحة الظاهرة (المجاورة absolute أثناء السحب ثم تدخل التدفق) — لا فراغ كبير. شريط التبويبات المسطَّر (.mtabs/.cattabs)
   يحصل خطاً يتبع موضع السحب؛ الأشرطة الممتلئة (.ftabs/.ntabs) تتبدّل عند الإفلات فقط.
2) **صفحات الشريط السفلي** (المباريات · الدوريات · المتابَعة · البحث، بترتيب الشريط ومعكوساً بالعربي) — فقط بصفحة تحمل
   `<meta name="sw-page">` (`head_html()`): الصفحة تتحرك مع الإصبع ومعاينة خفيفة للصفحة المجاورة تنزلق (عنوانها من نص زر الشريط + بطاقات
   هيكلية، بلا iframe)، والشريط السفلي يبدّل التلوين بعد المنتصف. الإفلات بعد العتبة = تنقّل عادي (location) مع View Transition عبر
   المستندات (`@view-transition {navigation:auto}` + انزلاق باتجاه السحب، والشريط السفلي ثابت باسم انتقال خاص)؛ متصفح بلا دعم = المعاينة
   تُكمل انزلاقها ثم تنقّل عادي (بلا وميض أبيض). الصفحتان المجاورتان prefetch عند الخمول. أي تنقّل آخر (رابط/رجوع) بلا انتقال.

قواعد مشتركة: قفل المحور بعد 10px — العمودي يبقى للمتصفح (touch-action:pan-y)؛ لا شيء يبدأ من حقول الإدخال/الأوراق/الشريطين/عنصر
قابل للتمرير أفقياً. داخل مجموعة تبويبات: السحب للتبويب المجاور، وعند أول/آخر تبويب يمرّ لسحب الصفحات (إن كانت صفحة شريط). الرئيسية:
السحب على لوحات الأيام يبقى للأيام كما كان (DAY_SCRIPT)، وسحب الصفحات من الشريط العلوي فقط. prefers-reduced-motion = بلا حركة.
"""

META = '<meta name="sw-page" content="1">\n'

# بصفحات الشريط السفلي فقط (لا بغيرها: الانتقال يتطلب اشتراك المستندين)
HEAD_VT = """<style>
  @view-transition { navigation: auto; }
  .nav { view-transition-name: fbnav; }
  @keyframes fbSwOutL { to { transform: translateX(-100%); } }
  @keyframes fbSwInL { from { transform: translateX(100%); } }
  @keyframes fbSwOutR { to { transform: translateX(100%); } }
  @keyframes fbSwInR { from { transform: translateX(-100%); } }
  html.vt-l::view-transition-old(root) { animation: fbSwOutL .24s ease-out both; }
  html.vt-l::view-transition-new(root) { animation: fbSwInL .24s ease-out both; }
  html.vt-r::view-transition-old(root) { animation: fbSwOutR .24s ease-out both; }
  html.vt-r::view-transition-new(root) { animation: fbSwInR .24s ease-out both; }
  @media (prefers-reduced-motion: reduce) {
    ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
  }
</style>
<script>
(function(){
  // اتجاه الانتقال من السحب (sessionStorage، تكتبه الصفحة السابقة لحظة الإفلات)؛ أي تنقّل آخر = بلا انتقال
  var d=null;
  try{ d=sessionStorage.getItem('fbSwDir'); if(d) sessionStorage.removeItem('fbSwDir'); }catch(e){}
  if(d==='l'||d==='r') document.documentElement.classList.add('vt-'+d);
  window.addEventListener('pagereveal',function(e){ if(e.viewTransition&&d!=='l'&&d!=='r') e.viewTransition.skipTransition(); });
})();
</script>
"""


def head_html():
    """رأس صفحات الشريط السفلي: علامة التفعيل + View Transitions + اتجاه الانتقال"""
    return META + HEAD_VT


SWIPE_JS = r"""<script>
(function(){
  if(window.__fbSwipe)return; window.__fbSwipe=1;
  if(!('ontouchstart' in window))return;   // السحب للمس فقط (سطح المكتب: النقر كما هو)
  var D=document, H=D.documentElement, RTL=H.dir==='rtl';
  var RM=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  var DUR=RM?0:220, GAP=16, LOCK=10, FRAC=.3, VFLICK=.3;
  var st=D.createElement('style');
  st.textContent='.swind{position:absolute;bottom:0;height:2px;background:var(--accent);pointer-events:none;border-radius:2px}'+
    '.swdrag>*{border-bottom-color:transparent!important}'+
    '.swpv{position:fixed;top:0;left:0;right:0;bottom:0;z-index:850;background:var(--bg);padding:24px 16px;pointer-events:none;overflow:hidden}'+
    '.swpv .swh{font-size:clamp(16px,5.2vw,22px);font-weight:700;color:var(--text);min-height:44px;display:flex;align-items:center;margin-bottom:12px}'+
    '.swpv .sk{height:64px;border-radius:12px;background:var(--card);margin-bottom:10px;opacity:.8}'+
    '.swpv .sk.s{height:40px;width:60%}';
  D.head.appendChild(st);

  // مجموعات التبويبات المعروفة: الشريط، الزر، صنف التفعيل، لوحة الزر، وهل الخط يتبع السحب
  var SETS=[
    {bar:'.mtabs', tab:'.mtab', on:'on', ind:true, panel:function(b){return D.querySelector('.mp[data-tab="'+b.getAttribute('data-tab')+'"]');}},
    {bar:'.cattabs', tab:'.tab', on:'active', ind:true, panel:function(b){return D.querySelector('.panel[data-cat="'+b.getAttribute('data-cat')+'"]');}},
    {bar:'.ftabs', tab:'.ftab', on:'active', ind:false, panel:function(b){return D.getElementById((b.id||'').replace('tab-','view-'));}},
    {bar:'.ntabs', tab:'.ntab', on:'on', ind:false, panel:function(b){return D.getElementById(b.getAttribute('data-t')==='l'?'nl':'nt');}}
  ];
  function shown(el){return !!el&&getComputedStyle(el).display!=='none'&&!el.hidden;}
  function findSet(target){
    for(var i=0;i<SETS.length;i++){
      var s=SETS[i], bar=D.querySelector(s.bar); if(!bar||!shown(bar))continue;
      var tabs=[].filter.call(bar.querySelectorAll(s.tab),function(b){return shown(b)&&s.panel(b);});
      if(tabs.length<2)continue;
      var cur=-1; tabs.forEach(function(b,k){if(b.classList.contains(s.on))cur=k;});
      if(cur<0)continue;
      var p=s.panel(tabs[cur]);
      if(p&&p.contains(target))return {s:s,bar:bar,tabs:tabs,cur:cur,panel:p};
    }
    return null;
  }
  function hScroll(el){
    for(;el&&el!==D.body;el=el.parentElement){
      var ox=getComputedStyle(el).overflowX;
      if((ox==='auto'||ox==='scroll')&&el.scrollWidth>el.clientWidth+2)return true;
    }
    return false;
  }
  var EXC='input,textarea,select,.nav,.psheet,.ptoast,.fsh,.sovl2,.sdl,.fbar,.mtabs,.cattabs,.ftabs,.ntabs,.daynav,.allsheet,#allsheet';
  var PAGE=!!D.querySelector('meta[name="sw-page"]');
  var HOMEP=!!D.querySelector('.daypanel');   // الرئيسية: السحب على المحتوى للأيام (DAY_SCRIPT)

  var g=null;   // الإيماءة الجارية
  D.addEventListener('touchstart',function(e){
    if(g&&g.anim)return;
    g=null;
    if(e.touches.length!==1)return;
    var t=e.target;
    if(!t.closest||t.closest(EXC)||hScroll(t))return;
    var x=e.touches[0].clientX,y=e.touches[0].clientY;
    g={x0:x,y0:y,t:t,mode:null,set:findSet(t),pts:[[Date.now(),x]],dx:0};
  },{passive:true});

  D.addEventListener('touchmove',function(e){
    if(!g||g.mode==='no'||g.anim)return;
    var x=e.touches[0].clientX,y=e.touches[0].clientY,dx=x-g.x0,dy=y-g.y0;
    if(!g.mode){
      if(Math.abs(dx)<LOCK&&Math.abs(dy)<LOCK)return;
      if(Math.abs(dy)>=Math.abs(dx)){g.mode='no';return;}   // عمودي: للمتصفح
      g.sign=dx<0?-1:1;   // اتجاه الإصبع الأول
      var fwd=(dx<0)!==RTL;   // نحو التبويب/الصفحة التالية بترتيب القراءة
      if(g.set){
        var n=g.set.cur+(fwd?1:-1);
        if(n>=0&&n<g.set.tabs.length){startTab(n);}
      }
      // الرئيسية (لوحات أيام): سحب الصفحات من الشريط العلوي فقط — باقي الشاشة لسحب الأيام (DAY_SCRIPT) كما كان
      if(!g.mode&&PAGE&&!(HOMEP&&!(g.t.closest&&g.t.closest('.appbar'))))startPage(fwd);
      if(!g.mode){g.mode='no';return;}
    }
    e.preventDefault();
    g.pts.push([Date.now(),x]); if(g.pts.length>12)g.pts.shift();
    g.dx=g.sign<0?Math.min(0,dx):Math.max(0,dx);   // لا عبور للجهة الأخرى
    if(g.mode==='tab')moveTab(g.dx);else moveP(g.dx);
  },{passive:false});

  function endGesture(cancel){
    if(!g||!g.mode||g.mode==='no'){g=null;return;}
    // سرعة آخر 150ms فقط (لا من بداية اللمسة: تأخير قفل المحور يخفّض السرعة الحقيقية)
    var p=g.pts, v=0, b=p[p.length-1], a=b;
    for(var k=p.length-1;k>=0&&b[0]-p[k][0]<=150;k--)a=p[k];
    if(a!==b)v=(b[1]-a[1])/Math.max(1,b[0]-a[0]);
    var W=g.W, go=!cancel&&(Math.abs(g.dx)>FRAC*W||(Math.abs(v)>VFLICK&&(v<0)===(g.sign<0)&&Math.abs(g.dx)>20));
    if(g.mode==='tab')endTab(go);else endPage(go);
  }
  D.addEventListener('touchend',function(){endGesture(false);},{passive:true});
  D.addEventListener('touchcancel',function(){endGesture(true);},{passive:true});

  function tr(el,x,anim){
    el.style.transition=anim&&DUR?'transform '+DUR+'ms ease-out':'none';
    el.style.transform=x?'translateX('+x+'px)':'';
  }
  function save(el,keys){var o={};keys.forEach(function(k){o[k]=el.style[k];});return o;}
  function restore(el,o){Object.keys(o).forEach(function(k){el.style[k]=o[k];});}

  // ── التبويبات ──
  function startTab(n){
    var S=g.set, cur=S.panel, nb=S.s.panel(S.tabs[n]), wrap=cur.parentNode;
    if(!nb)return;
    g.mode='tab'; g.n=n; g.nb=nb; g.wrap=wrap; g.W=cur.offsetWidth;
    g.sv={cur:save(cur,['transform','transition','willChange']),nb:save(nb,['display','position','top','left','width','transform','transition','willChange']),
          wrap:save(wrap,['position','overflowX']),bar:save(S.bar,['position'])};
    if(getComputedStyle(wrap).position==='static')wrap.style.position='relative';
    wrap.style.overflowX='clip';
    // المجاورة تُعرض من أعلى الجزء المرئي من اللوحة الحالية (تحت الشريط الثابت إن وُجد)، وتُثبَّت هناك بعد الإنهاء
    var inset=Math.max(0,S.bar.getBoundingClientRect().bottom), top=cur.getBoundingClientRect().top;
    g.delta=Math.max(0,inset-top);
    g.off=(g.sign<0?1:-1)*(g.W+GAP);
    nb.style.display='block'; nb.style.position='absolute'; nb.style.top=(cur.offsetTop+g.delta)+'px';
    nb.style.left=cur.offsetLeft+'px'; nb.style.width=g.W+'px';
    cur.style.willChange=nb.style.willChange='transform';
    tr(nb,g.off,false);
    if(S.s.ind){
      // مواضع الزرّين تُقرأ مرة واحدة هنا: قراءتها بعد كل كتابة transform تفرض إعادة تخطيط الصفحة كلها بكل حركة (بطء على اللوحات الكبيرة)
      var ta=S.tabs[S.cur], tb=S.tabs[n]; g.ix=[ta.offsetLeft,ta.offsetWidth,tb.offsetLeft,tb.offsetWidth];
      if(getComputedStyle(S.bar).position==='static')S.bar.style.position='relative';
      g.ind=D.createElement('span'); g.ind.className='swind'; S.bar.appendChild(g.ind); S.bar.classList.add('swdrag');
    }
  }
  function indAt(p){
    if(!g.ind)return;
    var x=g.ix, l=x[0]+(x[2]-x[0])*p, w=x[1]+(x[3]-x[1])*p;
    g.ind.style.left=l+'px'; g.ind.style.width=w+'px';
  }
  function moveTab(dx){
    tr(g.set.panel,dx,false); tr(g.nb,g.off+dx,false);
    indAt(Math.min(1,Math.abs(dx)/(g.W+GAP)));
  }
  function endTab(go){
    var G=g, S=G.set, cur=S.panel, nb=G.nb, fin=go?-G.off:0;
    G.anim=true;
    tr(cur,fin,true); tr(nb,G.off+fin,true);
    if(G.ind){G.ind.style.transition=DUR?'left '+DUR+'ms ease-out, width '+DUR+'ms ease-out':'none';indAt(go?1:0);}
    setTimeout(function(){
      restore(cur,G.sv.cur); restore(nb,G.sv.nb); restore(G.wrap,G.sv.wrap); restore(S.bar,G.sv.bar);
      if(G.ind){G.ind.remove(); S.bar.classList.remove('swdrag');}
      if(go){
        var y0=window.pageYOffset;
        S.tabs[G.n].click();   // منطق الصفحة نفسه (لوحات كسولة، history، تمرير)
        if(G.delta>0&&window.pageYOffset===y0)window.scrollBy(0,-G.delta);
      }
      if(g===G)g=null;
    },DUR+20);
  }

  // ── صفحات الشريط السفلي ──
  var NAV=[].slice.call(D.querySelectorAll('.nav a')), CURP=-1;
  NAV.forEach(function(a,k){if(a.classList.contains('on'))CURP=k;});
  function startPage(fwd){
    if(CURP<0)return;
    var n=CURP+(fwd?1:-1); if(n<0||n>=NAV.length)return;
    var page=D.querySelector('.wrap'); if(!page)return;
    g.mode='page'; g.n=n; g.page=page; g.W=window.innerWidth; g.off=(g.sign<0?1:-1)*g.W;
    g.sv={page:save(page,['transform','transition','willChange'])};
    var pv=D.createElement('div'); pv.className='swpv'; pv.setAttribute('aria-hidden','true');
    var nb=D.querySelector('.nav'); if(nb)pv.style.bottom=nb.offsetHeight+'px';
    var lab=NAV[n].querySelector('span:last-child'), h=D.createElement('div'); h.className='swh'; h.textContent=lab?lab.textContent:'';
    pv.appendChild(h);
    for(var i=0;i<7;i++){var c=D.createElement('div');c.className='sk'+(i===0?' s':'');pv.appendChild(c);}
    D.body.appendChild(pv); g.pv=pv;
    page.style.willChange='transform';
    tr(pv,g.off,false);
  }
  function navOn(k){NAV.forEach(function(a,i){var on=i===k;a.classList.toggle('on',on);
    [].forEach.call(a.querySelectorAll('span'),function(s){s.classList.toggle('on',on);});});}
  function moveP(dx){
    tr(g.page,dx,false); tr(g.pv,g.off+dx,false);
    navOn(Math.abs(dx)>g.W/2?g.n:CURP);
  }
  function vtNav(){return 'onpagereveal' in window||typeof PageRevealEvent!=='undefined';}
  function endPage(go){
    var G=g; G.anim=true;
    if(!go){
      tr(G.page,0,true); tr(G.pv,G.off,true); navOn(CURP);
      setTimeout(function(){cleanPage(G);if(g===G)g=null;},DUR+20);
      return;
    }
    navOn(G.n);
    var href=NAV[G.n].href;
    try{sessionStorage.setItem('fbSwDir',G.sign<0?'l':'r');}catch(e){}
    if(vtNav()&&!RM){location.href=href;return;}   // الانتقال يكمل الانزلاق من الموضع الحالي
    tr(G.page,-G.off,true); tr(G.pv,0,true);        // بلا دعم: المعاينة تملأ الشاشة ثم تنقّل (بلا وميض)
    setTimeout(function(){location.href=href;},DUR+10);
  }
  function cleanPage(G){
    if(!G)return;
    if(G.page)restore(G.page,G.sv.page);
    if(G.pv&&G.pv.parentNode)G.pv.parentNode.removeChild(G.pv);
    navOn(CURP);
  }
  // الرجوع (bfcache) يعيد الصفحة كما تُركت أثناء الانتقال: تنظيف كامل
  window.addEventListener('pageshow',function(e){if(e.persisted&&g){cleanPage(g);g=null;}
    [].forEach.call(D.querySelectorAll('.swpv'),function(x){x.remove();});
    var w=D.querySelector('.wrap'); if(w&&w.style.transform){w.style.transform='';w.style.transition='';}
    if(CURP>=0)navOn(CURP);});

  // جلب مسبق للصفحتين المجاورتين (Chromium؛ Safari يتجاهل rel=prefetch بلا ضرر)
  if(PAGE&&CURP>=0){
    var pre=function(){[CURP-1,CURP+1].forEach(function(k){if(k<0||k>=NAV.length)return;
      var l=D.createElement('link');l.rel='prefetch';l.href=NAV[k].href;D.head.appendChild(l);});};
    if(window.requestIdleCallback)requestIdleCallback(pre,{timeout:3000});else setTimeout(pre,1500);
  }
})();
</script>"""

# العمودي للمتصفح والأفقي للسكربت على اللوحات (CSS ثابت يُضاف للصفحات؛ السكربت نفسه لا يعتمد عليه للعمل)
TOUCH_CSS = """
  .mp, .panel, .fview, .nview, .wrap { touch-action: pan-y pinch-zoom; }
"""


def swipe_script():
    return SWIPE_JS
