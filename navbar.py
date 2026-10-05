#!/usr/bin/env python3
"""
الشريط السفلي الثابت
======================
وحدة مستقلة على نمط `search_view.py` و`lineup_view.py`.
لا تشغّلها لحالها — سكربتات التوليد بتستوردها.

بتقدّم:
    NAV_CSS              → يُضاف لبلوك STYLE
    navbar(t, depth)     → الشريط نفسه — أربعة عناصر فقط
                            (Matches · Leagues · Following · Search)
    settings_button(t)   → أيقونة الإعدادات — تُوضع يدوياً بخانة
                            نهاية `.topbar` بكل صفحة (بند 1، 22
                            سبتمبر: كانت خامس عنصر بالشريط)
    settings_overlay(t)  → نافذة الإعدادات
    nav_script(t, lang)  → السكربت

**الأيقونات SVG لا رموز نصية** — الرمز النصي (⚙ ⌕ ⚽) شكله
يختلف جذرياً بين iOS وAndroid وWindows، وبعضها لا يُعرض أصلاً.
SVG يضمن شكلاً واحداً على كل جهاز.

⚠️ **"الدوريات" صفحة مستقلة** (`leagues.html` / `en/leagues.html`)
   منذ 21 أغسطس. كانت مرساة `#tables` داخل الرئيسية، فحُذف معها
   مراقب التمرير الذي كان يلوّن الأيقونة.

⚠️ **البحث صفحة مستقلة (5 أكتوبر):** `navsearch` رابط عادي إلى `search.html`
   (`make_search_page.py`)؛ لا نافذة ولا `#sovl`.

⚠️ **الإعدادات نافذة لا صفحة** — تجنّباً لتوليد صفحتين إضافيتين
   × 9,000 صفحة. تحتوي: تبديل اللغة + الوضع الفاتح/الداكن.

⚠️ **`padding-bottom` على body إجباري** — الشريط `position:fixed`
   فيغطي آخر محتوى الصفحة بدونه.

⚠️ **زر الإعدادات انتقل لأيقونة علوية (22 سبتمبر)** — كان خامس
   عنصر بالشريط السفلي، صار `settings_button(t)` مستقلة تُوضع
   بخانة نهاية `.topbar` (يسار الشاشة بالعربي RTL، يمين الشاشة
   بالإنجليزي LTR — نفس منطق back_button/season_menu الحالي، لا
   شرط لغة إضافي، flex الصف يتبع `dir` تلقائياً). المعرّف `navset`
   نفسه لم يتغيّر فـ`nav_script()` يعمل بلا أي تعديل.

الاستخدام:
    from navbar import (NAV_CSS, navbar, settings_button,
                         settings_overlay, nav_script)
"""

