#!/usr/bin/env python3
"""
فحص أندية الموسم الجديد — قبل انطلاق أي دوري
================================================
يفحص كل نادٍ يظهر في مباريات موسم 2026 ويكشف ثلاث حالات:

    ❌ مفقود من teams_arabic.csv  → لا صفحة نادٍ، ومبارياته تختفي
    ⚠️ بلا اسم عربي              → make_clubs.py قد يتخطاه
    ⚠️ عدد الأندية غير متوقع     → ناقص أو زائد عن حجم الدوري

هذا الفحص **مقصود** لا بالصدفة — درس 35: العربي ودوقرة اكتُشفا
مصادفةً أثناء فحص الشعارات، ولولا ذلك لاختفت أول جولة أردنية.

⚠️ للقراءة فقط. لا يعدّل أي ملف ولا يستهلك أي طلب API.

التشغيل:
    python check_season.py
    python check_season.py --season 2025
"""

import csv
import os
import sqlite3
import sys

DB = "football.db"
CSV_FILE = "teams_arabic.csv"

# ⚠️ حجم الدوري يتغيّر بين المواسم — الأردني صار 10 أندية
#    اعتباراً من موسم 2025 (كان 12 في 2023 و2024)
EXPECTED = {
    ("JOR", 2023): 12,
    ("JOR", 2024): 12,
    ("JOR", 2025): 10,
    ("JOR", 2026): 10,
    "IRQ": 20,
    "SAU": 18,
}

NAMES = {
    "JOR": "الدوري الأردني",
    "IRQ": "الدوري العراقي",
    "SAU": "الدوري السعودي",
}

SEASON = 2026
if "--season" in sys.argv:
    i = sys.argv.index("--season")
    if i + 1 < len(sys.argv):
        try:
            SEASON = int(sys.argv[i + 1])
        except ValueError:
            pass


def load_csv():
    if not os.path.exists(CSV_FILE):
        return {}
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        return {str(r.get("team_id", "")).strip(): r
                for r in csv.DictReader(f)}


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db — تأكد إنك بمجلد Football")
        return

    rows = load_csv()
    conn = sqlite3.connect(DB)

    print()
    print("=" * 58)
    print(f"  فحص أندية موسم {SEASON}")
    print("=" * 58)

    total_missing = []

    for code in ("JOR", "IRQ", "SAU"):
        ids = [str(r[0]) for r in conn.execute("""
            SELECT DISTINCT home_id FROM matches
            WHERE league_code = ? AND season = ?
            UNION
            SELECT DISTINCT away_id FROM matches
            WHERE league_code = ? AND season = ?
        """, (code, SEASON, code, SEASON))]

        n_matches = conn.execute("""
            SELECT COUNT(match_id) FROM matches
            WHERE league_code = ? AND season = ?
        """, (code, SEASON)).fetchone()[0]

        exp = EXPECTED.get((code, SEASON), EXPECTED.get(code))
        mark = "✅" if len(ids) == exp else "⚠️"
        if not ids:
            mark = "—"

        print()
        print(f"  {NAMES[code]}")
        print(f"  {'-' * 54}")
        print(f"  مباريات: {n_matches}   "
              f"أندية: {len(ids)} / {exp} متوقع  {mark}")

        if not ids:
            print("  لا مباريات بعد لهذا الموسم")
            continue

        missing = [i for i in ids if i not in rows]
        no_ar = [i for i in ids
                 if i in rows
                 and not (rows[i].get("short_name_ar") or "").strip()]

        if missing:
            print(f"\n  ❌ {len(missing)} نادٍ مفقود من "
                  f"teams_arabic.csv:")
            for i in missing:
                print(f"       {i}  ← شغّل: python fetch_missing.py")
            total_missing += missing

        if no_ar:
            print(f"\n  ⚠️ {len(no_ar)} نادٍ بلا اسم عربي:")
            for i in no_ar:
                print(f"       {i}  {rows[i].get('name_en', '')}")

        if not missing and not no_ar:
            print("  كل الأندية موجودة بأسماء عربية ✅")

        # قائمة الأندية للتحقق الخارجي
        print("\n  القائمة للمقارنة مع المصدر الرسمي:")
        named = sorted(
            (rows.get(i, {}).get("short_name_ar") or f"[{i}]")
            for i in ids)
        line = "       "
        for nm in named:
            if len(line) + len(nm) > 56:
                print(line)
                line = "       "
            line += nm + " · "
        if line.strip():
            print(line.rstrip(" ·"))

    conn.close()

    print()
    print("=" * 58)
    if total_missing:
        print(f"  ❌ إجمالي المفقودين: {len(total_missing)}")
        print("     أضفهم لـteams_arabic.csv قبل انطلاق الموسم")
    else:
        print("  ✅ لا نادي مفقود")
    print("=" * 58)
    print("""
  الخطوة التالية — تحقق خارجي:
      الأردني : jfa.jo
      العراقي : الموقع الرسمي للدوري
      السعودي : spl.com.sa
    """)


if __name__ == "__main__":
    main()
