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
                         (14 نوفمبر 2026) venue = {name:{ar,en}, city?:{ar,en}} — العربي من venues_arabic.csv وإلا الإنجليزي
  leagues/<CODE>.json    (المرحلة 2) code, season, name, logo, table[{rank, team, played, w, d, l, gf, ga, gd, pts, form?, zone?}],
                         scorers_from ("player_stats" = بطاقات الصفحة / "goals" = قائمة get_scorers)،
                         (14 نوفمبر 2026) rounds[].rows = صفوف match_row بجانب matches[]، وcurrent_round (فهرس الجولة الحالية)،
                         scorers[{rank, player{id?, name, short?}, team, goals}], rounds[{round?, matches[ids]}]
                         — index.leagues[].file يشير إليه
  teams/<id>.json        (المرحلة 3) id, name, short?, logo, color?, league, season, venue?{name{ar,en}, city?{ar,en}, capacity?, surface?},
                         coach?{name, age?, nationality?} (من جدول coaches حتى لو أخفته الصفحة), standing?{rank, pts, played},
                         form?, squad[{player?, number?, pos?, pos_code?, apps}], matches{results[], upcoming[]}
  players/<id>.json      (المرحلة 3) id, slug, url, name, short?, full_name?{ar?, en?}, team?, number?, pos?, pos_code?,
                         nationality?, height?, age?, birth?, photo? (false = صورة المزوّد العامة), stats[{league, season, apps?,
                         starts?, minutes?, goals?, assists?, rating?, yellow?, red?}], matches[] (الأحدث أولاً)
                         (14 نوفمبر 2026) كل لاعب له صفحة ومعرّف (لا الموسم الجاري وحده، ولاعبو الكؤوس وحدها أيضاً):
                         stats = كل المواسم وكل المسابقات (صف الكأس برمزه، مثل SAU-KC — PLY.season_agg كصفحة الموقع، الأحدث أولاً)،
                         matches = كل المسابقات؛ team/number/pos/الاسم من صفوف الدوري وحدها (كصفحة الموقع)
  cups/<CODE>.json       (الموجة 1، 4 نوفمبر 2026) code, type, country?, season (موسم المزوّد), label (العرض: «2026/27» أو «2026»),
                         name, logo?, rounds[{round{ar,en}, ties[{home?, away?, legs[ids], agg?{h,a}, pen?{h,a}, winner?, tbd?}]}],
                         third_place?[tie], champion?, scorers[{rank, player{id?, name, short?}, team, goals}]
                         — بلا table (لا جدول لكأس). (الموجة 3) كأس بمرحلة مجموعات/دوري (config "table") يضيف
                         tables[{group?, name?{ar,en}, line?, rows[{pos, team, p, w, d, l, gf, ga, gd, pts}]}] (cup_tables، محسوب من النتائج؛
                         name = اسم المجموعة الرسمي، الموجة 4: AFC-CLE «West/East»، AFC-CL2 «Group A..H»)
                         (14 نوفمبر 2026) ties[].rows = صف مضغوط لكل مباراة (match_row: {id, ko|date, st, h, a, s?[h,a], p?[h,a]})؛
                         كأس بمرحلة: group_rounds[{round?, rows[]}] + current_round (فهرس أول جولة فيها مباراة يومها ≥ اليوم، عمّان)
                         وrounds من أدوار ما بعد المرحلة وحدها. index.cups[] يشير إليه. مباريات الكؤوس بملفات matches/ و days/ أيضاً
                         (بعد الدوريات بنفس اليوم، بترتيب config.COMPETITIONS)، والمباراة تحمل pen{h,a} إن حُسمت بالترجيح.
  search.json            (المرحلة 3) صفوف make_search.collect(): {type:"team", id, name, league, n} و{type:"player", id?, slug?,
                         url?, name, team, file} + بآخرها لاعبو players/ الغائبون عن collect (search_add_missing)
  ⚠️ full_name.ar هو **الاستثناء الوحيد** من «كل اسم {ar, en}»: يظهر فقط إن وُجد اسم كامل عربي حقيقي. pos_code = G/D/M/F
     موحَّد من الصيغتين (رمز المباراة أو اسم player_info)؛ pos يبقى كما هو.

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
from make_site3 import window_matches, get_table, get_scorers  # noqa: E402
import make_leagues as ML          # noqa: E402
import league_player_cards as LPC  # noqa: E402
import player_pages as PP          # noqa: E402
from zones import zone_list        # noqa: E402
import make_clubs as MC            # noqa: E402
import make_players as MP          # noqa: E402
import player_layout as PLY        # noqa: E402
import make_search as MS           # noqa: E402
from i18n import T, league_name, off_label  # noqa: E402
from live_view import var_label  # noqa: E402
from match_round import label as round_label  # noqa: E402
import competitions as CP  # noqa: E402
import cup_bracket as CB  # noqa: E402
import cup_tables as CT  # noqa: E402
import match_score as MSC  # noqa: E402  (MS = make_search أعلاه)
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


