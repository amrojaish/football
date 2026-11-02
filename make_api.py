#!/usr/bin/env python3
"""
JSON API v1 — المرحلة 1 (الأيام + المباريات) — 2 نوفمبر 2026
==============================================================
يقرأ football.db ويكتب ملفات JSON ثابتة تحت api/v1/ (أو --out <مجلد>). لا طلبات API، لا كتابة على القاعدة.
خطوة بـupdate_all.py بعد make_matches.py (2 نوفمبر 2026)؛ api/ مولَّد (generated_paths.txt + .gitignore) ومنشور كما هو.
للتطبيق الأصلي (native app). الكتابة بمجلد مؤقت شقيق (.v1.tmp) ثم استبدال api/v1 كاملاً (swap_in): لا بقايا قديمة.

    python make_api.py                 ← api/v1/ داخل المشروع
    python make_api.py --out <مجلد>    ← مجلد آخر (اختبار؛ يُستبدل كاملاً بنفس الطريقة)

الملفات:
  index.json             {v, built, leagues[{code, name{ar,en}, season, logo}], days[{date, n, hash}]}
  teams.json             {id: {name{ar,en}, short{ar,en}, logo, color}}
  days/YYYY-MM-DD.json   [مباراة مختصرة] بترتيب الرئيسية (الدوري بترتيب LEAGUES ثم الموعد)
  matches/<id>.json      المختصرة + venue/referee/events/lineups/stats/h2h/table_mini/correction

القواعد: كل اسم = {"ar","en"} (العربي = ما تعرضه الصفحة العربية: الترجمة وإلا الإنجليزي — نفس ارتداد الصفحات)؛
`short` يُضاف فقط حين يختلف المختصر المعروض (short_names، حارس التصادم على مستوى المباراة) عن الاسم الكامل؛
بيانات غائبة = المفتاح محذوف (لا null ولا ""). الموسم الجاري = أحدث موسم لكل دوري (كـmake_players.LATEST_BY_LG).
JSON مضغوط بلا مسافات، UTF-8، ensure_ascii=False.

⚠️ المصادر كلها من الدوال التي تبني الصفحات نفسها (لا SQL منسوخ): make_matches (load_teams/tname/logo_url/
   load_corrections/match_event_rows/stats_data/h2h_data/positions_data/team_color/league_logo_src)،
   lineup_view.team_rows، short_names، make_site3.window_matches (تجميع الأيام)، i18n (league_name/off_label/T).
"""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import date as _date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# make_matches يقرأ sys.argv[1] كرمز دوري عند الاستيراد (ONLY) — نخفي وسائطنا عنه
_ARGV = sys.argv[:]
sys.argv = sys.argv[:1]
import make_matches as MM          # noqa: E402
import lineup_view as LV           # noqa: E402
import short_names as SN           # noqa: E402
from make_site3 import window_matches  # noqa: E402
from i18n import T, league_name, off_label  # noqa: E402
from live_view import var_label  # noqa: E402
from match_round import label as round_label  # noqa: E402
from config import DB_FILE, LEAGUES  # noqa: E402
sys.argv = _ARGV

BASE = DB_FILE.parent
LANGS2 = ("ar", "en")
FINAL = ("FT", "AET", "PEN")


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def clean(s):
    return (s or "").strip()


def site_path(p):
    """مسار نسبي من صفحة عربية (../x) أو جذر (x) → مسار من جذر الموقع (/x)؛ الروابط الخارجية كما هي"""
    if not p or p.startswith("http"):
        return p
    while p.startswith("../"):
        p = p[3:]
    return "/" + p.lstrip("/")


def kickoff_iso(d):
    """'YYYY-MM-DD HH:MM' (UTC خام) → 'YYYY-MM-DDTHH:MM:00Z'؛ بلا وقت → None"""
    parts = str(d or "").split()
    if len(parts) < 2 or not parts[1][:5]:
        return None
    return f"{parts[0]}T{parts[1][:5]}:00Z"


# ── الموسم الجاري والمباريات ──
def current_seasons(conn):
    """{code: أحدث موسم} لكل دوري بـLEAGUES له مباريات — نفس تعريف make_players.LATEST_BY_LG"""
    got = dict(conn.execute("SELECT league_code, MAX(season) FROM matches GROUP BY league_code").fetchall())
    return {c: got[c] for c in LEAGUES if c in got}


