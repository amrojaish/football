#!/usr/bin/env python3
"""
أعمدة إحصائيات لاعبين جديدة (28 أكتوبر 2026، طلب عمرو) — `player_stats.offsides / dribbles_past / pen_won / pen_committed`
==========================================================================================================================
ردّ fixtures/players يحملها أصلاً (offsides، dribbles.past، penalty.won، penalty.commited) ولم نكن نخزّنها. عيّنة 28 أكتوبر
(FootballBackups/player-stats-probe-2026-10-28): SAU تملؤها لكل من لعب، EGY ترجعها null (عدا offsides) — فهي NULL حيث لا مصدر.

⚠️ هجرة يدوية واحدة (`migrate()`: ALTER TABLE ... ADD COLUMN فقط، أعمدة INTEGER تقبل NULL، لا حذف ولا تعديل ولا تعبئة) —
   **الكود لا يضيفها بنفسه** (نفس نمط match_round.py): fetch_player_stats.py يكتبها فقط إن وُجدت (`present()`)، والعرض
   (make_players.season_stats_rows، lineup_view) يقرؤها فقط إن وُجدت؛ قبل الهجرة يبقى السلوك القديم حرفياً (لا كسر للـCI).
⚠️ بلا تعبئة رجعية: المباريات المخزّنة تبقى NULL (يُخفى بالعرض)؛ تمتلئ للمباريات الجديدة فقط (fetch_player_stats تزايدي:
   يسحب المباريات التي لا إحصائيات لها).

التشغيل (لا يكتب شيئاً بلا --migrate):
    python player_stats_extra.py              # الحالة: أي الأعمدة موجودة (قراءة فقط)
    python player_stats_extra.py --migrate    # الهجرة على football.db — بعد موافقة عمرو، ثم db_push
"""
import sqlite3
import sys

# (عمود، نوع، مسار الحقل بكتلة statistics بردّ المزوّد) — "commited" بتهجئة المزوّد
NEW_COLS = [
    ("offsides", "INTEGER", ("offsides",)),
    ("dribbles_past", "INTEGER", ("dribbles", "past")),
    ("pen_won", "INTEGER", ("penalty", "won")),
    ("pen_committed", "INTEGER", ("penalty", "commited")),
]
NAMES = [c for c, _, _ in NEW_COLS]


def present(conn):
    """الأعمدة الجديدة الموجودة فعلاً بالجدول (بترتيب NEW_COLS)"""
    have = {r[1] for r in conn.execute("PRAGMA table_info(player_stats)")}
    return [c for c in NAMES if c in have]


def migrate(conn):
    """الهجرة الوحيدة: ADD COLUMN لكل عمود غائب (آمن للتكرار). يرجّع قائمة ما أُضيف."""
    added = []
    have = set(present(conn))
    for col, typ, _ in NEW_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE player_stats ADD COLUMN {col} {typ}")
            added.append(col)
    conn.commit()
    return added


def extract(stat, num):
    """{عمود: قيمة} من كتلة statistics للاعب؛ num = محوّل القيم بـfetch_player_stats"""
    out = {}
    for col, _, path in NEW_COLS:
        v = stat or {}
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        out[col] = num(v)
    return out


def main():
    from config import DB_FILE
    conn = sqlite3.connect(DB_FILE)
    try:
        if "--migrate" in sys.argv:
            added = migrate(conn)
            print(f"  player_stats: أُضيف {added}" if added else "  player_stats: الأعمدة موجودة — لا شيء")
        else:
            have = present(conn)
            print(f"  player_stats: موجود {have} · غائب {[c for c in NAMES if c not in have]} (قراءة فقط؛ --migrate للإضافة)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
