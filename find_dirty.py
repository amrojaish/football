#!/usr/bin/env python3
"""
كشف الأسماء التالفة المتبقية بالديتابيس
==========================================
`fix_names.py` نظّف `goals` — لكن الأسماء التالفة قد تبقى
في `lineup_players` · `events` · `player_stats`، فيولّد
`make_players.py` صفحات يتيمة لها (0-saad-al-salouli.html).
"""
import sqlite3, sys, re
from config import DB_FILE
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

conn = sqlite3.connect(DB_FILE)
DIRTY = re.compile(r'^\s|\s$|^\d|\d$|\s{2,}')

total = 0
for t in ("goals", "lineup_players", "events", "player_stats"):
    try:
        rows = conn.execute(
            f"SELECT DISTINCT player_en FROM {t} WHERE player_en != ''"
        ).fetchall()
    except sqlite3.OperationalError:
        continue
    bad = [r[0] for r in rows if DIRTY.search(r[0])]
    print(f"\n=== {t} — تالف: {len(bad)} من {len(rows)} ===")
    for n in bad[:12]:
        print(f"    {n!r}")
    total += len(bad)

print(f"\n{'=' * 52}")
print(f"  إجمالي القيم التالفة: {total}")
if total:
    print("  شغّل: python _archive/fix_names.py --check")
print('=' * 52)
