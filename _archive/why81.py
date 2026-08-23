"""
لماذا قفز العراقي من 1 إلى 33؟
=================================
احتمالان:
  أ) الأتمتة سحبت مباريات عراقية جديدة (الموسم بدأ) — طبيعي
  ب) الدمج نقل صيغاً مترجَمة إلى صيغ غير مترجَمة — خطير
"""
import sqlite3, sys
from collections import Counter
from config import DB_FILE

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

print("\n=== الأسماء العراقية غير المترجَمة — أحدث مباراة لكل اسم ===")
rows = conn.execute("""
    SELECT x.player_en, MAX(DATE(m.date)) d, MAX(m.season) s
    FROM (
        SELECT player_en, match_id FROM goals
        WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM lineup_players
        WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM events
        WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
    ) x
    JOIN matches m ON m.match_id = x.match_id
    WHERE m.league_code='IRQ'
    GROUP BY x.player_en ORDER BY d DESC
""").fetchall()
print("العدد:", len(rows))
c = Counter(r["d"][:7] for r in rows if r["d"])
print("حسب الشهر:", dict(sorted(c.items(), reverse=True)))
print()
for r in rows[:20]:
    print(f"  {r['d']}  موسم {r['s']}  {r['player_en']}")

print("\n=== هل هي صيغ ناتجة عن الدمج؟ ===")
import csv
try:
    keeps = {r['keep_name'].strip() for r in
             csv.DictReader(open('player_merges.csv', encoding='utf-8-sig'))}
    hit = [r["player_en"] for r in rows if r["player_en"] in keeps]
    print(f"  منها أسماء مُحتفَظ بها في player_merges.csv: {len(hit)}")
    for h in hit[:15]:
        print("   ", h)
except FileNotFoundError:
    print("  ما لقيت player_merges.csv")
