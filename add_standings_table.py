#!/usr/bin/env python3
"""
إنشاء جدول الترتيب الرسمي
============================
جدول لتخزين ترتيب المزوّد **كما هو** — مرجع للمقارنة مع
حسابنا المبني على المباريات.

ليش مهم:
كل التحقق الخارجي حتى الآن كان يدوياً — صور من التطبيقات
ومقارنة بصرية. هذا الجدول يجعله **فحصاً آلياً**: أمر واحد
يقارن كل الجداول ويكشف الفروق فوراً.

⚠️ ترتيب المزوّد **ليس بالضرورة صحيحاً** — اكتشفنا أخطاءه
   مراراً (درس 13). لكنه مرجع ثالث مفيد بجانب حسابنا
   والمصادر الرسمية.

بيشتغل مرة وحدة. إعادة تشغيله آمنة.

التشغيل:
    python add_standings_table.py
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
        CREATE TABLE IF NOT EXISTS api_standings (
            league_code TEXT,
            season      INTEGER,
            team_id     INTEGER,
            rank        INTEGER,
            played      INTEGER,
            wins        INTEGER,
            draws       INTEGER,
            losses      INTEGER,
            goals_for   INTEGER,
            goals_against INTEGER,
            points      INTEGER,
            form        TEXT,
            description TEXT,
            fetched_at  TEXT,
            PRIMARY KEY (league_code, season, team_id)
        );

        CREATE INDEX IF NOT EXISTS idx_std_ls
            ON api_standings(league_code, season);
    """)
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM api_standings").fetchone()[0]
    c = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT league_code, season FROM api_standings
        )
    """).fetchone()[0]

    print(f"\n{'=' * 58}")
    print("  جدول api_standings جاهز")
    print(f"{'=' * 58}")
    print(f"  سجلات: {n}   |   تركيبات دوري/موسم: {c}")
    print("""
  الأعمدة:
    rank        = ترتيب المزوّد
    form        = آخر 5 نتائج (WWDLW)
    description = تأهل/هبوط حسب المزوّد
    fetched_at  = وقت السحب — مهم لأن الترتيب يتغيّر

  الخطوة الجاية: python fetch_standings.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
