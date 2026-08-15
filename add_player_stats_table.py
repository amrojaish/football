#!/usr/bin/env python3
"""
إنشاء جدول إحصائيات اللاعبين
===============================
صف لكل لاعب في كل مباراة: التقييم، الدقائق، التسديدات،
التمريرات، المراوغات، الالتحامات...

هذا أضخم جدول بالمشروع — ~18,000 سجل للسعودي وحده.

بيشتغل مرة وحدة. إعادة تشغيله آمنة.

التشغيل:
    python add_player_stats_table.py
"""

import sqlite3
import sys
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS player_stats (
            match_id        INTEGER,
            team_id         INTEGER,
            player_id       INTEGER,
            player_en       TEXT,
            player_ar       TEXT,
            minutes         INTEGER,
            rating          REAL,
            captain         INTEGER,
            substitute      INTEGER,
            pos             TEXT,
            shots_total     INTEGER,
            shots_on        INTEGER,
            goals           INTEGER,
            conceded        INTEGER,
            assists         INTEGER,
            saves           INTEGER,
            passes_total    INTEGER,
            passes_key      INTEGER,
            passes_pct      INTEGER,
            tackles         INTEGER,
            blocks          INTEGER,
            interceptions   INTEGER,
            duels_total     INTEGER,
            duels_won       INTEGER,
            dribbles_try    INTEGER,
            dribbles_ok     INTEGER,
            fouls_drawn     INTEGER,
            fouls_made      INTEGER,
            yellow          INTEGER,
            red             INTEGER,
            pen_scored      INTEGER,
            pen_missed      INTEGER,
            pen_saved       INTEGER,
            PRIMARY KEY (match_id, player_id)
        );

        CREATE INDEX IF NOT EXISTS idx_ps_match
            ON player_stats(match_id);
        CREATE INDEX IF NOT EXISTS idx_ps_player
            ON player_stats(player_id);
        CREATE INDEX IF NOT EXISTS idx_ps_team
            ON player_stats(team_id);
    """)
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM player_stats").fetchone()[0]
    m = conn.execute(
        "SELECT COUNT(DISTINCT match_id) FROM player_stats").fetchone()[0]

    print(f"\n{'=' * 58}")
    print("  جدول player_stats جاهز")
    print(f"{'=' * 58}")
    print(f"  سجلات: {n}   |   مباريات مغطاة: {m}")
    print("""
  المفتاح (match_id, player_id) — صف لكل لاعب بكل مباراة.

  أهم الأعمدة:
    rating      = تقييم اللاعب (6.0 - 10.0)
    duels_won   = الالتحامات المكسوبة
    dribbles_ok = المراوغات الناجحة
    passes_key  = التمريرات المفتاحية

  player_ar فارغ — طبقة الترجمة لاحقاً، و player_id يربط
  اللاعب عبر كل المباريات فترجمة واحدة تكفي.

  الخطوة الجاية: python fetch_player_stats.py SAU --budget 5
    """)

    conn.close()


if __name__ == "__main__":
    main()
