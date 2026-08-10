#!/usr/bin/env python3
"""
دمج سجلات الأندية المكررة
============================
بيقرأ team_merges.csv وبيحوّل كل المباريات والأهداف من الـID
القديم للـID الجديد.

ليش موجود:
الـAPI أحياناً بيملك معرّفين لنفس النادي (مثال: نوروز 6689 و25062).
النتيجة: النادي بيظهر مرتين بجدول الترتيب بأرقام ناقصة.
أي سحب جديد بيرجّع المشكلة، فهالسكربت بينطبّق بعد كل سحب.

صفر طلبات API.

التشغيل:
    python apply_merges.py --check    <- عرض بس
    python apply_merges.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

MERGES_FILE = BASE_DIR / "team_merges.csv"
CHECK_ONLY = "--check" in sys.argv


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not MERGES_FILE.exists():
        print(f"ما لقيت {MERGES_FILE.name}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    with open(MERGES_FILE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)
                if (r.get("old_id") or "").strip()]

    if not rows:
        print("ملف الدمج فاضي")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"  عمليات دمج مسجّلة: {len(rows)}")
    print(f"{'=' * 60}")

    merged = clean = 0

    for r in rows:
        old = int(r["old_id"])
        new = int(r["new_id"])
        note = (r.get("note") or "").strip()

        # كم مباراة وهدف تحت الـID القديم
        n_home = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE home_id = ?",
            (old,)).fetchone()[0]
        n_away = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE away_id = ?",
            (old,)).fetchone()[0]
        n_goals = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE team_id = ?",
            (old,)).fetchone()[0]

        total = n_home + n_away

        # اسم النادي الجديد إن وُجد
        t = conn.execute(
            "SELECT short_name_ar FROM teams WHERE team_id = ?",
            (new,)).fetchone()
        label = t["short_name_ar"] if t else str(new)

        if total == 0 and n_goals == 0:
            print(f"\n  ✅ {old} → {new} ({label})")
            print(f"     مدموج أصلاً")
            clean += 1
            continue

        print(f"\n  🔗 {old} → {new} ({label})")
        print(f"     مباريات: {total}   أهداف: {n_goals}")
        print(f"     السبب: {note}")

        if CHECK_ONLY:
            continue

        conn.execute("UPDATE matches SET home_id = ? WHERE home_id = ?",
                     (new, old))
        conn.execute("UPDATE matches SET away_id = ? WHERE away_id = ?",
                     (new, old))
        conn.execute("UPDATE goals SET team_id = ? WHERE team_id = ?",
                     (new, old))
        merged += 1

    if not CHECK_ONLY:
        conn.commit()

    print(f"\n{'=' * 60}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انعدّل شي")
        print(f"  محتاجة دمج: {merged}  |  مدموجة أصلاً: {clean}")
    else:
        print(f"  اندمج: {merged}  |  كان مدموجاً: {clean}")
    print(f"{'=' * 60}")

    if merged and not CHECK_ONLY:
        print("\n  الخطوة الجاية:  python make_site3.py\n")

    conn.close()


if __name__ == "__main__":
    main()
