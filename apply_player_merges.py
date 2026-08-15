#!/usr/bin/env python3
"""
تطبيق دمج أسماء اللاعبين اليدوي
==================================
بيقرأ player_merges.csv وبيوحّد الصيغ المختلفة لنفس اللاعب.

الفرق عن merge_dupes.py:
    merge_dupes.py  → آلي، للفروق الشكلية فقط (تشكيل/نقاط)
    apply_player_merges.py → يدوي، للحالات اللي تحتاج قراراً بشرياً
                             (C. Ronaldo ←→ Cristiano Ronaldo)

⚠️ **الحالات المستبعدة عمداً** — لاعبون مختلفون رغم تشابه اللقب:
    Karrar Ali / Kosrat Ali
    Matheus Lucas / Moisés Lucas
    H. Ali / Hameed Ali / Hussein Ali
    A. Qasim / Abbas Qasim / Abdulrazzaq Qasim
    A. Khaled / Ahmad Khaled / Ali Khaled
    Hasan Abdulkareem / Hayder Abdulkareem
    Atheer Saleh / Ali Saleh
    Mohanad Ali / Mujtaba Ali
    Abdullah Al Salem / Ali Al Salem
    A. Fadhil Abbas / Alaa Abbas
    M. Taha / M. Abu Taha
    A. Abd Rabbo / A. Rabbo

بيعمل نسخة احتياطية قبل التعديل. إعادة التشغيل آمنة.

التشغيل:
    python apply_player_merges.py --check    <- عرض بس
    python apply_player_merges.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
import shutil
from config import DB_FILE, BASE_DIR

SOURCE = BASE_DIR / "player_merges.csv"
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
        return

    pairs = []
    skipped = 0
    with open(SOURCE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            old = (r.get("old_name") or "").strip()
            keep = (r.get("keep_name") or "").strip()
            conf = (r.get("confidence") or "").strip()
            if not old or not keep:
                continue
            if conf == "تخميني":
                skipped += 1
                continue
            pairs.append((old, keep, conf, (r.get("note") or "").strip()))

    if not pairs:
        print("ملف الدمج فاضي")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    print(f"\n{'=' * 62}")
    print(f"  عمليات دمج مسجّلة: {len(pairs)}")
    if skipped:
        print(f"  متروك [تخميني]: {skipped}")
    print(f"{'=' * 62}")

    todo = []
    done = 0
    missing = []

    for old, keep, conf, note in pairs:
        n_old = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE player_en = ?",
            (old,)).fetchone()[0]
        n_keep = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE player_en = ?",
            (keep,)).fetchone()[0]

        if n_old == 0 and n_keep == 0:
            missing.append((old, keep))
            continue

        if n_old == 0:
            done += 1
            continue

        todo.append((old, keep, n_old, n_keep, note))

    for old, keep, n_old, n_keep, note in sorted(
            todo, key=lambda x: -(x[2] + x[3])):
        print(f"\n  🔗 {old}  ({n_old})  →  {keep}  ({n_keep})")
        print(f"      المجموع: {n_old + n_keep}   |   {note}")

    tables = ["goals"]
    for t in ("lineup_players", "player_stats", "events"):
        if has_table(conn, t):
            tables.append(t)

    if CHECK_ONLY:
        print(f"\n{'=' * 62}")
        print("  [وضع الفحص] — ما انكتب شي")
        print(f"  جاهز للدمج: {len(todo)}  |  مدموج أصلاً: {done}"
              f"  |  مفقود: {len(missing)}")
        print(f"  الجداول: {', '.join(tables)}")
        print(f"{'=' * 62}\n")
        conn.close()
        return

    backup = DB_FILE.parent / "football_before_merges.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    total = 0
    for table in tables:
        n = 0
        for old, keep, _, _, _ in todo:
            cur = conn.execute(
                f"UPDATE {table} SET player_en = ? WHERE player_en = ?",
                (keep, old))
            n += cur.rowcount
        conn.commit()
        print(f"      {table:<18} {n} سجل")
        total += n

    after = conn.execute("""
        SELECT COUNT(DISTINCT player_en) FROM goals WHERE player_en != ''
    """).fetchone()[0]

    print(f"\n{'=' * 62}")
    print(f"  اندمج: {len(todo)}   |   سجلات معدّلة: {total}")
    print(f"  أسماء مختلفة بجدول goals: {after}")
    if missing:
        print(f"  ⚠️ ما لقى مطابق: {len(missing)}")
        for old, keep in missing[:5]:
            print(f"      {old} → {keep}")
    print(f"{'=' * 62}")
    print("""
  الخطوة الجاية:
      python export_players_ar.py
      python merge_players_ar.py
      python apply_players_ar.py
      python make_site3.py + make_clubs.py + make_matches.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
