#!/usr/bin/env python3
"""
شرائح الدوريات/الأندية — مشتركة
===================================
⚠️ **لم يعد هذا الملف معالجاً** (6 سبتمبر) — المعالج نُقل بالكامل
   لـ`following.html` (وضعان: أول زيارة بخطوة "التالي" مطويّة/
   عائد بعرض حرّ، راجع `make_following.py`). `wizard_html`/
   `wizard_script`/`wizard_style` **حُذفت** — صفر مستهلك لها بعد
   الانتقال (كانت مستوردة من `make_site3.py` وحده).

يُصدِّر الآن **كتل البناء المشتركة فقط** — نفس شكل شرائح الدوريات/
الأندية (`.chip`/`.pick`/`.lgroup`) الذي كان خاصاً بالمعالج القديم،
يستهلكه `make_following.py` وحده حالياً:
    CHIP_CSS            → قواعد الشرائح (يعتمد على متغيرات theme.py)
    league_chips_html()  → أزرار شرائح الدوريات
    club_chips_html()    → أزرار شرائح الأندية، مجمَّعة حسب الدوري

التفضيلات نفسها (fbLeagues/fbClubs/fbSetup) تُقرأ/تُكتب عبر
`window.FBPrefs` (`prefs.py`) — هذا الملف بلا أي علاقة بـ
`localStorage` مباشرة.

⚠️ الأندية تُمرَّر من بايثون وقت التوليد — الصفحة لا تستطيع
   الاستعلام من قاعدة البيانات.

الاستخدام:
    from onboard import CHIP_CSS, league_chips_html, club_chips_html
"""


# ── CSS الشرائح — مشتركة، بلا كروم نافذة منبثقة ──
# ⚠️ **`.wsearch` هو المحدِّد الوحيد** لصندوق البحث — العنصر
#    الفعلي بـ`make_following.py` يحمل `class="wsearch"` مباشرة
#    على `<input type="text">`، فلا حاجة لمحدِّد أب.
CHIP_CSS = """
  .wsearch { width:100%; background:var(--bg);
         border:1px solid var(--line); border-radius:9px;
         padding:14px 16px; color:var(--text); font-size:17px;
         font-family:inherit; margin-bottom:14px; }
  .wsearch:focus { outline:none; border-color:var(--accent); }
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
"""


def league_chips_html(leagues):
    """leagues: [(code, name), ...] → أزرار شرائح الدوريات"""
    return "".join(
        f'<button class="chip" data-lg="{c}">{n}</button>'
        for c, n in leagues)


def club_chips_html(leagues, clubs):
    """
    clubs: [(team_id, name, logo, league_code, popular), ...]
           popular = 1 لأشهر 4 أندية بكل دوري (غير مستخدَمة حالياً
           بـfollowing.html — الحقل باقٍ للتوافق لو احتيج لاحقاً)
    مجمّعة حسب الدوري.
    """
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
    return cl
