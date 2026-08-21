#!/usr/bin/env python3
"""
تطبيق أسماء اللاعبين العربية
===============================
بيقرأ players_ar.csv وبيعبّي عمود player_ar بجداول:
    goals
    lineup_players
    player_stats

⚠️ المطابقة **نصية** على player_en لأن جدول goals لا يخزّن
   player_id (خطأ بنيوي مبكر — درس 26). لو كتب المزوّد الاسم
   بصيغتين مختلفتين، يُعامَلان كلاعبَين.

الأسماء الفارغة تُتخطّى — الكود يرتد للإنجليزي.

صفر طلبات API.

التشغيل:
    python apply_players_ar.py --check    <- عرض بس
    python apply_players_ar.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

SOURCE = BASE_DIR / "players_ar.csv"
CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def has_table(conn, name):
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not SOURCE.exists():
        print(f"ما لقيت {SOURCE.name}")
        print("شغّل: python export_players_ar.py")
        return

    names = {}
    with open(SOURCE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            en = (r.get("player_en") or "").strip()
            ar = (r.get("player_ar") or "").strip()
            if en and ar:
                names[en] = ar

    print(f"\n{'=' * 58}")
    print(f"  أسماء مترجَمة بالملف: {len(names)}")
    print(f"{'=' * 58}")

    if not names:
        print("\n  ما في أسماء مترجمة — عبّي عمود player_ar أول\n")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    targets = ["goals"]
    for t in ("lineup_players", "player_stats", "events"):
        if has_table(conn, t):
            targets.append(t)

    total = 0

    for table in targets:
        before = conn.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """).fetchone()[0]

        will = 0
        for en, ar in names.items():
            n = conn.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE player_en = ?
                  AND (player_ar IS NULL OR player_ar = '' OR player_ar != ?)
            """, (en, ar)).fetchone()[0]
            will += n

            if not CHECK_ONLY and n:
                conn.execute(f"""
                    UPDATE {table} SET player_ar = ?
                    WHERE player_en = ?
                """, (ar, en))

        if not CHECK_ONLY:
            conn.commit()

        after = conn.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """).fetchone()[0]

        print(f"\n  {table}")
        print(f"      سجلات متأثرة : {will}")
        if not CHECK_ONLY:
            print(f"      قبل → بعد     : {before} → {after}")
        total += will

    # الأسماء اللي ما لقت مطابق
    missing = []
    for en in names:
        n = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE player_en = ?",
            (en,)).fetchone()[0]
        if n == 0:
            missing.append(en)

    conn.close()

    print(f"\n{'=' * 58}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انكتب شي")
    print(f"  إجمالي السجلات المتأثرة: {total}")
    print(f"{'=' * 58}")

    if missing:
        print(f"\n  ⚠️ {len(missing)} اسم بالملف ما لقى مطابق بجدول goals:")
        for en in missing[:10]:
            print(f"      {en}")
        if len(missing) > 10:
            print(f"      ... و{len(missing) - 10} غيرهم")
        print("  (تأكد من التطابق الحرفي مع اسم المزوّد)")

    if total and not CHECK_ONLY:
        print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
        """)


if __name__ == "__main__":
    main()
