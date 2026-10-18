#!/usr/bin/env python3
"""
صف المباراة المشترك (18 أكتوبر 2026، دفعة C — شكل FotMob)
==========================================================
مصدر واحد لبطاقة المباراة بكل القوائم: الرئيسية وأقسام المتابعة وتبويب مباريات الدوري وأرشيفه (`make_site3.match_card`)
وقائمة صفحة النادي (`make_clubs.render_season::build_cards`). صف واحد مدمج بالوسط:

    [اسم المضيف][شعاره]  الوقت/النتيجة  [شعار الضيف][اسمه]

الاسمان يلتصقان بالشعارين (المضيف محاذٍ نحو الوسط، الضيف من الوسط)، الاسم الطويل سطر واحد ثم «…» بلا التفاف أبداً.
RTL: المضيف يبقى بجهة البداية كما كان (الترتيب يتبع اتجاه الصفحة).

⚠️ **بنية DOM لم تتغيّر** (رابط غامر · `.side` المضيف [شعار، اسم] · `.score` · `.side.away` [اسم، شعار] · ذيل اختياري):
   `live_view.py` يضيف `.lvpill` قبل أول `.side` ويكتب داخل `.score`، و`matchtime.py` يقرأ `data-utc` داخلها. التخطيط الجديد
   كله بـCSS (`ROW_CSS`): `row-reverse` على الجانبين يضع الشعار ملاصقاً للنتيجة بالاتجاهين.

صفر طلبات API.
"""

# يُلحَق **بعد** أنماط الصفحة (STYLE بـmake_site3 وCSS_TYPE بـmake_clubs) ليعلو قواعدها القديمة؛ قواعد البث (.match.live بـLIVE_CSS) أخصّ فتبقى.
ROW_CSS = """
  /* صف المباراة المدمج (دفعة C): [اسم][شعار] الوقت/النتيجة [شعار][اسم] متلاصقة بالوسط؛ الاسم سطر واحد ثم «…» */
  .match { grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); column-gap:8px; }
  .match .side { display:inline-flex; flex-direction:row-reverse; align-items:center; gap:6px;
                 min-width:0; max-width:100%; width:max-content; justify-self:end; margin-inline-start:0; }
  .match .side.away { justify-self:start; margin-inline-start:0; }
  .match .side span { display:block; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                      -webkit-line-clamp:none; text-align:end; }
  .match .side.away span { text-align:start; }
  /* عمود الوسط بعرض ثابت (--scw): الشعارات تصطف عمودياً بطاقةً بعد بطاقة. 80px يسع أعرض تسمية فعلية بالرئيسية/الدوري
     (Postponed 78 · in <1 min 77 · «بعد 59 د» 65 · 10 - 10 70)؛ صفحة النادي خطّها أكبر: 84px (Postponed 81). */
  /* حدّ بداية شفاف 3px لكل بطاقة (:where = صفر خصوصية، فالملوّن يغلبه: .soon بالرئيسية، .rw/.rd/.rl بالنادي): المحتوى بنفس الإزاحة فيصطف */
  :where(.match) { border-inline-start:3px solid transparent; }
  .match .score { width:var(--scw,80px); text-align:center; overflow:hidden; text-overflow:ellipsis; }
  /* حالة البث بعد الانتهاء/التوقف (live_view: «2 - 1 انتهت»، «متوقفة مؤقتاً») بسطر صغير تحت النتيجة داخل العمود نفسه */
  .match .score .lvend { display:block; white-space:normal; font-size:11px; line-height:1.15; margin-top:1px; }
"""


def match_row(mid, href, home, away, score_html, cls="match", attrs="", tail=""):
    """بطاقة مباراة واحدة. home/away = (الاسم، وسم الشعار، رابط النادي أو None).
    رابط النادي (صفحة النادي) = `<a class="side">` يعلو الرابط الغامر؛ بلا رابط = `<div class="side">` (الضغط يمرّ للمباراة).
    attrs: سمات إضافية للبطاقة (data-h/data-a/data-k…)، tail: ما بعد الفريق الضيف (سطر التاريخ)."""
    def side(t, away_side):
        name, logo, club = t
        tag, h = ("a", f' href="{club}"') if club else ("div", "")
        inner = f'<span>{name}</span>{logo}' if away_side else f'{logo}<span>{name}</span>'
        return f'<{tag} class="side{" away" if away_side else ""}"{h}>{inner}</{tag}>'
    return (f'<div class="{cls}" data-mid="{mid}"{attrs}>'
            f'<a class="open" href="{href}" aria-label="{home[0]} - {away[0]}"></a>'
            f'{side(home, False)}{score_html}{side(away, True)}{tail}</div>')
