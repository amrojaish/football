#!/usr/bin/env python3
"""
الثيم — الألوان بمكان واحد
=============================
كل ألوان الموقع هنا. أي تغيير لون يصير هنا فقط، لا في
أربعة ملفات توليد.

الاستخدام:
    from theme import VARS, THEME_SCRIPT, THEME_BUTTON

    STYLE = "<style>" + VARS + "  body { background: var(--bg); }" ...

المتغيرات:
    --bg      خلفية الصفحة
    --card    خلفية البطاقات والجداول
    --card2   خلفية أغمق/أفتح (رؤوس الجداول)
    --deep    خلفية النتيجة داخل البطاقة
    --text    لون النص الأساسي
    --muted   لون النص الثانوي
    --line    لون الحدود والفواصل
    --accent  الأزرق (روابط، نقاط، تفعيل)
    --green   فوز / تبويب الموسم
    --red     خسارة / هبوط

⚠️ الوضع يُحفظ في localStorage باسم "theme" ويُطبَّق **قبل**
   رسم الصفحة لمنع وميض أبيض عند التحميل.
"""

VARS = """
  :root {
    --bg:     #0f1419;
    --card:   #161b22;
    --card2:  #1c2128;
    --deep:   #0d1117;
    --text:   #e8eaed;
    --muted:  #7d8590;
    --line:   #21262d;
    --accent: #2f81f7;
    --green:  #3fb950;
    --red:    #f85149;
  }
  [data-theme="light"] {
    --bg:     #ffffff;
    --card:   #f6f8fa;
    --card2:  #eaeef2;
    --deep:   #eaeef2;
    --text:   #1f2328;
    --muted:  #59636e;
    --line:   #d1d9e0;
    --accent: #0969da;
    --green:  #1a7f37;
    --red:    #cf222e;
  }
  html { background: var(--bg); }
  .themebtn {
    background: var(--card); color: var(--muted);
    border: 1px solid var(--line); padding: 6px 12px;
    border-radius: 8px; font-size: 15px; cursor: pointer;
    font-family: inherit; line-height: 1;
  }
  .themebtn:hover { background: var(--card2); color: var(--text); }
  .backbtn { background: var(--card); color: var(--muted);
             border: 1px solid var(--line); padding: 6px 14px;
             border-radius: 8px; font-size: 13px; cursor: pointer;
             font-family: inherit; }
  .backbtn:hover { background: var(--card2); color: var(--text); }
"""

# يوضع في <head> — يطبّق الوضع قبل رسم الصفحة
THEME_HEAD = """<script>
(function(){try{var t=localStorage.getItem('theme');
if(t==='light'){document.documentElement.setAttribute('data-theme','light');}
}catch(e){}})();
</script>"""

# يوضع قبل </body>
THEME_SCRIPT = """<script>
(function(){
  var b=document.getElementById('themebtn');
  if(!b)return;
  function icon(){
    var l=document.documentElement.getAttribute('data-theme')==='light';
    b.textContent=l?'\\u2600':'\\u263E';
  }
  icon();
  b.addEventListener('click',function(){
    var h=document.documentElement;
    var l=h.getAttribute('data-theme')==='light';
    if(l){h.removeAttribute('data-theme');}
    else{h.setAttribute('data-theme','light');}
    try{localStorage.setItem('theme',l?'dark':'light');}catch(e){}
    icon();
  });
})();
</script>"""

THEME_BUTTON = '<button class="themebtn" id="themebtn">\u263E</button>'


BACK_SCRIPT = """<script>
(function(){
  var b=document.getElementById('backbtn');
  if(!b)return;
  // يظهر فقط إن كان في تاريخ تصفّح داخل الموقع
  if(history.length<=1){b.style.display='none';return;}
  b.addEventListener('click',function(){history.back();});
})();
</script>"""


def back_button(label):
    return f'<button class="backbtn" id="backbtn">{label}</button>'


SITE = "https://saffara.app"


def url_for(rel):
    """
    الرابط الكامل لمسار نسبي من جذر الموقع. index.html يُحوَّل
    لمسار المجلد — نفس منطق make_sitemap.py حرفياً (مصدر واحد
    لبناء الروابط، يستوردها make_sitemap.py من هنا لا العكس).
    """
    if rel == "index.html":
        return SITE + "/"
    if rel.endswith("/index.html"):
        return f"{SITE}/{rel[:-len('index.html')]}"
    return f"{SITE}/{rel}"


def head_meta(title, desc, url_prefix="", lang="ar", canonical=""):
    """
    أيقونة الموقع + بطاقة المشاركة + وسوم PWA + رابط قانوني.

    ⚠️ **canonical مسار نسبي من الجذر** (مثل "clubs/976.html" أو
       "en/clubs/976.html")، لا رابطاً كاملاً — `url_for()` يبنيه.
       تُرِك اختيارياً (فراغ = بلا وسم) لتوافق الاستدعاءات القديمة،
       لكن كل نداء بالمشروع يمرّره الآن (راجع درس الأداء/SEO
       5 سبتمبر — بند مفتوح).

    ⚠️ **مسارات PWA مطلقة عمداً** (`/icons/...`) لا نسبية —
       الـmanifest والـservice worker يجب أن يشيرا لنفس الملف
       من كل عمق (الجذر · clubs/ · en/clubs/)، وإلا سجّل كل
       مستوى تطبيقاً منفصلاً.

    ⚠️ **manifest لكل لغة** — اسم التطبيق يتبع لغة الصفحة، لكن
       `scope` موحّد (`/`) حتى يبقى التنقّل بين
       العربية والإنجليزية داخل التطبيق لا بالمتصفح.
    """
    mf = "manifest-ar.json" if lang == "ar" else "manifest-en.json"
    canon = (f'<link rel="canonical" href="{url_for(canonical)}">\n'
             if canonical else "")
    return (
        canon +
        f'<link rel="icon" type="image/svg+xml" '
        f'href="{url_prefix}favicon.svg">\n'
        f'<link rel="icon" type="image/png" sizes="32x32" '
        f'href="/icons/icon-32.png">\n'
        f'<link rel="apple-touch-icon" '
        f'href="/icons/icon-180.png">\n'
        f'<link rel="manifest" href="/{mf}">\n'
        f'<meta name="theme-color" content="#0D47A1">\n'
        f'<meta name="mobile-web-app-capable" content="yes">\n'
        f'<meta name="apple-mobile-web-app-capable" content="yes">\n'
        f'<meta name="apple-mobile-web-app-status-bar-style" '
        f'content="black-translucent">\n'
        f'<meta name="apple-mobile-web-app-title" '
        f'content="{"صافرة" if lang == "ar" else "Whistle"}">\n'
        f'<meta name="description" content="{desc}">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:image" '
        # ⚠️ **og:image يجب أن يكون مطلقاً بالدومين الكامل** —
        # واتساب وتويتر لا يقبلان مساراً نسبياً لصورة المشاركة.
        f'content="https://saffara.app/icons/icon-512.png">\n'
        f'<meta name="twitter:card" content="summary">\n'
    )
