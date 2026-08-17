#!/usr/bin/env python3
"""
فحص القاسم × نفط البصرة — العراقي 2023
=========================================
آخر فرق متبقٍّ في الموسم:

    القاسم      ف: 7≠8   ت: 15≠14  له: 39≠42  نقاط: 36≠35
    نفط البصرة  ت: 11≠10 خ: 19≠20  عليه: 43≠46 نقاط: 35≠34

قراءة الفرق: المزوّد يحسب للقاسم فوزاً بفرق 3 أهداف نظيفة
على نفط البصرة، ونحن نحسبها تعادلاً.

[مرجّح] مباراة حُسمت إدارياً 3-0 (نمط درس 19) —
أو نتيجة خاطئة عند المزوّد (نمط درس 13).

يعرض: مباريات الناديين وجهاً لوجه + أهدافها المسجّلة +
حالة كل مباراة في ملفات التصحيح والاستثناء.

⚠️ للقراءة فقط.

التشغيل:
    python check_qasim.py
"""

import csv
import os
import sqlite3

DB = "football.db"
A, B = 15546, 11072  # القاسم، نفط البصرة


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    names = {r["team_id"]: r["short_name_ar"]
             for r in conn.execute(
                 "SELECT team_id, short_name_ar FROM teams")}

    def nm(t):
        return names.get(t, str(t))

    print()
    print("=" * 60)
    print(f"  {nm(A)} × {nm(B)} — العراقي 2023")
    print("=" * 60)

    rows = list(conn.execute("""
        SELECT match_id, date, home_id, away_id,
               home_goals, away_goals
        FROM matches
        WHERE league_code = 'IRQ' AND season = 2023
          AND ((home_id = ? AND away_id = ?)
            OR (home_id = ? AND away_id = ?))
        ORDER BY date
    """, (A, B, B, A)))

    if not rows:
        print("  لا مباريات بينهما في الديتابيس")

    for m in rows:
        print(f"\n  {m['date'][:10]}  id={m['match_id']}")
        print(f"  {nm(m['home_id'])} {m['home_goals']}-"
              f"{m['away_goals']} {nm(m['away_id'])}")

        goals = list(conn.execute("""
            SELECT minute, player_en, player_ar, team_id, detail
            FROM goals WHERE match_id = ?
            ORDER BY minute
        """, (m["match_id"],)))

        if goals:
            print("  الأهداف:")
            for g in goals:
                p = g["player_ar"] or g["player_en"] or "?"
                d = f" ({g['detail']})" if g["detail"] else ""
                print(f"    د.{g['minute']}  {p} — {nm(g['team_id'])}{d}")
        else:
            print("  لا أهداف مسجّلة")

    # حالة الملفات اليدوية
    print()
    print("-" * 60)
    print("  حالة الملفات اليدوية لهذين الناديين")
    print("-" * 60)

    ids = {str(m["match_id"]) for m in rows}

    corr = [r for r in load_csv("match_corrections.csv")
            if str(r.get("match_id", "")).strip() in ids]
    print(f"\n  match_corrections.csv: {len(corr)} سطر")
    for r in corr:
        print(f"    {r}")

    excl = [r for r in load_csv("excluded_matches.csv")
            if str(r.get("match_id", "")).strip() in ids]
    print(f"\n  excluded_matches.csv: {len(excl)} سطر")
    for r in excl:
        print(f"    id={r.get('match_id')}  "
              f"السبب: {r.get('reason', '')[:60]}")

    manual = [r for r in load_csv("manual_matches.csv")
              if str(r.get("home_id", "")).strip() in (str(A), str(B))
              and str(r.get("away_id", "")).strip() in (str(A), str(B))]
    print(f"\n  manual_matches.csv (بين الناديين): {len(manual)} سطر")
    for r in manual:
        print(f"    {r}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
