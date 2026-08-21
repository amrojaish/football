"""
فحص تجزؤ قائمة الهدافين
==========================
هدّاف واحد بصيغتين إنجليزيتين داخل نفس الدوري/الموسم تُقسَم
أهدافه بين سطرين، فيسقط من الترتيب أو يظهر مرتين.

⚠️ **جدول `goals` بلا `player_id`** — فلا جسر ممكن. الدليل
   الوحيد المتاح: نفس الترجمة العربية (درس 70).
   والتجزؤ كله أردني/عراقي، وهما بلا `lineup_players` أصلاً.

العلاج: إضافة الصيغ لـplayer_merges.csv (build_merges.py يلتقطها).

    python check_scorers.py
"""
import sqlite3, sys
from collections import defaultdict, Counter
from config import DB_FILE

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT g.player_en, g.player_ar, COUNT(*) n, m.league_code lg, m.season s
    FROM goals g JOIN matches m ON m.match_id = g.match_id
    WHERE g.player_en != '' AND g.player_ar IS NOT NULL AND g.player_ar != ''
    GROUP BY g.player_en, m.league_code, m.season
""").fetchall()

by = defaultdict(list)
for r in rows:
    by[(r["player_ar"], r["lg"], r["s"])].append((r["player_en"], r["n"]))
split = {k: v for k, v in by.items() if len(v) > 1}

print(f"\n{'='*58}")
print(f"  حالات تجزؤ الهدافين: {len(split)}")
print(f"{'='*58}")
print("  حسب الدوري:", dict(Counter(k[1] for k in split)))
if not split:
    print("\n  لا تجزؤ — القائمة سليمة\n")
    sys.exit()
print()
for k, v in sorted(split.items(), key=lambda x: -sum(n for _, n in x[1]))[:20]:
    tot = sum(n for _, n in v)
    parts = " + ".join(f"{e}({n})" for e, n in sorted(v, key=lambda x: -x[1]))
    print(f"  {k[0]:22} {k[1]} {k[2]}  المجموع {tot} = {parts}")
print(f"""
  العلاج: أضف الصيغ لـplayer_merges.csv ثم:
      python apply_player_merges.py
""")
