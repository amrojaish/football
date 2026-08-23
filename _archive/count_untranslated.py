import sqlite3

conn = sqlite3.connect('football.db')
cur = conn.cursor()
cur.execute("""
    SELECT COUNT(DISTINCT player_en) FROM (
        SELECT player_en, player_ar FROM goals
        UNION
        SELECT player_en, player_ar FROM lineup_players
    ) WHERE (player_ar IS NULL OR player_ar='') AND player_en != ''
""")
print('غير مترجم:', cur.fetchone()[0])