NAV_CSS = """
  body { padding-bottom:78px; }

  .nav { position:fixed; inset-inline:0; bottom:0; z-index:900;
         background:var(--card); border-top:1px solid var(--line);
         display:flex; justify-content:space-around;
         align-items:stretch; padding:6px 4px 8px;
         backdrop-filter:blur(10px); }
  .nav a, .nav button { flex:1; display:flex; flex-direction:column;
         align-items:center; justify-content:center; gap:3px;
         background:none; border:none; cursor:pointer;
         color:var(--muted); font-family:inherit; font-size:12px;
         text-decoration:none; padding:5px 2px; border-radius:9px;
         transition:color .15s, background .15s; }
  .nav a:hover, .nav button:hover { background:var(--card2); }
  .nav .ic { width:22px; height:22px; display:block; }
  .nav .ic svg { width:100%; height:100%; display:block;
                 fill:none; stroke:currentColor; stroke-width:1.7;
                 stroke-linecap:round; stroke-linejoin:round; }
  .nav .on { color:var(--accent); }

  /* زر الإعدادات — انتقل من الشريط السفلي لأيقونة علوية بخانة
     نهاية .topbar (طرف اليسار بالعربي RTL، طرف اليمين بالإنجليزي
     LTR — نفس منطق season_menu/back_button الحالي بلا أي شرط لغة). */
  .topbtn { background:var(--card); color:var(--muted);
            border:1px solid var(--line); border-radius:9px;
            width:44px; height:44px; display:flex; align-items:center;
            justify-content:center; cursor:pointer; padding:0;
            font-family:inherit; }
  .topbtn:hover { background:var(--card2); color:var(--text); }
  /* شريط التطبيق العلوي (على نمط FotMob): الاسم على جهة، والإعدادات واللغة
     على الجهة الأخرى — الاتجاه تلقائي: عربي الاسم يميناً، إنجليزي يساراً. */
  .appbar { display:flex; align-items:center; justify-content:space-between;
            gap:12px; margin-bottom:8px; }
  .appname { font-size:clamp(16px,5.2vw,22px); font-weight:700;
             color:var(--text); text-decoration:none; line-height:1.2;
             min-width:0; overflow:hidden; text-overflow:ellipsis;
             white-space:nowrap; }
  /* زر الرجوع داخل الشريط: سهم 44×44 بجهة اسم التطبيق (يمين بالعربي،
     يسار بالإنجليزي — flex يتبع dir). الاسم يصغر/يُقتطع عند الضيق. */
  .appl { display:flex; align-items:center; gap:8px; min-width:0; }
  .backarrow { flex:0 0 44px; }
  .appbtns { display:flex; align-items:center; gap:8px; flex:0 0 auto; }
  a.topbtn { text-decoration:none; font-size:14px; font-weight:700;
             font-family:inherit; }
  .vh { position:absolute; width:1px; height:1px; overflow:hidden;
        clip:rect(0 0 0 0); white-space:nowrap; }
  .slink { display:flex; align-items:center; justify-content:space-between;
           width:100%; color:var(--text); text-decoration:none; font-size:14px;
           min-height:44px; }
  .slink .lval { color:var(--muted); font-size:13px; }
  .topbtn .ic { width:18px; height:18px; display:block; }
  .topbtn .ic svg { width:100%; height:100%; display:block;
                     fill:none; stroke:currentColor; stroke-width:1.7;
                     stroke-linecap:round; stroke-linejoin:round; }

  .sovl2 { position:fixed; inset:0; background:rgba(0,0,0,.72);
           display:none; align-items:center; justify-content:center;
           z-index:950; padding:20px; }
  .sovl2.on { display:flex; }
  .sbox2 { background:var(--card); border:1px solid var(--line);
           border-radius:16px; width:100%; max-width:420px;
           padding:20px 18px; }
  .sbox2 h3 { font-size:16px; margin-bottom:14px; }
  .srow { display:flex; align-items:center;
          justify-content:space-between; padding:12px 2px;
          border-bottom:1px solid var(--line); }
  .srow:last-of-type { border-bottom:none; }
  .srow .lbl { font-size:14px; }
  .seg { display:flex; gap:6px; }
  .seg a, .seg button { background:var(--bg); color:var(--muted);
          border:1px solid var(--line); border-radius:8px;
          padding:7px 14px; font-size:13px; cursor:pointer;
          font-family:inherit; text-decoration:none; }
  .seg .act { background:var(--accent); color:#fff;
              border-color:var(--accent); }
  /* شريط "غير متصل" — يظهر أعلى الصفحة عند انقطاع الشبكة.
     ⚠️ ضروري لأن الصفحة قد تُعرض من المخزون: بدونه يظن الزائر
     أن النتيجة المعروضة حالية وهي لقطة قديمة. */
  .offbar { position:fixed; inset-inline:0; top:0; z-index:990;
            background:#8a5300; color:#fff; text-align:center;
            font-size:12.5px; padding:8px 12px; display:none; }
  .offbar.on { display:block; }
  body.offline { padding-top:34px; }

  .sclose2 { display:block; width:100%; margin-top:16px;
             background:var(--card2); color:var(--text);
             border:1px solid var(--line); border-radius:10px;
             padding:11px; font-size:14px; cursor:pointer;
             font-family:inherit; }
"""


