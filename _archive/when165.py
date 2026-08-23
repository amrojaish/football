"""
متى دخلت مباريات أغسطس 2026؟
"""
import sqlite3, sys, subprocess
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row

print("\n=== مباريات أغسطس 2026 وتشكيلاتها ===")
for r in conn.execute("""
    SELECT m.league_code lg, DATE(m.date) d, COUNT(DISTINCT m.match_id) n,
           SUM(CASE WHEN lp.match_id IS NOT NULL THEN 1 ELSE 0 END) lps
    FROM matches m
    LEFT JOIN lineup_players lp ON lp.match_id = m.match_id
    WHERE DATE(m.date) >= '2026-08-01'
    GROUP BY m.league_code, DATE(m.date) ORDER BY d"""):
    print(f"  {r['d']} {r['lg']}  مباريات={r['n']}  سجلات تشكيلات={r['lps']}")

print("\n=== أحدث سجل تشكيلة أُدخل (بالمعرّف التسلسلي) ===")
for r in conn.execute("""
    SELECT lp.rowid rid, lp.player_en, m.date, m.league_code
    FROM lineup_players lp JOIN matches m ON m.match_id=lp.match_id
    ORDER BY lp.rowid DESC LIMIT 5"""):
    print(f"  rowid={r['rid']}  {r['date'][:10]} {r['league_code']}  {r['player_en']}")

print("\n=== آخر تعديلات الديتابيس حسب Git ===")
try:
    out = subprocess.run(["git","log","-6","--format=%h %ad %s","--date=format:%m-%d %H:%M","--","football.db"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    print(out or "  (لا سجل)")
except Exception as e:
    print("  تعذّر:", e)
