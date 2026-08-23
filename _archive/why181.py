"""
لماذا ارتفع غير المترجَم من 81 إلى 181؟
==========================================
ثلاثة احتمالات:
  أ) الأتمتة سحبت مباريات جديدة              -> طبيعي
  ب) ترجمات ضاعت من الديتابيس                 -> خطير
  ج) players_ar.csv فقد صفوفاً                -> خطير
"""
import sqlite3, csv, sys
from collections import Counter
from config import DB_FILE, BASE_DIR

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

# 1) حالة players_ar.csv
p = BASE_DIR / "players_ar.csv"
rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
filled = [r for r in rows if (r.get("player_ar") or "").strip()]
print(f"\n=== players_ar.csv ===")
print(f"  صفوف: {len(rows)}   مترجَم: {len(filled)}")

# 2) حالة الديتابيس
known = set()
for t in ("goals", "lineup_players", "player_stats", "events"):
    for r in conn.execute(
            f"SELECT DISTINCT player_en FROM {t} "
            f"WHERE player_ar IS NOT NULL AND player_ar != ''"):
        known.add(r[0])
print(f"\n=== الديتابيس ===")
print(f"  أسماء مترجَمة فعلياً: {len(known)}")

# 3) هل ضاعت ترجمات؟ (بالملف ومش بالديتابيس)
csv_tr = {r["player_en"].strip() for r in filled}
lost = csv_tr - known
print(f"\n=== ترجمات بالملف ولم تصل الديتابيس: {len(lost)} ===")
for x in sorted(lost)[:15]:
    print("   ", x)
if len(lost) > 15:
    print(f"    ... و{len(lost)-15} غيرها")
print("  (رقم كبير = شغّل apply_players_ar.py)")

# 4) غير المترجَم — حسب تاريخ أحدث مباراة
print("\n=== غير المترجَم — حسب شهر أحدث مباراة ===")
rows2 = conn.execute("""
    SELECT x.player_en, MAX(DATE(m.date)) d
    FROM (
        SELECT player_en, match_id FROM goals
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM lineup_players
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
        UNION ALL
        SELECT player_en, match_id FROM events
          WHERE (player_ar IS NULL OR player_ar='') AND player_en!=''
    ) x JOIN matches m ON m.match_id = x.match_id
    GROUP BY x.player_en
""").fetchall()
c = Counter((r["d"] or "?")[:7] for r in rows2)
for k, v in sorted(c.items(), reverse=True)[:8]:
    print(f"  {k}: {v}")

# 5) هل هي أسماء موجودة بالملف أصلاً؟
blank_names = {r["player_en"] for r in rows2}
in_csv_filled = blank_names & csv_tr
print(f"\n=== غير مترجَم بالديتابيس لكنه مترجَم بالملف: {len(in_csv_filled)} ===")
for x in sorted(in_csv_filled)[:10]:
    print("   ", x)
print("  (رقم كبير = الترجمة موجودة، ينقص التطبيق فقط)")
