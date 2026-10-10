#!/usr/bin/env python3
"""
فحص عمود grid — هل يصلح لرسم ملعب؟
=====================================
`grid` من المزوّد بصيغة "صف:عمود" مثل "2:4".
رسم الملعب يعتمد عليه كلياً، فلو كان ناقصاً أو غير متسق
ينكسر التخطيط ولا يوجد بديل.

يفحص:
    1. كم لاعباً أساسياً بلا grid
    2. هل عدد الأساسيين = 11 دائماً
    3. هل الصفوف متسقة مع الخطة المعلنة (formation)
    4. عيّنة مرسومة نصياً لمباراة واحدة

⚠️ للقراءة فقط.

التشغيل:
    python check_grid.py
"""

import sqlite3
from collections import defaultdict

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print()
    print("=" * 58)
    print("  فحص عمود grid")
    print("=" * 58)

    # ── 1. الأساسيون بلا grid ─────────────────────────
    total = conn.execute("""
        SELECT COUNT(*) FROM lineup_players WHERE starter = 1
    """).fetchone()[0]

    no_grid = conn.execute("""
        SELECT COUNT(*) FROM lineup_players
        WHERE starter = 1 AND (grid IS NULL OR grid = '')
    """).fetchone()[0]

    pct = (no_grid / total * 100) if total else 0
    mark = "✅" if pct < 1 else "⚠️"
    print(f"\n  أساسيون إجمالاً : {total:,}")
    print(f"  بلا grid        : {no_grid:,}  ({pct:.2f}%)  {mark}")

    # ── 2. البدلاء ────────────────────────────────────
    subs = conn.execute("""
        SELECT COUNT(*) FROM lineup_players WHERE starter = 0
    """).fetchone()[0]
    subs_grid = conn.execute("""
        SELECT COUNT(*) FROM lineup_players
        WHERE starter = 0 AND grid IS NOT NULL AND grid != ''
    """).fetchone()[0]
    print(f"\n  بدلاء إجمالاً    : {subs:,}")
    print(f"  منهم لهم grid   : {subs_grid:,}  "
          f"(المتوقع 0 — البدلاء خارج الملعب)")

    # ── 3. هل الأساسيون 11 دائماً؟ ────────────────────
    print()
    print("-" * 58)
    print("  عدد الأساسيين لكل فريق في كل مباراة")
    print("-" * 58)
    counts = defaultdict(int)
    for r in conn.execute("""
            SELECT match_id, team_id, COUNT(*) AS n
            FROM lineup_players WHERE starter = 1
            GROUP BY match_id, team_id"""):
        counts[r["n"]] += 1

    for n in sorted(counts):
        mark = "✅" if n == 11 else "⚠️"
        print(f"    {n} لاعباً : {counts[n]:,} حالة  {mark}")

    # ── 4. الخطط المستعملة ────────────────────────────
    print()
    print("-" * 58)
    print("  الخطط الأكثر استعمالاً")
    print("-" * 58)
    for r in conn.execute("""
            SELECT formation, COUNT(*) AS n FROM lineups
            WHERE formation IS NOT NULL AND formation != ''
            GROUP BY formation ORDER BY n DESC LIMIT 12"""):
        print(f"    {r['formation']:<12} {r['n']:,}")

    empty_f = conn.execute("""
        SELECT COUNT(*) FROM lineups
        WHERE formation IS NULL OR formation = ''
    """).fetchone()[0]
    print(f"\n    بلا خطة معلنة: {empty_f}")

    # ── 5. رسم نصي لعيّنة ─────────────────────────────
    row = conn.execute("""
        SELECT l.match_id, l.team_id, l.formation
        FROM lineups l
        JOIN matches m ON m.match_id = l.match_id
        WHERE m.league_code = 'SAU' AND m.season = 2025
          AND l.formation IS NOT NULL AND l.formation != ''
        LIMIT 1
    """).fetchone()

    if not row:
        conn.close()
        return

    print()
    print("=" * 58)
    print(f"  عيّنة — مباراة {row['match_id']}  خطة {row['formation']}")
    print("=" * 58)

    rows = list(conn.execute("""
        SELECT player_en, number, pos, grid
        FROM lineup_players
        WHERE match_id = ? AND team_id = ? AND starter = 1
        ORDER BY grid
    """, (row["match_id"], row["team_id"])))

    by_row = defaultdict(list)
    bad = []
    for r in rows:
        g = (r["grid"] or "").strip()
        if ":" not in g:
            bad.append(r["player_en"])
            continue
        try:
            line, col = g.split(":", 1)
            by_row[int(line)].append((int(col), r))
        except ValueError:
            bad.append(r["player_en"])

    for line in sorted(by_row):
        players = sorted(by_row[line])
        print(f"\n  الصف {line}:")
        for col, r in players:
            print(f"    [{col}] #{r['number']:<3} {r['pos'] or '-':<2} "
                  f"{r['player_en']}")

    if bad:
        print(f"\n  ⚠️ grid غير صالح لـ{len(bad)}: {bad}")

    print(f"\n  عدد الصفوف: {len(by_row)}  |  "
          f"الخطة {row['formation']} = "
          f"{len(row['formation'].split('-')) + 1} صفوف متوقعة")

    conn.close()
    print()


if __name__ == "__main__":
    main()
