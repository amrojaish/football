#!/usr/bin/env python3
"""
تفصيل النتيجة (الموجة 0 للكؤوس، 3 نوفمبر 2026) — `matches.ft_home/ft_away/et_home/et_away/pen_home/pen_away`
=================================================================================================================
من ردّ fixtures نفسه (صفر طلبات إضافية): score.fulltime (90 د)، score.extratime (أهداف الشوطين الإضافيين وحدهما)،
score.penalty (ركلات الترجيح). home_goals/away_goals تبقى = goals عند المزوّد (تشمل الإضافي، بلا الترجيح) — لا تغيير.
أمثلة حقيقية (cups_check، 3 نوفمبر 2026):
    PEN 1645511 كأس رئيس الدولة: goals 2-2 · fulltime 1-1 · extratime 1-1 · penalty 4-3
    PEN السوبر السعودي (نصف النهائي): goals 0-0 · fulltime 0-0 · extratime null (المزوّد يتركه فارغاً حين لا أهداف) · penalty 5-4
    AET كأس ولي العهد الكويتي: goals 1-0 · fulltime 0-0 · extratime 1-0 · penalty null

⚠️ هجرة يدوية واحدة (`migrate()`، نمط match_round/match_venue): الكود لا يضيف الأعمدة بنفسه — كل كاتب يفحص `has_score` ويكتب
   فقط إن وُجدت، فقبل الهجرة يبقى السلوك القديم حرفياً. **هذه الأداة لا تفتح football.db افتراضياً: --db إلزامي** (نسخة أولاً).
⚠️ INSERT OR REPLACE يمسح الأعمدة: كل كاتب صف مباراة من ردّ المزوّد يستدعي `save()` بعده (fetch_matches2.save_finished ومعه
   fetch_overdue، fetch_upcoming لكل مباريات الموسم بنفس الردّ، fetch_missing_h2h).

ركلات الترجيح كأحداث (طلب واحد، fixtures/events?fixture=1645511، 3 نوفمبر 2026): كل ركلة حدث type=Goal بتفصيل
"Penalty" أو "Missed Penalty" و**comments = "Penalty Shootout"**، الدقيقة 120 وextra = رقم الركلة، بلا اسم لاعب. بلا فلتر كانت
الركلات المسجّلة تدخل جدول goals (هدّافون + مجموع أهداف ≠ النتيجة) — `is_shootout()` يستبعدها بكل كاتب أهداف.

التشغيل (لا يكتب شيئاً بلا --migrate):
    python match_score.py --db <نسخة.db>             # الحالة: الأعمدة الموجودة + عدد غير الفارغ (قراءة فقط)
    python match_score.py --db <نسخة.db> --migrate   # الهجرة على النسخة المحدَّدة فقط
"""
import sqlite3
import sys

COLS = ("ft_home", "ft_away", "et_home", "et_away", "pen_home", "pen_away")
SHOOTOUT = "Penalty Shootout"


def has_score(conn):
    have = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    return all(c in have for c in COLS)


def migrate(conn):
    """الهجرة الوحيدة: ADD COLUMN INTEGER لكل عمود غائب (آمن للتكرار). يرجّع قائمة ما أُضيف."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    added = [c for c in COLS if c not in have]
    for c in added:
        conn.execute(f"ALTER TABLE matches ADD COLUMN {c} INTEGER")
    conn.commit()
    return added


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def score_of(fx):
    """(ft_h, ft_a, et_h, et_a, pen_h, pen_a) من عنصر fixtures — None لكل غائب"""
    s = (fx or {}).get("score") or {}
    out = []
    for k in ("fulltime", "extratime", "penalty"):
        p = s.get(k) or {}
        out += [_int(p.get("home")), _int(p.get("away"))]
    return tuple(out)


def save(conn, fx):
    """يكتب الستة لصف المباراة (بعد INSERT OR REPLACE أو لأي صف موجود). لا شيء قبل الهجرة ولا لردّ بلا أي قيمة (قادمة).
    القيم من الردّ كما هي (الأحدث يغلب). يرجّع عدد الصفوف التي تغيّرت (0 أو 1)."""
    if not has_score(conn):
        return 0
    v = score_of(fx)
    if all(x is None for x in v):
        return 0
    mid = fx["fixture"]["id"]
    sets = ", ".join(f"{c} = ?" for c in COLS)
    diff = " OR ".join(f"{c} IS NOT ?" for c in COLS)
    return conn.execute(f"UPDATE matches SET {sets} WHERE match_id = ? AND ({diff})", v + (mid,) + v).rowcount


def is_shootout(e):
    """حدث ركلة ترجيح (لا هدف حقيقي) — يُستبعد من جدول goals والهدّافين"""
    return ((e or {}).get("comments") or "").strip() == SHOOTOUT


def row_score(m):
    """(pen_h, pen_a, et_h, et_a) من صف matches (sqlite3.Row/dict) — None لكل غائب أو قبل الهجرة"""
    out = []
    for c in ("pen_home", "pen_away", "et_home", "et_away"):
        try:
            out.append(m[c])
        except (IndexError, KeyError):
            out.append(None)
    return tuple(out)


def counts(conn):
    """{عمود: عدد غير الفارغ} — قراءة فقط"""
    if not has_score(conn):
        return {}
    return {c: conn.execute(f"SELECT COUNT(*) FROM matches WHERE {c} IS NOT NULL").fetchone()[0] for c in COLS}


def main():
    if "--db" not in sys.argv or sys.argv.index("--db") + 1 >= len(sys.argv):
        print("--db <path> إلزامي (لا افتراضي: لا يُفتح football.db من هنا)")
        sys.exit(2)
    path = sys.argv[sys.argv.index("--db") + 1]
    conn = sqlite3.connect(path)
    before = [r[1] for r in conn.execute("PRAGMA table_info(matches)")]
    print(f"{path}\n  أعمدة matches قبل: {len(before)}")
    if "--migrate" in sys.argv:
        added = migrate(conn)
        print(f"  أُضيف: {', '.join(added) if added else 'لا شيء (موجودة)'}")
    print(f"  has_score: {has_score(conn)}")
    print(f"  غير الفارغ: {counts(conn)}")
    print(f"  صفوف matches: {conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