def season_matches(conn, seasons):
    """كل مباريات الموسم الجاري بترتيب الرئيسية: window_matches (DATE بين أول وآخر يوم، ORDER BY date) ثم تجميع
    يوم → دوري بترتيب LEAGUES — نفس day_view بـmake_site3 (المفتاح str(date)[:10])."""
    lo, hi = conn.execute(
        "SELECT MIN(DATE(date)), MAX(DATE(date)) FROM matches WHERE " +
        " OR ".join("(league_code = ? AND season = ?)" for _ in seasons),
        [x for kv in seasons.items() for x in kv]).fetchone()
    rows = window_matches(conn, _date.fromisoformat(lo), _date.fromisoformat(hi))
    by_day = {}
    for m in rows:
        if seasons.get(m["league_code"]) != m["season"]:
            continue
        by_day.setdefault(str(m["date"])[:10], {}).setdefault(m["league_code"], []).append(m["match_id"])
    order = {}
    for d in sorted(by_day):
        order[d] = [mid for code in LEAGUES for mid in by_day[d].get(code, [])]
    return order


# ── الفرق ──
def teams_json(conn, teams, tids):
    """{id: {name{ar,en}, short{ar,en}, logo, color}} — الاسم العربي الكامل من teams.name_ar؛ المختصر = tname (ما تعرضه الصفحات)"""
    full_ar = {r[0]: clean(r[1]) for r in conn.execute("SELECT team_id, name_ar FROM teams")}
    out = {}
    for tid in sorted(tids):
        t = teams.get(tid)
        if not t:
            continue
        sh = {lg: MM.tname(t, lg) for lg in LANGS2}
        nm = {"ar": full_ar.get(tid) or sh["ar"], "en": t["name_en"] or sh["en"]}
        e = {"name": nm}
        if sh != nm:
            e["short"] = sh
        lo = site_path(MM.logo_url(t, "ar"))
        if lo:
            e["logo"] = lo
        c = MM.team_color(tid)
        if c:
            e["color"] = c
        out[str(tid)] = e
    return out


# ── المباراة ──
def match_core(m, fixes):
    """الحقول المشتركة بين ملف اليوم وملف المباراة"""
    o = {"id": m["match_id"], "league": m["league_code"]}
    rnd = {lg: round_label(MM._rnd(m), lg) for lg in LANGS2}
    if rnd["ar"] or rnd["en"]:
        o["round"] = rnd
    ko = kickoff_iso(m["date"])
    if ko:
        o["kickoff"] = ko
    else:
        o["date"] = str(m["date"])[:10]
    o["status"] = m["status"]
    o["home"], o["away"] = m["home_id"], m["away_id"]
    if m["home_goals"] is not None and m["away_goals"] is not None:
        o["score"] = {"h": m["home_goals"], "a": m["away_goals"]}
    off = {lg: off_label(m["status"], T[lg], m["date"]) for lg in LANGS2}
    if off["ar"]:
        o["postponed"] = {"label": off}
    fix = fixes.get(m["match_id"])
    if fix:
        o["correction"] = {k: v for k, v in fix.items() if v}
    return o


def _person(full, snm, pid=None):
    """{id?, name{ar,en}, short?{ar,en}} — full = {"ar","en"} الكامل (العربي مرتدّ للإنجليزي)"""
    if not (full["ar"] or full["en"]):
        return None
    full = {"ar": full["ar"] or full["en"], "en": full["en"] or full["ar"]}
    p = {}
    if pid:
        p["id"] = pid
    p["name"] = full
    sh = {lg: SN.apply(snm, full[lg]) for lg in LANGS2}
    if sh != full:
        p["short"] = sh
    return p


