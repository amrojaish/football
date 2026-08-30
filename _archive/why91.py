"""لماذا 91 لا 35؟ — بيانات جديدة أم ترجمات لم تُطبَّق؟"""
import sqlite3, csv, sys
from collections import Counter
from config import DB_FILE, BASE_DIR
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row

# 1) هل الدفعة طُبِّقت فعلاً؟
names = {}
for r in csv.DictReader(open(BASE_DIR/'to_translate_filled.csv',
                             encoding='utf-8-sig')):
    en = (r.get('player_en') or '').strip()
    ar = (r.get('player_ar') or '').strip()
    if en and ar: names[en] = ar

applied = missing = 0
for en in names:
    hit = conn.execute("""
        SELECT 1 FROM goals WHERE player_en=? AND player_ar!=''
        UNION SELECT 1 FROM lineup_players WHERE player_en=? AND player_ar!=''
        UNION SELECT 1 FROM events WHERE player_en=? AND player_ar!=''
        LIMIT 1""", (en,en,en)).fetchone()
    if hit: applied += 1
    else: missing += 1
print(f"\n=== الدفعة ({len(names)} اسماً) ===")
print(f"  مطبَّق : {applied}")
print(f"  غير مطبَّق: {missing}   <- لو كبير فالترجمة لم تصل")

# 2) غير المترجَم الآن — حسب شهر أحدث مباراة
print("\n=== غير المترجَم — حسب شهر أحدث مباراة ===")
rows = conn.execute("""
    SELECT x.player_en, MAX(DATE(m.date)) d FROM (
        SELECT player_en, match_id FROM goals
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM lineup_players
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM events
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
    ) x JOIN matches m ON m.match_id=x.match_id
    GROUP BY x.player_en""").fetchall()
c = Counter((r["d"] or "?")[:7] for r in rows)
for k,v in sorted(c.items(), reverse=True)[:6]:
    print(f"  {k}: {v}")

# 3) كم منها اختصارات تركناها عمداً؟
import re
AB = re.compile(r'^[A-Z]\.\s|\s[A-Z]\.$|^[A-Z]\.[A-Z]?\.')
ab = [r["player_en"] for r in rows if AB.search(r["player_en"])]
print(f"\n=== أسماء مختصرة (متروكة عمداً): {len(ab)} من {len(rows)} ===")
for x in ab[:10]: print("   ", x)
