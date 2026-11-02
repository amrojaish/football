#!/usr/bin/env python3
"""
أيقونات الإحصائيات الموحَّدة (2 نوفمبر 2026، دفعة 9 بند 5) — مجموعة SVG واحدة أحادية اللون بكل الموقع
=========================================================================================================
المباريات = ملعب صغير · الأهداف = كرة · الصناعة = حذاء · التقييم = نجمة. خطوط بـcurrentColor (fill:none) فتتبع لون النص
بالوضعين الفاتح والداكن؛ مقاس واحد (.sti = 16px، الصغير .sti.s = 13px). بدل رموز ⚽ والأيقونات المختلطة في:
  • صفحة اللاعب: رأس تبويب المسيرة، بطاقات الإحصائيات (الموسم الحالي + تبويب الإحصائيات)، صفوف تبويب المباريات
  • صفحة المباراة: أيقونة الهدف بقائمة الأحداث ومفتاح الأيقونات (make_matches) وأحداث البث (live_view)
الاستعمال: svg("goal") ← نص HTML؛ STAT_CSS بـsite.css (navbar.NAV_CSS) فيصل لكل الصفحات.
"""

_PATHS = {
    # ملعب: الإطار، خط المنتصف، الدائرة، منطقتا الجزاء
    "matches": '<rect x="2.5" y="5" width="19" height="14" rx="1.6"/><path d="M12 5v14"/><circle cx="12" cy="12" r="2.6"/>'
               '<path d="M2.5 9.2h2.8v5.6H2.5M21.5 9.2h-2.8v5.6h2.8"/>',
    # كرة: دائرة + خماسي بالمنتصف + خمسة خطوط للحافة
    "goal": '<circle cx="12" cy="12" r="9"/><path d="M12 8.3l3.2 2.3-1.2 3.7h-4l-1.2-3.7z"/>'
            '<path d="M12 3v5.3M15.2 10.6l5.3-1.7M14 14.3l3.2 4.4M10 14.3l-3.2 4.4M8.8 10.6L3.5 8.9"/>',
    # حذاء كرة: الجسم والنعل + أربعة مسامير
    "assist": '<path d="M3 13.6l1.4-1.1c1.5-1.2 3.4-1.5 5.1-.9l3.1-5.6h5.2l.3 5.6 2.9 2v2.9H3z"/>'
              '<path d="M6 16.5v2.2M10 16.5v2.2M14.5 16.5v2.2M18.5 16.5v2.2"/>',
    # نجمة
    "rating": '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
}
KEYS = tuple(_PATHS)


def svg(kind, small=False, label=""):
    """أيقونة واحدة. label = اسم للقارئ الآلي (role=img)، وإلا aria-hidden."""
    a11y = f' role="img" aria-label="{label}"' if label else ' aria-hidden="true"'
    return (f'<svg viewBox="0 0 24 24" class="sti sti-{kind}{" s" if small else ""}"{a11y}>{_PATHS[kind]}</svg>')


STAT_CSS = """
  /* أيقونات الإحصائيات الموحَّدة (دفعة 9 بند 5، stat_icons.py): نفس المقاس واللون بكل مكان، تتبع لون النص (فاتح/داكن) */
  .sti { width:16px; height:16px; flex:0 0 16px; display:inline-block; vertical-align:-3px; fill:none; stroke:currentColor;
         stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; }
  .sti.s { width:13px; height:13px; flex:0 0 13px; vertical-align:-2px; }
"""
