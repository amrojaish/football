"""
لماذا لم تُطبَّق 45 ترجمة؟ — مطابقة الاسم حرفية
================================================
`apply_players_ar.py` يطابق `player_en` نصياً. أي فرق — شرطة
بدل مسافة، حرف مختلف، ترميز يونيكود — يجعل الترجمة بلا هدف.
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

names = {}
for r in csv.DictReader(open(BASE_DIR/'to_translate_filled.csv',
                             encoding='utf-8-sig')):
    en = (r.get('player_en') or '').strip()
    ar = (r.get('player_ar') or '').strip()
    if en and ar: names[en] = ar

missing = [en for en in names if en not in db]
print(f"\nبالملف: {len(names)} | غير موجود بالداتا: {len(missing)}\n")

def norm(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()

db_norm = {}
for n in db:
    db_norm.setdefault(norm(n).replace('-', ' ').replace("'", ''), []).append(n)

exact_unicode, close, none_ = [], [], []
for en in sorted(missing):
    key = norm(en).replace('-', ' ').replace("'", '')
    if key in db_norm:
        exact_unicode.append((en, db_norm[key][0]))
    else:
        m = difflib.get_close_matches(en, db, n=1, cutoff=0.82)
        (close if m else none_).append((en, m[0] if m else None))

print(f"🟢 مطابق بعد تجاهل الترميز/الشرطات: {len(exact_unicode)}")
for a, b in exact_unicode:
    print(f"    {a:28} == {b}")
print(f"\n🟡 قريب جداً (فرق إملائي): {len(close)}")
for a, b in close:
    print(f"    {a:28} ≈  {b}")
print(f"\n🔴 لا نظير بالداتا: {len(none_)}")
for a, _ in none_:
    print(f"    {a}")
