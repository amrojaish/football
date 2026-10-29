#!/usr/bin/env python3
"""
ملعب كل نادٍ: السعة والأرضية (29 أكتوبر 2026، دفعة 2 C3) — جدول `venues` من ردّ /teams?league&season
=======================================================================================================
طلب واحد لكل دوري مفعَّل (10 طلبات للموسم الجاري) يرجع كل أندية الدوري ومعها ملاعبها:
    response[i].team.id · response[i].venue = {id, name, address, city, capacity, surface, image}
يُخزَّن صف لكل نادٍ (team_id بمعرّفنا بعد team_merges.csv). بطاقة «الملعب» بصفحة النادي (make_clubs.stadium_card) تقرأ هذا الجدول
إن وُجد صف للنادي، وإلا ترجع للملعب الأكثر تكراراً بمباريات النادي على أرضه (matches.venue_name/venue_city) كما كانت.

⚠️ هجرة يدوية واحدة (`migrate()`: CREATE TABLE IF NOT EXISTS فقط) — **الكود لا يضيفها بنفسه** (نمط match_venue.py): القرّاء
   يفحصون وجود الجدول (`has_venues`)، فقبل الهجرة يبقى السلوك القديم حرفياً (لا كسر للـCI).
⚠️ لا يُستدعى من update_all.py: الملاعب لا تتغيّر بين التشغيلات — سحب يدوي عند بداية الموسم أو عند الحاجة.

التشغيل (لا يكتب شيئاً بلا --migrate / --fetch):
    python venues.py                               # الحالة (قراءة فقط)
    python venues.py --check --from-json <مجلد>    # فحص بلا كتابة ولا طلبات: يقرأ ردوداً محفوظة <CODE>.json ويطبع ما سيُكتب
    python venues.py --migrate                     # الهجرة على football.db — بقفل db_pull ثم db_push
    python venues.py --fetch [--save-json <مجلد>]  # طلب /teams واحد لكل دوري مفعَّل؛ يتوقف إن نزل المتبقي تحت 2,000
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MIN_REMAINING = 2000
SURFACE = {   # نص المزوّد (بلا حساسية حالة) → (عربي، إنجليزي)
    "grass": ("عشب طبيعي", "Grass"),
    "artificial turf": ("عشب صناعي", "Artificial turf"),
    "hybrid": ("عشب هجين", "Hybrid grass"),
}


def has_venues(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'venues'").fetchone() is not None


def migrate(conn):
    """الهجرة الوحيدة (آمنة للتكرار). يرجّع True إن أُنشئ الجدول الآن."""
    if has_venues(conn):
        return False
    conn.execute("""CREATE TABLE IF NOT EXISTS venues (
        team_id INTEGER PRIMARY KEY, venue_id INTEGER, name TEXT, city TEXT, address TEXT,
        capacity INTEGER, surface TEXT, league_code TEXT, fetched_at TEXT)""")
    conn.commit()
    return True


def _txt(v):
    v = v.strip() if isinstance(v, str) else None
    return v or None


def parse(resp, merges=None):
    """عناصر /teams → [(team_id, venue_id, name, city, address, capacity, surface)] — نادٍ بلا اسم ملعب يُتخطّى"""
    merges = merges or {}
    out = []
    for it in resp or []:
        t, v = (it or {}).get("team") or {}, (it or {}).get("venue") or {}
        tid, name = t.get("id"), _txt(v.get("name"))
        if not isinstance(tid, int) or not name:
            continue
        cap = v.get("capacity")
        out.append((merges.get(tid, tid), v.get("id") if isinstance(v.get("id"), int) else None, name, _txt(v.get("city")),
                    _txt(v.get("address")), cap if isinstance(cap, int) and cap > 0 else None, _txt(v.get("surface"))))
    return out


def save(conn, code, rows):
    """INSERT OR REPLACE لكل نادٍ؛ قيمة قائمة لا تُمسح بـNULL (سعة/أرضية غابت عن ردّ لاحق). يرجّع عدد الصفوف المكتوبة."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    n = 0
    for tid, vid, name, city, addr, cap, surf in rows:
        old = conn.execute("SELECT venue_id, city, address, capacity, surface FROM venues WHERE team_id = ?", (tid,)).fetchone()
        if old:
            vid, city, addr, cap, surf = (new if new is not None else o for new, o in zip((vid, city, addr, cap, surf), old))
        conn.execute("INSERT OR REPLACE INTO venues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (tid, vid, name, city, addr, cap, surf, code, now))
        n += 1
    conn.commit()
    return n


def get_venue(conn, tid):
    """{name, city, capacity, surface} أو None (لا جدول / لا صف)"""
    if not has_venues(conn):
        return None
    r = conn.execute("SELECT name, city, capacity, surface FROM venues WHERE team_id = ?", (tid,)).fetchone()
    return dict(zip(("name", "city", "capacity", "surface"), r)) if r else None


def surface_label(s, lang):
    if not s:
        return ""
    m = SURFACE.get(s.strip().lower())
    return (m[0] if lang == "ar" else m[1]) if m else s


def _merges():
    from tiebreak import _team_merges
    return _team_merges()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from config import DB_FILE, LEAGUES, SEASON
    a = sys.argv

    def opt(name):
        return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None

    if "--check" in a:
        d = Path(opt("--from-json") or ".")
        conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        ours = {r[0] for r in conn.execute("SELECT DISTINCT home_id FROM matches WHERE season = ? UNION "
                                           "SELECT DISTINCT away_id FROM matches WHERE season = ?", (SEASON, SEASON))}
        tot = 0
        for code in LEAGUES:
            f = d / f"{code}.json"
            if not f.exists():
                print(f"  {code}: لا ملف {f.name} — تخطٍّ")
                continue
            rows = parse(json.loads(f.read_text(encoding="utf-8")).get("response"), _merges())
            unknown = [r[0] for r in rows if r[0] not in ours]
            caps = sum(1 for r in rows if r[5])
            print(f"  {code}: {len(rows)} نادياً بملعب · بسعة {caps} · بأرضية {sum(1 for r in rows if r[6])}"
                  + (f" · معرّفات خارج أنديتنا: {unknown}" if unknown else ""))
            tot += len(rows)
        print(f"  [فحص] كان سيُكتب {tot} صفاً — لم يُكتب شيء، صفر طلبات")
        return
    conn = sqlite3.connect(DB_FILE)
    try:
        if "--migrate" in a:
            print("  venues: أُنشئ" if migrate(conn) else "  venues: موجود — لا شيء")
        elif "--fetch" in a:
            if not has_venues(conn):
                raise SystemExit("❌ جدول venues غائب — --migrate أولاً")
            import requests
            from config import API_BASE, check_key, headers
            if not check_key():
                return
            keep = Path(opt("--save-json")) if opt("--save-json") else None
            if keep:
                keep.mkdir(parents=True, exist_ok=True)
            calls, rem = 0, None
            for code, v in LEAGUES.items():
                if rem is not None and rem < MIN_REMAINING:
                    print(f"  ⛔ المتبقي {rem} < {MIN_REMAINING} — توقّف قبل {code}")
                    break
                r = requests.get(f"{API_BASE}/teams", headers=headers(), params={"league": v["id"], "season": SEASON}, timeout=30)
                calls += 1
                try:
                    rem = int(r.headers.get("x-ratelimit-requests-remaining"))
                except (TypeError, ValueError):
                    pass
                d = r.json() if r.status_code == 200 else {}
                if keep:
                    (keep / f"{code}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                if r.status_code != 200 or d.get("errors"):
                    print(f"  {code}: فشل HTTP {r.status_code} {d.get('errors') if d else ''} — لا تغيير")
                else:
                    print(f"  {code}: كُتب {save(conn, code, parse(d.get('response'), _merges()))}")
                time.sleep(1.1)
            print(f"  طلبات: {calls} · المتبقي بعدها: {rem}")
        else:
            if not has_venues(conn):
                print("  venues: غائب (قراءة فقط؛ --migrate للإنشاء)")
            else:
                n, c, s = conn.execute("SELECT COUNT(*), COUNT(capacity), COUNT(surface) FROM venues").fetchone()
                print(f"  venues: {n} صفاً · بسعة {c} · بأرضية {s}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
