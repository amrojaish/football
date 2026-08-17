#!/usr/bin/env python3
"""
تدقيق فروق العراقي 2025 — مبررة أم لا؟
==========================================
compare_standings كشف 7 فرق بفروق مقابل المزوّد:

    الشرطة · ديالى · الميناء · نفط ميسان · الكهرباء · النجف · القاسم

لكن 2025 فيه 7 مباريات مضافة يدوياً و5 نتائج مصححة (درس 19)،
والتحقق الرسمي 20/20 كان **ضد المصدر الرسمي لا المزوّد**.
فالفرق مع المزوّد قد يكون مقصوداً بالكامل.

هذا السكربت يفحص لكل نادٍ من السبعة:
    1. كم مباراة يدوية تخصّه (id >= 9000000)
    2. كم تصحيح نتيجة يمسّه
    3. هل الفرق المتبقي بعد خصم أثر اليدوي = صفر؟

⚠️ للقراءة فقط.

التشغيل:
    python audit_irq25.py
"""

import csv
import os
import sqlite3

DB = "football.db"

# الأندية السبعة من مخرجات compare_standings
SUSPECT = {
    5242: "الشرطة",
    25061: "ديالى",
    11065: "الميناء",
    11074: "نفط ميسان",
    11064: "الكهرباء",
    11066: "النجف",
    15546: "القاسم",
}


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

    corrections = load_csv("match_corrections.csv")
    corr_irq25 = [r for r in corrections
                  if (r.get("league_code") or "").strip() == "IRQ"
                  and (r.get("season") or "").strip() == "2025"]

    print()
    print("=" * 62)
    print("  العراقي 2025 — تدقيق الفروق السبعة")
    print("=" * 62)

    # ── المباريات اليدوية بالموسم ─────────────────────
    manual = list(conn.execute("""
        SELECT match_id, date, home_id, away_id,
               home_goals, away_goals
        FROM matches
        WHERE league_code = 'IRQ' AND season = 2025
          AND match_id >= 9000000
        ORDER BY date
    """))

    print(f"\n  مباريات يدوية بالموسم (id>=9000000): {len(manual)}")
    for m in manual:
        mark = ""
        if m["home_id"] in SUSPECT or m["away_id"] in SUSPECT:
            mark = "  ← يمسّ نادياً من السبعة"
        print(f"    {m['date'][:10]}  {nm(m['home_id'])} "
              f"{m['home_goals']}-{m['away_goals']} "
              f"{nm(m['away_id'])}{mark}")

    # ── التصحيحات بالموسم ─────────────────────────────
    print(f"\n  تصحيحات نتائج بالموسم: {len(corr_irq25)}")
    for r in corr_irq25:
        mid = (r.get("match_id") or "").strip()
        row = conn.execute("""
            SELECT home_id, away_id FROM matches WHERE match_id = ?
        """, (mid,)).fetchone()
        who = ""
        if row:
            who = f"{nm(row['home_id'])} × {nm(row['away_id'])}"
            if (row["home_id"] in SUSPECT
                    or row["away_id"] in SUSPECT):
                who += "  ← يمسّ نادياً من السبعة"
        print(f"    id={mid}  {r.get('correct_home')}-"
              f"{r.get('correct_away')}  {who}")

    # ── ملخص لكل نادٍ من السبعة ───────────────────────
    print()
    print("-" * 62)
    print("  ملخص كل نادٍ: كم لعب عندنا + كم يدوي يخصّه")
    print("-" * 62)

    for tid, name in SUSPECT.items():
        played = conn.execute("""
            SELECT COUNT(match_id) FROM matches
            WHERE league_code = 'IRQ' AND season = 2025
              AND (home_id = ? OR away_id = ?)
              AND home_goals IS NOT NULL
        """, (tid, tid)).fetchone()[0]

        man_n = sum(1 for m in manual
                    if m["home_id"] == tid or m["away_id"] == tid)

        corr_ids = set()
        for r in corr_irq25:
            mid = (r.get("match_id") or "").strip()
            row = conn.execute("""
                SELECT home_id, away_id FROM matches
                WHERE match_id = ?""", (mid,)).fetchone()
            if row and (row["home_id"] == tid
                        or row["away_id"] == tid):
                corr_ids.add(mid)

        print(f"\n  {name}")
        print(f"    مباريات محسومة عندنا : {played}")
        print(f"    منها يدوية           : {man_n}")
        print(f"    تصحيحات تمسّه        : {len(corr_ids)}")

    conn.close()
    print()
    print("=" * 62)
    print("""
  القراءة:
  - نادٍ عنده مباراة يدوية والمزوّد أقل بواحدة = فرق مقصود ✓
  - نادٍ عنده تصحيح نتيجة = فرق ف/ت/خ مقصود ✓
  - فرق لا يغطيه يدوي ولا تصحيح = يحتاج تحقيقاً فعلياً ⚠️
    """)


if __name__ == "__main__":
    main()
