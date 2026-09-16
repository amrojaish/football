#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تطبيق دمج أسماء المدربين اليدوي — lineups.coach_en (بند المدربين)
====================================================================
بيقرأ coach_merges.csv وبيوحّد الصيغ المختلفة لنفس المدرب داخل
جدول lineups فقط.

⚠️ **أداة جديدة، لا استخدام لـapply_player_merges.py أو
   apply_players_ar.py** — راجع السبب:
   - `apply_players_ar.py` يكتب عمود *_ar (ترجمة) فقط، بمطابقة
     نصّية على *_en — لا يمسّ *_en نفسه. `coach_ar` فارغ كلياً
     بالمشروع حالياً (صفر ترجمة بُدئت) فلا ينطبق هنا أصلاً.
   - `apply_player_merges.py` يكتب `player_en` مباشرة لكن
     **بمطابقة نصّية عامة بلا قيد team_id/player_id على الإطلاق**
     (`UPDATE goals SET player_en=? WHERE player_en=?`) — آمن
     للاعبين لأن كل صف بـplayer_merges.csv رُوجِع يدوياً ليكون
     فريداً عالمياً. **خطر حقيقي لو استُخدم لنفس الأسلوب هنا**:
     "Jose Gomes"/"José Gomes" ظهرا بناديين مختلفين تماماً
     (Al-Fateh وAl Khaleej) — دمج عالمي بلا قيد نادٍ قد يوحّد
     مدربين مختلفين حقيقيين بالصدفة لو تشابه الاسم بناديين لا
     علاقة بينهما. **لذا كل UPDATE هنا مقيَّد بـteam_id إلزامياً،
     بلا استثناء.**

مصدر الصفوف: `check_coach_conflict_queue.py --write-csv` (فحص
آلي بمعايير بند 27 المعدَّلة) — **تُراجَع الصفوف يدوياً قبل أي
استخدام**، الملف بالمستودع (coach_merges.csv) نسخة مُراجَعة
فعلاً (دفعة أولى: 26 حالة (أ)/(أ*)، 16 سبتمبر 2026).

نسخة احتياطية قبل الكتابة (football_before_coach_merges.db).
إعادة التشغيل آمنة (UPDATE فوق صف مطابق أصلاً = صفر أثر).

التشغيل:
    python apply_coach_merges.py --check    <- عرض بس
    python apply_coach_merges.py            <- تنفيذ
"""
import csv
import shutil
import sqlite3
import sys
from config import DB_FILE, BASE_DIR

SOURCE = BASE_DIR / "coach_merges.csv"
CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_rows():
    rows = []
    with open(SOURCE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            team_id = (r.get("team_id") or "").strip()
            old = (r.get("old_name") or "").strip()
            keep = (r.get("keep_name") or "").strip()
            conf = (r.get("confidence") or "").strip()
            note = (r.get("note") or "").strip()
            if not (team_id and old and keep):
                continue
            if conf == "تخميني":
                continue
            rows.append((int(team_id), old, keep, note))
    return rows


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return
    if not SOURCE.exists():
        print(f"ما لقيت {SOURCE.name}")
        return

    rows = load_rows()
    if not rows:
        print("ملف الدمج فاضي")
        return

    print(f"\n{'=' * 62}")
    print(f"  عمليات دمج مسجّلة: {len(rows)}")
    print(f"{'=' * 62}")

    conn = sqlite3.connect(DB_FILE)

    todo = []
    done = 0
    missing = []
    self_pairs = 0

    for team_id, old, keep, note in rows:
        if old == keep:
            self_pairs += 1
            continue

        n_old = conn.execute(
            "SELECT COUNT(*) FROM lineups WHERE team_id = ? AND coach_en = ?",
            (team_id, old)).fetchone()[0]
        n_keep = conn.execute(
            "SELECT COUNT(*) FROM lineups WHERE team_id = ? AND coach_en = ?",
            (team_id, keep)).fetchone()[0]

        if n_old == 0 and n_keep == 0:
            missing.append((team_id, old, keep))
            continue
        if n_old == 0:
            done += 1
            continue

        todo.append((team_id, old, keep, n_old, n_keep, note))

    for team_id, old, keep, n_old, n_keep, note in sorted(todo, key=lambda x: -x[3]):
        print(f"\n  🔗 team_id={team_id}: {old!r}  ({n_old})  →  {keep!r}  ({n_keep})")
        print(f"      {note}")

    if CHECK_ONLY:
        print(f"\n{'=' * 62}")
        print("  [وضع الفحص] — ما انكتب شي")
        print(f"  جاهز للدمج: {len(todo)}  |  مدموج أصلاً: {done}  |  "
              f"مفقود: {len(missing)}  |  self-pair متروك: {self_pairs}")
        print(f"{'=' * 62}\n")
        if missing:
            print("  ⚠️ ما لقى مطابق (team_id, old_name):")
            for team_id, old, keep in missing:
                print(f"      team_id={team_id}: {old!r} → {keep!r}")
        conn.close()
        return

    backup = DB_FILE.parent / "football_before_coach_merges.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    total = 0
    for team_id, old, keep, n_old, n_keep, note in todo:
        cur = conn.execute(
            "UPDATE lineups SET coach_en = ? WHERE team_id = ? AND coach_en = ?",
            (keep, team_id, old))
        total += cur.rowcount
    conn.commit()

    print(f"\n{'=' * 62}")
    print(f"  اندمج: {len(todo)}   |   سجلات معدَّلة: {total}")
    if self_pairs:
        print(f"  self-pair متروك (old==keep، بلا تأثير): {self_pairs}")
    if missing:
        print(f"  ⚠️ ما لقى مطابق: {len(missing)}")
        for team_id, old, keep in missing:
            print(f"      team_id={team_id}: {old!r} → {keep!r}")
    print(f"{'=' * 62}")
    print("""
  الخطوة الجاية:
      python make_site3.py + make_leagues.py + make_clubs.py +
      make_matches.py + make_pages.py + make_players.py +
      make_search.py + make_sitemap.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
