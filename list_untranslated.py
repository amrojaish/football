#!/usr/bin/env python3
"""
كل لاعب غير مترجَم — من كل الجداول
=====================================
`players_ar.csv` يُبنى من `goals` فقط، فيغفل لاعبي التشكيلات
الذين لم يسجّلوا أهدافاً — وهم **مرئيون فعلاً** بالملعب المرسوم
في صفحات المباريات.

يفحص كل جدول فيه أسماء لاعبين ويجمع غير المترجَم منها:
    goals · lineup_players · player_stats · events

لكل اسم: كم مرة ظهر، وبأي جدول، وبأي دوري — لترتيب الأولوية.

⚠️ للقراءة فقط. يكتب `untranslated.txt` للمراجعة.

التشغيل:
    python list_untranslated.py
"""

import io
import os
import sqlite3
from collections import defaultdict

DB = "football.db"
OUT = "untranslated.txt"


def clean(v):
    return (v or "").strip()


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    print()
    print("=" * 62)
    print(f"  جداول الديتابيس: {len(tables)}")
    print("=" * 62)
    print("  " + " · ".join(sorted(tables)))

    # ── الأسماء المترجَمة (من أي جدول) ───────────────
    translated = set()
    counts = defaultdict(int)
    sources = defaultdict(set)
    leagues = defaultdict(set)

    CANDIDATES = ["goals", "lineup_players", "player_stats", "events"]

    print()
    print("=" * 62)
    print("  مسح الجداول")
    print("=" * 62)

    for tbl in CANDIDATES:
        if tbl not in tables:
            print(f"    {tbl:<18} — غير موجود")
            continue

        cols = {c[1] for c in conn.execute(f"PRAGMA table_info({tbl})")}
        if "player_en" not in cols:
            print(f"    {tbl:<18} — لا عمود player_en")
            continue

        has_ar = "player_ar" in cols
        has_match = "match_id" in cols

        if has_match:
            q = f"""
                SELECT t.player_en AS en,
                       {"t.player_ar AS ar," if has_ar else "'' AS ar,"}
                       m.league_code AS lg
                FROM {tbl} t
                LEFT JOIN matches m ON m.match_id = t.match_id
                WHERE t.player_en IS NOT NULL AND t.player_en != ''
            """
        else:
            q = f"""
                SELECT player_en AS en,
                       {"player_ar AS ar," if has_ar else "'' AS ar,"}
                       '' AS lg
                FROM {tbl}
                WHERE player_en IS NOT NULL AND player_en != ''
            """

        n = 0
        for r in conn.execute(q):
            en = clean(r["en"])
            if not en:
                continue
            if clean(r["ar"]):
                translated.add(en)
            counts[en] += 1
            sources[en].add(tbl)
            if clean(r["lg"]):
                leagues[en].add(r["lg"])
            n += 1

        print(f"    {tbl:<18} {n:>7} سجل")

    conn.close()

    # ── غير المترجَم ─────────────────────────────────
    missing = [(en, c) for en, c in counts.items()
               if en not in translated]
    missing.sort(key=lambda x: -x[1])

    print()
    print("=" * 62)
    print(f"  أسماء فريدة إجمالاً : {len(counts):,}")
    print(f"  مترجَمة             : {len(translated):,}")
    print(f"  **غير مترجَمة**     : {len(missing):,}")
    print("=" * 62)

    if not missing:
        print("\n  ✅ كل الأسماء مترجَمة\n")
        return

    # توزيع حسب الدوري
    by_lg = defaultdict(int)
    for en, _ in missing:
        for lg in (leagues.get(en) or {"?"}):
            by_lg[lg] += 1

    print("\n  حسب الدوري:")
    for lg in sorted(by_lg):
        print(f"    {lg or '?':<5} {by_lg[lg]:>5}")

    # توزيع حسب مرات الظهور
    buckets = [("50+", 50), ("20-49", 20), ("10-19", 10),
               ("5-9", 5), ("2-4", 2), ("مرة واحدة", 1)]
    print("\n  حسب مرات الظهور:")
    prev = 10 ** 9
    for label, lo in buckets:
        n = sum(1 for _, c in missing if lo <= c < prev)
        print(f"    {label:<12} {n:>5}")
        prev = lo

    # ── كتابة الملف ──────────────────────────────────
    out = io.StringIO()
    out.write(f"أسماء غير مترجَمة — {len(missing)} اسماً\n")
    out.write("=" * 55 + "\n\n")

    grouped = defaultdict(list)
    for en, c in missing:
        lg = " · ".join(sorted(leagues.get(en) or [])) or "?"
        grouped[lg].append((en, c))

    for lg in sorted(grouped):
        out.write(f"--- {lg} ---\n")
        for en, c in grouped[lg]:
            out.write(f"   {en}  ({c})\n")
        out.write("\n")

    io.open(OUT, "w", encoding="utf-8").write(out.getvalue())

    print(f"\n  كُتب {OUT}")
    print()


if __name__ == "__main__":
    main()
