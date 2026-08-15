#!/usr/bin/env python3
"""
تحليل نطاق الترجمة
====================
بيوري بالضبط:
  - كم اسم مخزّن بكل جدول
  - كم اسم **يظهر فعلياً بالموقع**
  - كم منهم مترجم

الفرق بين الرقمين هو الفرق بين شغل يومين وشغل نصف ساعة.

التشغيل:
    python translation_scope.py
"""

import sqlite3
import sys
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row


def has_table(name):
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


print(f"\n{'#' * 62}")
print("#  نطاق الترجمة")
print(f"{'#' * 62}")

# ---------------------------------------------------------------
# 1. الهدافون — اللي بيظهروا فعلاً بالموقع
# ---------------------------------------------------------------
print(f"\n{'=' * 62}")
print("  1) الهدافون")
print(f"{'=' * 62}")

total_scorers = conn.execute("""
    SELECT COUNT(DISTINCT player_en) FROM goals WHERE player_en != ''
""").fetchone()[0]

translated = conn.execute("""
    SELECT COUNT(DISTINCT player_en) FROM goals
    WHERE player_en != '' AND player_ar IS NOT NULL AND player_ar != ''
""").fetchone()[0]

print(f"\n  إجمالي الهدافين بالـDB : {total_scorers}")
print(f"  مترجَم                 : {translated}")

# اللي بيظهروا: أعلى 10 لكل (دوري، موسم) + أعلى 12 لكل نادٍ
visible = set()

combos = conn.execute("""
    SELECT DISTINCT league_code, season FROM matches
""").fetchall()

for c in combos:
    for r in conn.execute("""
        SELECT g.player_en FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en != '' AND m.league_code = ? AND m.season = ?
        GROUP BY g.player_en ORDER BY COUNT(*) DESC LIMIT 10
    """, (c["league_code"], c["season"])):
        visible.add(r["player_en"])

teams = conn.execute("SELECT team_id FROM teams").fetchall()
for t in teams:
    for c in combos:
        for r in conn.execute("""
            SELECT g.player_en FROM goals g
            JOIN matches m ON m.match_id = g.match_id
            WHERE g.player_en != '' AND g.team_id = ?
              AND m.league_code = ? AND m.season = ?
            GROUP BY g.player_en ORDER BY COUNT(*) DESC LIMIT 12
        """, (t["team_id"], c["league_code"], c["season"])):
            visible.add(r["player_en"])

print(f"\n  ⭐ يظهرون فعلياً بالموقع : {len(visible)}")
print(f"     (قوائم الهدافين: 10 لكل دوري/موسم + 12 لكل نادٍ)")

# التوزيع حسب الدوري
print(f"\n  التوزيع حسب الدوري:")
for code in LEAGUES:
    n = conn.execute("""
        SELECT COUNT(DISTINCT g.player_en) FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en != '' AND m.league_code = ?
    """, (code,)).fetchone()[0]
    print(f"      {LEAGUES[code]['name_ar']:<18} {n}")

# ---------------------------------------------------------------
# 2. لاعبو التشكيلات وإحصائيات اللاعبين
# ---------------------------------------------------------------
print(f"\n{'=' * 62}")
print("  2) لاعبو التشكيلات والإحصائيات")
print(f"{'=' * 62}")

if has_table("player_stats"):
    n_ps = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM player_stats").fetchone()[0]
    print(f"\n  لاعبون في player_stats  : {n_ps}")

    # اللي لعبوا فعلاً (مش احتياط دائم)
    n_real = conn.execute("""
        SELECT COUNT(DISTINCT player_id) FROM player_stats
        WHERE minutes IS NOT NULL AND minutes > 0
    """).fetchone()[0]
    print(f"  منهم لعبوا دقيقة فأكثر  : {n_real}")

    n_500 = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT player_id FROM player_stats
            GROUP BY player_id HAVING SUM(COALESCE(minutes,0)) >= 500
        )
    """).fetchone()[0]
    print(f"  ⭐ لعبوا 500 دقيقة فأكثر : {n_500}")
else:
    print("\n  جدول player_stats غير موجود")

if has_table("lineup_players"):
    n_lp = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM lineup_players"
    ).fetchone()[0]
    print(f"\n  لاعبون في lineup_players: {n_lp}")

# ---------------------------------------------------------------
# 3. المدربون
# ---------------------------------------------------------------
print(f"\n{'=' * 62}")
print("  3) المدربون")
print(f"{'=' * 62}")

if has_table("lineups"):
    n_c = conn.execute("""
        SELECT COUNT(DISTINCT coach_en) FROM lineups
        WHERE coach_en != ''
    """).fetchone()[0]
    print(f"\n  مدربون مختلفون: {n_c}")
else:
    print("\n  جدول lineups غير موجود")

# ---------------------------------------------------------------
# 4. مشكلة player_id المفقود بجدول goals
# ---------------------------------------------------------------
print(f"\n{'=' * 62}")
print("  4) الربط بين goals و player_stats")
print(f"{'=' * 62}")

if has_table("player_stats"):
    matched = conn.execute("""
        SELECT COUNT(DISTINCT g.player_en) FROM goals g
        WHERE g.player_en != '' AND EXISTS (
            SELECT 1 FROM player_stats p
            WHERE p.player_en = g.player_en
        )
    """).fetchone()[0]
    print(f"\n  أسماء goals لها مطابق نصي بـplayer_stats: "
          f"{matched} من {total_scorers}")
    print("  (الباقي أردني/عراقي — لا توجد لهم إحصائيات لاعبين)")

# ---------------------------------------------------------------
# 5. الخلاصة
# ---------------------------------------------------------------
print(f"\n{'#' * 62}")
print("#  الخلاصة")
print(f"{'#' * 62}")
print(f"""
  الحد الأدنى لتغطية كل ما يُعرض اليوم:
      {len(visible)} اسم هدّاف

  للتوسع لاحقاً (عند عرض التشكيلات):
      لاعبو السعودي بـ500 دقيقة فأكثر

  ⚠️ الأسماء غير المؤكدة تُترك فارغة — الكود يرتد للإنجليزي.
""")

conn.close()
