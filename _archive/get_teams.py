#!/usr/bin/env python3
"""
جلب أسماء الأندية المفقودة من المزوّد
========================================
يأخذ معرّفات أندية ويجلب اسمها الرسمي الإنجليزي وشعارها،
فتُضاف لـteams_arabic.csv بأسماء صحيحة لا مخمَّنة.

⚠️ **لا تخمّن اسم نادٍ من معرّفه.** الاسم الرسمي يأتي من
   المزوّد، والترجمة العربية تُكتب يدوياً بعد رؤيته (درس 61).

الكلفة: طلب واحد لكل نادٍ.

    python get_teams.py 15543 17792 6689 2926 2950
"""

import sys
import time
import requests
from config import API_BASE, headers, check_key

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ids = [a for a in sys.argv[1:] if a.isdigit()]
if not ids:
    print("الاستعمال: python get_teams.py 15543 17792 ...")
    sys.exit(1)

if not check_key():
    sys.exit(1)

print()
print("=" * 66)
print(f"  جلب {len(ids)} نادياً")
print("=" * 66)

rows = []
for tid in ids:
    try:
        r = requests.get(f"{API_BASE}/teams", headers=headers(),
                         params={"id": tid}, timeout=30)
        data = r.json().get("response", [])
    except Exception as e:
        print(f"  {tid}: فشل — {type(e).__name__}")
        continue

    if not data:
        print(f"  {tid}: لا نتيجة")
        continue

    t = data[0]["team"]
    v = data[0].get("venue", {}) or {}
    print(f"\n  team_id = {tid}")
    print(f"     الاسم    : {t.get('name')}")
    print(f"     البلد    : {t.get('country')}   التأسيس: {t.get('founded')}")
    print(f"     المدينة  : {v.get('city') or '—'}")
    print(f"     الشعار   : {t.get('logo')}")
    rows.append((tid, t.get("name"), t.get("logo")))
    time.sleep(1)

print()
print("=" * 66)
print("  للصق في teams_arabic.csv (املأ العمود العربي بنفسك):")
print("=" * 66)
for tid, name, logo in rows:
    print(f"  {tid},{name},,{logo}")
print("""
  ⚠️ رتّب الأعمدة حسب رأس ملفك الفعلي — هذا سرد للقيم فقط.
""")
