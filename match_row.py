#!/usr/bin/env python3
"""
صف المباراة المشترك (18 أكتوبر 2026، دفعة C — شكل FotMob)
==========================================================
مصدر واحد لبطاقة المباراة بكل القوائم: الرئيسية وأقسام المتابعة وتبويب مباريات الدوري وأرشيفه (`make_site3.match_card`)
وقائمة صفحة النادي (`make_clubs.render_season::build_cards`). صف واحد مدمج بالوسط:

    [اسم المضيف][شعاره]  الوقت/النتيجة  [شعار الضيف][اسمه]

الاسمان يلتصقان بالشعارين (المضيف محاذٍ نحو الوسط، الضيف من الوسط). الاسم الطويل **يلتفّ لسطرين** محاذياً جهة شعاره
بلا قصّ ولا «…» (26 أكتوبر 2026، دفعة UI 3 إصلاح 2، كـFotMob)؛ البطاقة تطول فقط حين يلتف اسم.
RTL: المضيف يبقى بجهة البداية كما كان (الترتيب يتبع اتجاه الصفحة).

⚠️ **بنية DOM لم تتغيّر** (رابط غامر · `.side` المضيف [شعار، اسم] · `.score` · `.side.away` [اسم، شعار] · ذيل اختياري):
   `live_view.py` يضيف `.lvpill` قبل أول `.side` ويكتب داخل `.score`، و`matchtime.py` يقرأ `data-utc` داخلها. التخطيط الجديد
   كله بـCSS (`ROW_CSS`): `row-reverse` على الجانبين يضع الشعار ملاصقاً للنتيجة بالاتجاهين.

صفر طلبات API.
"""

# يُلحَق **بعد** أنماط الصفحة (STYLE بـmake_site3 وCSS_TYPE بـmake_clubs) ليعلو قواعدها القديمة؛ قواعد البث (.match.live بـLIVE_CSS) أخصّ فتبقى.
ROW_CSS = """
  /* صف المباراة المدمج (دفعة C): [اسم][شعار] الوقت/النتيجة [شعار][اسم] متلاصقة بالوسط.
     الاسم الطويل يلتف (26 أكتوبر 2026، إصلاح 2 — كان سطراً واحداً ثم «…»): بلا قصّ، محاذٍ لجهة شعاره، والشعار بمنتصف السطرين.
     overflow-wrap:break-word يكسر كلمة واحدة أعرض من العمود فقط (لا يغيّر عرض المحتوى الأدنى فلا يتسع العمود). */
  .match { grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); column-gap:8px; }
  .match .side { display:inline-flex; flex-direction:row-reverse; align-items:center; gap:6px;
                 min-width:0; max-width:100%; width:max-content; justify-self:end; margin-inline-start:0; }
  .match .side.away { justify-self:start; margin-inline-start:0; }
  .match .side span { display:block; min-width:0; white-space:normal; overflow:visible; text-overflow:clip;
                      overflow-wrap:break-word; line-height:1.2; -webkit-line-clamp:none; text-align:end; }
  .match .side.away span { text-align:start; }
  /* عمود الوسط بعرض ثابت (--scw): الشعارات تصطف عمودياً بطاقةً بعد بطاقة. 80px يسع أعرض تسمية فعلية بالرئيسية/الدوري
     (Postponed 78 · in <1 min 77 · «بعد 59 د» 65 · 10 - 10 70)؛ صفحة النادي خطّها أكبر: 84px (Postponed 81). */
  /* حدّ بداية شفاف 3px لكل بطاقة (:where = صفر خصوصية، فالملوّن يغلبه: .soon بالرئيسية، .rw/.rd/.rl بالنادي): المحتوى بنفس الإزاحة فيصطف */
  :where(.match) { border-inline-start:3px solid transparent; }
  .match .score { width:var(--scw,80px); text-align:center; overflow:hidden; text-overflow:ellipsis; }
  /* حالة البث بعد الانتهاء/التوقف (live_view: «2 - 1 انتهت»، «متوقفة مؤقتاً») بسطر صغير تحت النتيجة داخل العمود نفسه */
  .match .score .lvend { display:block; white-space:normal; font-size:11px; line-height:1.15; margin-top:1px; }
"""


def card_css(scope):
    """أساس البطاقة نفسه (خلفية/شبكة/رابط غامر/شعار/خلية الوسط) **محصوراً بحاوية** لصفحة لا تحمل STYLE الرئيسية (صفحة المباراة،
    دفعة D2: بطاقة المباراة أعلى «المواجهات»). القيم = قواعد .match/.side/.score بـmake_site3.STYLE؛ الحصر يمنع مسّ `.score`
    الكبيرة برأس صفحة المباراة. يُستعمل مع ROW_CSS (المحصور أصلاً بـ.match)."""
    s = scope
    return f"""
  /* بطاقة مباراة مشتركة داخل {s} (match_row.card_css) */
  {s} .match {{ background:var(--card); border-radius:10px; padding:7px 10px; min-height:48px; display:grid;
               align-items:center; gap:4px 6px; position:relative; }}
  {s} .match .open {{ position:absolute; inset:0; z-index:1; border-radius:10px; }}
  {s} .match:hover {{ background:var(--card2); }}
  {s} .match .side {{ position:relative; z-index:2; pointer-events:none; font-size:13px; color:var(--text); text-decoration:none; }}
  {s} .match.soon {{ border-inline-start:3px solid var(--accent); }}
  {s} .match .side img {{ width:22px; height:22px; object-fit:contain; flex:0 0 22px; }}
  {s} .match .score {{ font-size:16px; font-weight:700; padding:3px 9px; background:var(--deep); border-radius:6px; white-space:nowrap; }}
  {s} .match .score.time {{ font-size:13px; color:var(--accent); }}
  {s} .match .score.pst {{ font-size:12px; color:var(--muted); }}
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
