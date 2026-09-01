#!/usr/bin/env python3
"""
إيجاد الإملاء الصحيح لاسم لاعب بالداتا
==========================================
حين تكتب اسماً من الذاكرة ولا يطابق الداتا (درس 21)، هذه
الأداة تبحث عنه بنادي اللاعب وتعرض كل الأسماء غير المترجَمة
فيه — فتلتقط الإملاء الصحيح بالنظر.

    python find_key.py الدرعية
    python find_key.py الحزم ضمك الرائد
"""
import sqlite3, sys
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

clubs = sys.argv[1:]
if not clubs:
    print("الاستعمال: python find_key.py <اسم النادي> [نادٍ آخر ...]")
    sys.exit(1)

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

for c in clubs:
    print(f"\n{'='*56}")
    print(f"  أسماء غير مترجَمة في: {c}")
    print('='*56)
    rows = conn.execute("""
        SELECT DISTINCT x.player_en, MAX(m.season) s, COUNT(*) n
        FROM (
            SELECT player_en, match_id, team_id FROM goals
              WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
            UNION ALL
            SELECT player_en, match_id, team_id FROM lineup_players
              WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
            UNION ALL
            SELECT player_en, match_id, team_id FROM events
              WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        ) x
        JOIN matches m ON m.match_id = x.match_id
        JOIN teams t ON t.team_id = x.team_id
        WHERE t.short_name_ar = ?
        GROUP BY x.player_en ORDER BY n DESC
    """, (c,)).fetchall()
    if not rows:
        print("   (لا أسماء غير مترجَمة — أو اسم النادي غير مطابق)")
        continue
    for r in rows:
        print(f"   {r['player_en']:34} موسم {r['s']}  ({r['n']})")
