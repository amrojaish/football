import sqlite3

conn = sqlite3.connect('football.db')
cur = conn.cursor()

cur.execute("""
    SELECT t.league_code, COUNT(DISTINCT x.player_en)
    FROM (
        SELECT g.player_en, g.player_ar, g.team_id FROM goals g
        UNION
        SELECT lp.player_en, lp.player_ar, lp.team_id FROM lineup_players lp
    ) x
    JOIN teams t ON x.team_id = t.team_id
    WHERE (x.player_ar IS NULL OR x.player_ar = '') AND x.player_en != ''
    GROUP BY t.league_code
    ORDER BY COUNT(DISTINCT x.player_en) DESC
""")

print('غير مترجم حسب الدوري:')
total = 0
for league, n in cur.fetchall():
    print(f'  {league}: {n}')
    total += n
print(f'  المجموع: {total}')
