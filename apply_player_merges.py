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
            old_raw = r.get("old_name") or ""
            old = old_raw.strip()
            keep = (r.get("keep_name") or "").strip()
            conf = (r.get("confidence") or "").strip()
            if not old or not keep:
                continue
            if conf == "تخميني":
                skipped += 1
                continue
            # ⚠️ old_raw بلا strip() — بعض الصفوف المسافة الطرفية
            #    نفسها هي التلف المطلوب مطابقته حرفياً (مثال:
            #    "Rakan Al-Kaabi " بعمود assist_en، 6 سبتمبر).
            #    تُستخدَم بتمريرة assist_en فقط أدناه — تمريرة
            #    player_en تستمر تستخدم `old` (مقصوصة) كما كانت
            #    دائماً، صفر تغيير سلوك هناك.
            pairs.append((old, keep, conf, (r.get("note") or "").strip(),
                         old_raw))

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

    tables = ["goals"]
    for t in ("lineup_players", "player_stats", "events"):
        if has_table(conn, t):
            tables.append(t)

    # ⚠️ **موسَّع 6 سبتمبر — كان يفحص `goals` وحده.** فشل صامت
    #    حقيقي: قيمة تالفة حيّة بـ`player_stats` بلا أي أثر بـ
    #    `goals` كانت تُصنَّف "مفقود" (بدل "جاهز للدمج")، وقيمة
    #    نظيفة موجودة بـ`goals` فقط بينما التالفة حيّة بجدول آخر
    #    كانت تُصنَّف "مُصلَحة أصلاً" رغم بقاء التلف الفعلي — كلا
    #    الحالتين تعني تخطّي صف يحتاج تصحيحاً حقيقياً، بأداة تعمل
    #    آلياً كل 30 دقيقة عبر update_all.py. الفحص الآن مجموع
    #    عبر الجداول الأربعة كلها، لا `goals` فقط.
    todo = []
    done = 0
    missing = []

    for old, keep, conf, note, old_raw in pairs:
        n_old = sum(conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE player_en = ?",
            (old,)).fetchone()[0] for t in tables)
        n_keep = sum(conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE player_en = ?",
            (keep,)).fetchone()[0] for t in tables)

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

    # ── تمريرة assist_en — مستقلة تماماً عن تمريرة player_en أعلاه
    #    (6 سبتمبر) — نفس صفوف CSV (pairs)، أعمدة/جداول مختلفة.
    #    ⚠️ الجداول تُفحص عبر PRAGMA فعلياً — لا افتراض أن
    #       goals/events فقط عندهم assist_en. old_raw (بلا strip)
    #       هو مفتاح البحث هنا عمداً — راجع التعليق عند بنائه أعلاه.
    assist_tables = [t for t in tables
                     if "assist_en" in {c[1] for c in
                         conn.execute(f"PRAGMA table_info({t})")}]

    # ⚠️ استثناء صريح — راجعتُ مراجعة يدوية قبل تفعيل تمريرة
    #    assist_en (6 سبتمبر): confidence "مرجح" لا "مؤكد"، وملاحظته
    #    الخاصة تحذّر "احذر: Mujtaba Ali لاعب آخر" — نفس الزوج
    #    مذكور أصلاً بقائمة "الحالات المستبعدة عمداً" أعلى هذا
    #    الملف (Mohanad Ali / Mujtaba Ali). المبدأ الأول: صفر
    #    تخمين بأسماء اللاعبين. **يخصّ تمريرة assist_en الجديدة
    #    فقط** — لا يمسّ تطبيقه القائم على player_en (خارج نطاق
    #    اليوم، قرار منفصل لو احتيج).
    ASSIST_EXCLUDE = {("M. Ali", "Mohanad Ali")}

    assist_todo = []
    if assist_tables:
        for old, keep, conf, note, old_raw in pairs:
            if (old, keep) in ASSIST_EXCLUDE:
                continue
            n_old = sum(conn.execute(
                f"SELECT COUNT(*) FROM {t} WHERE assist_en = ?",
                (old_raw,)).fetchone()[0] for t in assist_tables)
            if n_old == 0:
                continue
            n_keep = sum(conn.execute(
                f"SELECT COUNT(*) FROM {t} WHERE assist_en = ?",
                (keep,)).fetchone()[0] for t in assist_tables)
            assist_todo.append((old_raw, keep, n_old, n_keep, note))

        for old_raw, keep, n_old, n_keep, note in assist_todo:
            print(f"\n  🔗 assist_en: {old_raw!r}  ({n_old})  →  "
                  f"{keep}  ({n_keep})")
            print(f"      {note}")

    if CHECK_ONLY:
        print(f"\n{'=' * 62}")
        print("  [وضع الفحص] — ما انكتب شي")
        print(f"  جاهز للدمج (player_en): {len(todo)}  |  "
              f"مدموج أصلاً: {done}  |  مفقود: {len(missing)}")
        print(f"  جاهز للدمج (assist_en): {len(assist_todo)}  |  "
              f"جداول assist_en: {', '.join(assist_tables) or '—'}")
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

    assist_total = 0
    for table in assist_tables:
        n = 0
        for old_raw, keep, _, _, _ in assist_todo:
            cur = conn.execute(
                f"UPDATE {table} SET assist_en = ? WHERE assist_en = ?",
                (keep, old_raw))
            n += cur.rowcount
        conn.commit()
        print(f"      {table:<18} {n} سجل (assist_en)")
        total += n
        assist_total += n

    after = conn.execute("""
        SELECT COUNT(DISTINCT player_en) FROM goals WHERE player_en != ''
    """).fetchone()[0]

    print(f"\n{'=' * 62}")
    print(f"  اندمج (player_en): {len(todo)}   |   "
          f"اندمج (assist_en): {len(assist_todo)}")
    print(f"  سجلات معدّلة: {total}  (منها {assist_total} بـassist_en)")
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