def events_json(conn, m):
    """الأحداث تصاعدياً بالدقيقة (بلا دقيقة آخراً) — نفس صفوف build_items (match_event_rows) ونفس قواعد الأسماء.
    معرّف اللاعب: الأهداف/الأحداث بلا player_id بالقاعدة، فيُؤخذ من تشكيلة المباراة نفسها (نفس الفريق ونفس الاسم الإنجليزي)
    إن وُجد هناك؛ وإلا يُحذف المفتاح."""
    mid = m["match_id"]
    rows = MM.match_event_rows(conn, mid)
    snm = SN.match_map(conn, mid)
    names = MM.name_map(conn)
    pid_of = {}
    for tid in (m["home_id"], m["away_id"]):
        for r in LV.team_rows(conn, mid, tid)[1]:
            if r["player_id"] and clean(r["player_en"]):
                pid_of.setdefault((tid, clean(r["player_en"])), r["player_id"])

    def pid(team, en):
        return pid_of.get((team, clean(en))) or None

    out = []
    for g in rows["goals"]:
        e = {"team": g["team_id"], "type": "goal", "detail": clean(g["detail"]) or "Normal Goal"}
        p = _person({"ar": clean(g["player_ar"]), "en": clean(g["player_en"])}, snm, pid(g["team_id"], g["player_en"]))
        if p:
            e["player"] = p
        out.append((g["minute"], e))
    for c in rows["cancelled"]:
        e = {"team": c["team_id"], "type": "cancelled_goal"}
        p = _person({"ar": clean(c["player_ar"]), "en": clean(c["player_en"])}, snm, pid(c["team_id"], c["player_en"]))
        if p:
            e["player"] = p
        out.append((c["minute"], e))
    for v in rows["events"]:
        en = clean(v["player_en"])
        typ = {"Card": "card", "subst": "subst"}.get(v["type"], "var")
        e = {"team": v["team_id"], "type": typ}
        if clean(v["detail"]):
            e["detail"] = clean(v["detail"])
        if typ == "var":
            e["label"] = {lg: var_label(v["detail"], lg) for lg in LANGS2}
        p = _person({"ar": clean(v["player_ar"]) or names.get(en, ""), "en": en}, snm, pid(v["team_id"], en))
        if p:
            e["player"] = p
        if typ == "subst" and clean(v["assist_en"]):
            ien = clean(v["assist_en"])
            a = _person({"ar": names.get(ien, ""), "en": ien}, snm, pid(v["team_id"], ien))
            if a:
                e["assist"] = a   # التبديل: player = الخارج، assist = الداخل (اصطلاح المزوّد)
        out.append((v["minute"], e))
    # ترتيب ثابت: الدقيقة تصاعدياً، وداخلها ترتيب الإدراج (أهداف ← ملغاة ← أحداث، كـbuild_items قبل العكس)؛ بلا دقيقة آخراً
    idx = list(range(len(out)))
    idx.sort(key=lambda i: (out[i][0] is None, out[i][0] if out[i][0] is not None else 0, i))
    res = []
    for i in idx:
        mn, e = out[i]
        if mn is not None:
            e = {"minute": mn, **e}
        res.append(e)
    return res


def lineups_json(conn, m):
    """{home|away: {formation?, coach?, start[], subs[]}} — نفس صفوف كتلة الفريق بصفحة المباراة (lineup_view.team_rows)"""
    mid = m["match_id"]
    if not conn.execute("SELECT COUNT(*) FROM lineups WHERE match_id = ?", (mid,)).fetchone()[0]:
        return None
    snm = SN.match_map(conn, mid)
    out = {}
    for side, tid in (("home", m["home_id"]), ("away", m["away_id"])):
        info, players = LV.team_rows(conn, mid, tid)
        if not players:
            continue
        t = {}
        if info and clean(info["formation"]):
            t["formation"] = clean(info["formation"])
        if info:
            c = _person({"ar": clean(info["coach_ar"]), "en": clean(info["coach_en"])}, {})
            if c:
                c.pop("short", None)
                t["coach"] = c
        for key, starter in (("start", 1), ("subs", 0)):
            lst = []
            for p in players:
                if bool(p["starter"]) != bool(starter):
                    continue
                e = {}
                if p["number"] is not None:
                    e["number"] = p["number"]
                if clean(p["pos"]):
                    e["pos"] = clean(p["pos"])
                if clean(p["grid"]):
                    e["grid"] = clean(p["grid"])
                pl = _person({"ar": clean(p["player_ar"]), "en": clean(p["player_en"])}, snm, p["player_id"] or None)
                if pl:
                    e["player"] = pl
                lst.append(e)
            if lst:
                t[key] = lst
        out[side] = t
    return out or None


def stats_json(conn, m):
    rows = MM.stats_data(conn, m["match_id"], m["home_id"], m["away_id"])
    return {col: {"h": va, "a": vb} for col, _key, _unit, va, vb in rows} or None


def h2h_json(conn, m):
    rows, hw, dr, aw = MM.h2h_data(conn, m)
    if not rows:
        return None
    lst = []
    for r in rows:
        e = {"id": r["match_id"], "league": r["league_code"], "season": r["season"]}
        ko = kickoff_iso(r["date"])
        if ko:
            e["kickoff"] = ko
        else:
            e["date"] = str(r["date"])[:10]
        e.update({"home": r["home_id"], "away": r["away_id"], "score": {"h": r["home_goals"], "a": r["away_goals"]}})
        lst.append(e)
    return {"n": len(rows), "home_wins": hw, "draws": dr, "away_wins": aw, "matches": lst}


