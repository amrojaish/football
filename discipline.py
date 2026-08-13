#!/usr/bin/env python3
"""
إحصائيات الانضباط
===================
محسوبة من جدول events — أرقام لا يعطيها أي API جاهز.

يعرض:
  - أكثر اللاعبين بطاقات (مع تفصيل صفراء/حمراء)
  - انضباط الأندية (البطاقات لكل مباراة)
  - توزيع البطاقات على أوقات المباراة
  - توقيت التبديلات
  - المباريات الأكثر خشونة

⚠️ متوفر للدوري السعودي فقط — المزوّد لا يوفّر هذه الأحداث
   للأردني والعراقي (درس 17 في README).

صفر طلبات API.

التشغيل:
    python discipline.py              <- السعودي، كل المواسم
    python discipline.py SAU 2025     <- موسم محدد
"""

import sqlite3
import sys
from collections import defaultdict
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "SAU"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else None

YELLOW = "Yellow Card"
RED = "Red Card"
SECOND = "Second Yellow card"


def line(title=""):
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def bar(n, peak, width=26):
    if not peak:
        return ""
    return "█" * max(1, int(n / peak * width)) if n else ""


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM events LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول events غير موجود — شغّل add_events_table.py أول")
        conn.close()
        return

    where = "m.league_code = ?"
    params = [CODE]
    if SEASON is not None:
        where += " AND m.season = ?"
        params.append(SEASON)

    # عدد المباريات اللي عندها أحداث فعلاً
    n_matches = conn.execute(f"""
        SELECT COUNT(DISTINCT e.match_id)
        FROM events e JOIN matches m ON m.match_id = e.match_id
        WHERE {where} AND e.type != 'none'
    """, params).fetchone()[0]

    if not n_matches:
        name = LEAGUES.get(CODE, {}).get("name_ar", CODE)
        print(f"\n  ما في أحداث مخزّنة لـ{name}")
        print("  (المزوّد لا يوفّر البطاقات والتبديلات لهذا الدوري)\n")
        conn.close()
        return

    league_ar = LEAGUES.get(CODE, {}).get("name_ar", CODE)
    season_txt = f"موسم {SEASON}-{SEASON+1}" if SEASON else "كل المواسم"

    print(f"\n{'#' * 60}")
    print(f"#  إحصائيات الانضباط — {league_ar} · {season_txt}")
    print(f"{'#' * 60}")

    # ---- إجمالي ----
    tot = conn.execute(f"""
        SELECT
          SUM(CASE WHEN e.detail = ? THEN 1 ELSE 0 END) y,
          SUM(CASE WHEN e.detail = ? THEN 1 ELSE 0 END) r,
          SUM(CASE WHEN e.detail = ? THEN 1 ELSE 0 END) s,
          SUM(CASE WHEN e.type = 'subst' THEN 1 ELSE 0 END) sub
        FROM events e JOIN matches m ON m.match_id = e.match_id
        WHERE {where}
    """, [YELLOW, RED, SECOND] + params).fetchone()

    y, r, s, sub = tot["y"] or 0, tot["r"] or 0, tot["s"] or 0, tot["sub"] or 0
    cards = y + r + s

    print(f"""
  مباريات بأحداث: {n_matches}
  صفراء: {y}   |   حمراء مباشرة: {r}   |   صفراء ثانية: {s}
  إجمالي البطاقات: {cards}   ({cards / n_matches:.2f} بالمباراة)
  تبديلات: {sub}   ({sub / n_matches:.2f} بالمباراة)""")

    # ---- أكثر اللاعبين بطاقات ----
    line("أكثر اللاعبين بطاقات")

    rows = conn.execute(f"""
        SELECT e.player_en pl, t.short_name_ar tm,
               SUM(CASE WHEN e.detail = ? THEN 1 ELSE 0 END) y,
               SUM(CASE WHEN e.detail IN (?, ?) THEN 1 ELSE 0 END) r,
               COUNT(*) n
        FROM events e
        JOIN matches m ON m.match_id = e.match_id
        LEFT JOIN teams t ON t.team_id = e.team_id
        WHERE {where} AND e.type = 'Card' AND e.player_en != ''
        GROUP BY e.player_en, t.short_name_ar
        ORDER BY n DESC, r DESC LIMIT 12
    """, [YELLOW, RED, SECOND] + params).fetchall()

    print(f"\n  {'#':<3} {'اللاعب':<26} {'النادي':<14} "
          f"{'صفرا':>5} {'حمرا':>5} {'مجموع':>6}")
    print("  " + "-" * 62)
    for i, p in enumerate(rows, 1):
        print(f"  {i:<3} {p['pl'][:25]:<26} {(p['tm'] or '?'):<14} "
              f"{p['y']:>5} {p['r']:>5} {p['n']:>6}")

    # ---- انضباط الأندية ----
    line("انضباط الأندية (الأقل بطاقات لكل مباراة)")

    played = defaultdict(int)
    for m in conn.execute(f"""
        SELECT m.home_id h, m.away_id a FROM matches m
        WHERE {where.replace('e.', 'm.')}
    """, params):
        played[m["h"]] += 1
        played[m["a"]] += 1

    club = conn.execute(f"""
        SELECT e.team_id tid, t.short_name_ar tm,
               SUM(CASE WHEN e.detail = ? THEN 1 ELSE 0 END) y,
               SUM(CASE WHEN e.detail IN (?, ?) THEN 1 ELSE 0 END) r,
               COUNT(*) n
        FROM events e
        JOIN matches m ON m.match_id = e.match_id
        LEFT JOIN teams t ON t.team_id = e.team_id
        WHERE {where} AND e.type = 'Card'
        GROUP BY e.team_id, t.short_name_ar
    """, [YELLOW, RED, SECOND] + params).fetchall()

    ranked = []
    for c in club:
        p = played.get(c["tid"], 0)
        if p:
            ranked.append((c["tm"] or str(c["tid"]), c["y"], c["r"],
                           c["n"], c["n"] / p))
    ranked.sort(key=lambda x: x[4])

    print(f"\n  {'#':<3} {'النادي':<16} {'صفرا':>5} {'حمرا':>5} "
          f"{'مجموع':>6} {'بالمباراة':>10}")
    print("  " + "-" * 52)
    for i, (nm, cy, cr, cn, avg) in enumerate(ranked, 1):
        print(f"  {i:<3} {nm:<16} {cy:>5} {cr:>5} {cn:>6} {avg:>10.2f}")

    # ---- توزيع البطاقات على الوقت ----
    line("متى تُشهر البطاقات")

    mins = conn.execute(f"""
        SELECT e.minute mn FROM events e
        JOIN matches m ON m.match_id = e.match_id
        WHERE {where} AND e.type = 'Card' AND e.minute IS NOT NULL
    """, params).fetchall()

    buckets = defaultdict(int)
    for x in mins:
        buckets[min(x["mn"] // 15, 5)] += 1

    labels = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90+"]
    total = sum(buckets.values())
    peak = max(buckets.values()) if buckets else 1

    print()
    for i, lab in enumerate(labels):
        n = buckets.get(i, 0)
        pct = n / total * 100 if total else 0
        print(f"  {lab:>7}  {bar(n, peak)} {n} ({pct:.0f}%)")

    first = sum(buckets.get(i, 0) for i in (0, 1, 2))
    second = total - first
    print(f"\n  الشوط الأول: {first}  |  الشوط الثاني: {second}")
    if first:
        print(f"  نسبة الثاني للأول: {second / first:.2f}")

    # ---- توقيت التبديلات ----
    line("متى تحدث التبديلات")

    smins = conn.execute(f"""
        SELECT e.minute mn FROM events e
        JOIN matches m ON m.match_id = e.match_id
        WHERE {where} AND e.type = 'subst' AND e.minute IS NOT NULL
    """, params).fetchall()

    sb = defaultdict(int)
    for x in smins:
        sb[min(x["mn"] // 15, 5)] += 1

    st = sum(sb.values())
    speak = max(sb.values()) if sb else 1

    print()
    for i, lab in enumerate(labels):
        n = sb.get(i, 0)
        pct = n / st * 100 if st else 0
        print(f"  {lab:>7}  {bar(n, speak)} {n} ({pct:.0f}%)")

    # ---- أخشن المباريات ----
    line("المباريات الأكثر بطاقات")

    rough = conn.execute(f"""
        SELECT m.match_id id, m.date d,
               h.short_name_ar hn, a.short_name_ar an,
               m.home_goals hg, m.away_goals ag,
               COUNT(*) n,
               SUM(CASE WHEN e.detail IN (?, ?) THEN 1 ELSE 0 END) reds
        FROM events e
        JOIN matches m ON m.match_id = e.match_id
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE {where} AND e.type = 'Card'
        GROUP BY m.match_id
        ORDER BY n DESC, reds DESC LIMIT 6
    """, [RED, SECOND] + params).fetchall()

    print()
    for i, x in enumerate(rough, 1):
        reds = f"  ({x['reds']} حمرا)" if x["reds"] else ""
        print(f"  {i}. {x['hn']} {x['hg']}-{x['ag']} {x['an']}"
              f"   ({x['d']})   {x['n']} بطاقة{reds}")

    print(f"""
{'=' * 60}
  كل رقم أعلاه محسوب من الأحداث الخام.
  ما في API بيعطيك انضباط الأندية ولا توزيع البطاقات.
{'=' * 60}
    """)

    conn.close()


if __name__ == "__main__":
    main()
