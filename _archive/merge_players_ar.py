#!/usr/bin/env python3
"""
دمج الأسماء المترجمة
======================
بيقرأ players_ar_filled.csv (اللي فيه الترجمات + مستوى الثقة)
وبيدمجها بملف players_ar.csv الرئيسي.

⚠️ الأسماء بمستوى [تخميني] **لا تُطبَّق** — تُترك فارغة والكود
   يرتد للإنجليزي. الاسم المخمّن الخاطئ أسوأ من الإنجليزي.

⚠️ **لا يمحو** أي ترجمة موجودة مسبقاً.

التشغيل:
    python merge_players_ar.py --check    <- عرض بس
    python merge_players_ar.py            <- تنفيذ
"""

import csv
import sys
import shutil
from config import BASE_DIR

MAIN = BASE_DIR / "players_ar.csv"
FILLED = BASE_DIR / "players_ar_filled.csv"
CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not MAIN.exists():
        print(f"ما لقيت {MAIN.name} — شغّل export_players_ar.py أول")
        return

    if not FILLED.exists():
        print(f"ما لقيت {FILLED.name}")
        return

    # الترجمات مع مستوى الثقة
    trans = {}
    skipped = []
    with open(FILLED, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            en = (r.get("player_en") or "").strip()
            ar = (r.get("player_ar") or "").strip()
            conf = (r.get("confidence") or "").strip()
            if not en:
                continue
            if not ar or conf == "تخميني":
                skipped.append(en)
                continue
            trans[en] = {"ar": ar, "conf": conf,
                         "src": (r.get("source") or "").strip()}

    # الملف الرئيسي
    with open(MAIN, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    print(f"\n{'=' * 62}")
    print(f"  ترجمات جاهزة: {len(trans)}   |   متروك [تخميني]: {len(skipped)}")
    print(f"{'=' * 62}")

    added = already = notfound = 0
    seen = set()

    for row in rows:
        en = (row.get("player_en") or "").strip()
        if en not in trans:
            continue

        seen.add(en)
        cur = (row.get("player_ar") or "").strip()
        new = trans[en]["ar"]

        if cur == new:
            already += 1
            continue

        if cur:
            print(f"\n  ⚠️ {en}")
            print(f"     موجود : {cur}")
            print(f"     جديد  : {new}   — تُرك الموجود")
            already += 1
            continue

        print(f"\n  ➕ {en}")
        print(f"     → {new}   [{trans[en]['conf']}]")

        if not CHECK_ONLY:
            row["player_ar"] = new
        added += 1

    notfound = [en for en in trans if en not in seen]

    if not CHECK_ONLY and added:
        backup = MAIN.parent / "players_ar_backup.csv"
        shutil.copy(MAIN, backup)
        with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"\n  نسخة احتياطية: {backup.name}")

    print(f"\n{'=' * 62}")
    if CHECK_ONLY:
        print("  [وضع الفحص] — ما انكتب شي")
        print(f"  جاهز للإضافة: {added}  |  موجود أصلاً: {already}")
    else:
        print(f"  انضاف: {added}  |  كان موجوداً: {already}")
    if notfound:
        print(f"  ⚠️ ما لقى مطابق: {len(notfound)}")
        for en in notfound[:5]:
            print(f"      {en}")
    print(f"{'=' * 62}")

    if added and not CHECK_ONLY:
        print("""
  الخطوة الجاية:
      python apply_players_ar.py
      python make_site3.py + make_clubs.py + make_matches.py
        """)


if __name__ == "__main__":
    main()
