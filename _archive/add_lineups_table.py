#!/usr/bin/env python3
"""
إنشاء جداول التشكيلات
========================
جدولان:
    lineups        — الخطة والمدرب لكل فريق بكل مباراة
    lineup_players — اللاعبون: أساسي/احتياط، الرقم، المركز

ليش جدولان:
الخطة والمدرب صف واحد لكل فريق، واللاعبون ~18 صف. دمجهما
كان سيكرّر الخطة 18 مرة.

بيشتغل مرة وحدة. إعادة تشغيله آمنة.

التشغيل:
    python add_lineups_table.py
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
        CREATE TABLE IF NOT EXISTS lineups (
            match_id    INTEGER,
            team_id     INTEGER,
            formation   TEXT,
            coach_en    TEXT,
            coach_ar    TEXT,
            PRIMARY KEY (match_id, team_id)
        );

        CREATE TABLE IF NOT EXISTS lineup_players (
            match_id    INTEGER,
            team_id     INTEGER,
            player_id   INTEGER,
            player_en   TEXT,
            player_ar   TEXT,
            number      INTEGER,
            pos         TEXT,
            grid        TEXT,
            starter     INTEGER,
            PRIMARY KEY (match_id, player_id)
        );

        CREATE INDEX IF NOT EXISTS idx_lp_match
            ON lineup_players(match_id);
        CREATE INDEX IF NOT EXISTS idx_lp_player
            ON lineup_players(player_id);
        CREATE INDEX IF NOT EXISTS idx_lp_team
            ON lineup_players(team_id);
    """)
    conn.commit()

    n1 = conn.execute("SELECT COUNT(*) FROM lineups").fetchone()[0]
    n2 = conn.execute("SELECT COUNT(*) FROM lineup_players").fetchone()[0]

    print(f"\n{'=' * 58}")
    print("  جداول التشكيلات جاهزة")
    print(f"{'=' * 58}")
    print(f"  lineups        : {n1} سجل")
    print(f"  lineup_players : {n2} سجل")
    print("""
  الأعمدة:
    formation  = 4-3-3
    pos        = G / D / M / F
    grid       = صف:عمود بالملعب (مفيد للرسم لاحقاً)
    starter    = 1 أساسي، 0 احتياط
    player_ar  = فارغ — طبقة الترجمة لاحقاً

  ⚠️ player_id من المزوّد — يربط اللاعب عبر المباريات والمواسم،
     وهذا يجعل ترجمة الاسم مرة واحدة كافية لكل ظهور له.

  الخطوة الجاية: python fetch_lineups.py --check
    """)

    conn.close()


if __name__ == "__main__":
    main()
