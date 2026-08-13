#!/usr/bin/env python3
"""
إيجاد المواجهات الناقصة
=========================
بنظام الذهاب والإياب، كل فريقين لازم يتقابلوا مرتين.
هالسكربت بيلاقي الأزواج اللي تقابلوا أقل من المطلوب.

بيفيد لما يكون عدد المباريات أقل من المتوقع — بيحدد
بالضبط أي مباراة ناقصة، مش بس كم وحدة.

صفر طلبات API.

التشغيل:
    python find_missing.py IRQ 2025
    python find_missing.py IRQ 2025 3     <- نظام 3 مراحل
"""

import sqlite3
import sys
from collections import defaultdict
from config import DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "IRQ"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 2


def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    names = {}
    for r in conn.execute(
        "SELECT team_id, short_name_ar, name_en FROM teams"
    ):
        names[r["team_id"]] = (r["short_name_ar"] or r["name_en"]
                               or str(r["team_id"]))

    # كل الأندية اللي لعبت بهالموسم
    ids = set()
    pairs = defaultdict(list)

    for m in conn.execute("""
        SELECT match_id, date, home_id, away_id, home_goals, away_goals
        FROM matches WHERE league_code = ? AND season = ?
    """, (CODE, SEASON)):
        h, a = m["home_id"], m["away_id"]
        ids.add(h)
        ids.add(a)
        key = tuple(sorted((h, a)))
        pairs[key].append(m)

    ids = sorted(ids)
    n = len(ids)

    league_ar = LEAGUES.get(CODE, {}).get("name_ar", CODE)
    expected_pairs = n * (n - 1) // 2
    expected_matches = expected_pairs * ROUNDS

    print(f"\n{'=' * 62}")
    print(f"  المواجهات الناقصة — {league_ar} / موسم {SEASON}")
    print(f"{'=' * 62}")
    print(f"""
  أندية: {n}
  أزواج ممكنة: {expected_pairs}
  مباريات متوقعة ({ROUNDS} مراحل): {expected_matches}
  مباريات موجودة: {sum(len(v) for v in pairs.values())}""")

    # الأزواج الناقصة
    missing = []
    for i in range(n):
        for j in range(i + 1, n):
            key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
            got = len(pairs.get(key, []))
            if got < ROUNDS:
                missing.append((key, got))

    if not missing:
        print("\n  ✅ كل المواجهات مكتملة\n")
        conn.close()
        return

    print(f"\n{'=' * 62}")
    print(f"  أزواج ناقصة: {len(missing)}")
    print(f"{'=' * 62}\n")

    for (a, b), got in missing:
        na, nb = names.get(a, str(a)), names.get(b, str(b))
        print(f"  ⚠️  {na}  ×  {nb}   "
              f"(موجود {got} من {ROUNDS})")

        played = pairs.get((a, b), [])
        for m in played:
            hn = names.get(m["home_id"], "?")
            an = names.get(m["away_id"], "?")
            print(f"        لُعبت: {m['date']}  {hn} "
                  f"{m['home_goals']}-{m['away_goals']} {an}")
        if not played:
            print("        لم تُلعب أي مواجهة بينهما")
        print()

    # ملخص لكل فريق
    print(f"{'=' * 62}")
    print("  كم مباراة ناقصة لكل فريق")
    print(f"{'=' * 62}\n")

    short = defaultdict(int)
    for (a, b), got in missing:
        short[a] += ROUNDS - got
        short[b] += ROUNDS - got

    for tid, k in sorted(short.items(), key=lambda x: -x[1]):
        print(f"      {k}  ناقصة   {names.get(tid, tid)}")

    print(f"\n{'=' * 62}\n")
    conn.close()


if __name__ == "__main__":
    main()