# ── أيقونات SVG ────────────────────────────────────────────
IC_MATCHES = (
    '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/>'
    '<path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>'
    '<path d="M12 8.5l3 2.2-1.1 3.5h-3.8L9 10.7z"/></svg>'
)

IC_LEAGUES = (
    '<svg viewBox="0 0 24 24">'
    '<path d="M7 4h10v5a5 5 0 0 1-10 0V4z"/>'
    '<path d="M7 6H4.5A1.5 1.5 0 0 0 3 7.5C3 9.4 4.6 11 6.5 11H7"/>'
    '<path d="M17 6h2.5A1.5 1.5 0 0 1 21 7.5c0 1.9-1.6 3.5-3.5 3.5H17"/>'
    '<path d="M12 14v3M9 20h6M10 17h4"/></svg>'
)

IC_FOLLOWING = (
    '<svg viewBox="0 0 24 24"><path d="M12 4l2.4 5.2 5.6.6-4.2 3.8 '
    '1.2 5.6L12 16.4l-5 2.8 1.2-5.6L4 9.8l5.6-.6z"/></svg>'
)

IC_SEARCH = (
    '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/>'
    '<path d="M20 20l-3.5-3.5"/></svg>'
)

IC_SETTINGS = (
    '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8'
    'l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a2 2 0 0 1-4 0'
    'v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8'
    'l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1'
    'a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8'
    'l.1.1a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1'
    'a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8'
    'l-.1.1a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1h.2a2 2 0 0 1 0 4'
    'h-.1a1.6 1.6 0 0 0-1.5 1z"/></svg>'
)


def navbar(t, depth=0, active="", lang="ar"):
    """
    depth  : عمق الصفحة من الجذر (0 رئيسية · 1 clubs/matches ·
             2 en/clubs)
    active : "matches" أو "leagues" — يلوّن الأيقونة الحالية
    lang   : ⚠️ إجباري للحفاظ على اللغة عند التنقل

    ⚠️ **الرابط يحترم اللغة الحالية.** الاعتماد على العمق وحده
       كان يعيد الزائر الإنجليزي للصفحة العربية: من
       `en/clubs/x.html` (عمق 2) يصير `../../index.html` وهو
       العربي، لا `../en/index.html` المطلوب.
    """
    up = "../" * depth
    # من داخل en/ ننزل للجذر ثم نصعد لـen مجدداً
    home = (up + "index.html") if lang == "ar" else (up + "en/index.html"
            if depth == 0 else "../" * (depth - 1) + "index.html")

    # ⚠️ صفحة الدوريات جارة للرئيسية دائماً — نفس منطق العمق واللغة
    #    (كانت مرساة #tables داخل الرئيسية قبل 21 أغسطس)
    leagues_href = home.replace("index.html", "leagues.html")
    # ⚠️ following.html نفس المنطق — انظر make_following.py
    following_href = home.replace("index.html", "following.html")
    search_href = home.replace("index.html", "search.html")

    def a(k):
        return " on" if active == k else ""

    return (
        f'<nav class="nav">'
        f'<a href="{home}" class="{a("matches").strip()}">'
        f'<span class="ic{a("matches")}">{IC_MATCHES}</span>'
        f'<span class="{a("matches").strip()}">{t["nv_matches"]}</span>'
        f'</a>'
        f'<a href="{leagues_href}" class="{a("leagues").strip()}">'
        f'<span class="ic{a("leagues")}">{IC_LEAGUES}</span>'
        f'<span class="{a("leagues").strip()}">{t["nv_leagues"]}</span>'
        f'</a>'
        # ⚠️ rel="nofollow" مقصود — محتواها 100% من localStorage،
        #    noindex بالصفحة نفسها + استبعاد من sitemap.xml
        #    (make_sitemap.py::SKIP_FILES) يمنعان الفهرسة، وnofollow
        #    هنا طبقة تعزيز إضافية على الرابط الوحيد المؤدي إليها
        #    من كل صفحات الموقع (تلميح لا ضمان — جوجل قد يزحف رغمه).
        f'<a href="{following_href}" rel="nofollow" '
        f'class="{a("following").strip()}">'
        f'<span class="ic{a("following")}">{IC_FOLLOWING}</span>'
        f'<span class="{a("following").strip()}">{t["nv_following"]}</span>'
        f'</a>'
        # ⚠️ البحث صفحة كاملة (دفعة 5) لا نافذة: رابط عادي، والرجوع يعيد الزائر مكانه
        f'<a id="navsearch" href="{search_href}" rel="nofollow" '
        f'class="{a("search").strip()}">'
        f'<span class="ic{a("search")}">{IC_SEARCH}</span>'
        f'<span class="{a("search").strip()}">{t["nv_search"]}</span></a>'
        f'</nav>'
    )


