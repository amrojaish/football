#!/usr/bin/env python3
"""
تطبيق الشريط السفلي على كل ملفات التوليد
==========================================
يعدّل تلقائياً: make_clubs.py · make_matches.py · make_site3.py
(make_players.py معدَّل يدوياً بالفعل)

لكل ملف يضيف:
    1. استيراد navbar
    2. NAV_CSS لبلوك STYLE
    3. navbar() + settings_overlay() + nav_script() للمخرجات

⚠️ **نسخة احتياطية قبل أي كتابة** — `<file>.before_nav`

⚠️ **يتخطى أي ملف معدَّل أصلاً** (يفحص وجود `from navbar`)
   فتشغيله مرتين آمن.

⚠️ العمق: الأندية والمباريات = 1 دائماً. الرئيسية = 0 للعربي
   و1 للإنجليزي (ملف `en/index.html`).

التشغيل:
    python apply_navbar.py --check    <- عرض فقط
    python apply_navbar.py            <- تنفيذ
"""

import io
import os
import shutil
import sys

CHECK = "--check" in sys.argv

IMPORT_LINE = ("from navbar import (NAV_CSS, navbar, settings_overlay,\n"
               "                    nav_script)\n")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def patch(path, style_old, style_new, out_old, out_new, label):
    if not os.path.exists(path):
        return f"[X] {path} غير موجود"

    src = io.open(path, encoding="utf-8").read()

    if "from navbar import" in src:
        return f"[=] {path} معدَّل أصلاً — تخطّي"

    problems = []

    # 1. الاستيراد — بعد سطر search_view
    anchor = "from search_view import"
    i = src.find(anchor)
    if i == -1:
        problems.append("لم أجد استيراد search_view")
    else:
        end = src.find("\n", src.find(")", i))
        if end == -1:
            end = src.find("\n", i)
        src = src[:end + 1] + IMPORT_LINE + src[end + 1:]

    # 2. CSS
    if style_old not in src:
        problems.append("لم أجد بلوك STYLE المتوقع")
    else:
        src = src.replace(style_old, style_new, 1)

    # 3. المخرجات
    if out_old not in src:
        problems.append("لم أجد كتلة المخرجات المتوقعة")
    else:
        src = src.replace(out_old, out_new, 1)

    if problems:
        return f"[X] {path}: " + " · ".join(problems)

    if CHECK:
        return f"[OK] {path} جاهز للتعديل ({label})"

    shutil.copy(path, path + ".before_nav")
    io.open(path, "w", encoding="utf-8").write(src)
    return f"[OK] {path} عُدِّل  (نسخة: {path}.before_nav)"


results = []

# ── make_clubs.py ──────────────────────────────────────────
results.append(patch(
    "make_clubs.py",
    '""" + SEARCH_CSS + """',
    '""" + SEARCH_CSS + NAV_CSS + """',
    """        + search_overlay(t)
        + page_script(t) + THEME_SCRIPT + BACK_SCRIPT""",
    """        + search_overlay(t)
        + navbar(t, 1)
        + settings_overlay(t, switch, lang)
        + page_script(t) + THEME_SCRIPT + BACK_SCRIPT
        + nav_script(t)""",
    "عمق 1",
))

# ── make_matches.py ────────────────────────────────────────
results.append(patch(
    "make_matches.py",
    '""" + LINEUP_CSS + SEARCH_CSS + """',
    '""" + LINEUP_CSS + SEARCH_CSS + NAV_CSS + """',
    """        + search_overlay(t)
        + THEME_SCRIPT + BACK_SCRIPT""",
    """        + search_overlay(t)
        + navbar(t, 1)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT + BACK_SCRIPT
        + nav_script(t)""",
    "عمق 1",
))

# ── make_site3.py ──────────────────────────────────────────
results.append(patch(
    "make_site3.py",
    '""" + SEARCH_CSS + """',
    '""" + SEARCH_CSS + NAV_CSS + """',
    """        + search_overlay(t)
        + SCRIPT + THEME_SCRIPT + wizard_script(t)""",
    """        + search_overlay(t)
        + navbar(t, 0 if lang == "ar" else 1, "matches")
        + settings_overlay(t, switch, lang)
        + SCRIPT + THEME_SCRIPT + wizard_script(t)
        + nav_script(t)""",
    "عمق 0/1 حسب اللغة",
))

print()
print("=" * 60)
for r in results:
    print("  " + r)
print("=" * 60)

if CHECK:
    print("\n  [وضع الفحص] — ما انكتب شي\n")
else:
    ok = sum(1 for r in results if r.startswith("[OK]"))
    print(f"""
  عُدِّل: {ok} من {len(results)}

  الخطوة الجاية:
      python make_clubs.py
      python make_matches.py
      python make_site3.py
    """)
