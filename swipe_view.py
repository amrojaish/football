#!/usr/bin/env python3
"""
السحب بين التبويبات بمتابعة الإصبع (27 أكتوبر 2026، طلب عمرو #3 دفعة 2؛ دفعة C 28 أكتوبر 2026)
=================================================================================================
سكربت واحد مكتفٍ بنفسه (`swipe_script()`) يُضمَّن بكل صفحة فيها مجموعة تبويبات. المجموعات تُكتشف تلقائياً من جدول SETS: أيام
الرئيسية `.daytabs` (28 أكتوبر 2026)، المباراة/اللاعب `.mtabs`، الدوري `.cattabs`، المتابَعة `.ftabs`، الإشعارات `.ntabs`.
اللوحة الحالية والمجاورة تتحرّكان مع الإصبع 1:1 (transform)، والمجاورة تُعرض مؤقتاً بجانبها (absolute بنفس العرض)؛ الإفلات بعد 25% من
العرض أو بنقرة سريعة (≥ 0.3 px/ms بآخر 150ms) = التبويب المجاور، وإلا ترجع. الإنهاء = نقرة التبويب الأصلية نفسها (`btn.click()`) فيبقى
كل منطق الصفحة كما هو (لوحات كسولة، history.state، توسيط شريط الأيام…). الأشرطة المسطَّرة (.daytabs/.mtabs/.cattabs) خطّها يتبع السحب؛
الممتلئة (.ftabs/.ntabs) تتبدّل عند الإفلات. بالعربي الاتجاه معكوس (التالي بترتيب القراءة يساراً).

⚠️ (28 أكتوبر 2026، دفعة C، قرار عمرو) **أُزيل السحب بين صفحات الشريط السفلي** (المباريات/الدوريات/المتابَعة/البحث) ومعه المعاينة
   وView Transitions والجلب المسبق: الشريط بالنقر وحده كما كان. `head_html()` باقٍ (فارغ) فلا تتغيّر الصفحات المستدعية.

قواعد: قفل المحور بعد 10px — العمودي للمتصفح (touch-action:pan-y)؛ لا شيء يبدأ من حقول الإدخال/الأوراق/الأشرطة/الشريط السفلي أو من
عنصر قابل للتمرير أفقياً (جدول إحصائيات اللاعب يتمرّر ولا يبدّل التبويب). prefers-reduced-motion = بلا حركة إطلاقاً: لا لوحة تتبع
الإصبع، والإفلات بعد العتبة يبدّل فوراً.
"""

def head_html():
    """كان رأس صفحات الشريط السفلي (علامة السحب بين الصفحات + View Transitions) — أُزيل السحب بين الصفحات (28 أكتوبر 2026)"""
    return ""


