"""
يدمج to_translate_filled.csv في players_ar.csv

يختلف عن merge_players_ar.py:
    merge_players_ar.py يتخطى أي اسم غير موجود بالملف الرئيسي
    هذا يضيفه كصف جديد (أسماء events الحصرية غير موجودة أصلاً)

لا يمحو أي ترجمة موجودة. يعمل نسخة احتياطية.

    python merge_batch.py --check    <- عرض بس
    python merge_batch.py            <- تنفيذ
"""

import csv
import sys
import shutil
import re

MAIN = 'players_ar.csv'
BATCH = 'to_translate_filled.csv'
CHECK = '--check' in sys.argv

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

latin = re.compile(r'[A-Za-z]')

# الدفعة
batch = {}
skipped_bad = []
for r in csv.DictReader(open(BATCH, encoding='utf-8-sig')):
    en = (r.get('player_en') or '').strip()
    ar = (r.get('player_ar') or '').strip()
    if not en or not ar:
        continue
    if latin.search(ar):
        skipped_bad.append((en, ar))
        continue
    batch[en] = {
        'ar': ar,
        'league': (r.get('league') or '').strip(),
        'team_ar': (r.get('team_ar') or '').strip(),
    }

# الملف الرئيسي
with open(MAIN, encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames or [])
    rows = list(reader)

print()
print('=' * 58)
print(f'  ترجمات بالدفعة : {len(batch)}')
if skipped_bad:
    print(f'  مرفوض (تلوّث) : {len(skipped_bad)}')
print('=' * 58)

added = already = 0
seen = set()

for row in rows:
    en = (row.get('player_en') or '').strip()
    if en not in batch:
        continue
    seen.add(en)
    cur = (row.get('player_ar') or '').strip()
    new = batch[en]['ar']

    if cur == new:
        already += 1
        continue
    if cur:
        print(f'  تعارض {en}: موجود={cur} | جديد={new} — تُرك الموجود')
        already += 1
        continue

    if not CHECK:
        row['player_ar'] = new
    added += 1

# الأسماء غير الموجودة -> صفوف جديدة
missing = [en for en in batch if en not in seen]
new_rows = []
for en in missing:
    b = batch[en]
    nr = {k: '' for k in fields}
    if 'priority' in nr:
        nr['priority'] = 'E'      # حصري بـevents
    if 'goals' in nr:
        nr['goals'] = '0'
    if 'league' in nr:
        nr['league'] = b['league']
    if 'team_ar' in nr:
        nr['team_ar'] = b['team_ar']
    nr['player_en'] = en
    nr['player_ar'] = b['ar']
    new_rows.append(nr)

if not CHECK and (added or new_rows):
    shutil.copy(MAIN, 'players_ar_backup.csv')
    with open(MAIN, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows + new_rows)
    print()
    print('  نسخة احتياطية: players_ar_backup.csv')

print()
print('=' * 58)
if CHECK:
    print('  [وضع الفحص] — ما انكتب شي')
print(f'  عُبِّئ بصفوف موجودة : {added}')
print(f'  أُضيف كصفوف جديدة  : {len(new_rows)}   (priority = E)')
print(f'  كان موجوداً أصلاً  : {already}')
print(f'  المجموع            : {added + len(new_rows)}')
print('=' * 58)

if not CHECK and (added or new_rows):
    print("""
  الخطوة الجاية:
      python apply_players_ar.py --check
      python apply_players_ar.py
      python export_to_translate.py
    """)
