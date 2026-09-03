#!/usr/bin/env python3
"""
مطابقة التعادلات مع الفروقات
==============================
بعد إضافة المباريات السبع الناقصة، بقيت فروقات على 8 فرق —
نمطها: تعادل بالملعب تحوّل لحسم إداري 3-0.

هالسكربت بيطلّع كل تعادلات الفرق المتأثرة من الـDB، وبيجرّب
كل تحويل ممكن (تعادل → 3-0 لأحد الطرفين)، وبيلاقي المجموعة
اللي بتصفّر الفروقات مع الجدول الرسمي.

صفر طلبات API.

التشغيل:
    python match_draws.py
"""

import sqlite3
import sys
from itertools import combinations, product
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = "IRQ"
SEASON = 2025

# الجدول الرسمي (لعب, فاز, تعادل, خسر, له, عليه, نقاط)
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
    "بغداد":        (38, 10, 7, 21, 47, 68, 37),
    "النجف":        (38, 6, 7, 25, 33, 70, 25),
    "القاسم":       (38, 1, 2, 35, 20, 98, 5),
}

# المباريات السبع الناقصة — محسومة
MISSING = [
    ("الكهرباء", "النجف", 3, 0),
    ("بغداد", "زاخو", 3, 0),
    ("الطلبة", "النفط", 0, 3),
    ("القاسم", "الموصل", 0, 3),
    ("الكهرباء", "القاسم", 3, 0),
    ("الكرمة", "الكهرباء", 3, 0),
    ("ديالى", "الموصل", 3, 0),
]


def local_table(conn):
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


def apply_new(t, home, away, hg, ag):
    h, a = t[home], t[away]
    h[0] += 1; a[0] += 1
    h[4] += hg; h[5] += ag
    a[4] += ag; a[5] += hg
    if hg > ag:
        h[1] += 1; a[3] += 1; h[6] += 3
    elif hg < ag:
        h[3] += 1; a[1] += 1; a[6] += 3
    else:
        h[2] += 1; a[2] += 1; h[6] += 1; a[6] += 1


def convert_draw(t, winner, loser, old_wg, old_lg):
    """تعادل (old_wg-old_lg متساويين) يتحول: الفائز 3-0"""
    w, l = t[winner], t[loser]
    # شيل التعادل
    w[2] -= 1; l[2] -= 1
    w[6] -= 1; l[6] -= 1
    w[4] -= old_wg; w[5] -= old_lg
    l[4] -= old_lg; l[5] -= old_wg
    # ضيف الفوز 3-0
    w[1] += 1; l[3] += 1
    w[6] += 3
    w[4] += 3; l[5] += 3


def diff(t):
    n = 0
    det = []
    for nm, off in OFFICIAL.items():
        cur = t.get(nm)
        bad = [i for i in range(7) if cur[i] != off[i]]
        if bad:
            n += len(bad)
            det.append((nm, tuple(cur), off))
    return n, det


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    base = local_table(conn)

    # طبّق السبع الناقصة
    for h, a, hg, ag in MISSING:
        apply_new(base, h, a, hg, ag)

    n0, det0 = diff(base)
    print(f"\n{'=' * 62}")
    print(f"  بعد السبع الناقصة: {n0} خانة مختلفة")
    print(f"{'=' * 62}\n")

    # الفرق اللي لسا فيها فروقات
    affected = {x[0] for x in det0}
    print("  الفرق المتأثرة:", "، ".join(affected))

    # كل التعادلات بين فريقين متأثرين (أو فريق متأثر مع أي حد)
    id2name = {}
    for r in conn.execute("SELECT team_id, short_name_ar FROM teams"):
        id2name[r["team_id"]] = r["short_name_ar"]

    draws = []
    for m in conn.execute("""
        SELECT match_id, date, home_id, away_id, home_goals, away_goals
        FROM matches
        WHERE league_code=? AND season=? AND home_goals = away_goals
    """, (CODE, SEASON)):
        hn = id2name.get(m["home_id"], "?")
        an = id2name.get(m["away_id"], "?")
        if hn in affected and an in affected:
            draws.append((m["match_id"], m["date"], hn, an,
                          m["home_goals"], m["away_goals"]))

    print(f"\n  تعادلات بين فريقين متأثرين: {len(draws)}\n")
    for mid, d, hn, an, hg, ag in draws:
        print(f"      {d}  {hn} {hg}-{ag} {an}   id={mid}")

    # جرّب كل مجموعة تحويلات (كل تعادل: يبقى / يفوز المضيف / يفوز الضيف)
    print(f"\n  بجرّب 3^{len(draws)} = {3 ** len(draws):,} تركيبة ...\n")

    best = None
    for combo in product([0, 1, 2], repeat=len(draws)):
        t = {k: v[:] for k, v in base.items()}
        for (mid, d, hn, an, hg, ag), c in zip(draws, combo):
            if c == 1:
                convert_draw(t, hn, an, hg, ag)
            elif c == 2:
                convert_draw(t, an, hn, ag, hg)
        n, det = diff(t)
        if best is None or n < best[0]:
            best = (n, combo, det)
        if n == 0:
            break

    n, combo, det = best
    print(f"{'=' * 62}")
    print(f"  أفضل حل: {n} خانة مختلفة")
    print(f"{'=' * 62}\n")

    for (mid, d, hn, an, hg, ag), c in zip(draws, combo):
        if c == 0:
            continue
        winner = hn if c == 1 else an
        loser = an if c == 1 else hn
        print(f"  🔧 {d}  {hn} {hg}-{ag} {an}  →  "
              f"{winner} 3-0 {loser}   id={mid}")

    if n == 0:
        print("\n  ✅ مطابقة كاملة للجدول الرسمي — 20 فريقاً، 140 خانة")
    else:
        print(f"\n  الفروقات المتبقية:")
        for nm, cur, off in det:
            dd = [off[i] - cur[i] for i in range(7)]
            print(f"      {nm:<14} Δ = {tuple(dd)}")

    conn.close()


if __name__ == "__main__":
    main()