SWIPE_JS = r"""<script>
(function(){
  if(window.__fbSwipe)return; window.__fbSwipe=1;
  if(!('ontouchstart' in window))return;   // السحب للمس فقط (سطح المكتب: النقر كما هو)
  var D=document, H=D.documentElement, RTL=H.dir==='rtl';
  var RM=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  var DUR=RM?0:220, GAP=16, LOCK=10, FRAC=.3, VFLICK=.3;   // (30 أكتوبر 2026) عتبة الإفلات 30% من العرض (كانت 25%)
  var st=D.createElement('style');
  st.textContent='.swind{position:absolute;bottom:0;height:2px;background:var(--accent);pointer-events:none;border-radius:2px}'+
    '.swdrag>*{border-bottom-color:transparent!important}';
  D.head.appendChild(st);

  // مجموعات التبويبات المعروفة: الشريط، الزر، صنف التفعيل، لوحة الزر، وهل الخط يتبع السحب
  var SETS=[
    // أيام الرئيسية (28 أكتوبر 2026): كل الأيام التي يبلغها الشريط وأسهمه؛ الإنهاء بنقرة اليوم = show + توسيط الشريط (DAY_SCRIPT)
    {bar:'.daytabs', tab:'.daytab', on:'active', ind:true, panel:function(b){return D.getElementById('d'+b.getAttribute('data-day'));}},
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
      if(!g.mode){g.mode='no';return;}   // أول/آخر تبويب أو خارج أي مجموعة: لا شيء (لا سحب بين الصفحات)
    }
    e.preventDefault();
    g.pts.push([Date.now(),x]); if(g.pts.length>12)g.pts.shift();
    g.dx=g.sign<0?Math.min(0,dx):Math.max(0,dx);   // لا عبور للجهة الأخرى
    moveTab(g.dx);
  },{passive:false});

  function endGesture(cancel){
    if(!g||!g.mode||g.mode==='no'){g=null;return;}
    // سرعة آخر 150ms فقط (لا من بداية اللمسة: تأخير قفل المحور يخفّض السرعة الحقيقية)
    var p=g.pts, v=0, b=p[p.length-1], a=b;
    for(var k=p.length-1;k>=0&&b[0]-p[k][0]<=150;k--)a=p[k];
    if(a!==b)v=(b[1]-a[1])/Math.max(1,b[0]-a[0]);
    var W=g.W, go=!cancel&&(Math.abs(g.dx)>FRAC*W||(Math.abs(v)>VFLICK&&(v<0)===(g.sign<0)&&Math.abs(g.dx)>20));
    endTab(go);
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
    if(RM){g.rm=true;return;}   // حركة مخفّضة: لا لوحة تتبع الإصبع — القرار عند الإفلات فقط
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
      // (30 أكتوبر 2026، دفعة 3 بند 6d) الشريط يتبع الإصبع: إزاحة تمرير الشريط التي تُظهر التبويب الهدف كاملاً تُحسب مرة هنا
      //   (من موضعه مقابل حافتَي الشريط — لا scrollIntoView: قد يمرّر الصفحة)، وتُطبَّق تدريجياً بنسبة السحب. زيادة scrollLeft =
      //   تحريك المنظور يميناً بالاتجاهين (CSSOM)، فالحساب نفسه بالعربي والإنجليزي.
      var br=S.bar.getBoundingClientRect(), tr2=tb.getBoundingClientRect(), d=0;
      if(tr2.left<br.left) d=tr2.left-br.left; else if(tr2.right>br.right) d=tr2.right-br.right;
      g.sl=[S.bar.scrollLeft,d]; g.sb=S.bar.style.scrollBehavior; S.bar.style.scrollBehavior='auto';
    }
  }
  function indAt(p){
    if(g.sl&&g.sl[1])g.set.bar.scrollLeft=g.sl[0]+g.sl[1]*p;
    if(!g.ind)return;
    var x=g.ix, l=x[0]+(x[2]-x[0])*p, w=x[1]+(x[3]-x[1])*p;
    g.ind.style.left=l+'px'; g.ind.style.width=w+'px';
  }
  function moveTab(dx){
    if(g.rm)return;
    tr(g.set.panel,dx,false); tr(g.nb,g.off+dx,false);
    indAt(Math.min(1,Math.abs(dx)/(g.W+GAP)));
  }
  function endTab(go){
    var G=g, S=G.set, cur=S.panel, nb=G.nb, fin=go?-G.off:0;
    if(G.rm){if(go)S.tabs[G.n].click(); g=null; return;}   // فوراً، بلا انتقال
    G.anim=true;
    tr(cur,fin,true); tr(nb,G.off+fin,true);
    if(G.ind){G.ind.style.transition=DUR?'left '+DUR+'ms ease-out, width '+DUR+'ms ease-out':'none';indAt(go?1:0);}
    setTimeout(function(){
      restore(cur,G.sv.cur); restore(nb,G.sv.nb); restore(G.wrap,G.sv.wrap); restore(S.bar,G.sv.bar);
      if(G.ind){G.ind.remove(); S.bar.classList.remove('swdrag');}
      if(G.sl){S.bar.style.scrollBehavior=G.sb||''; if(!go&&G.sl[1])try{S.bar.scrollTo({left:G.sl[0],behavior:DUR?'smooth':'auto'});}catch(e){S.bar.scrollLeft=G.sl[0];}}
      if(go){
        var y0=window.pageYOffset;
        S.tabs[G.n].click();   // منطق الصفحة نفسه (لوحات كسولة، history، تمرير)
        if(G.delta>0&&window.pageYOffset===y0)window.scrollBy(0,-G.delta);
      }
      if(g===G)g=null;
    },DUR+20);
  }

})();
</script>"""

# العمودي للمتصفح والأفقي للسكربت على اللوحات (CSS ثابت يُضاف للصفحات؛ السكربت نفسه لا يعتمد عليه للعمل)
TOUCH_CSS = """
  .mp, .panel, .fview, .nview, .wrap, .daypanel { touch-action: pan-y pinch-zoom; }
"""


def swipe_script():
    return SWIPE_JS
