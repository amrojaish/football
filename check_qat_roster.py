#!/usr/bin/env python3
"""
روستر القطري من المباريات الفعلية — فحص قراءة فقط
======================================================
يجلب كل مباريات موسم مُعطى لدوري نجوم قطر (id=305) ويستخرج
الأندية التي **لعبت فعلياً** (لا قائمة /teams النظرية)، مع عدد
مبارياتها. لا يكتب بالديتابيس. طلب واحد لكل موسم.

التشغيل:
    python check_qat_roster.py 2025 2026
"""

import sys
import requests
from collections import Counter

from config import API_BASE, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LEAGUE_ID = 305

seasons = [int(a) for a in sys.argv[1:] if a.isdigit()]
if not seasons:
    print("الاستعمال: python check_qat_roster.py 2025 [2026 ...]")
    sys.exit(1)

for season in seasons:
    r = requests.get(f"{API_BASE}/fixtures", headers=headers(),
                      params={"league": LEAGUE_ID, "season": season},
                      timeout=30)
    data = r.json()
    resp = data.get("response", [])

    by_status = Counter(f["fixture"]["status"]["short"] for f in resp)
    teams = Counter()
    names = {}
    for f in resp:
        for side in ("home", "away"):
            t = f["teams"][side]
            teams[t["id"]] += 1
            names[t["id"]] = t["name"]

    print(f"\n{'=' * 60}")
    print(f"  موسم {season} — إجمالي المباريات: {len(resp)}")
    print(f"  الحالات: {dict(by_status)}")
    print(f"  عدد الأندية التي لعبت فعلياً: {len(teams)}")
    print(f"{'=' * 60}")
    for tid, n in sorted(teams.items(), key=lambda x: -x[1]):
        print(f"  {tid:>6}  {names[tid]:<28}  مباريات: {n}")
