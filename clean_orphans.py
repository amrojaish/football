#!/usr/bin/env python3
"""
حذف الصفحات اليتيمة
=====================
المولّدات تكتب ولا تحذف. أي اسم لاعب يُدمَج أو يُصحَّح يترك
صفحته القديمة للأبد — لا يصلها زائر، لكنها **تدخل خريطة
الموقع** (تُبنى من الملفات لا الديتابيس) فتُقدَّم لجوجل
كصفحات رقيقة.

⚠️ **الأمان:** يبني قائمة الصفحات المتوقَّعة بنفس منطق
   `make_players.py` و`make_clubs.py` و`make_matches.py`،
   ويحذف ما ليس فيها **فقط**.

    python clean_orphans.py --check    <- عرض بلا حذف
    python clean_orphans.py            <- تنفيذ
"""
import os
import sqlite3
import sys

from config import DB_FILE, BASE_DIR
from player_slug import build_slug_map

CHECK = "--check" in sys.argv
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def expected_players(conn):
    """
    ⚠️ **يطابق `make_players.py` حرفياً:** الصفحات تُبنى من
       `goals` وحدها، وبخريطة {اسم: عدد أهداف} لأن
       `build_slug_map` يمنح الرابط النظيف للأكثر أهدافاً عند
       التصادم. جمعُ الأسماء من جداول أخرى — أو تمريرُ مجموعة
       بلا أعداد — يغيّر الروابط ويحذف صفحات سليمة.
    """
    counts = {}
    for name, n in conn.execute(
            "SELECT player_en, COUNT(*) FROM goals "
            "WHERE player_en IS NOT NULL AND player_en != '' "
            "GROUP BY player_en"):
        counts[name] = n
    return {f"{s}.html" for s in build_slug_map(counts).values()}


def expected_clubs(conn):
    return {f"{r[0]}.html" for r in
            conn.execute("SELECT team_id FROM teams")}


def expected_matches(conn):
    return {f"{r[0]}.html" for r in
            conn.execute("SELECT match_id FROM matches")}


def sweep(folder, keep, label):
    total = removed = 0
    for base in (BASE_DIR / folder, BASE_DIR / "en" / folder):
        if not base.is_dir():
            continue
        for f in base.glob("*.html"):
            total += 1
            if f.name in keep:
                continue
            removed += 1
            if not CHECK:
                f.unlink()
    print(f"  {label:10} موجود: {total:5}   يتيم: {removed:5}")
    return removed


def main():
    conn = sqlite3.connect(DB_FILE)
    print()
    print("=" * 52)
    print("  فحص الصفحات اليتيمة" if CHECK else "  حذف الصفحات اليتيمة")
    print("=" * 52)

    n = 0
    n += sweep("players", expected_players(conn), "لاعبون")
    n += sweep("clubs", expected_clubs(conn), "أندية")
    n += sweep("matches", expected_matches(conn), "مباريات")

    print("=" * 52)
    if CHECK:
        print(f"  [وضع الفحص] — ما انحذف شي.  يتيم: {n}")
    else:
        print(f"  حُذف: {n}")
        if n:
            print("\n  ⚠️ أعد توليد الخريطة:  python make_sitemap.py")
    print("=" * 52)
    conn.close()


if __name__ == "__main__":
    main()
