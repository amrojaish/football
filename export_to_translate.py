"""
يصدّر كل الأسماء غير المترجَمة لملف واحد جاهز للترجمة اليدوية.

يقرأ من: goals + lineup_players + events  (كل مكان يعرض الاسم)
يكتب:    to_translate.csv

الأعمدة:
    league        الدوري
    team_ar       النادي (لتسهيل البحث بصفحة النادي)
    appearances   عدد الظهور (الأكثر ظهوراً أهم)
    player_en     الاسم المختصر كما بالداتا  <- المفتاح، لا تعدّله
    full_name_en  الاسم الكامل عبر جسر player_id (يساعد بالبحث)
    player_ar     <- اكتب الترجمة هنا فقط

مرتّب: بالنادي ثم بعدد الظهور (الأكثر ظهوراً أولاً بكل نادٍ)
"""

import sqlite3
import csv
from collections import defaultdict

DB = 'football.db'
OUT = 'to_translate.csv'

conn = sqlite3.connect(DB)
cur = conn.cursor()


def has_table(name):
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


# الأسماء الفارغة من كل الجداول التي تعرض الاسم
tables = ['goals', 'lineup_players']
if has_table('events'):
    tables.append('events')

blank = {}          # player_en -> {'team_id':.., 'count':..}
counts = defaultdict(int)
team_of = {}

for t in tables:
    cur.execute(f"""
        SELECT player_en, team_id, COUNT(*)
        FROM {t}
        WHERE (player_ar IS NULL OR player_ar = '')
          AND player_en IS NOT NULL AND player_en != ''
        GROUP BY player_en, team_id
    """)
    for en, tid, n in cur.fetchall():
        counts[en] += n
        if en not in team_of:
            team_of[en] = tid

# الاسم الكامل عبر جسر player_id
full = defaultdict(set)
if has_table('player_stats'):
    cur.execute("""
        SELECT DISTINCT lp.player_en, ps.player_en
        FROM lineup_players lp
        JOIN player_stats ps ON lp.player_id = ps.player_id
        WHERE lp.player_en IS NOT NULL AND lp.player_en != ''
          AND ps.player_en IS NOT NULL AND ps.player_en != ''
    """)
    for short, fl in cur.fetchall():
        if short != fl:
            full[short].add(fl)

# بيانات الأندية
cur.execute("SELECT team_id, short_name_ar, league_code FROM teams")
teams = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

rows = []
for en in counts:
    tid = team_of.get(en)
    team_ar, league = teams.get(tid, ('', ''))
    fulls = sorted(full.get(en, []))
    rows.append({
        'league': league,
        'team_ar': team_ar,
        'appearances': counts[en],
        'player_en': en,
        'full_name_en': ' | '.join(fulls),
        'player_ar': '',
    })

rows.sort(key=lambda r: (r['league'], r['team_ar'], -r['appearances']))

with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=[
        'league', 'team_ar', 'appearances',
        'player_en', 'full_name_en', 'player_ar'])
    w.writeheader()
    w.writerows(rows)

conn.close()

print(f"الجداول المفحوصة : {', '.join(tables)}")
print(f"أسماء غير مترجَمة : {len(rows)}")
print(f"منها باسم كامل    : {sum(1 for r in rows if r['full_name_en'])}")
print()
by_league = defaultdict(int)
for r in rows:
    by_league[r['league'] or '?'] += 1
for lg, n in sorted(by_league.items(), key=lambda x: -x[1]):
    print(f"  {lg}: {n}")
print()
print(f"تم إنشاء {OUT}")
