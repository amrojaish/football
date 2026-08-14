#!/usr/bin/env python3
"""
فحص بنية صفحة النادي
======================
بيطبع شكل بطاقات المباريات وأزرار الإحصائيات كما هي بالـHTML،
عشان نعرف ليش الفلترة مش شغالة.

التشغيل:
    python peek.py
"""

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PATH = "clubs/4532.html"

html = open(PATH, encoding="utf-8").read()

print("\n" + "=" * 58)
print("  بطاقات المباريات (أول 4)")
print("=" * 58)
cards = re.findall(r'<div class="match[^"]*"[^>]*>', html)
for x in cards[:4]:
    print("   ", x)
print(f"\n  العدد الكلي: {len(cards)}")

print("\n" + "=" * 58)
print("  مربعات الإحصائيات")
print("=" * 58)
stats = re.findall(r'<div class="stat[^"]*"[^>]*>', html)
for x in stats[:10]:
    print("   ", x)

print("\n" + "=" * 58)
print("  صناديق المباريات والأزرار")
print("=" * 58)
print("   mbox:", html.count('class="mbox"'))
print("   more:", html.count('class="more"'))
print("   spanel:", html.count('class="spanel"'))

print("\n" + "=" * 58)
print("  فحص الكلاسات المطلوبة للفلترة")
print("=" * 58)
for c in ("w", "d", "l"):
    n = len(re.findall(r'<div class="match ' + c + r'[ "]', html))
    print(f"   بطاقات بكلاس '{c}': {n}")

print()
