#!/usr/bin/env python3
"""
تطبيق استثناءات المباريات
===========================
بيقرأ excluded_matches.csv وبيحذف المباريات اللي ما لازم تكون
بالديتابيس (مباريات من خارج الدوري، أندية غير مشاركة، إلخ).

ليش موجود:
الـAPI يضع أحياناً مباريات من مسابقات أخرى تحت نفس league_id.
أي سحب جديد بيرجّعها، فهالسكربت بينطبّق بعد كل سحب.

صفر طلبات API.

التشغيل:
    python apply_exclusions.py --check    <- عرض بس
    python apply_exclusions.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

EXCLUSIONS_FILE = BASE_DIR / "excluded_matches.csv"
CHECK_ONLY = "--check" in sys.argv


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not EXCLUSIONS_FILE.exists():
        print(f"ما لقيت {EXCLUSIONS_FILE.name}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    with open(EXCLUSIONS_FILE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)
                if (r.get("match_id") or "").strip()]

    if not rows:
        print("ملف الاستثناءات فاضي")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"  استثناءات مسجّلة: {len(rows)}")
    print(f"{'=' * 60}")

    removed = clean = 0

    for r in rows:
        mid = int(r["match_id"])
        reason = (r.get("reason") or "").strip()

        m = conn.execute("""
            SELECT m.date, m.home_goals hg, m.away_goals ag,
                   h.short_name_ar AS home, a.short_name_ar AS away
            FROM matches m
            LEFT JOIN teams h ON h.team_id = m.home_id
            LEFT JOIN teams a ON a.team_id = m.away_id
            WHERE m.match_id = ?
        """, (mid,)).fetchone()

        if m is None:
            print(f"\n  ✅ {mid} — محذوفة أصلاً")
            clean += 1
            continue

        print(f"\n  🗑️  {m['home']} {m['hg']}-{m['ag']} {m['away']}"
              f"  ({m['date']})")
        print(f"      id={mid}")
        print(f"      السبب: {reason}")

        if CHECK_ONLY:
            continue

        n = conn.execute("SELECT COUNT(*) FROM goals WHERE match_id = ?",
                         (mid,)).fetchone()[0]
        conn.execute("DELETE FROM matches WHERE match_id = ?", (mid,))
        conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))
        if n:
            print(f"      انحذف معها {n} هدف")
        removed += 1

    if not CHECK_ONLY:
        conn.commit()

    print(f"\n{'=' * 60}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انحذف شي")
        print(f"  محتاجة حذف: {removed}  |  محذوفة أصلاً: {clean}")
    else:
        print(f"  انحذف: {removed}  |  كانت محذوفة: {clean}")
    print(f"{'=' * 60}")

    if removed and not CHECK_ONLY:
        print("\n  الخطوة الجاية:  python make_site3.py\n")

    conn.close()


if __name__ == "__main__":
    main()
