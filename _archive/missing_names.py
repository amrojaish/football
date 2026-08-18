#!/usr/bin/env python3
"""
الأندية بلا اسم إنجليزي رسمي
==============================
62 من 70 نادياً لهم name_en_official بعد تطبيق club_names_review.csv.
الباقون أُضيفوا **بعد** إعداد سجل المراجعة، فيرتدّون لاسم المزوّد
في النسخة الإنجليزية (درس 22).

يطبع لكل نادٍ: المعرّف · الدوري · الاسم العربي · اسم المزوّد ·
هل هو نشط في موسم 2026.

⚠️ للقراءة فقط.

التشغيل:
    python missing_names.py
"""

import csv
import os
import sqlite3

CSV_FILE = "teams_arabic.csv"
DB = "football.db"


def main():
    if not os.path.exists(CSV_FILE):
        print("ما لقيت teams_arabic.csv")
        return

    with open(CSV_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    missing = [r for r in rows
               if not (r.get("name_en_official") or "").strip()]

    # أندية موسم 2026 النشطة
    active = set()
    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        active = {str(x[0]) for x in conn.execute("""
            SELECT DISTINCT home_id FROM matches WHERE season = 2026
            UNION
            SELECT DISTINCT away_id FROM matches WHERE season = 2026
        """)}
        conn.close()

    print()
    print("=" * 60)
    print(f"  بلا اسم إنجليزي رسمي: {len(missing)} من {len(rows)}")
    print("=" * 60)
    print()

    for r in sorted(missing, key=lambda x: (x.get("league_code", ""),
                                            x.get("team_id", ""))):
        tid = (r.get("team_id") or "").strip()
        flag = " ⚽ نشط 2026" if tid in active else ""
        print(f"  {tid:>6}  {r.get('league_code', ''):<4} "
              f"{(r.get('short_name_ar') or ''):<14}")
        print(f"          اسم المزوّد: {r.get('name_en', '')}{flag}")
        print()

    n_active = sum(1 for r in missing
                   if (r.get("team_id") or "").strip() in active)

    print("=" * 60)
    print(f"  منهم نشطون في موسم 2026: {n_active}")
    print("=" * 60)
    print("""
  الخطوة التالية: أضف سطراً لكل نادٍ في
  club_names_review.csv بالأعمدة:
      team_id, league, current_api_name,
      official_english, confidence, note
  ثم:  python apply_club_names.py --check
    """)


if __name__ == "__main__":
    main()
