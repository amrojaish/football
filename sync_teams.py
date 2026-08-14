#!/usr/bin/env python3
"""
نقل جدول الأندية من CSV للديتابيس
====================================
teams_arabic.csv هو المصدر الوحيد للحقيقة بأسماء الأندية.
هذا السكربت ينقلها للديتابيس بعد أي تعديل.

⚠️ لازم يُشغَّل بعد أي تعديل على teams_arabic.csv، وإلا
   الموقع يبقى على الأسماء القديمة.

الأعمدة:
    name_en           = اسم المزوّد (مرجع، لا يُعرض)
    name_en_official  = الاسم الإنجليزي الرسمي (يُعرض)
    name_ar           = الاسم العربي الكامل
    short_name_ar     = الاسم العربي المختصر (يُعرض)

صفر طلبات API.

التشغيل:
    python sync_teams.py
"""

import sqlite3
import csv
import sys
from config import DB_FILE, TEAMS_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not TEAMS_FILE.exists():
        print("ما لقيت teams_arabic.csv")
        return

    conn = sqlite3.connect(DB_FILE)

    # العمود الجديد — إضافته آمنة ومتكررة
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN name_en_official TEXT")
        print("  انضاف عمود name_en_official لجدول teams")
    except sqlite3.OperationalError:
        pass

    rows = []
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not (r.get("team_id") or "").strip():
                continue
            rows.append((
                int(r["team_id"]),
                (r.get("league_code") or "").strip(),
                (r.get("name_en") or "").strip(),
                (r.get("name_en_official") or "").strip(),
                (r.get("name_ar") or "").strip(),
                (r.get("short_name_ar") or "").strip(),
                (r.get("city") or "").strip(),
                (r.get("logo") or "").strip(),
            ))

    conn.executemany("""
        INSERT OR REPLACE INTO teams
        (team_id, league_code, name_en, name_en_official,
         name_ar, short_name_ar, city, logo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

    n_off = conn.execute("""
        SELECT COUNT(*) FROM teams
        WHERE name_en_official IS NOT NULL AND name_en_official != ''
    """).fetchone()[0]

    n_ar = conn.execute("""
        SELECT COUNT(*) FROM teams
        WHERE short_name_ar IS NOT NULL AND short_name_ar != ''
    """).fetchone()[0]

    print(f"\n{'=' * 55}")
    print(f"  تم نقل {len(rows)} نادي من CSV للديتابيس")
    print(f"{'=' * 55}")
    print(f"  باسم عربي مختصر  : {n_ar}")
    print(f"  باسم إنجليزي رسمي: {n_off}")

    missing = len(rows) - n_off
    if missing:
        print(f"  ⚠️ بلا اسم إنجليزي رسمي: {missing}"
              f"  (سيرتد لاسم المزوّد)")

    print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
    """)

    conn.close()


if __name__ == "__main__":
    main()
