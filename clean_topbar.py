#!/usr/bin/env python3
"""
حذف زرَّي اللغة والمظهر من الشريط العلوي
==========================================
بعد إضافة الشريط السفلي، صارت اللغة والمظهر متاحين من نافذة
الإعدادات — فوجودهما بالأعلى تكرار.

يحذف من الشريط العلوي في:
    make_site3.py · make_clubs.py · make_matches.py · make_players.py

    - `<a class="lang" href="{switch}">…</a>`   ← زر اللغة
    - `{THEME_BUTTON}`                          ← زر القمر
    - `{search_box(t)}`                         ← البحث (صار بالأسفل)

⚠️ **`switch` يبقى مستعملاً** في `settings_overlay` — لا يُحذف
   المتغيّر نفسه، فقط الزر.

⚠️ **`THEME_SCRIPT` يبقى** — هو من يطبّق الوضع المحفوظ عند
   تحميل الصفحة، ويخرج بهدوء إن لم يجد الزر.

⚠️ نسخة احتياطية `<file>.before_topbar` قبل أي كتابة.

التشغيل:
    python clean_topbar.py --check    <- عرض فقط
    python clean_topbar.py            <- تنفيذ
"""

import io
import os
import re
import shutil
import sys

CHECK = "--check" in sys.argv

FILES = ["make_site3.py", "make_clubs.py",
         "make_matches.py", "make_players.py"]

# الأنماط المحذوفة — كل واحد سطر كامل داخل f-string
PATTERNS = [
    # زر اللغة (بأي صيغة مسافات)
    re.compile(r"[ \t]*f'<a class=\"lang\" href=\"\{switch\}\">"
               r"\{SWITCH_LABEL\[lang\]\}</a>'\n"),
    # search_box + THEME_BUTTON معاً أو منفصلين
    re.compile(r"\{search_box\(t\)\}"),
    re.compile(r"\{THEME_BUTTON\}"),
]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def clean(path):
    if not os.path.exists(path):
        return f"[X] {path} غير موجود"

    src = io.open(path, encoding="utf-8").read()
    orig = src
    hits = []

    for i, pat in enumerate(PATTERNS):
        n = len(pat.findall(src))
        if n:
            src = pat.sub("", src)
            hits.append(f"{n}×نمط{i + 1}")

    if src == orig:
        return f"[=] {path} — ما في شي للحذف"

    if CHECK:
        return f"[OK] {path} — سيُحذف: {' · '.join(hits)}"

    shutil.copy(path, path + ".before_topbar")
    io.open(path, "w", encoding="utf-8").write(src)
    return f"[OK] {path} — حُذف: {' · '.join(hits)}"


print()
print("=" * 60)
for f in FILES:
    print("  " + clean(f))
print("=" * 60)

if CHECK:
    print("\n  [وضع الفحص] — ما انكتب شي\n")
else:
    print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
      python make_players.py
    """)
