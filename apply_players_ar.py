#!/usr/bin/env python3
"""
تطبيق أسماء اللاعبين العربية
===============================
بيقرأ players_ar.csv وبيعبّي عمود player_ar بجداول:
    goals
    lineup_players
    player_stats
    events (إذا موجود)

⚠️ المطابقة **نصية** على player_en لأن جدول goals لا يخزّن
   player_id (خطأ بنيوي مبكر — درس 26). لو كتب المزوّد الاسم
   بصيغتين مختلفتين، يُعامَلان كلاعبَين.

   عمودان اختياريان بـplayers_ar.csv — player_id وteam_id —
   يسمحان بتقييد صف معيّن بمعرّف محدد عند وجود تصادم نصي حقيقي
   مع لاعب آخر بنفس player_en (بند 27، فئة أ-1). فارغان = نفس
   السلوك القديم (مطابقة نصية عامة بلا قيد). القيد يُطبَّق فقط
   على الجداول اللي عندها العمود المطلوب فعلياً — goals وevents
   ما عندهم player_id (نفس الخطأ البنيوي أعلاه)، فلو صف حدد
   player_id بس بلا team_id، بيتخطى تحديث هذين الجدولين بدل ما
   يحدّثهم بلا قيد (يطبع تنبيه بالمخرجات).

الأسماء الفارغة تُتخطّى — الكود يرتد للإنجليزي.

صفر طلبات API.

التشغيل:
    python apply_players_ar.py --check    <- عرض بس
    python apply_players_ar.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR

SOURCE = BASE_DIR / "players_ar.csv"
CHECK_ONLY = "--check" in sys.argv

# الأعمدة اللي ممكن نقيّد التحديث فيها، إذا وُجدت بملف الـCSV
# وبالجدول الهدف معاً
CONSTRAINT_COLS = ("player_id", "team_id")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def has_table(conn, name):
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def table_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def load_rows():
    """يرجّع لائحة صفوف {en, ar, player_id, team_id} — لائحة لا
    قاموس، عشان نفس player_en ممكن يتكرر بمعرّفات مختلفة (حالة
    تصادم نصي حقيقي مع لاعب تاني)."""
    rows = []
    seen_unconstrained = set()
    with open(SOURCE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            en = (r.get("player_en") or "").strip()
            ar = (r.get("player_ar") or "").strip()
            if not (en and ar):
                continue

            pid = (r.get("player_id") or "").strip()
            tid = (r.get("team_id") or "").strip()

            if not pid and not tid:
                if en in seen_unconstrained:
                    print(f"  ⚠️ تكرار غير مقيَّد لنفس الاسم بالملف: {en} "
                          f"— الصف الأول بس هو يلي بينطبق")
                    continue
                seen_unconstrained.add(en)

            rows.append({
                "en": en, "ar": ar,
                "player_id": pid or None,
                "team_id": tid or None,
            })
    return rows


def build_where(row, cols_in_table):
    """يرجّع (where_sql, params, unusable) لصف معيّن مقابل جدول
    معيّن. where_sql بيرجع None إذا الصف طالب قيداً وولا عمود
    منه موجود بهاد الجدول — يعني: تخطّي الجدول لهذا الصف."""
    where = ["player_en = ?"]
    params = [row["en"]]

    requested = {c: row[c] for c in CONSTRAINT_COLS if row[c]}
    if not requested:
        return " AND ".join(where), params, []

    usable = {c: v for c, v in requested.items() if c in cols_in_table}
    unusable = [c for c in requested if c not in cols_in_table]

    if not usable:
        return None, None, unusable

    for c, v in usable.items():
        where.append(f"{c} = ?")
        params.append(v)

    return " AND ".join(where), params, unusable


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not SOURCE.exists():
        print(f"ما لقيت {SOURCE.name}")
        print("شغّل: python export_players_ar.py")
        return

    rows = load_rows()

    print(f"\n{'=' * 58}")
    print(f"  أسماء مترجَمة بالملف: {len(rows)}")
    constrained = sum(1 for r in rows if r["player_id"] or r["team_id"])
    if constrained:
        print(f"  منها مقيَّد بمعرّف (player_id/team_id): {constrained}")
    print(f"{'=' * 58}")

    if not rows:
        print("\n  ما في أسماء مترجمة — عبّي عمود player_ar أول\n")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    targets = ["goals"]
    for t in ("lineup_players", "player_stats", "events"):
        if has_table(conn, t):
            targets.append(t)

    cols_by_table = {t: table_columns(conn, t) for t in targets}

    total = 0
    skipped = []  # (en, table, unusable_cols) — تشخيصي بس

    for table in targets:
        cols = cols_by_table[table]

        before = conn.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """).fetchone()[0]

        will = 0
        for row in rows:
            ar = row["ar"]
            where, params, unusable = build_where(row, cols)

            if where is None:
                skipped.append((row["en"], table, unusable))
                continue

            n = conn.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE {where}
                  AND (player_ar IS NULL OR player_ar = '' OR player_ar != ?)
            """, (*params, ar)).fetchone()[0]
            will += n

            if not CHECK_ONLY and n:
                conn.execute(f"""
                    UPDATE {table} SET player_ar = ?
                    WHERE {where}
                """, (ar, *params))

        if not CHECK_ONLY:
            conn.commit()

        after = conn.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE player_ar IS NOT NULL AND player_ar != ''
        """).fetchone()[0]

        print(f"\n  {table}")
        print(f"      سجلات متأثرة : {will}")
        if not CHECK_ONLY:
            print(f"      قبل → بعد     : {before} → {after}")
        total += will

    # الأسماء اللي ما لقت مطابق (فحص نصي بمعزل عن أي قيد)
    missing = []
    for row in rows:
        n = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE player_en = ?",
            (row["en"],)).fetchone()[0]
        if n == 0:
            missing.append(row["en"])

    conn.close()

    print(f"\n{'=' * 58}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انكتب شي")
    print(f"  إجمالي السجلات المتأثرة: {total}")
    print(f"{'=' * 58}")

    if skipped:
        print(f"\n  ⚠️ {len(skipped)} حالة تخطّت جدولاً لعدم توفّر عمود "
              f"القيد المطلوب فيه:")
        for en, table, unusable in skipped[:10]:
            print(f"      {en} → {table} (ناقص: {', '.join(unusable)})")
        if len(skipped) > 10:
            print(f"      ... و{len(skipped) - 10} غيرهم")

    if missing:
        print(f"\n  ⚠️ {len(missing)} اسم بالملف ما لقى مطابق بجدول goals:")
        for en in missing[:10]:
            print(f"      {en}")
        if len(missing) > 10:
            print(f"      ... و{len(missing) - 10} غيرهم")
        print("  (تأكد من التطابق الحرفي مع اسم المزوّد)")

    if total and not CHECK_ONLY:
        print("""
  الخطوة الجاية:
      python make_site3.py
      python make_clubs.py
      python make_matches.py
        """)


if __name__ == "__main__":
    main()