def settings_button(t):
    """
    زر الإعدادات — أيقونة علوية بخانة نهاية .topbar (بند 1، 22
    سبتمبر). حلّ محل زر "Settings" الرابع بالشريط السفلي، الذي
    صار أربعة عناصر فقط (Matches · Leagues · Following · Search).

    ⚠️ **نفس المعرّف `navset`** — nav_script() يربط سلوك الفتح
       والتلوين بالمعرّف لا بالموضع، فنقل الزر بالـHTML وحده كافٍ
       بلا أي تعديل بالسكربت.
    """
    return (
        f'<button id="navset" class="topbtn" title="{t["nv_settings"]}">'
        f'<span class="ic">{IC_SETTINGS}</span></button>'
    )


def back_arrow(t, lang):
    """سهم رجوع 44×44 (id=backbtn فيربطه BACK_SCRIPT بـhistory.back)"""
    pts = "9 6 15 12 9 18" if lang == "ar" else "15 6 9 12 15 18"
    return (f'<button class="topbtn backarrow" id="backbtn" '
            f'aria-label="{t["back"]}" title="{t["back"]}">'
            f'<span class="ic"><svg viewBox="0 0 24 24">'
            f'<polyline points="{pts}"/></svg></span></button>')


def appbar(t, lang, switch_href, back=False):
    """
    شريط التطبيق العلوي بكل الصفحات: اسم التطبيق (رابط الرئيسية) على جهة،
    وزر الإعدادات على الجهة الأخرى. الروابط مطلقة فلا تتأثر بعمق الصفحة.
    زر الإعدادات بنفس المعرّف `navset` (nav_script يربطه).

    ⚠️ **لا زر لغة بالشريط العلوي** (نُقل لقائمة الإعدادات كصف بجانب "حول"):
       `switch_href` يبقى معاملاً لأن settings_overlay() يستخدمه بنفس الاستدعاءات.
    """
    home = "/" if lang == "ar" else "/en/"
    return (
        f'<div class="appbar">'
        f'<span class="appl">{back_arrow(t, lang) if back else ""}'
        f'<a class="appname" href="{home}">{t["site_title"]}</a></span>'
        f'<span class="appbtns">{settings_button(t)}</span></div>\n'
    )


def settings_overlay(t, switch_href, lang):
    """نافذة الإعدادات — اللغة والوضع وحول"""
    other = "en" if lang == "ar" else "ar"
    other_name = "English" if lang == "ar" else "العربية"
    about = "/about.html" if lang == "ar" else "/en/about.html"

    return (
        f'<div class="sovl2" id="sovl2"><div class="sbox2">'
        f'<h3>{t["nv_settings"]}</h3>'

        # اللغة: صف رابط كـ"حول" يذهب لنفس الصفحة بالنسخة الأخرى (hreflang)
        f'<div class="srow"><a class="slink" href="{switch_href}" hreflang="{other}">'
        f'<span class="lbl">{t["st_lang"]}</span>'
        f'<span class="lval">{other_name}</span></a></div>'

        f'<div class="srow"><span class="lbl">{t["st_theme"]}</span>'
        f'<span class="seg">'
        f'<button id="thdark">{t["st_dark"]}</button>'
        f'<button id="thlight">{t["st_light"]}</button>'
        f'</span></div>'

        f'<div class="srow"><a class="slink" href="{about}">'
        f'{t["st_about"]}</a></div>'

        # ⚠️ **صف "أنديتي" (wizrow/openwiz) حُذف نهائياً** (6 سبتمبر)
        #    — صار مكرَّراً وظيفياً بعد أن صارت "المتابَعة" أيقونة
        #    دائمة بالشريط السفلي على كل صفحة (كان هذا الصف مخفياً
        #    أصلاً بكل صفحة غير الرئيسية). راجع بند مفتوح بالـREADME.
        f'<button class="sclose2" id="sclose2">{t["st_close"]}</button>'
        f'</div></div>'
    )


