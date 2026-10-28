#!/usr/bin/env python3
"""
الملعب والمدينة والحكم (28 أكتوبر 2026، طلب عمرو) — `matches.venue_name / venue_city / referee` من ردّ fixtures نفسه
=====================================================================================================================
fixture.venue.name / fixture.venue.city / fixture.referee — نص المزوّد كما هو (بلا ترجمة). عيّنة 28 أكتوبر (EGY 2026، 190 مباراة):
الملعب والمدينة 143، الحكم 52 (الحكم يُعلَن قرب المباراة). بطاقة معلومات المباراة (make_matches.info_card) تعرض «الملعب، المدينة»
و«الحكم» حين يوجدان وتخفيهما حين NULL.

⚠️ هجرة يدوية واحدة (`migrate()`: ALTER TABLE ... ADD COLUMN فقط، TEXT تقبل NULL) — **الكود لا يضيفها بنفسه** (نمط match_round.py):
   كل كاتب لجدول matches يفحص وجودها (`has_venue`) ويكتبها فقط إن وُجدت، فقبل الهجرة يبقى السلوك القديم حرفياً (لا كسر للـCI).
⚠️ `INSERT OR REPLACE` يستبدل الصف كله فيمسح الأعمدة: كل من يكتب صف مباراة من ردّ المزوّد يستدعي `save()` بعده مباشرة —
   fetch_matches2.save_finished (ومعه fetch_overdue)، fetch_upcoming (القادمة + كل مباريات الموسم بنفس الردّ، صفر طلبات إضافية)،
   fetch_missing_h2h. `save()` لا يمسح قيمة قائمة بـNULL (COALESCE): ردّ لاحق بلا حكم لا يُضيّع حكماً معروفاً.
   import_league.py: المصدر (نسخة سحب مؤقتة) يُهاجَر تلقائياً إن كان الهدف مهاجَراً (كعمود الجولة).

التشغيل (لا يكتب شيئاً بلا --migrate / --backfill):
    python match_venue.py                 # الحالة: الأعمدة الموجودة + عدد غير الفارغ (قراءة فقط)
    python match_venue.py --migrate       # الهجرة على football.db — بعد موافقة عمرو، بقفل db_pull ثم db_push
    python match_venue.py --backfill      # الموسم الجاري لكل دوري مفعَّل: طلب fixtures?league&season واحد لكل دوري (سقف 12)
"""
import sqlite3
import sys

COLS = ("venue_name", "venue_city", "referee")
MAX_BACKFILL_CALLS = 12


def has_venue(conn):
    have = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    return all(c in have for c in COLS)


def migrate(conn):
    """الهجرة الوحيدة: ADD COLUMN لكل عمود غائب (آمن للتكرار). يرجّع قائمة ما أُضيف."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    added = [c for c in COLS if c not in have]
    for c in added:
        conn.execute(f"ALTER TABLE matches ADD COLUMN {c} TEXT")
    conn.commit()
    return added


def _txt(v):
    v = (v or "").strip() if isinstance(v, str) else None
    return v or None


def venue_of(fx):
    """(الملعب، المدينة، الحكم) من عنصر fixtures — None لكل غائب/فارغ"""
    f = (fx or {}).get("fixture") or {}
    v = f.get("venue") or {}
    return _txt(v.get("name")), _txt(v.get("city")), _txt(f.get("referee"))


def current(conn, mid):
    """القيم القائمة (الملعب، المدينة، الحكم) قبل INSERT OR REPLACE — يمرّرها الكاتب لـsave(keep=…) فلا يضيع ما يغيب عن الردّ الجديد.
    None قبل الهجرة أو بلا صف."""
    if not has_venue(conn):
        return None
    r = conn.execute("SELECT venue_name, venue_city, referee FROM matches WHERE match_id = ?", (mid,)).fetchone()
    return tuple(r) if r else None


def save(conn, fx, keep=None):
    """يكتب الثلاثة لصف المباراة (بعد INSERT OR REPLACE أو لأي صف موجود). لا شيء قبل الهجرة. قيمة قائمة لا تُمسح بـNULL:
    بالصف نفسه (COALESCE) وعبر INSERT OR REPLACE (keep = current() قبله). يرجّع عدد الصفوف التي تغيّرت (0 أو 1)."""
    if not has_venue(conn):
        return 0
    n, c, r = venue_of(fx)
    if keep:
        n, c, r = (new if new is not None else old for new, old in zip((n, c, r), keep))
    if n is None and c is None and r is None:
        return 0
    mid = fx["fixture"]["id"]
    return conn.execute("""UPDATE matches SET venue_name = COALESCE(?, venue_name), venue_city = COALESCE(?, venue_city),
                                              referee = COALESCE(?, referee)
                           WHERE match_id = ? AND (COALESCE(venue_name, '') != COALESCE(?, venue_name, '')
                                 OR COALESCE(venue_city, '') != COALESCE(?, venue_city, '')
                                 OR COALESCE(referee, '') != COALESCE(?, referee, ''))""",
                        (n, c, r, mid, n, c, r)).rowcount


def backfill(conn, leagues, season, get):
    """طلب fixtures?league&season واحد لكل دوري؛ get(params) -> (ok, response list, reason). يرجّع (calls, {code: changed})."""
    calls, out = 0, {}
    for code, lid in leagues:
        if calls >= MAX_BACKFILL_CALLS:
            print(f"  ⚠️ سقف {MAX_BACKFILL_CALLS} طلباً — توقّف قبل {code}")
            break
        ok, fx, why = get({"league": lid, "season": season})
        calls += 1
        if not ok:
            print(f"  {code}: فشل ({why}) — لا تغيير")
            out[code] = None
            continue
        out[code] = sum(save(conn, f) for f in fx)
        conn.commit()
        print(f"  {code}: {len(fx)} مباراة بالردّ · تغيّر {out[code]}")
    return calls, out


def counts(conn, season):
    """(كل مباريات الموسم، بملعب، بحكم) — قراءة فقط"""
    if not has_venue(conn):
        return None
    return conn.execute("SELECT COUNT(*), COUNT(venue_name), COUNT(referee) FROM matches WHERE season = ?", (season,)).fetchone()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from config import DB_FILE, LEAGUES, SEASON
    conn = sqlite3.connect(DB_FILE)
    try:
        if "--migrate" in sys.argv:
            added = migrate(conn)
            print(f"  matches: أُضيف {added}" if added else "  matches: الأعمدة موجودة — لا شيء")
        elif "--backfill" in sys.argv:
            if not has_venue(conn):
                raise SystemExit("❌ الأعمدة غائبة — --migrate أولاً")
            from config import check_key
            if not check_key():
                return
            from fetch_matches2 import get
            before = counts(conn, SEASON)
            calls, out = backfill(conn, [(c, v["id"]) for c, v in LEAGUES.items()], SEASON, lambda p: get("fixtures", p))
            after = counts(conn, SEASON)
            print(f"  طلبات: {calls} · الموسم {SEASON}: مباريات {after[0]} · بملعب {before[1]} → {after[1]} · بحكم {before[2]} → {after[2]}")
        else:
            have = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
            print(f"  matches: موجود {[c for c in COLS if c in have]} · غائب {[c for c in COLS if c not in have]}"
                  f" (قراءة فقط؛ --migrate للإضافة)")
            if has_venue(conn):
                print(f"  الموسم {SEASON}: (كل، بملعب، بحكم) = {tuple(counts(conn, SEASON))}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
