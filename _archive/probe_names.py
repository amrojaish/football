#!/usr/bin/env python3
"""
تحقيق: أسماء لاعبين ملتصقة بأرقام
====================================
`fix_spaces.py --check` كشف 43 قيمة في جدول goals بهذا الشكل:

    '5                         Mohammed Al Jahif'
    'I. Toney                                  6'
    '0                         Cristiano Ronaldo'

الرقم أحياناً **قبل** الاسم وأحياناً **بعده** — أي أن حقلين
انضغطا في حقل واحد أثناء السحب أو الاستيراد.

⚠️ **خطر:** تنظيف المسافات وحده يحوّلها إلى '5 Mohammed Al Jahif'
   — أي يحفظ الرقم داخل الاسم إلى الأبد ويطمس دليل الخطأ.

هذا السكربت **يشخّص فقط**: يعرض السجل كاملاً، والمباريات
المتأثرة، وهل للاعب صيغة نظيفة موجودة أصلاً.

⚠️ للقراءة فقط. لا يعدّل شيئاً.

التشغيل:
    python probe_names.py
"""

import re
import sqlite3

DB = "football.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute("""
        SELECT * FROM goals
        WHERE player_en LIKE '%  %'
        ORDER BY match_id
    """))

    print()
    print("=" * 62)
    print(f"  سجلات فيها مسافات متعددة: {len(rows)}")
    print("=" * 62)

    # ── السجل كاملاً — لرؤية كل الأعمدة ──────────────
    print("\n  أول 3 سجلات كاملة:\n")
    for r in rows[:3]:
        print(f"    {dict(r)}\n")

    # ── تحليل النمط ──────────────────────────────────
    print("-" * 62)
    print("  تحليل النمط")
    print("-" * 62)

    before = after = other = 0
    clean_names = {}

    for r in rows:
        v = r["player_en"]
        parts = v.split()
        if not parts:
            continue
        if parts[0].isdigit():
            before += 1
            name = " ".join(parts[1:])
        elif parts[-1].isdigit():
            after += 1
            name = " ".join(parts[:-1])
        else:
            other += 1
            name = " ".join(parts)
        clean_names.setdefault(name, 0)
        clean_names[name] += 1

    print(f"    الرقم **قبل** الاسم : {before}")
    print(f"    الرقم **بعد** الاسم : {after}")
    print(f"    بلا رقم واضح        : {other}")

    # ── هل الاسم النظيف موجود أصلاً؟ ─────────────────
    print()
    print("-" * 62)
    print("  هل توجد صيغة نظيفة لنفس اللاعب؟")
    print("-" * 62)

    exists = missing = 0
    for name in sorted(clean_names):
        n = conn.execute("""
            SELECT COUNT(player_en) FROM goals WHERE player_en = ?
        """, (name,)).fetchone()[0]
        mark = "✅ موجود" if n else "❌ غير موجود"
        if n:
            exists += 1
        else:
            missing += 1
        print(f"    {name:<34} {mark}  ({n} هدف نظيف)")

    print()
    print("=" * 62)
    print(f"  أسماء لها صيغة نظيفة : {exists}")
    print(f"  أسماء بلا صيغة نظيفة : {missing}")
    print("=" * 62)

    # ── المواسم المتأثرة ─────────────────────────────
    print("\n  المواسم والدوريات المتأثرة:")
    q = """
        SELECT m.league_code, m.season, COUNT(g.player_en) AS n
        FROM goals g JOIN matches m ON m.match_id = g.match_id
        WHERE g.player_en LIKE '%  %'
        GROUP BY m.league_code, m.season
        ORDER BY m.season
    """
    for r in conn.execute(q):
        print(f"    {r['league_code']}  {r['season']}   {r['n']} هدف")

    conn.close()
    print()


if __name__ == "__main__":
    main()