# رسالة "غير متصل" — مصدر واحد للـHTML الثابت (pwa_offbar) ولسكربت PWA المشترك
OFFLINE_MSG = {
    "ar": "لا يوجد اتصال — البيانات المعروضة قد تكون قديمة",
    "en": "You're offline — data shown may be outdated",
}


def pwa_offbar(lang="ar"):
    """شريط "غير متصل" (HTML فقط) — السكربت المقابل بـ`pwa_script`/`PWA_JS`."""
    return f'<div class="offbar" id="offbar">{OFFLINE_MSG[lang]}</div>\n'


# ⚠️ **مصدر واحد** لتسجيل الـservice worker وشريط "غير متصل": يدخل `assets/site.js`
#    (صفحات المباراة/النادي/اللاعب) ومنه `pwa_script` (الرئيسية/الدوري/المتابعة
#    المضمَّنة بلا site.js). اللغة من `<html lang>`، والشريط يُنشأ إن لم يوجد بالـHTML.
PWA_JS = (
    '(function(){\n'
    # حماية من التشغيل مرتين لو حُمّل المصدران (site.js و`pwa_script`) بصفحة واحدة
    'if(window.__pwa)return;window.__pwa=1;\n'
    'var M={ar:"' + OFFLINE_MSG["ar"] + '",en:"' + OFFLINE_MSG["en"] + '"};\n'
    # التسجيل بعد التحميل حتى لا يزاحم عرض الصفحة
    'if("serviceWorker" in navigator){\n'
    'window.addEventListener("load",function(){\n'
    'navigator.serviceWorker.register("/sw.js")\n'
    '.catch(function(){});});}\n'
    'var bar=document.getElementById("offbar");\n'
    'if(!bar){bar=document.createElement("div");bar.className="offbar";\n'
    'bar.id="offbar";\n'
    'bar.textContent=M[(document.documentElement.lang||"ar").slice(0,2)==="en"?"en":"ar"];\n'
    'document.body.insertBefore(bar,document.body.firstChild);}\n'
    'function upd(){\n'
    'var off=!navigator.onLine;\n'
    'bar.classList.toggle("on",off);\n'
    'document.body.classList.toggle("offline",off);}\n'
    'window.addEventListener("online",upd);\n'
    'window.addEventListener("offline",upd);\n'
    'upd();\n'
    '})();\n'
)


def pwa_script(lang="ar"):
    """تسجيل الـservice worker + شريط "غير متصل" (للصفحات المضمَّنة بلا site.js)"""
    return pwa_offbar(lang) + '<script>\n' + PWA_JS + '</script>'


def nav_script(t):
    """ربط الشريط بالبحث الموجود + فتح/إغلاق الإعدادات"""
    return """
<script>
(function(){
  var ns=document.getElementById('navsearch');
  // اختصار "/" يفتح صفحة البحث (كان يفتح النافذة)
  document.addEventListener('keydown',function(e){
    if(e.key==='/' && ns && !/^(INPUT|TEXTAREA)$/.test(
        document.activeElement.tagName)){
      e.preventDefault(); location.href=ns.href;
    }
  });

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
</script>"""
