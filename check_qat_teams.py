#!/usr/bin/env python3
"""
أندية دوري نجوم قطر — فحص قراءة فقط
=======================================
يجلب قائمة الأندية لموسم مُعطى من /teams?league=305&season=X.
لا يكتب بالديتابيس. طلب واحد لكل موسم يُمرَّر.

التشغيل:
    python check_qat_teams.py 2025
    python check_qat_teams.py 2025 2026
"""

import sys
import requests

from config import API_BASE, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LEAGUE_ID = 305  # Qatar Stars League

seasons = [int(a) for a in sys.argv[1:] if a.isdigit()]
if not seasons:
    print("الاستعمال: python check_qat_teams.py 2025 [2026 ...]")
    sys.exit(1)

for season in seasons:
    r = requests.get(f"{API_BASE}/teams", headers=headers(),
                      params={"league": LEAGUE_ID, "season": season},
                      timeout=30)
    data = r.json()
    resp = data.get("response", [])

    print(f"\n{'=' * 60}")
    print(f"  موسم {season} — عدد الأندية: {len(resp)}")
    print(f"{'=' * 60}")

    for item in sorted(resp, key=lambda x: x["team"]["name"]):
        t = item["team"]
        v = item.get("venue", {}) or {}
        print(f"  {t['id']:>6}  {t['name']:<28}  "
              f"تأسس {t.get('founded') or '—'}  "
              f"ملعب: {v.get('name') or '—'}")
