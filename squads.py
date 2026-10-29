#!/usr/bin/env python3
"""
القائمة الرسمية والمدرب (29 أكتوبر 2026، دفعة 2 C7) — جدولا `squads` و`coaches`
==================================================================================
    /players/squads?team=<id>   → response[0].players = [{id, name, age, number, position, photo}]   (طلب لكل نادٍ)
    /coachs?team=<id>           → [{id, name, nationality, age, career: [{team: {id}, start, end}]}]  (طلب لكل نادٍ)
المدرب الحالي = من career بنفس النادي و end فارغ (الأحدث start عند أكثر من واحد). أندية الموسم الجاري للدوريات المفعّلة (~154 نادياً
= ~308 طلباً، طلب بالثانية). تبويب «اللاعبون» بصفحة النادي (make_clubs.squad_block) يقرأ القائمة الرسمية إن وُجدت للنادي/الموسم
(بأرقامها ومراكزها، والمشاركات من تشكيلاتنا)، وإلا القائمة المبنية من التشكيلات كما كانت. صف المدرب من coaches وإلا من التشكيلات.
العمر والجنسية: من player_info الموجود فقط (لا طلبات /players إضافية).

⚠️ هجرة يدوية واحدة (`migrate()`: CREATE TABLE IF NOT EXISTS فقط) — الكود لا يضيفها بنفسه (نمط match_venue.py/venues.py)؛ القرّاء
   يفحصون الوجود (`has_squads`). لا يُستدعى من update_all.py (سحب يدوي).
⚠️ القائمة تُستبدل كاملة لكل (نادٍ، موسم) عند السحب (لاعب غادر يختفي). ردّ فاشل/فارغ لا يمسح قائمة قائمة.

التشغيل (لا يكتب شيئاً بلا --migrate / --fetch):
    python squads.py                               # الحالة (قراءة فقط)
    python squads.py --check --from-json <مجلد>    # بلا كتابة ولا طلبات: يقرأ squad_<id>.json وcoach_<id>.json ويطبع ما سيُكتب
    python squads.py --migrate                     # الهجرة — بقفل db_pull ثم db_push
    python squads.py --fetch [--save-json <مجلد>]  # طلبان لكل نادٍ، طلب بالثانية؛ يتوقف إن نزل المتبقي تحت 2,000 (الجزئي محفوظ)
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MIN_REMAINING = 2000
POS = {"Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Attacker": "F"}


def has_squads(conn):
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('squads', 'coaches')")}
    return have == {"squads", "coaches"}


def migrate(conn):
    """الهجرة الوحيدة (آمنة للتكرار). يرجّع قائمة الجداول المُنشأة الآن."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    made = []
    if "squads" not in have:
        conn.execute("""CREATE TABLE squads (team_id INTEGER, season INTEGER, player_id INTEGER, name TEXT, number INTEGER,
                        position TEXT, fetched_at TEXT, PRIMARY KEY (team_id, season, player_id))""")
        made.append("squads")
    if "coaches" not in have:
        conn.execute("""CREATE TABLE coaches (team_id INTEGER PRIMARY KEY, coach_id INTEGER, name TEXT, nationality TEXT,
                        age INTEGER, fetched_at TEXT)""")
        made.append("coaches")
    conn.commit()
    return made


def parse_squad(resp):
    """/players/squads → [(player_id, name, number, pos G/D/M/F/"")] — لاعب بلا معرّف يُتخطّى"""
    out = []
    for blk in resp or []:
        for p in (blk or {}).get("players") or []:
            pid = p.get("id")
            if not isinstance(pid, int) or pid <= 0:
                continue
            num = p.get("number")
            out.append((pid, (p.get("name") or "").strip(), num if isinstance(num, int) else None, POS.get(p.get("position"), "")))
    return out


def parse_coach(resp, provider_tid):
    """/coachs → (coach_id, name, nationality, age) للمدرب الحالي لهذا النادي (career بنفس النادي، end فارغ؛ الأحدث start)، أو None"""
    best = None
    for c in resp or []:
        for car in (c or {}).get("career") or []:
            if ((car or {}).get("team") or {}).get("id") == provider_tid and not car.get("end"):
                k = car.get("start") or ""
                if best is None or k > best[0]:
                    best = (k, (c.get("id"), (c.get("name") or "").strip(), c.get("nationality"), c.get("age")))
    return best[1] if best else None


def save_squad(conn, tid, season, rows):
    if not rows:
        return 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    conn.execute("DELETE FROM squads WHERE team_id = ? AND season = ?", (tid, season))
    conn.executemany("INSERT OR REPLACE INTO squads VALUES (?, ?, ?, ?, ?, ?, ?)", [(tid, season, *r, now) for r in rows])
    conn.commit()
    return len(rows)


def save_coach(conn, tid, coach):
    if not coach or not coach[1]:
        return 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    conn.execute("INSERT OR REPLACE INTO coaches VALUES (?, ?, ?, ?, ?, ?)", (tid, *coach, now))
    conn.commit()
    return 1


