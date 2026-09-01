"""
تحقق أن مفاتيح الترجمة موجودة بالداتا حرفياً (درس 21)
=========================================================
`apply_players_ar.py` يطابق `player_en` نصاً كاملاً. أي فرق —
شرطة، حرف مركّب، إملاء — يجعل الترجمة بلا هدف **بصمت**.
"""
import sqlite3, csv, sys, unicodedata, difflib
from config import DB_FILE, BASE_DIR
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
db = set()
for t in ("goals", "lineup_players", "events", "player_stats"):
    try:
        for (n,) in conn.execute(
                f"SELECT DISTINCT player_en FROM {t} WHERE player_en != ''"):
            db.add(n)
    except Exception:
        pass

names = [r['player_en'].strip() for r in
         csv.DictReader(open(BASE_DIR/'to_translate_filled.csv',
                             encoding='utf-8-sig'))]
missing = [n for n in names if n not in db]
print(f"\nبالملف: {len(names)} | مطابق: {len(names)-len(missing)} "
      f"| غير مطابق: {len(missing)}")

def norm(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)) \
             .lower().replace('-', ' ').replace("'", '')

idx = {}
for n in db:
    idx.setdefault(norm(n), []).append(n)

if missing:
    print("\nالمقترح لكل غير مطابق:")
    for n in sorted(missing):
        k = norm(n)
        if k in idx:
            print(f"  🟢 {n:28} -> {idx[k][0]}")
        else:
            c = difflib.get_close_matches(n, db, n=1, cutoff=0.82)
            print(f"  {'🟡' if c else '🔴'} {n:28} -> {c[0] if c else '(لا نظير)'}")
else:
    print("\n✅ كل المفاتيح مطابقة — الدفعة ستُطبَّق كاملة")
