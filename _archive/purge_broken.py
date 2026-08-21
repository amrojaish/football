#!/usr/bin/env python3
"""
مسح الترجمات المعطوبة من الديتابيس
=====================================
`clean_and_list.py` نظّف 569 ترجمة معطوبة من `players_ar.csv`،
لكن `apply_players_ar.py` **لا يمسح** — يتخطى القيم الفارغة
بدل كتابتها (يفترض أن الفراغ يعني "لا ترجمة" لا "امسح").

فالنتيجة: الترجمات النصف-عربية ما زالت في الديتابيس ومنشورة:

    "Radhi ال العتيبي"  ·  "محمد ال Khabrani"

هذا السكربت يمسحها **مباشرة من الديتابيس** — أي `player_ar`
يحوي حرفاً لاتينياً يُفرَّغ، فيرتد الاسم للإنجليزي الكامل.

⚠️ نسخة احتياطية قبل أي كتابة.

⚠️ **الإنجليزي الكامل أفضل من النصف-عربي** — قاعدة المشروع
   منذ البداية: "الاسم المخمّن الخاطئ أسوأ من الإنجليزي".

التشغيل:
    python purge_broken.py --check
    python purge_broken.py
"""

import os
import shutil
import sqlite3
import sys

DB = "football.db"
CHECK = "--check" in sys.argv

TABLES = ["goals", "lineup_players", "player_stats", "events"]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def has_latin(s):
    return any("a" <= c.lower() <= "z" for c in (s or ""))


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 60)
    print("  فحص الترجمات المعطوبة بالديتابيس")
    print("=" * 60)

    plan = []
    total = 0

    for tbl in TABLES:
        try:
            cols = {c[1] for c in conn.execute(
                f"PRAGMA table_info({tbl})")}
        except sqlite3.Error:
            continue
        if "player_ar" not in cols:
            continue

        rows = list(conn.execute(f"""
            SELECT DISTINCT player_ar FROM {tbl}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """))

        bad = [r["player_ar"] for r in rows
               if has_latin(r["player_ar"])]

        if not bad:
            print(f"    {tbl:<18} نظيف ✅")
            continue

        n = conn.execute(f"""
            SELECT COUNT(*) FROM {tbl}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """).fetchone()[0]

        affected = 0
        for v in bad:
            affected += conn.execute(f"""
                SELECT COUNT(*) FROM {tbl} WHERE player_ar = ?
            """, (v,)).fetchone()[0]

        print(f"    {tbl:<18} {len(bad):>4} قيمة معطوبة  "
              f"({affected} سجل)")
        plan.append((tbl, bad, affected))
        total += affected

    if not plan:
        print("\n  ✅ الديتابيس نظيف — ما في شي للمسح\n")
        conn.close()
        return

    print()
    print("  عيّنة:")
    for tbl, bad, _ in plan[:1]:
        for v in bad[:8]:
            print(f"    {v}")

    print()
    print("=" * 60)
    print(f"  إجمالي السجلات المتأثرة: {total:,}")
    print("=" * 60)

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        conn.close()
        return

    conn.close()
    shutil.copy(DB, "football_before_purge.db")
    print("\n  نسخة احتياطية: football_before_purge.db")

    conn = sqlite3.connect(DB)
    changed = 0
    for tbl, bad, _ in plan:
        for v in bad:
            cur = conn.execute(f"""
                UPDATE {tbl} SET player_ar = ''
                WHERE player_ar = ?
            """, (v,))
            changed += cur.rowcount
    conn.commit()
    conn.close()

    print(f"  سجلات مُسِحت: {changed:,}")
    print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
      python make_players.py
      python make_search.py
    """)


if __name__ == "__main__":
    main()
