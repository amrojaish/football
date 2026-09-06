#!/usr/bin/env python3
"""
كشف الأسماء التالفة المتبقية بالديتابيس
==========================================
`fix_names.py` نظّف `goals` — لكن الأسماء التالفة قد تبقى
في `lineup_players` · `events` · `player_stats`، فيولّد
`make_players.py` صفحات يتيمة لها (0-saad-al-salouli.html).

⚠️ **يفحص كل أعمدة الأسماء الفعلية بكل جدول** (6 سبتمبر —
   كان يفحص `player_en` فقط بأربعة جداول، فيغفل `player_ar`/
   `assist_en`/`coach_en`/`coach_ar` كلياً؛ اكتُشف بمقارنة
   مخرجاته بـ`_archive/fix_names.py --check`، راجع بند مفتوح
   بالـREADME). القائمة أدناه **مطابقة لـ`TARGETS` بـ
   `_archive/fix_names.py` عمداً** — لا استيراد من `_archive/`
   (لا اعتماد حي على سكربت مؤرشَف)، لكن أي تعديل هناك يجب أن
   يُنسَخ هنا يدوياً.
"""
import sqlite3, sys, re
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
DIRTY = re.compile(r'^\s|\s$|^\d|\d$|\s{2,}')

# ⚠️ طابِق TARGETS بـ_archive/fix_names.py يدوياً عند أي تعديل هناك
TARGETS = {
    "goals": ["player_en", "player_ar", "assist_en"],
    "lineup_players": ["player_en", "player_ar"],
    "player_stats": ["player_en", "player_ar"],
    "events": ["player_en", "player_ar", "assist_en"],
    "lineups": ["coach_en", "coach_ar"],
}

total = 0
for t, cols in TARGETS.items():
    try:
        have = {c[1] for c in conn.execute(f"PRAGMA table_info({t})")}
    except sqlite3.OperationalError:
        continue
    for col in [c for c in cols if c in have]:
        rows = conn.execute(
            f"SELECT DISTINCT {col} FROM {t} WHERE {col} != ''"
        ).fetchall()
        bad = [r[0] for r in rows if DIRTY.search(r[0])]
        print(f"\n=== {t}.{col} — تالف: {len(bad)} من {len(rows)} ===")
        for n in bad[:12]:
            print(f"    {n!r}")
        total += len(bad)

print(f"\n{'=' * 52}")
print(f"  إجمالي القيم التالفة: {total}")
if total:
    print("  شغّل: python _archive/fix_names.py --check")
print('=' * 52)
