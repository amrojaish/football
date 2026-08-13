#!/usr/bin/env python3
"""
حل المباريات الناقصة
======================
بيقارن جدولنا مع الجدول الرسمي، وبيجرّب كل النتائج الممكنة
للمباريات الناقصة، ويلاقي التركيبة اللي بتصفّر الفروقات.

المشكلة اللي بيحلها:
لما يكون في مباريات مش موجودة بالـAPI (محسومة إدارياً/ملغاة)،
الفرق بين جدولنا والرسمي بيتوزّع على كل الفرق. الحساب اليدوي
بيصير معقد لأن كل مباراة بتأثر على فريقين.

صفر طلبات API.

التشغيل:
    python solve_missing.py
"""

import sqlite3
import sys
from itertools import product
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = "IRQ"
SEASON = 2025

# ---------------------------------------------------------------
# الجدول الرسمي — من مصدر خارجي (صورة الاتحاد/التطبيق)
# الاسم: (لعب, فاز, تعادل, خسر, له, عليه, نقاط)
# ---------------------------------------------------------------
OFFICIAL = {
    "القوة الجوية": (38, 27, 8, 3, 62, 28, 89),
    "الشرطة":       (38, 25, 7, 6, 71, 29, 82),
    "أربيل":        (38, 23, 10, 5, 59, 32, 79),
    "الزوراء":      (38, 17, 15, 6, 50, 32, 66),
    "الكرمة":       (38, 17, 14, 7, 53, 26, 65),
    "الطلبة":       (38, 18, 11, 9, 53, 38, 65),
    "الكرخ":        (38, 16, 12, 10, 51, 41, 60),
    "نوروز":        (38, 16, 6, 16, 48, 47, 54),
    "زاخو":         (38, 14, 11, 13, 49, 45, 53),
    "دهوك":         (38, 13, 11, 14, 44, 45, 50),
    "النفط":        (38, 11, 15, 12, 33, 34, 48),
    "ديالى":        (38, 13, 9, 16, 39, 46, 48),
    "الموصل":       (38, 11, 14, 13, 46, 49, 47),
    "الغراف":       (38, 11, 11, 16, 40, 43, 44),
    "الميناء":      (38, 10, 12, 16, 41, 47, 42),
    "نفط ميسان":    (38, 11, 9, 18, 46, 58, 42),
    "الكهرباء":     (38, 12, 5, 21, 47, 56, 41),
    "بغداد":  (38, 10, 7, 21, 47, 68, 37),
    "النجف":        (38, 6, 7, 25, 33, 70, 25),
    "القاسم":       (38, 1, 2, 35, 20, 98, 5),
}

# المباريات الناقصة — (المضيف, الضيف) حسب find_missing.py
MISSING = [
    ("الكهرباء", "النجف"),
    ("الكهرباء", "القاسم"),
    ("الكرمة",   "الكهرباء"),
    ("الطلبة",   "النفط"),
    ("بغداد", "زاخو"),
    ("القاسم",   "الموصل"),
    ("ديالى",    "الموصل"),
]

# النتائج المرشحة لكل مباراة (بيت-ضيف)
# الحسم الإداري عادة 3-0 أو 0-3
CANDIDATES = [(3, 0), (0, 3), (2, 0), (0, 2)]


def local_table(conn):
    """الجدول المحسوب من الـDB"""
    rows = conn.execute("""
        WITH g AS (
            SELECT home_id t, home_goals gf, away_goals ga
            FROM matches WHERE league_code=? AND season=?
            UNION ALL
            SELECT away_id, away_goals, home_goals
            FROM matches WHERE league_code=? AND season=?
        )
        SELECT t.short_name_ar nm,
            COUNT(*) p,
            SUM(CASE WHEN gf>ga THEN 1 ELSE 0 END) w,
            SUM(CASE WHEN gf=ga THEN 1 ELSE 0 END) d,
            SUM(CASE WHEN gf<ga THEN 1 ELSE 0 END) l,
            SUM(gf) gf, SUM(ga) ga,
            SUM(CASE WHEN gf>ga THEN 3 WHEN gf=ga THEN 1 ELSE 0 END) pts
        FROM g JOIN teams t ON t.team_id = g.t
        GROUP BY t.short_name_ar
    """, (CODE, SEASON, CODE, SEASON)).fetchall()
    return {r["nm"]: [r["p"], r["w"], r["d"], r["l"],
                      r["gf"], r["ga"], r["pts"]] for r in rows}


def apply_result(tbl, home, away, hg, ag):
    """بيضيف نتيجة للجدول"""
    h, a = tbl[home], tbl[away]
    h[0] += 1
    a[0] += 1
    h[4] += hg
    h[5] += ag
    a[4] += ag
    a[5] += hg
    if hg > ag:
        h[1] += 1
        a[3] += 1
        h[6] += 3
    elif hg < ag:
        h[3] += 1
        a[1] += 1
        a[6] += 3
    else:
        h[2] += 1
        a[2] += 1
        h[6] += 1
        a[6] += 1


def diff_count(tbl):
    """كم خانة مختلفة عن الرسمي"""
    n = 0
    detail = []
    for nm, off in OFFICIAL.items():
        cur = tbl.get(nm)
        if cur is None:
            n += 7
            detail.append((nm, "مفقود"))
            continue
        bad = [i for i in range(7) if cur[i] != off[i]]
        if bad:
            n += len(bad)
            detail.append((nm, tuple(cur), off))
    return n, detail


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    base = local_table(conn)

    # فحص الأسماء
    missing_names = [nm for nm in OFFICIAL if nm not in base]
    if missing_names:
        print("⚠️ أسماء بالجدول الرسمي مش موجودة بالـDB:")
        for nm in missing_names:
            print(f"      {nm}")
        print("\n  الأسماء الموجودة بالـDB:")
        for nm in sorted(base):
            print(f"      {nm}")
        conn.close()
        return

    n0, d0 = diff_count({k: v[:] for k, v in base.items()})
    print(f"\n{'=' * 62}")
    print(f"  قبل الإضافة: {n0} خانة مختلفة عن الرسمي")
    print(f"{'=' * 62}")

    print(f"\n  بجرّب {len(CANDIDATES)}^{len(MISSING)} = "
          f"{len(CANDIDATES) ** len(MISSING):,} تركيبة ...\n")

    best = []
    for combo in product(CANDIDATES, repeat=len(MISSING)):
        tbl = {k: v[:] for k, v in base.items()}
        for (home, away), (hg, ag) in zip(MISSING, combo):
            apply_result(tbl, home, away, hg, ag)
        n, det = diff_count(tbl)
        best.append((n, combo, det))

    best.sort(key=lambda x: x[0])

    for rank, (n, combo, det) in enumerate(best[:3], 1):
        print(f"{'=' * 62}")
        print(f"  الاحتمال {rank} — {n} خانة مختلفة")
        print(f"{'=' * 62}")
        for (home, away), (hg, ag) in zip(MISSING, combo):
            print(f"      {home}  {hg} - {ag}  {away}")
        if n == 0:
            print("\n      ✅ مطابقة كاملة للجدول الرسمي")
            break
        if det and rank == 1:
            print(f"\n      الفروقات المتبقية:")
            print(f"      {'الفريق':<16} {'عندنا (ل ف ت خ له عليه ن)':<32} الرسمي")
            for x in det[:8]:
                if len(x) == 3:
                    nm, cur, off = x
                    print(f"      {nm:<16} {str(cur):<32} {off}")
        print()

    conn.close()


if __name__ == "__main__":
    main()