def table_mini_json(conn, m):
    out = []
    for i, r, tid in MM.positions_data(conn, m):
        out.append({"team": tid, "pos": i, "played": r["played"], "w": r["wins"], "d": r["draws"], "l": r["losses"],
                    "gf": r["scored"], "ga": r["scored"] - r["diff"], "gd": r["diff"], "pts": r["points"]})
    return out or None


def match_json(conn, m, fixes):
    o = match_core(m, fixes)
    venue = {k: v for k, v in (("name", MM._col(m, "venue_name")), ("city", MM._col(m, "venue_city"))) if v}
    if venue:
        o["venue"] = venue
    ref = MM._col(m, "referee")
    if ref:
        o["referee"] = ref
    for key, fn in (("events", events_json), ("lineups", lineups_json), ("stats", stats_json),
                    ("h2h", h2h_json), ("table_mini", table_mini_json)):
        v = fn(conn, m)
        if v:
            o[key] = v
    return o


def write(path, obj):
    b = dump(obj).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
    return b


def swap_in(tmp, target):
    """يستبدل target كله بـtmp (مجلدان شقيقان على نفس القرص): لا تبقى ملفات يوم/مباراة قديمة (مباراة انتقلت ليوم آخر).
    target القديم يُنقل جانباً أولاً ثم يُحذف بعد نجاح النقل؛ فشل النقل = target القديم يعود كما كان."""
    old = target.with_name(f".{target.name}.old")
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        target.rename(old)
    try:
        tmp.rename(target)
    except Exception:
        if old.exists() and not target.exists():
            old.rename(target)
        raise
    if old.exists():
        shutil.rmtree(old)


def main():
    t0 = time.time()
    target = Path(arg("--out") or (BASE / "api" / "v1")).resolve()
    # البناء بمجلد مؤقت شقيق ثم الاستبدال كاملاً (swap_in)؛ بقايا تشغيل سابق متعطّل تُمسح أولاً
    out = target.with_name(f".{target.name}.tmp")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    conn = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    teams = MM.load_teams()
    fixes = MM.load_corrections()
    seasons = current_seasons(conn)
    days = season_matches(conn, seasons)

    cols = "match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status" + (
        ", round" if MM.has_round(conn) else "") + (", venue_name, venue_city, referee" if MM.has_venue(conn) else "")
    byid = {r["match_id"]: r for r in conn.execute(f"SELECT {cols} FROM matches WHERE " + " OR ".join(
        "(league_code = ? AND season = ?)" for _ in seasons), [x for kv in seasons.items() for x in kv])}

    tids, day_index, n_matches, skipped = set(), [], 0, 0
    for d, mids in days.items():
        lst = []
        for mid in mids:
            m = byid[mid]
            # نفس make_matches: مباراة بنادٍ غير معروف بـteams_arabic.csv لا صفحة لها
            if m["home_id"] not in teams or m["away_id"] not in teams:
                skipped += 1
                continue
            tids.update((m["home_id"], m["away_id"]))
            lst.append(match_core(m, fixes))
            write(out / "matches" / f"{mid}.json", match_json(conn, m, fixes))
            n_matches += 1
        if not lst:
            continue
        b = write(out / "days" / f"{d}.json", lst)
        day_index.append({"date": d, "n": len(lst), "hash": hashlib.sha1(b).hexdigest()[:10]})

    write(out / "teams.json", teams_json(conn, teams, tids))
    leagues = []
    for code, season in seasons.items():
        e = {"code": code, "name": {lg: league_name(code, lg) for lg in LANGS2}, "season": season}
        lo = site_path(MM.league_logo_src(code, ""))
        if lo:
            e["logo"] = lo
        leagues.append(e)
    write(out / "index.json", {"v": 1, "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "leagues": leagues, "days": day_index})
    conn.close()
    swap_in(out, target)
    print(f"api/v1 → {target}")
    print(f"  {n_matches} مباراة، {len(day_index)} يوماً، {len(tids)} فريقاً، متخطّى (نادٍ غير معروف): {skipped}")
    print(f"  {time.time() - t0:.1f} ث")


if __name__ == "__main__":
    main()
