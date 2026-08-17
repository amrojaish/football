#!/usr/bin/env python3
"""
إنشاء جدول إحصائيات المباريات
================================
جدول لتخزين إحصائيات كل فريق في كل مباراة:
الاستحواذ، التسديدات، الركنيات، التمريرات، الأخطاء...

ليش منفصل عن goals و events:
هذه أرقام مُجمَّعة لكل فريق في المباراة (صف واحد لكل فريق)،
لا أحداث بدقائق. خلطها بالجداول الأخرى كان سيعقّد كل استعلام.

بيشتغل مرة وحدة. إعادة تشغيله آمنة — ما بيمسح شي.

التشغيل:
    python add_stats_table.py
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
        CREATE TABLE IF NOT EXISTS match_stats (
            match_id        INTEGER,
            team_id         INTEGER,
            possession      INTEGER,
            shots_total     INTEGER,
            shots_on        INTEGER,
            shots_off       INTEGER,
            shots_blocked   INTEGER,
            shots_inbox     INTEGER,
            shots_outbox    INTEGER,
            corners         INTEGER,
            offsides        INTEGER,
            fouls           INTEGER,
            yellow          INTEGER,
            red             INTEGER,
            saves           INTEGER,
            passes_total    INTEGER,
            passes_ok       INTEGER,
            passes_pct      INTEGER,
            xg              REAL,
            PRIMARY KEY (match_id, team_id)
        );
        CREATE INDEX IF NOT EXISTS idx_stats_match
            ON match_stats(match_id);
        CREATE INDEX IF NOT EXISTS idx_stats_team
            ON match_stats(team_id);
    """)
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM match_stats").fetchone()[0]
    m = conn.execute(
        "SELECT COUNT(DISTINCT match_id) FROM match_stats").fetchone()[0]

    print(f"\n{'=' * 58}")
    print(f"  جدول match_stats جاهز")
    print(f"{'=' * 58}")
    print(f"  سجلات: {n}   |   مباريات مغطاة: {m}")
    print("""
  المفتاح الأساسي (match_id, team_id) — صف لكل فريق بكل مباراة.
  إعادة السحب تستبدل ولا تكرّر.

  الخطوة الجاية: python fetch_stats.py --check
    """)

    conn.close()


if __name__ == "__main__":
    main()
