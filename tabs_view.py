#!/usr/bin/env python3
"""
شريط التبويبات المشترك (18 أكتوبر 2026) — صفحة المباراة وصفحة اللاعب
=====================================================================
شريط `.mtabs` تحت الرأس بأزرار `.mtab[data-tab]`، ولوحة واحدة ظاهرة من `.mp[data-tab]`؛ أول عنوان h2 باللوحة مخفي بصرياً (يبقى
للفهرسة وبلا JS). بلا JS: noscript يُظهر كل اللوحات ويخفي الشريط (كل صفحة تضيفه بنفسها).
TABS_CSS = نص قواعد صفحة المباراة نفسه (نُقل من make_matches.py بلا تغيير حرفي)؛ tabs_script() = نفس منطق التبديل بصفحة المباراة
(هناك ما زال ضمن سكربت الصفحة الأكبر).

صفر طلبات API.
"""

TABS_CSS = """  /* تبويبات الصفحة (12 أكتوبر): شريط تحت الرأس، لوحة واحدة ظاهرة، عنوان اللوحة الأول مخفي بصرياً (يبقى للفهرسة وبلا JS) */
  .mtabs { display:flex; gap:2px; margin:14px 0 2px; overflow-x:auto; border-bottom:1px solid var(--line);
           scrollbar-width:none; }
  .mtabs::-webkit-scrollbar { display:none; }
  .mtab { flex:1 1 auto; background:none; border:none; border-bottom:2px solid transparent; margin-bottom:-1px;
          color:var(--muted); padding:10px 6px; font-family:inherit; font-size:13px; font-weight:600;
          cursor:pointer; white-space:nowrap; min-height:44px; }
  .mtab:hover { color:var(--text); }
  .mtab.on { color:var(--text); border-bottom-color:var(--accent); }
  .mp { display:none; }
  .mp.on { display:block; }
"""

NOSCRIPT = ('<noscript><style>.mp{display:block!important}.mp>h2:first-child{display:block!important}'
            '.mtabs{display:none}</style></noscript>\n')


def tabs_html(panels, labels, default):
    """panels: [(key, html)] بالترتيب؛ labels: {key: نص الزر}. اللوحة الفارغة تُحذف؛ لوحة واحدة = بلا شريط."""
    avail = [(k, h) for k, h in panels if h]
    if not avail:
        return ""
    keys = [k for k, _ in avail]
    on = default if default in keys else keys[0]
    secs = "".join(f'<section class="mp{" on" if k == on else ""}" data-tab="{k}">{h}</section>' for k, h in avail)
    if len(avail) < 2:
        return secs
    bar = "".join(f'<button class="mtab{" on" if k == on else ""}" data-tab="{k}" role="tab" '
                  f'aria-selected="{"true" if k == on else "false"}">{labels[k]}</button>' for k in keys)
    return f'<div class="mtabs" role="tablist">{bar}</div>{secs}'


def tabs_script():
    """تبديل اللوحة بلا إعادة تحميل ولا تخزين (الحالة بالـDOM فقط) — نفس منطق صفحة المباراة"""
    return (
        '<script>\n'
        'var mtb=document.querySelectorAll(".mtab");\n'
        'mtb.forEach(function(b){\n'
        'b.addEventListener("click",function(){\n'
        'var k=b.getAttribute("data-tab");\n'
        'mtb.forEach(function(x){var on=x===b;x.classList.toggle("on",on);\n'
        'x.setAttribute("aria-selected",on?"true":"false");});\n'
        'document.querySelectorAll(".mp").forEach(function(p){\n'
        'p.classList.toggle("on",p.getAttribute("data-tab")===k);});\n'
        '});});\n'
        '</script>'
    )
