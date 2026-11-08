#!/usr/bin/env python3
"""
تطبيق تصحيحات النتائج اليدوية
================================
بيقرأ match_corrections.csv وبيصحّح النتائج بالديتابيس.

ليش موجود:
الـAPI أحياناً بيحتفظ بنتيجة خاطئة (هدف ملغي، نتيجة محسومة إدارياً).
أي سحب جديد بيرجّع الغلط، فهالسكربت بينطبّق بعد كل سحب.

أعمدة اختيارية (6 نوفمبر 2026، الموجة 2b — فارغة = بلا لمس):
    ft_home, ft_away, et_home, et_away   تفصيل النتيجة (match_score: 90 د / أهداف الإضافي وحدها) — فقط بعد هجرة match_score
    exclude_goals                        أهداف تُحذف من goals بكل تشغيل: «الدقيقة|اسم اللاعب» مفصولة بـ«;»
                                         (مثال: ركلتا ترجيح بلا وسم comments عند المزوّد «120|B. Hasni;120|A. Hichri»)
                                         حذف لا أرشفة: cancelled_goals تُعرض «هدفاً ملغى» بصفحة المباراة.
                                         هدف بلا اسم لاعب (الموجة 5ب): «الدقيقة||معرّف الفريق» (مثال: «54||5400»)
كلها تبقى بعد أي إعادة سحب لأن السكربت يُعاد بعد كل سحب (update_all: «تصحيح النتائج»).

صفر طلبات API.

التشغيل:
    python apply_corrections.py --check    <- عرض بس
    python apply_corrections.py            <- تنفيذ
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR
import match_score as MS

CORRECTIONS_FILE = BASE_DIR / "match_corrections.csv"
CHECK_ONLY = "--check" in sys.argv
SCORE_COLS = ("ft_home", "ft_away", "et_home", "et_away")


def _opt_int(v):
    v = (v or "").strip()
    return int(v) if v else None


def parse_excludes(spec):
    """«120|B. Hasni;54||5400» -> [(120, "B. Hasni"), (54, "", 5400)] — الثلاثية = هدف بلا اسم، بالدقيقة + الفريق"""
    out = []
    for part in (spec or "").split(";"):
        part = part.strip()
        if not part:
            continue
        minute, _, rest = part.partition("|")
        player, _, team = rest.partition("|")
        if player.strip() and not team.strip():
            out.append((int(minute), player.strip()))
        elif not player.strip() and team.strip().isdigit():
            out.append((int(minute), "", int(team)))
        else:
            raise ValueError(f"exclude_goals: صيغة «الدقيقة|اللاعب» أو «الدقيقة||معرّف الفريق» مطلوبة: {part!r}")
    return out


def load_rows(path=CORRECTIONS_FILE):
    with open(path, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if (r.get("match_id") or "").strip()]


def apply_rows(conn, rows, check_only=False):
    """يطبّق التصحيحات على conn (بلا commit). يرجّع (applied, already, notfound)."""
    prev, conn.row_factory = conn.row_factory, sqlite3.Row
    try:
        return _apply_rows(conn, rows, check_only)
    finally:
        conn.row_factory = prev


def _apply_rows(conn, rows, check_only):
    score_ok = MS.has_score(conn)
    applied = already = notfound = 0

    for r in rows:
        mid = int(r["match_id"])
        new_h = int(r["correct_home"])
        new_a = int(r["correct_away"])
        note = (r.get("note") or "").strip()
        extra = {c: _opt_int(r.get(c)) for c in SCORE_COLS} if score_ok else {}
        extra = {c: v for c, v in extra.items() if v is not None}
        excludes = parse_excludes(r.get("exclude_goals"))

        cols = ", ".join(f"m.{c}" for c in extra)
        m = conn.execute(f"""
            SELECT m.home_goals, m.away_goals{(", " + cols) if cols else ""},
                   h.short_name_ar AS home, a.short_name_ar AS away, m.date
            FROM matches m
            LEFT JOIN teams h ON h.team_id = m.home_id
            LEFT JOIN teams a ON a.team_id = m.away_id
            WHERE m.match_id = ?
        """, (mid,)).fetchone()

        if m is None:
            print(f"\n  {mid} — مش موجودة بالديتابيس")
            notfound += 1
            continue

        cur_h, cur_a = m["home_goals"], m["away_goals"]
        label = f"{m['home']} × {m['away']} ({m['date']})"
        extra_diff = {c: v for c, v in extra.items() if m[c] != v}
        ex_ids = []
        for ex in excludes:
            minute, player = ex[:2]
            if player:
                found = conn.execute("SELECT id FROM goals WHERE match_id = ? AND minute = ? AND player_en = ?",
                                     (mid, minute, player))
            else:
                found = conn.execute("SELECT id FROM goals WHERE match_id = ? AND minute = ? AND team_id = ? "
                                     "AND (player_en IS NULL OR TRIM(player_en) = '')", (mid, minute, ex[2]))
            ex_ids += [g[0] for g in found]

        if (cur_h, cur_a) == (new_h, new_a) and not extra_diff and not ex_ids:
            print(f"\n  ✅ {label}")
            print(f"     مصححة أصلاً: {new_h}-{new_a}")
            already += 1
            continue

        print(f"\n  🔧 {label}")
        print(f"     الـAPI:  {cur_h}-{cur_a}")
        print(f"     الصحيح: {new_h}-{new_a}")
        if extra_diff:
            print(f"     التفصيل: {extra_diff}")
        if ex_ids:
            print(f"     أهداف مستبعدة: {len(ex_ids)} {excludes}")
        print(f"     السبب:  {note}")

        if check_only:
            applied += 1
            continue

        conn.execute(
            "UPDATE matches SET home_goals = ?, away_goals = ? WHERE match_id = ?",
            (new_h, new_a, mid))
        if extra_diff:
            conn.execute(f"UPDATE matches SET {', '.join(f'{c} = ?' for c in extra_diff)} WHERE match_id = ?",
                         tuple(extra_diff.values()) + (mid,))
        if ex_ids:
            conn.executemany("DELETE FROM goals WHERE id = ?", [(i,) for i in ex_ids])

        # لو النتيجة الصحيحة 0-0، الأهداف المسجّلة كلها ملغاة
        if new_h == 0 and new_a == 0:
            n = conn.execute(
                "SELECT COUNT(*) FROM goals WHERE match_id = ?",
                (mid,)).fetchone()[0]
            if n:
                conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))
                print(f"     انحذف {n} هدف ملغي من جدول goals")

        applied += 1

    return applied, already, notfound


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if not CORRECTIONS_FILE.exists():
        print(f"ما لقيت {CORRECTIONS_FILE.name}")
        return

    conn = sqlite3.connect(DB_FILE)
    rows = load_rows()

    if not rows:
        print("ملف التصحيحات فاضي")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"  تصحيحات مسجّلة: {len(rows)}")
    print(f"{'=' * 60}")

    applied, already, notfound = apply_rows(conn, rows, CHECK_ONLY)

    if not CHECK_ONLY:
        conn.commit()

    print(f"\n{'=' * 60}")
    if CHECK_ONLY:
        print(f"  [وضع الفحص] — ما انعدّل شي")
        print(f"  محتاجة تصحيح: {applied}  |  مصححة أصلاً: {already}"
              f"  |  مفقودة: {notfound}")
    else:
        print(f"  انصحح: {applied}  |  كانت مصححة: {already}"
              f"  |  مفقودة: {notfound}")
    print(f"{'=' * 60}")

    if applied and not CHECK_ONLY:
        print("\n  الخطوة الجاية:  python make_site3.py\n")

    conn.close()


if __name__ == "__main__":
    main()