def get_squad(conn, tid, season):
    """[{pid, name, number, pos}] أو [] (لا جداول / لا قائمة)"""
    if not has_squads(conn):
        return []
    return [dict(zip(("pid", "name", "number", "pos"), r)) for r in conn.execute(
        "SELECT player_id, name, number, position FROM squads WHERE team_id = ? AND season = ?", (tid, season))]


def get_coach(conn, tid):
    if not has_squads(conn):
        return None
    r = conn.execute("SELECT name, nationality, age FROM coaches WHERE team_id = ?", (tid,)).fetchone()
    return dict(zip(("name", "nationality", "age"), r)) if r else None


def teams_to_fetch(conn, season, leagues):
    """[(معرّفنا، معرّف المزوّد للطلب، الدوري)] لأندية الموسم الجاري — معرّف المزوّد = آخر معرّف قديم بـteam_merges يحوّل إلينا
    إن وُجد (الشرطة: المزوّد يستعمل 28571 لموسم 2026)، وإلا معرّفنا"""
    from tiebreak import _team_merges
    back = {}
    for old, new in _team_merges().items():
        back[new] = old
    out = []
    for code in leagues:
        for (tid,) in conn.execute("SELECT DISTINCT home_id FROM matches WHERE league_code = ? AND season = ? UNION "
                                   "SELECT DISTINCT away_id FROM matches WHERE league_code = ? AND season = ?",
                                   (code, season, code, season)):
            out.append((tid, back.get(tid, tid), code))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from config import DB_FILE, LEAGUES, SEASON
    a = sys.argv

    def opt(name):
        return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None

    if "--check" in a:
        d = Path(opt("--from-json") or ".")
        conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        teams = teams_to_fetch(conn, SEASON, LEAGUES)
        ns = nc = seen = 0
        for tid, ptid, code in teams:
            fs, fc = d / f"squad_{ptid}.json", d / f"coach_{ptid}.json"
            if not fs.exists() and not fc.exists():
                continue
            seen += 1
            rows = parse_squad(json.loads(fs.read_text(encoding="utf-8")).get("response")) if fs.exists() else []
            co = parse_coach(json.loads(fc.read_text(encoding="utf-8")).get("response"), ptid) if fc.exists() else None
            ns += len(rows)
            nc += 1 if co else 0
            print(f"  {code} {tid}: {len(rows)} لاعباً · مدرب: {co[1] if co else '—'}")
        print(f"  [فحص] أندية الموسم {len(teams)} · بملفات {seen} · كان سيُكتب {ns} صف squads و{nc} صف coaches — لم يُكتب شيء، صفر طلبات")
        return
    conn = sqlite3.connect(DB_FILE)
    try:
        if "--migrate" in a:
            made = migrate(conn)
            print(f"  أُنشئ: {made}" if made else "  squads/coaches موجودان — لا شيء")
        elif "--fetch" in a:
            if not has_squads(conn):
                raise SystemExit("❌ الجداول غائبة — --migrate أولاً")
            import requests
            from config import API_BASE, check_key, headers
            if not check_key():
                return
            keep = Path(opt("--save-json")) if opt("--save-json") else None
            if keep:
                keep.mkdir(parents=True, exist_ok=True)
            calls, rem, ns, nc, stop = 0, None, 0, 0, False
            for tid, ptid, code in teams_to_fetch(conn, SEASON, LEAGUES):
                for kind, path, params in (("squad", "players/squads", {"team": ptid}), ("coach", "coachs", {"team": ptid})):
                    if rem is not None and rem < MIN_REMAINING:
                        print(f"  ⛔ المتبقي {rem} < {MIN_REMAINING} — توقّف عند {code} {tid} (ما سُحب محفوظ)")
                        stop = True
                        break
                    r = requests.get(f"{API_BASE}/{path}", headers=headers(), params=params, timeout=30)
                    calls += 1
                    try:
                        rem = int(r.headers.get("x-ratelimit-requests-remaining"))
                    except (TypeError, ValueError):
                        pass
                    d = r.json() if r.status_code == 200 else {}
                    if keep:
                        (keep / f"{kind}_{ptid}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    if r.status_code != 200 or d.get("errors"):
                        print(f"  {code} {tid} {kind}: فشل HTTP {r.status_code} — لا تغيير")
                    elif kind == "squad":
                        ns += save_squad(conn, tid, SEASON, parse_squad(d.get("response")))
                    else:
                        nc += save_coach(conn, tid, parse_coach(d.get("response"), ptid))
                    time.sleep(1.0)
                if stop:
                    break
            print(f"  طلبات: {calls} · صفوف squads {ns} · coaches {nc} · المتبقي بعدها: {rem}")
        else:
            if not has_squads(conn):
                print("  squads/coaches: غائبان (قراءة فقط؛ --migrate للإنشاء)")
            else:
                print("  squads:", conn.execute("SELECT COUNT(*), COUNT(DISTINCT team_id) FROM squads").fetchone(),
                      "· coaches:", conn.execute("SELECT COUNT(*) FROM coaches").fetchone()[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
