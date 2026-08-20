#!/usr/bin/env python3
"""
تمرير `lang` لدالة navbar
===========================
`navbar()` صارت تستقبل معامل `lang` رابعاً للحفاظ على اللغة
عند التنقل (كان الزائر الإنجليزي يُعاد للصفحة العربية).

يحدّث كل الاستدعاءات في:
    make_site3.py · make_clubs.py · make_matches.py · make_players.py

    navbar(t, 1)                              → navbar(t, 1, "", lang)
    navbar(t, depth)                          → navbar(t, depth, "", lang)
    navbar(t, 0 if lang=="ar" else 1,"matches")→ … + , lang)

⚠️ يتخطى أي استدعاء يحوي `lang)` أصلاً — تشغيله مرتين آمن.

التشغيل:
    python fix_navlang.py --check
    python fix_navlang.py
"""

import io
import os
import re
import shutil
import sys

CHECK = "--check" in sys.argv
FILES = ["make_site3.py", "make_clubs.py",
         "make_matches.py", "make_players.py"]

SUBS = [
    (re.compile(r'navbar\(t, 0 if lang == "ar" else 1, "matches"\)'),
     'navbar(t, 0 if lang == "ar" else 1, "matches", lang)'),
    (re.compile(r'navbar\(t, depth\)'),
     'navbar(t, depth, "", lang)'),
    (re.compile(r'navbar\(t, 1\)'),
     'navbar(t, 1, "", lang)'),
    (re.compile(r'navbar\(t, 2\)'),
     'navbar(t, 2, "", lang)'),
]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fix(path):
    if not os.path.exists(path):
        return f"[X] {path} غير موجود"

    src = io.open(path, encoding="utf-8").read()
    orig = src
    hits = []

    for pat, rep in SUBS:
        n = len(pat.findall(src))
        if n:
            src = pat.sub(rep, src)
            hits.append(f"{n}×")

    if src == orig:
        found = re.findall(r'navbar\(t[^)]*\)', src)
        if found:
            return f"[=] {path} — محدَّث أصلاً: {found[0]}"
        return f"[X] {path} — لم أجد أي استدعاء لـnavbar"

    if CHECK:
        cur = re.findall(r'navbar\(t[^)]*\)', src)
        return f"[OK] {path} → {cur[0] if cur else '?'}"

    shutil.copy(path, path + ".before_navlang")
    io.open(path, "w", encoding="utf-8").write(src)
    cur = re.findall(r'navbar\(t[^)]*\)', src)
    return f"[OK] {path} → {cur[0] if cur else '?'}"


print()
print("=" * 62)
for f in FILES:
    print("  " + fix(f))
print("=" * 62)

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
