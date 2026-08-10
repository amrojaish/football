#!/usr/bin/env python3
"""
إنشاء جدول الأحداث
====================
جدول جديد لتخزين البطاقات والتبديلات وبقية أحداث المباراة.

ليش منفصل عن جدول goals:
جدول goals مخصص للأهداف وله منطق تنظيف خاص (fix_goals.py).
خلطه بالبطاقات كان بيعقّد كل استعلامات الهدافين.

بيشتغل مرة وحدة. إعادة تشغيله آمنة — ما بيمسح شي.

التشغيل:
    python add_events_table.py
"""

import sqlite3
from config import DB_FILE


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id    INTEGER,
            team_id     INTEGER,
            minute      INTEGER,
            type        TEXT,
            detail      TEXT,
            player_en   TEXT,
            player_ar   TEXT,
            assist_en   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_match
            ON events(match_id);
        CREATE INDEX IF NOT EXISTS idx_events_team
            ON events(team_id);
    """)
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    print(f"\n{'=' * 55}")
    print(f"  جدول events جاهز — فيه {n} سجل")
    print(f"{'=' * 55}")
    print("""
  الأعمدة:
    type      = Card / subst / Var
    detail    = Yellow Card / Red Card / Substitution 1 ...
    player_en = اللاعب (أو الداخل في التبديل)
    assist_en = الخارج في التبديل
    player_ar = فارغ — طبقة الترجمة لاحقاً

  الخطوة الجاية: تعديل fetch_matches2.py ليخزّن الأحداث
    """)

    conn.close()


if __name__ == "__main__":
    main()
