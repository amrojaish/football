#!/usr/bin/env python3
"""حالة الديتابيس — مباريات وترجمات حسب الموسم"""
import sqlite3, sys
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
print("\n=== المباريات حسب الدوري والموسم ===")
for r in conn.execute("""SELECT league_code lg, season s, COUNT(*) n
    FROM matches GROUP BY league_code, season ORDER BY league_code, season"""):
    print(f"  {r['lg']} {r['s']}: {r['n']}")

print("\n=== أسماء غير مترجَمة حسب موسم المباراة ===")
for r in conn.execute("""
    SELECT m.season s, COUNT(DISTINCT x.player_en) n FROM (
        SELECT player_en, match_id FROM goals
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM lineup_players
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM events
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
    ) x JOIN matches m ON m.match_id=x.match_id
    GROUP BY m.season ORDER BY m.season"""):
    print(f"  موسم {r['s']}: {r['n']}")

print("\n=== إجمالي الأسماء بموسم 2022 ===")
tot = conn.execute("""SELECT COUNT(DISTINCT g.player_en) FROM goals g
    JOIN matches m ON m.match_id=g.match_id WHERE m.season=2022""").fetchone()[0]
blank = conn.execute("""SELECT COUNT(DISTINCT g.player_en) FROM goals g
    JOIN matches m ON m.match_id=g.match_id WHERE m.season=2022
    AND (g.player_ar IS NULL OR g.player_ar='')""").fetchone()[0]
print(f"  هدّافون 2022: {tot}   منهم غير مترجَم: {blank}")

print("\n=== حجم players_ar.csv ===")
import csv
from config import BASE_DIR
rows = list(csv.DictReader(open(BASE_DIR/'players_ar.csv', encoding='utf-8-sig')))
print(f"  صفوف: {len(rows)}  مترجَم: {sum(1 for r in rows if (r.get('player_ar') or '').strip())}")
