#!/usr/bin/env python3
"""
فحص الأسماء الإنجليزية الرسمية
================================
README يوثّق **17 اسماً مصححاً**، لكن sync_teams.py أبلغ عن
**4 فقط**. الفارق 13 اسماً — إما ضاعت من CSV، أو لم تُنقل
للديتابيس، أو رقم README خطأ من الأصل.

يقارن ثلاثة مصادر:
    teams_arabic.csv       ← الأصل
    football.db (teams)    ← بعد sync_teams.py
    club_names_review.csv  ← سجل المراجعة ومصادرها

⚠️ للقراءة فقط. لا يعدّل شيئاً.

التشغيل:
    python check_names.py
"""

import csv
import os
import sqlite3

CSV_FILE = "teams_arabic.csv"
REVIEW_FILE = "club_names_review.csv"
DB = "football.db"


def clean(v):
    return (v or "").strip()


def main():
    print()
    print("=" * 58)
    print("  الأسماء الإنجليزية الرسمية — مقارنة المصادر")
    print("=" * 58)

    # ── 1. من الـCSV ──────────────────────────────────
    csv_rows = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                csv_rows[clean(r.get("team_id"))] = r
    else:
        print("  ❌ ما لقيت teams_arabic.csv")
        return

    csv_official = {k: v for k, v in csv_rows.items()
                    if clean(v.get("name_en_official"))}

    print(f"\n  teams_arabic.csv : {len(csv_rows)} نادياً")
    print(f"  منها باسم رسمي   : {len(csv_official)}")

    # ── 2. من الديتابيس ───────────────────────────────
    db_official = {}
    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute("""
                SELECT team_id, short_name_ar, name_en,
                       name_en_official
                FROM teams
            """):
                if clean(r["name_en_official"]):
                    db_official[str(r["team_id"])] = dict(r)
        except sqlite3.Error as e:
            print(f"  ⚠️ خطأ بقراءة الديتابيس: {e}")
        conn.close()
        print(f"  football.db      : {len(db_official)} باسم رسمي")
    else:
        print("  ⚠️ ما لقيت football.db")

    # ── 3. من سجل المراجعة ────────────────────────────
    review = {}
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE, encoding="utf-8-sig") as f:
            rd = csv.DictReader(f)
            cols = rd.fieldnames or []
            for r in rd:
                tid = clean(r.get("team_id"))
                if tid:
                    review[tid] = r
        print(f"  club_names_review: {len(review)} سطراً")
        print(f"  أعمدته: {', '.join(cols)}")
    else:
        print("  ⚠️ ما لقيت club_names_review.csv")

    # ── القائمة الفعلية ───────────────────────────────
    print()
    print("=" * 58)
    print(f"  الأسماء الرسمية الموجودة فعلاً في CSV ({len(csv_official)})")
    print("=" * 58)
    for tid, r in sorted(csv_official.items()):
        print(f"  {tid:>6}  {clean(r.get('short_name_ar')):<14} "
              f"{clean(r.get('name_en'))}")
        print(f"          → {clean(r.get('name_en_official'))}")

    # ── الفجوة بين CSV والديتابيس ─────────────────────
    only_csv = set(csv_official) - set(db_official)
    only_db = set(db_official) - set(csv_official)

    if only_csv or only_db:
        print()
        print("=" * 58)
        print("  ⚠️ تعارض بين CSV والديتابيس")
        print("=" * 58)
        for tid in sorted(only_csv):
            print(f"  في CSV وليس بالديتابيس: {tid} "
                  f"{clean(csv_official[tid].get('short_name_ar'))}")
        for tid in sorted(only_db):
            print(f"  بالديتابيس وليس بـCSV : {tid} "
                  f"{clean(db_official[tid].get('short_name_ar'))}")
    else:
        print("\n  ✅ CSV والديتابيس متطابقان")

    # ── هل سجل المراجعة يحمل أسماء ضائعة؟ ─────────────
    if review:
        cand = []
        for tid, r in review.items():
            vals = {k: clean(v) for k, v in r.items()}
            has_en = any(
                ("official" in k.lower() or "en" in k.lower())
                and v for k, v in vals.items())
            if has_en and tid not in csv_official:
                cand.append((tid, r))

        print()
        print("=" * 58)
        print(f"  أسماء في سجل المراجعة وغير مطبَّقة في CSV: "
              f"{len(cand)}")
        print("=" * 58)
        for tid, r in sorted(cand)[:25]:
            vals = " | ".join(f"{k}={clean(v)}"
                              for k, v in r.items() if clean(v))
            print(f"  {tid}: {vals}")
        if len(cand) > 25:
            print(f"  ... و{len(cand) - 25} غيرها")

    print()
    print("=" * 58)
    print(f"  الخلاصة: CSV={len(csv_official)}  "
          f"DB={len(db_official)}  README يقول 17")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
