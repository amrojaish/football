#!/usr/bin/env python3
"""
أرشفة سجلات الأهداف الخاطئة (بدل حذفها)
==========================================
ينقل من `goals` إلى `cancelled_goals`:
  1. ركلات الجزاء الضائعة (`detail = 'Missed Penalty'`) — ليست أهدافاً
  2. الأهداف **بلا اسم لاعب** في مباريات انتهت 0-0 — ملغاة بالفار

⚠️ **النقل لا الحذف.** النسخة القديمة كانت تحذف نهائياً، فضاعت
   حالتان بلا أثر. الجدول الجديد يتيح عرضها لاحقاً
   ("هدف ملغى د.13") ويحفظ إمكانية المراجعة.

⚠️ **الهدف باسم لاعب في مباراة 0-0 لا يُنقَل** — يُعرَض للمراجعة
   فقط. حالة محقَّقة (مباراة 1140143): هدفان باسمين في مباراة
   مسجّلة 0-0، أي أن **النتيجة خاطئة** لا أن الهدفين ملغيان.
   حذفهما كان يخفي الخطأ بدل إصلاحه — الصحيح تصحيح النتيجة عبر
   `match_corrections.csv`.

⚠️ إعادة التشغيل آمنة — `INSERT OR IGNORE` على `id`.
⚠️ نسخة احتياطية قبل أي كتابة. صفر طلبات API.

    python fix_goals.py --check    <- عرض بس
    python fix_goals.py            <- تنفيذ
"""

import sqlite3
import shutil
import sys
from config import DB_FILE

CHECK_ONLY = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS cancelled_goals (
    id          INTEGER PRIMARY KEY,
    match_id    INTEGER,
    team_id     INTEGER,
    minute      INTEGER,
    player_en   TEXT,
    player_ar   TEXT,
    detail      TEXT,
    reason      TEXT,
    archived_at TEXT DEFAULT (datetime('now'))
)
"""

MOVE = """
INSERT OR IGNORE INTO cancelled_goals
    (id, match_id, team_id, minute, player_en, player_ar, detail, reason)
SELECT id, match_id, team_id, minute, player_en, player_ar, detail, ?
FROM goals WHERE id IN ({ids})
"""


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # 1. ركلات جزاء ضائعة
    missed = conn.execute("""
        SELECT g.id, g.minute, g.player_en, g.player_ar,
               t.short_name_ar AS team
        FROM goals g JOIN teams t ON t.team_id = g.team_id
        WHERE g.detail = 'Missed Penalty'
    """).fetchall()

    # 2. مباريات 0-0 فيها أهداف — مفصولة حسب وجود اسم اللاعب
    zeros = conn.execute("""
        SELECT g.id, g.minute, g.player_en, g.player_ar, g.detail,
               t.short_name_ar AS team, m.match_id, m.date,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t ON t.team_id = g.team_id
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals + m.away_goals = 0
        ORDER BY m.date
    """).fetchall()

    ghost = [r for r in zeros if not (r["player_en"] or "").strip()]
    named = [r for r in zeros if (r["player_en"] or "").strip()]

    print()
    print("=" * 62)
    print(f"  ركلات جزاء ضائعة        : {len(missed)}")
    print(f"  أهداف بلا اسم بمباراة 0-0: {len(ghost)}   <- تُؤرشَف")
    print(f"  أهداف باسم بمباراة 0-0   : {len(named)}   <- للمراجعة فقط")
    print("=" * 62)

    for r in missed:
        nm = r["player_ar"] or r["player_en"] or "(بلا اسم)"
        print(f"    جزاء ضائع: د.{r['minute']} {nm} ({r['team']})")

    if ghost:
        print("\n  للأرشفة — ملغاة على الأرجح:")
        for r in ghost:
            print(f"    {r['date'][:10]}  {r['home']} 0-0 {r['away']}"
                  f"  د.{r['minute']} ({r['team']})")

    if named:
        print("\n  ⚠️ **لن تُؤرشَف — النتيجة هي المشكوك فيها لا الأهداف:**")
        for r in named:
            nm = r["player_ar"] or r["player_en"]
            print(f"    {r['date'][:10]}  {r['home']} 0-0 {r['away']}"
                  f"  د.{r['minute']} {nm} ({r['team']})  match={r['match_id']}")
        mids = sorted({r["match_id"] for r in named})
        print(f"\n    صحّح نتائج هذه المباريات في match_corrections.csv:")
        for mid in mids:
            print(f"       {mid}")

    total = len(missed) + len(ghost)
    if total == 0:
        print("\n  ما في شي للأرشفة\n")
        conn.close()
        return

    if CHECK_ONLY:
        print(f"\n  [وضع الفحص] — {total} سجل مرشَّح، ما انكتب شي\n")
        conn.close()
        return

    backup = DB_FILE.parent / "football_before_cancel.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    conn.execute(SCHEMA)

    for rows, reason in ((missed, "missed_penalty"), (ghost, "zero_zero_match")):
        if not rows:
            continue
        ids = ",".join(str(r["id"]) for r in rows)
        conn.execute(MOVE.format(ids=ids), (reason,))
        conn.execute(f"DELETE FROM goals WHERE id IN ({ids})")

    conn.commit()

    arch = conn.execute("SELECT COUNT(*) FROM cancelled_goals").fetchone()[0]
    left = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    chk = conn.execute("""
        SELECT (SELECT SUM(home_goals + away_goals) FROM matches) AS real,
               (SELECT COUNT(*) FROM goals) AS rec
    """).fetchone()

    print(f"""
{'=' * 62}
  أُرشِف: {total}   |   بجدول cancelled_goals: {arch}
  باقي بجدول goals: {left}
{'=' * 62}

  التحقق:
    أهداف من النتائج : {chk['real']}
    أهداف مسجّلة     : {chk['rec']}
    الفرق            : {chk['real'] - chk['rec']}

  (الفرق الموجب طبيعي — مباريات بلا أحداث بعد.
   السالب هو المشكلة، ولازم يصير صفراً أو موجباً.)
""")
    conn.close()

    print("""
  الخطوة الجاية:
      python audit.py
      python make_matches.py    (لعرض الملغاة لاحقاً)
    """)


if __name__ == "__main__":
    main()
