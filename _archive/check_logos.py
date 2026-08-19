#!/usr/bin/env python3
"""
فحص شعارات الأندية الصاعدة
=============================
7 أندية صاعدة حديثاً حسب فحص 18-19 أغسطس:
    الأردني : العربي (17472) · دوقرة (22188)
    العراقي : الجولان (28222) · غاز الشمال (28223)
    السعودي : الفيصلي (2930) · الدرعية (26738) · أبها (2951)

لكل نادٍ من هؤلاء، ولكل نادٍ نشط آخر بموسم 2026 لا يملك
logo_local، يطبع: هل له ملف محلي؟ ما رابط المزوّد؟ هل الرابط
شغّال (يرجع صورة فعلية)؟

⚠️ للقراءة فقط.

التشغيل:
    python check_logos.py
"""

import csv
import io
import os
import sqlite3
import urllib.request

CSV_FILE = "teams_arabic.csv"
DB = "football.db"

PROMOTED = {
    17472: ("JOR", "العربي"),
    22188: ("JOR", "دوقرة"),
    28222: ("IRQ", "الجولان"),
    28223: ("IRQ", "غاز الشمال"),
    2930: ("SAU", "الفيصلي"),
    26738: ("SAU", "الدرعية"),
    2951: ("SAU", "أبها"),
}


def clean(v):
    return (v or "").strip()


def url_ok(url, timeout=6):
    if not url:
        return None
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    if not os.path.exists(CSV_FILE):
        print("ما لقيت teams_arabic.csv")
        return

    with io.open(CSV_FILE, encoding="utf-8-sig") as f:
        rows = {int(r["team_id"]): r for r in csv.DictReader(f)
                if clean(r.get("team_id"))}

    print()
    print("=" * 62)
    print("  الأندية الصاعدة — حالة الشعار")
    print("=" * 62)

    missing_logo_file = []

    for tid, (lg, name_ar) in PROMOTED.items():
        r = rows.get(tid)
        if not r:
            print(f"\n  \u274c {tid} ({name_ar}) \u2014 غير موجود بالـCSV إطلاقاً")
            continue

        local = clean(r.get("logo_local"))
        remote = clean(r.get("logo"))
        has_file = bool(local) and os.path.exists(local)

        print(f"\n  {lg}  {name_ar}  (id={tid})")
        print(f"    logo_local : {local or '(فارغ)'}"
              f"  {'✅ موجود' if has_file else '❌ غير موجود' if local else ''}")
        print(f"    logo (مزوّد): {remote or '(فارغ)'}")

        if remote and not has_file:
            ok = url_ok(remote)
            mark = "✅ شغّال" if ok else "❌ لا يرجع صورة" if ok is False else "؟ غير مؤكد"
            print(f"    رابط المزوّد: {mark}")

        if not has_file:
            missing_logo_file.append((tid, lg, name_ar))

    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        active = {r[0] for r in conn.execute("""
            SELECT DISTINCT home_id FROM matches WHERE season = 2026
            UNION
            SELECT DISTINCT away_id FROM matches WHERE season = 2026
        """)}
        conn.close()

        no_local = [(tid, rows[tid]) for tid in active
                    if tid in rows
                    and not clean(rows[tid].get("logo_local"))]

        print()
        print("=" * 62)
        print(f"  كل الأندية النشطة 2026 بلا logo_local: {len(no_local)}")
        print("=" * 62)
        for tid, r in sorted(no_local, key=lambda x: x[1].get("league_code", "")):
            promoted_mark = " \u2b50 صاعد" if tid in PROMOTED else ""
            print(f"    {tid:>6}  {r.get('league_code'):<4} "
                  f"{r.get('short_name_ar', ''):<14}{promoted_mark}")

    print()
    print("=" * 62)
    if missing_logo_file:
        print(f"  \u274c {len(missing_logo_file)} نادٍ صاعد بلا ملف شعار محلي:")
        for tid, lg, name in missing_logo_file:
            print(f"      {tid}  {lg}  {name}")
    else:
        print("  \u2705 كل الأندية الصاعدة لها ملف شعار محلي بالفعل")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
