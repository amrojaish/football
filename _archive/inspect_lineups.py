#!/usr/bin/env python3
"""
فحص بنية جداول التشكيلات وتقييمات اللاعبين
=============================================
قبل كتابة كود العرض، لازم نعرف بالضبط:
    - أعمدة lineups و lineup_players و player_stats
    - شكل الداتا الفعلي (عيّنة من مباراة حقيقية)
    - التغطية: أي دوري وأي موسم فيه تشكيلات

⚠️ للقراءة فقط.

التشغيل:
    python inspect_lineups.py
"""

import sqlite3

DB = "football.db"
TABLES = ["lineups", "lineup_players", "player_stats"]


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # ── 1. الأعمدة ────────────────────────────────────
    for t in TABLES:
        print()
        print("=" * 58)
        print(f"  جدول {t}")
        print("=" * 58)
        try:
            cols = list(conn.execute(f"PRAGMA table_info({t})"))
        except sqlite3.Error as e:
            print(f"  ❌ {e}")
            continue

        if not cols:
            print("  الجدول غير موجود")
            continue

        for c in cols:
            print(f"    {c[1]:<22} {c[2]}")

        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"\n  عدد السجلات: {n:,}")

    # ── 2. التغطية حسب الدوري والموسم ─────────────────
    print()
    print("=" * 58)
    print("  التغطية — مباريات فيها تشكيلات")
    print("=" * 58)
    try:
        q = """
            SELECT m.league_code, m.season,
                   COUNT(DISTINCT l.match_id) AS n
            FROM lineups l
            JOIN matches m ON m.match_id = l.match_id
            GROUP BY m.league_code, m.season
            ORDER BY m.league_code, m.season
        """
        for r in conn.execute(q):
            print(f"    {r['league_code']}  {r['season']}   "
                  f"{r['n']} مباراة")
    except sqlite3.Error as e:
        print(f"  ❌ {e}")

    # ── 3. عيّنة من مباراة واحدة ──────────────────────
    print()
    print("=" * 58)
    print("  عيّنة — مباراة سعودية واحدة")
    print("=" * 58)

    row = conn.execute("""
        SELECT l.match_id FROM lineups l
        JOIN matches m ON m.match_id = l.match_id
        WHERE m.league_code = 'SAU' AND m.season = 2025
        LIMIT 1
    """).fetchone()

    if not row:
        print("  ما لقيت مباراة")
        conn.close()
        return

    mid = row["match_id"]
    print(f"  match_id = {mid}\n")

    print("  --- lineups ---")
    for r in conn.execute(
            "SELECT * FROM lineups WHERE match_id = ?", (mid,)):
        print(f"    {dict(r)}")

    print("\n  --- lineup_players (أول 6) ---")
    for r in conn.execute("""
            SELECT * FROM lineup_players WHERE match_id = ?
            LIMIT 6""", (mid,)):
        print(f"    {dict(r)}")

    print("\n  --- player_stats (أول 4) ---")
    try:
        for r in conn.execute("""
                SELECT * FROM player_stats WHERE match_id = ?
                LIMIT 4""", (mid,)):
            print(f"    {dict(r)}")
    except sqlite3.Error as e:
        print(f"    ❌ {e}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