# (14 نوفمبر 2026) أسماء الملاعب بالعربي: venues_arabic.csv (name_en,city_en,name_ar,city_ar)، المطابقة على اسم المزوّد حرفياً
# (name_en)؛ city_en للتوثيق فقط. بلا صف = العربي يرتد للإنجليزي (كبقية الأسماء {ar, en}).
VENUES_AR_FILE = BASE / "venues_arabic.csv"
_VENUES_AR = None


def venue_ar(name_en):
    """(name_ar, city_ar) أو (None, None)"""
    global _VENUES_AR
    if _VENUES_AR is None:
        _VENUES_AR = {}
        try:
            import csv
            with open(VENUES_AR_FILE, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if (r.get("name_en") or "").strip():
                        _VENUES_AR[r["name_en"].strip()] = ((r.get("name_ar") or "").strip() or None,
                                                            (r.get("city_ar") or "").strip() or None)
        except OSError:
            pass
    return _VENUES_AR.get((name_en or "").strip(), (None, None))


def venue_obj(name_en, city_en):
    """{name: {ar, en}, city?: {ar, en}} — None بلا اسم ولا مدينة"""
    name_en, city_en = clean(name_en), clean(city_en)
    nar, car = venue_ar(name_en)
    o = {}
    if name_en or nar:
        o["name"] = {"ar": nar or name_en, "en": name_en or nar}
    if city_en or car:
        o["city"] = {"ar": car or city_en, "en": city_en or car}
    return o or None


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
        order[d] = [mid for code in list(LEAGUES) + list(CP.COMPETITIONS) for mid in by_day[d].get(code, [])]
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
    # (الموجة 1) ركلات الترجيح — صفوف بأعمدة match_score فقط (بعد الهجرة)؛ الدوريات بلا ترجيح = لا مفتاح
    if "pen_home" in m.keys() and m["pen_home"] is not None and m["pen_away"] is not None:
        o["pen"] = {"h": m["pen_home"], "a": m["pen_away"]}
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
    venue = venue_obj(MM._col(m, "venue_name"), MM._col(m, "venue_city"))   # {name:{ar,en}, city?:{ar,en}}
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


# ── الدوري (المرحلة 2) ──
FORM_END = "9999-12-31"   # team_form قبل هذا التاريخ = آخر 5 منتهية حتى الآن (كل المسابقات، الأحدث أولاً — كبطاقة الفورمة)


def match_row(m):
    """(14 نوفمبر 2026) صف مباراة مضغوط داخل الجولات/المواجهات — يغني التطبيق عن جلب matches/<id>.json لكل مباراة:
    {id, ko (UTC ISO) أو date, st, h, a, s?:[أهداف المضيف، الضيف], p?:[ترجيح]} — نفس قيم match_core."""
    e = {"id": m["match_id"]}
    ko = kickoff_iso(m["date"])
    if ko:
        e["ko"] = ko
    else:
        e["date"] = str(m["date"])[:10]
    e["st"] = m["status"]
    e["h"], e["a"] = m["home_id"], m["away_id"]
    if m["home_goals"] is not None and m["away_goals"] is not None:
        e["s"] = [m["home_goals"], m["away_goals"]]
    if "pen_home" in m.keys() and m["pen_home"] is not None and m["pen_away"] is not None:
        e["p"] = [m["pen_home"], m["pen_away"]]
    return e


def current_round(groups_of_matches):
    """فهرس أول جولة فيها مباراة يومها (عمّان) ≥ اليوم — نفس قاعدة تبويب المباريات بصفحة الدوري (make_leagues.matches_tab:
    أول يوم ≥ اليوم)؛ كلها انتهت = الأخيرة."""
    today = datetime.now(ML.AMMAN).date()
    for i, ms in enumerate(groups_of_matches):
        if any(ML.match_day(m)[0] >= today for m in ms):
            return i
    return max(0, len(groups_of_matches) - 1)


def league_json(conn, code, season, mids, byid, plan):
    """leagues/<CODE>.json: الجدول (get_table + zones)، الهدّافون (get_scorers + scorer_names)، الجولات.
    mids: مباريات الموسم التي لها ملف (نفس ملفات matches/)."""
    o = {"code": code, "season": season, "name": {lg: league_name(code, lg) for lg in LANGS2}}
    lo = site_path(MM.league_logo_src(code, ""))
    if lo:
        o["logo"] = lo
    # الجدول: نفس صفوف صفحة الدوري بترتيبها (get_table → tiebreak.sort_table، بلا STANDINGS_EXCLUDED) ومنطقة كل مركز (zones.py)
    zl = zone_list(conn, code, season)
    table = []
    for i, r in enumerate(get_table(conn, code, season), 1):
        tid = r["team_id"]
        row = {"rank": i, "team": tid, "played": r["played"], "w": r["wins"], "d": r["draws"], "l": r["losses"],
               "gf": r["scored"], "ga": r["scored"] - r["diff"], "gd": r["diff"], "pts": r["points"]}
        form = [MM.form_result(x, tid) for x in MM.team_form(tid, FORM_END, None)]
        if form:
            row["form"] = form
        z = zl.get(i)
        if z:
            row["zone"] = {"code": z[0], "label": {"ar": z[1], "en": z[2]}}
        table.append(row)
    if table:
        o["table"] = table
    # الهدّافون = ما تعرضه صفحة الدوري نفسها:
    #   • تغطية player_stats كافية (lpc.available): بطاقة «الهدّافون» وقائمتها الكاملة <code>-goals.html — lpc.rows/ranked
    #     (مركز التعادل المشترك، معرّف اللاعب، آخر نادٍ لعب له) والأسماء المختصرة من lpc.list_names
    #   • وإلا: قائمة get_scorers (limit=1000، ترتيبها) والأسماء من ML.scorer_names؛ المعرّف من خطة صفحات اللاعبين
    lst = []
    if LPC.available(conn, code, season):
        o["scorers_from"] = "player_stats"
        ranked = LPC.ranked(LPC.rows(conn, code, season), "goals")
        snm = {lg: LPC.list_names(ranked, lg) for lg in LANGS2}
        for rk, p, v in ranked:
            full = {"ar": p["ar"] or p["en"], "en": p["en"] or p["ar"]}
            pl = {"id": p["pid"], "name": full}
            sh = {lg: SN.apply(snm[lg], LPC._name(p, lg)) for lg in LANGS2}
            if sh != full:
                pl["short"] = sh
            lst.append({"rank": rk, "player": pl, "team": p["tid"], "goals": v})
    else:
        o["scorers_from"] = "goals"
        scorers = get_scorers(conn, code, season, limit=1000)
        shown = {lg: ML.scorer_names(scorers, lg) for lg in LANGS2}
        pid_of = {p["slug"]: p["stats_pid"] for p in plan["pages"] if p.get("stats_pid")}
        for i, s in enumerate(scorers):
            en = clean(s["player"])
            full = {"ar": clean(s["player_ar"]) or en, "en": en}
            p = {}
            pid = pid_of.get(PP.link_slug(s["player"], s["team_id"], plan) or "")
            if pid:
                p["id"] = pid
            p["name"] = full
            sh = {lg: shown[lg][i] for lg in LANGS2}
            if sh != full:
                p["short"] = sh
            lst.append({"rank": i + 1, "player": p, "team": s["team_id"], "goals": s["goals"]})
    if lst:
        o["scorers"] = lst
    # الجولات: بترتيب أول موعد بكل جولة (ثم النص)، والمباريات داخلها بالموعد ثم المعرّف (ترتيب تبويب المباريات الزمني)
    groups = {}
    for mid in mids:
        m = byid[mid]
        groups.setdefault(MM._rnd(m), []).append(m)
    rounds = []
    for raw, ms in sorted(groups.items(), key=lambda kv: (min(str(m["date"]) for m in kv[1]), kv[0])):
        ms.sort(key=lambda m: (str(m["date"]), m["match_id"]))
        e = {}
        lbl = {lg: round_label(raw, lg) for lg in LANGS2}
        if lbl["ar"] or lbl["en"]:
            e["round"] = lbl
        e["matches"] = [m["match_id"] for m in ms]
        e["rows"] = [match_row(m) for m in ms]
        rounds.append(e)
    if rounds:
        o["rounds"] = rounds
        o["current_round"] = current_round([[byid[r["id"]] for r in e["rows"]] for e in rounds])
    return o


def cup_json(conn, code, season, plan):
    """cups/<CODE>.json (الموجة 1): الأدوار والمواجهات (cup_bracket.build — نفس تبويب الشجرة بصفحة الكأس) والهدّافون (get_scorers)"""
    c = CP.comp(code)
    o = {"code": code, "type": c["type"]}
    if c.get("country"):
        o["country"] = c["country"]
    o["season"] = season
    o["label"] = CP.season_label(code, season)
    o["name"] = {lg: league_name(code, lg) for lg in LANGS2}
    lo = site_path(MM.league_logo_src(code, ""))
    if lo:
        o["logo"] = lo
    rows = conn.execute("""SELECT match_id, date, status, round, home_id, away_id, home_goals, away_goals, pen_home, pen_away
                           FROM matches WHERE league_code = ? AND season = ?""", (code, season)).fetchall()
    how = CT.mode(code)   # (الموجة 3) None = كأس إقصائية بلا تغيير
    bk = CB.build(CT.knockout_rows(rows) if how else rows, c["type"])

    def tie(t):
        e = {}
        if t["a"] is not None:
            e["home"] = t["a"]
        if t["b"] is not None:
            e["away"] = t["b"]
        e["legs"] = [m["match_id"] for m in t["legs"]]
        e["rows"] = [match_row(m) for m in t["legs"]]
        if t["agg"] is not None:
            e["agg"] = {"h": t["agg"][0], "a": t["agg"][1]}
        if t["pens"]:
            e["pen"] = {"h": t["pens"][0], "a": t["pens"][1]}
        if t["winner"] is not None:
            e["winner"] = t["winner"]
        if t["placeholder"]:
            e["tbd"] = True
        return e
    rounds = []
    for rd in bk["rounds"]:
        raw = CB.display_round(rd["round"], bk)
        lbl = {lg: round_label(raw, lg) or raw for lg in LANGS2}
        rounds.append({"round": lbl, "ties": [tie(t) for t in rd["ties"]]})
    if rounds:
        o["rounds"] = rounds
    if bk["extra"]:
        o["third_place"] = [tie(t) for t in bk["extra"]]
    if bk["champion"] is not None:
        o["champion"] = bk["champion"]
    if how:
        tl = []
        for g in CT.tables(rows, how, CT.en_names(conn).get, code):
            e = {}
            if g["group"] is not None:
                e["group"] = g["group"]
            if g.get("name"):          # (الموجة 4) اسم المجموعة الرسمي {ar, en}
                e["name"] = dict(g["name"])
            if CT.line(code):
                e["line"] = CT.line(code)
            e["rows"] = [{"pos": r["pos"], "team": r["team"], "p": r["played"], "w": r["won"], "d": r["drawn"],
                          "l": r["lost"], "gf": r["gf"], "ga": r["ga"], "gd": r["gd"], "pts": r["points"]} for r in g["rows"]]
            tl.append(e)
        o["tables"] = tl
        # (14 نوفمبر 2026) مباريات مرحلة المجموعات/الدوري بجولاتها (كانت غائبة: rounds = ما بعد المرحلة وحده)
        groups = {}
        for m in rows:
            if CT.is_table_round(m["round"]):
                groups.setdefault(MM._rnd(m), []).append(m)
        gr, gms = [], []
        for raw, ms in sorted(groups.items(), key=lambda kv: (min(str(m["date"]) for m in kv[1]), kv[0])):
            ms.sort(key=lambda m: (str(m["date"]), m["match_id"]))
            e = {}
            lbl = {lg: round_label(raw, lg) for lg in LANGS2}
            if lbl["ar"] or lbl["en"]:
                e["round"] = lbl
            e["rows"] = [match_row(m) for m in ms]
            gr.append(e)
            gms.append(ms)
        if gr:
            o["group_rounds"] = gr
            o["current_round"] = current_round(gms)
    scorers = get_scorers(conn, code, season, limit=1000)
    shown = {lg: ML.scorer_names(scorers, lg) for lg in LANGS2}
    pid_of = {p["slug"]: p["stats_pid"] for p in plan["pages"] if p.get("stats_pid")}
    lst = []
    for i, s in enumerate(scorers):
        en = clean(s["player"])
        full = {"ar": clean(s["player_ar"]) or en, "en": en}
        p = {}
        pid = pid_of.get(PP.link_slug(s["player"], s["team_id"], plan) or "")
        if pid:
            p["id"] = pid
        p["name"] = full
        sh = {lg: shown[lg][i] for lg in LANGS2}
        if sh != full:
            p["short"] = sh
        lst.append({"rank": i + 1, "player": p, "team": s["team_id"], "goals": s["goals"]})
    if lst:
        o["scorers"] = lst
    return o


# رمز المركز الموحَّد (قرار 2 نوفمبر 2026): G/D/M/F من الصيغتين — رمز المباراة (G/D/M/F) أو اسم player_info
# (MC._INFO_POS: Goalkeeper/Defender/Midfielder/Attacker). `pos` يبقى نص المصدر كما هو؛ غير المعروف يُسجَّل بـUNMAPPED ولا pos_code.
UNMAPPED = set()


def pos_code(pos):
    p = (pos or "").strip()
    if p in ("G", "D", "M", "F"):
        return p
    c = MC._INFO_POS.get(p)
    if c:
        return c
    if p:
        UNMAPPED.add(p)
    return None


# ── الفرق (المرحلة 3) ──
def team_full_json(conn, tid, cteams, tentry):
    """teams/<id>.json — نفس بيانات صفحة النادي (make_clubs): الموسم الحالي = أحدث (دوري، موسم) للنادي (make_clubs.current_of)."""
    seasons = [(r["league_code"], r["season"]) for r in MC.club_seasons(conn, tid)]
    t = cteams.get(tid)
    if not seasons or not t:
        return None
    code, season = MC.current_of(seasons)   # كصفحة النادي: أحدث دوري (الكؤوس لا تكون «الحالي»، الموجة 0)
    o = {"id": tid, "name": {lg: MC.tname(t, lg, full=True) for lg in LANGS2}}
    sh = {lg: MC.tname(t, lg) for lg in LANGS2}
    if sh != o["name"]:
        o["short"] = sh
    for k in ("logo", "color"):
        if k in tentry:
            o[k] = tentry[k]
    o["league"], o["season"] = code, season
    v = MC.stadium_data(conn, tid)
    if v:
        # (14 نوفمبر 2026) name/city بـ{ar, en} من venues_arabic.csv كملاعب المباريات (venue_obj)؛ السعة والأرضية كما هي
        vo = venue_obj(v["name"], v["city"]) or {}
        vo.update({k: v[k] for k in ("capacity", "surface") if v[k]})
        if vo:
            o["venue"] = vo
    # المدرب (قرار 2 نوفمبر 2026): كلما وُجد بجدول coaches (أو تشكيلات الموسم) — حتى لو أخفت الصفحة تبويب اللاعبين
    #    (بلا قائمة رسمية ولا تشكيلات، squad_data = None) فلا تعرضه
    sd = MC.squad_data(conn, tid, code, season)
    cd = MC.coach_data(conn, tid, code, season)
    if cd:
        c = {"name": {"ar": cd["ar"] or cd["en"], "en": cd["en"]}}
        if cd["age"]:
            c["age"] = cd["age"]
        if cd["nationality"]:
            c["nationality"] = cd["nationality"]
        o["coach"] = c
    for i, r in enumerate(MC.standings(conn, code, season), 1):
        if r["team_id"] == tid:
            o["standing"] = {"rank": i, "pts": r["points"], "played": r["played"]}
            break
    form = [MM.form_result(x, tid) for x in MM.team_form(tid, FORM_END, None)]
    if form:
        o["form"] = form
    if sd:
        squad = []
        for code_p, _key in MC.POS_GROUPS:   # ترتيب تبويب اللاعبين: المركز ثم المشاركات ثم الاسم
            for p in MC.squad_group(sd["players"], code_p):
                e = {}
                pl = {}
                if p["pid"]:
                    pl["id"] = p["pid"]
                pl["name"] = {"ar": p["ar"] or p["en"], "en": p["en"] or p["ar"]}
                if pl["name"]["en"]:
                    e["player"] = pl
                if p["num"] is not None:
                    e["number"] = p["num"]
                if code_p:
                    e["pos"] = code_p
                    e["pos_code"] = pos_code(code_p)
                e["apps"] = len(p["apps"])
                squad.append(e)
        if squad:
            o["squad"] = squad
    ms = MC.club_season_matches(conn, tid, season, code)   # (الموجة 1) الكؤوس بنافذة التاريخ كصفحة النادي
    res = [m["match_id"] for m in ms if m["home_goals"] is not None and m["away_goals"] is not None]
    up = [m["match_id"] for m in ms if m["home_goals"] is None or m["away_goals"] is None]
    mm = {}
    if res:
        mm["results"] = res
    if up:
        mm["upcoming"] = up
    if mm:
        o["matches"] = mm
    return o


# ── اللاعبون (المرحلة 3) ──
def players_json(conn, seasons):
    """{pid: players/<pid>.json} — كل صفحة لاعب لها معرّف (stats_pid) ولعب أو سجّل بأي مسابقة وأي موسم (14 نوفمبر 2026؛
    كان: الموسم الجاري لدوريه فقط). seasons لم يعد يُستعمل هنا (باقٍ بالتوقيع لاستدعاء main).
    نفس مدخلات make_players.build: plan (player_pages)، gather، gather_extra، PLY.season_agg/profile_data، full_name، current_team."""
    plan = PP.get_plan()
    _goals, _bridge, _stats, srows_all = MP.gather(conn)
    pids = {p["stats_pid"] for p in plan["pages"] if p["stats_pid"]}
    info, plays = MP.gather_extra(conn, pids)
    PLY.load_squad_numbers(conn)   # رقم القميص من قائمة النادي الحالي (14 نوفمبر 2026)
    out, skipped = {}, {"no_id": 0, "no_data": 0, "dup_id": 0}
    # صفحات المعرّف (kind "pid") أولاً: صفحة اسم مجسورة لنفس المعرّف لا تغلب الصفحة القانونية؛ صفحتا اسم بمعرّف واحد = الأولى
    for page in sorted(plan["pages"], key=lambda p: p["kind"] != "pid"):
        pid = page["stats_pid"]
        if not pid:
            skipped["no_id"] += 1
            continue
        # النادي/المركز/الرقم/الاسم من صفوف الدوري وحدها (rows/pl، كـbase_rows بصفحة الموقع)؛ الإحصائيات والمباريات من الكل
        all_rows = page["goals"]
        all_pl = plays.get(pid, [])
        rows = [r for r in all_rows if not CP.is_cup(r["league_code"])]
        pl = [e for e in all_pl if not CP.is_cup(e["m"]["league_code"])]
        if not all_pl and not all_rows:
            skipped["no_data"] += 1
            continue
        if pid in out:
            skipped["dup_id"] += 1
            continue
        en = clean(page["display_en"])
        ar = page["display_ar"] or (MP.pick_display_ar(rows or page["goals"]) if page["goals"] else "")   # نفس اسم الصفحة
        o = {"id": pid, "slug": page["slug"], "url": f"/players/{page['slug']}.html",
             "name": {"ar": ar or en, "en": en or ar}}
        sh = {lg: SN.short_name(o["name"][lg]) for lg in LANGS2}
        if sh != o["name"]:
            o["short"] = sh
        # الاسم الكامل (قرار 2 نوفمبر 2026) — **الاستثناء الوحيد من «كل اسم {ar, en}»**: full_name.ar فقط إن وُجد اسم كامل عربي
        # حقيقي (full_name(pid, "ar") لا يرجع لاتينياً أبداً)، وإلا يُحذف؛ full_name.en من player_full_names.csv. كل لغة تظهر حين
        # تعرضها صفحتها: موجودة وتختلف عن الاسم المعروض.
        fa, fe = MP.full_name(pid, "ar"), MP.full_name(pid, "en")
        fn = {}
        if fa and fa.strip() != o["name"]["ar"].strip():
            fn["ar"] = fa
        if fe and fe.strip() != o["name"]["en"].strip():
            fn["en"] = fe
        if fn:
            o["full_name"] = fn
        team = MP.current_team(rows, pl)
        if team:
            o["team"] = team
        prof = PLY.profile_data(info.get(pid), pl, pid, team)
        for k in ("number", "pos", "nationality", "height"):
            if k in prof:
                o[k] = prof[k]
        # (14 نوفمبر 2026) صورة المزوّد الرمادية العامة (has_photo = 0) = بلا صورة، كـplayer_layout.photo_url — التطبيق يخفيها
        if (info.get(pid) or {}).get("has_photo") == 0:
            o["photo"] = False
        if "pos" in prof:
            pc = pos_code(prof["pos"])
            if pc:
                o["pos_code"] = pc
        if "age" in prof:
            y, m, d = prof["birth"]
            o["age"], o["birth"] = prof["age"], f"{y:04d}-{m:02d}-{d:02d}"
        agg = PLY.season_agg(all_pl, all_rows)
        srows = {(r["season"], r["league_code"]): r for r in MP.fill_goals(srows_all.get(pid, []), all_rows)}
        st = []
        for (s, lg), d in sorted(agg.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
            if not (d["matches"] or d["goals"]):
                continue
            e = {"league": lg, "season": s}
            for k, key in (("apps", "matches"), ("starts", "started"), ("minutes", "mins"), ("goals", "goals"),
                           ("assists", "assists"), ("rating", "rating")):
                v = d.get(key)
                if v is not None and not (key == "matches" and not v):
                    e[k] = v
            sr = srows.get((s, lg))
            if sr:
                for k, key in (("yellow", "yel"), ("red", "red")):
                    if sr.get(key) is not None:
                        e[k] = int(sr[key])
            st.append(e)
        if st:
            o["stats"] = st
        mids = [e["mid"] for e in all_pl]   # كل المسابقات، الأحدث أولاً (ترتيب gather_extra)
        if mids:
            o["matches"] = mids
        out[pid] = o
    return out, skipped


def search_json(api_pids):
    """search.json — نفس صفوف make_search.collect() وترتيبها (الأندية التي لها صفحة + اللاعبون بالأكثر أهدافاً).
    صف اللاعب: file = هل players/<id>.json موجود (api_pids)، url = رابط صفحته العربية بالموقع (إن وُجدت)."""
    clubs, players = MS.collect()
    out = []
    for tid, ar, en, lg, _logo, n in clubs:
        e = {"type": "team", "id": tid, "name": {"ar": ar or en, "en": en or ar}}
        if lg:
            e["league"] = lg
        e["n"] = n
        out.append(e)
    for ar, en, tid, slg, pid in players:
        e = {"type": "player"}
        if pid:
            e["id"] = pid
        if slg:
            e["slug"] = slg
            e["url"] = f"/players/{slg}.html"
        e["name"] = {"ar": ar or en, "en": en or ar}
        e["team"] = tid
        e["file"] = bool(pid) and pid in api_pids
        out.append(e)
    return out


def search_add_missing(sj, pj):
    """لاعبو players/ الغائبون عن صفوف collect() (2 نوفمبر 2026): collect يجمّع الأهداف بـ(الاسم الإنجليزي، النادي) فهويّتان
    بنفس الاسم والنادي (ali-saleh / ali-saleh-2) تصيران صفاً واحداً — الثانية لا يجدها بحث الموقع نفسه. تُلحَق بآخر القائمة (أدنى
    رتبة) من ملفاتها نفسها فيجد التطبيق كل لاعب له ملف. يرجّع قائمة المُلحَقين (للتقرير)."""
    have = {e.get("id") for e in sj if e["type"] == "player" and e.get("file")}
    added = []
    for pid in sorted(pj):
        if pid in have:
            continue
        o = pj[pid]
        e = {"type": "player", "id": pid, "slug": o["slug"], "url": o["url"], "name": o["name"]}
        if "team" in o:
            e["team"] = o["team"]
        e["file"] = True
        sj.append(e)
        added.append(o["slug"])
    return added


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
    # (الموجة 1) الكؤوس: موسم المزوّد الجاري بالسجلّ، فقط ما له مباريات — بالأيام والمباريات مع الدوريات، وملفاتها بـcups/
    cups = {c: CP.current_season(c) for c in CP.COMPETITIONS
            if conn.execute("SELECT 1 FROM matches WHERE league_code = ? AND season = ? LIMIT 1",
                            (c, CP.current_season(c))).fetchone()}
    allsea = {**seasons, **cups}
    days = season_matches(conn, allsea)

    cols = "match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status" + (
        ", round" if MM.has_round(conn) else "") + (", venue_name, venue_city, referee" if MM.has_venue(conn) else "") + (
        ", " + ", ".join(MSC.COLS) if MSC.has_score(conn) else "")
    byid = {r["match_id"]: r for r in conn.execute(f"SELECT {cols} FROM matches WHERE " + " OR ".join(
        "(league_code = ? AND season = ?)" for _ in allsea), [x for kv in allsea.items() for x in kv])}

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

    MM.build_form_index(conn)
    plan = PP.get_plan()   # نفس الخطة المخبّأة التي تستعملها روابط اللاعبين بالصفحات (بلا conn = قراءة فقط)
    written = {mid for mids in days.values() for mid in mids
               if byid[mid]["home_id"] in teams and byid[mid]["away_id"] in teams}
    leagues = []
    for code, season in seasons.items():
        lj = league_json(conn, code, season, sorted(m for m in written if byid[m]["league_code"] == code), byid, plan)
        tids.update(r["team"] for r in lj.get("table", []))
        tids.update(s["team"] for s in lj.get("scorers", []))
        write(out / "leagues" / f"{code}.json", lj)
        e = {"code": code, "name": lj["name"], "season": season}
        if "logo" in lj:
            e["logo"] = lj["logo"]
        e["file"] = f"leagues/{code}.json"
        leagues.append(e)
    cup_index = []
    for code, season in cups.items():
        cj = cup_json(conn, code, season, plan)
        for rd in cj.get("rounds", []) + [{"ties": cj.get("third_place", [])}]:
            for t in rd["ties"]:
                tids.update(x for x in (t.get("home"), t.get("away")) if x is not None and x in teams)
        tids.update(s["team"] for s in cj.get("scorers", []) if s["team"] in teams)
        write(out / "cups" / f"{code}.json", cj)
        e = {"code": code, "type": cj["type"], "name": cj["name"], "season": season, "label": cj["label"]}
        if "logo" in cj:
            e["logo"] = cj["logo"]
        e["file"] = f"cups/{code}.json"
        cup_index.append(e)
    tj = teams_json(conn, teams, tids)
    write(out / "teams.json", tj)
    # المرحلة 3: الفرق واللاعبون والبحث
    cteams = MC.load_teams()
    n_teams = 0
    for tid in sorted(tids):
        o = team_full_json(conn, tid, cteams, tj.get(str(tid), {}))
        if o:
            write(out / "teams" / f"{tid}.json", o)
            n_teams += 1
    pj, pskip = players_json(conn, seasons)
    for pid, o in pj.items():
        write(out / "players" / f"{pid}.json", o)
    sj = search_json(set(pj))
    s_added = search_add_missing(sj, pj)
    write(out / "search.json", sj)
    write(out / "index.json", {"v": 1, "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "leagues": leagues, **({"cups": cup_index} if cup_index else {}), "days": day_index,
                               "files": {"teams": "teams/{id}.json", "players": "players/{id}.json", "search": "search.json"},
                               "counts": {"teams": n_teams, "players": len(pj), "search": len(sj)}})
    conn.close()
    swap_in(out, target)
    print(f"api/v1 → {target}")
    print(f"  {n_matches} مباراة، {len(day_index)} يوماً، {len(tids)} فريقاً، متخطّى (نادٍ غير معروف): {skipped}")
    print(f"  teams/ {n_teams}، players/ {len(pj)} (متخطّى: {pskip})، search.json {len(sj)} صفاً")
    print(f"  pos_code: قيم بلا رمز موحَّد: {sorted(UNMAPPED) or 'لا شيء'}")
    print(f"  search.json: لاعبون أُلحِقوا (غائبون عن بحث الموقع: نفس الاسم والنادي): {len(s_added)} {s_added}")
    print(f"  {time.time() - t0:.1f} ث")


if __name__ == "__main__":
    main()
