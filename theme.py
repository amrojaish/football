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
    --bg:     #f0f2f5;
    --card:   #ffffff;
    --card2:  #e8ebef;
    --deep:   #e4e8ed;
    --text:   #24292f;
    --muted:  #6b7480;
    --line:   #dde1e6;
    --accent: #0b62c4;
    --green:  #1a7f37;
    --red:    #c9303c;
  }
  html { background: var(--bg); }
  .themebtn {
    background: var(--card); color: var(--muted);
    border: 1px solid var(--line); padding: 6px 12px;
    border-radius: 8px; font-size: 15px; cursor: pointer;
    font-family: inherit; line-height: 1;
  }
  .themebtn:hover { background: var(--card2); color: var(--text); }
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
