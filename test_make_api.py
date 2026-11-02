#!/usr/bin/env python3
"""
JSON API v1 (make_api.py) — مخطط + تطابق مع صفحات المباريات (2 نوفمبر 2026). قراءة فقط: لا كتابة على football.db ولا على الصفحات.
    python C:\\Users\\User\\Projects\\Football\\test_make_api.py [api_dir] [n_parity]
api_dir افتراضياً api/v1. يحتاج: make_api.py شُغّل إلى api_dir، وmake_matches.py شُغّل من نفس football.db (الصفحات تُقرأ من
matches/ وen/matches/ بالمستودع).

  a. المخطط: كل ملف (index, teams, days/*, matches/*) — المفاتيح المطلوبة وأنواعها، لا null ولا "" بأي مكان، كل name = {ar,en}
     نصّان غير فارغين، ملفات الأيام = index.days (العدد والـhash)، كل مباراة بيوم لها ملف، كل فريق مذكور موجود بـteams.json.
  b. التطابق: n_parity مباراة (افتراضياً 200؛ كل الدوريات؛ منتهية/قادمة/مؤجّلة/بجزاء/بهدف عكسي/ببطاقة حمراء، ركلات ترجيح إن وُجدت)
     مقابل الصفحتين العربية والإنجليزية: النتيجة، الحالة (شارة FT)، الموعد، تسمية التأجيل، اسما الفريقين، الهدّافون (الاسم
     المعروض + الدقيقة + الجهة)، البطاقات الحمراء. أي اختلاف = فشل ويُطبع.
  c. لا اسم عربي فارغ/إنجليزي حيث الصفحة العربية تعرض العربي (كل أسطر الأحداث بالعيّنة).
  d. (المرحلة 2) leagues/<CODE>.json مقابل صفحة الدوري الحالية (عربي + إنجليزي) لكل الدوريات: كل صف بالجدول (المركز، الفريق،
     لعب، النقاط، الفارق) وأول 10 هدّافين (الاسم المعروض + الأهداف + المركز) — من قائمة الصفحة أو <code>-goals.html لدوريات
     بطاقات player_stats؛ والجدول = لقطة assets/table_<CODE>_<season>.json (make_live_tables.py؛ JOR بلا لقطة).
     يحتاج make_leagues.py وmake_live_tables.py من نفس القاعدة.
"""
import hashlib
import html
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
R = Path(__file__).resolve().parent
API = Path(sys.argv[1]) if len(sys.argv) > 1 else R / "api" / "v1"
N_PARITY = int(sys.argv[2]) if len(sys.argv) > 2 else 200
FAILS = []


def fail(msg):
    FAILS.append(msg)


AR_RE = re.compile(r"[\u0600-\u06FF]")
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── a. المخطط ──
def no_empty(obj, where):
    if obj is None:
        fail(f"{where}: null")
    elif isinstance(obj, str):
        if not obj.strip():
            fail(f"{where}: empty string")
    elif isinstance(obj, dict):
        if not obj:
            fail(f"{where}: empty object")
        for k, v in obj.items():
            no_empty(v, f"{where}.{k}")
            if k in ("name", "label", "short", "round") and isinstance(v, dict):
                if set(v) != {"ar", "en"} or not all(isinstance(v[x], str) and v[x].strip() for x in ("ar", "en")):
                    fail(f"{where}.{k}: not {{ar,en}} non-empty: {v}")
    elif isinstance(obj, list):
        if not obj:
            fail(f"{where}: empty list")
        for i, v in enumerate(obj):
            no_empty(v, f"{where}[{i}]")


def need(o, key, typ, where):
    if key not in o:
        fail(f"{where}: missing {key}")
        return False
    if not isinstance(o[key], typ) or (typ is int and isinstance(o[key], bool)):
        fail(f"{where}.{key}: type {type(o[key]).__name__}")
        return False
    return True


def check_core(m, where, teams):
    for k, t in (("id", int), ("league", str), ("status", str), ("home", int), ("away", int)):
        need(m, k, t, where)
    if "kickoff" in m:
        if not ISO_Z.match(m["kickoff"]):
            fail(f"{where}.kickoff: {m['kickoff']}")
    elif not (isinstance(m.get("date"), str) and DATE.match(m["date"])):
        fail(f"{where}: neither kickoff nor date")
    for side in ("home", "away"):
        if str(m.get(side)) not in teams:
            fail(f"{where}.{side}: team {m.get(side)} not in teams.json")
    for k in ("score", "pen"):
        if k in m and not (isinstance(m[k], dict) and set(m[k]) == {"h", "a"}
                           and all(isinstance(m[k][x], int) for x in ("h", "a"))):
            fail(f"{where}.{k}: {m[k]}")
    if m.get("status") in ("FT", "AET", "PEN") and "score" not in m:
        fail(f"{where}: finished without score")
    if "postponed" in m and "label" not in m["postponed"]:
        fail(f"{where}.postponed: no label")


def check_person(p, where):
    if need(p, "name", dict, where) and "id" in p and not isinstance(p["id"], int):
        fail(f"{where}.id: {p['id']}")


def check_match_file(o, where, teams):
    check_core(o, where, teams)
    for e_i, e in enumerate(o.get("events", [])):
        w = f"{where}.events[{e_i}]"
        need(e, "team", int, w)
        need(e, "type", str, w)
        if e.get("type") not in ("goal", "cancelled_goal", "card", "subst", "var"):
            fail(f"{w}.type: {e.get('type')}")
        if "minute" in e and not isinstance(e["minute"], int):
            fail(f"{w}.minute: {e['minute']}")
        for k in ("player", "assist"):
            if k in e:
                check_person(e[k], f"{w}.{k}")
    lu = o.get("lineups", {})
    for side, t in lu.items():
        if side not in ("home", "away"):
            fail(f"{where}.lineups: side {side}")
        for k in ("start", "subs"):
            for i, p in enumerate(t.get(k, [])):
                if "player" in p:
                    check_person(p["player"], f"{where}.lineups.{side}.{k}[{i}]")
                if "number" in p and not isinstance(p["number"], int):
                    fail(f"{where}.lineups.{side}.{k}[{i}].number")
    for k, v in o.get("stats", {}).items():
        if not (isinstance(v, dict) and set(v) == {"h", "a"} and all(isinstance(v[x], (int, float)) for x in "ha")):
            fail(f"{where}.stats.{k}: {v}")
    if "h2h" in o:
        h = o["h2h"]
        for k in ("n", "home_wins", "draws", "away_wins"):
            need(h, k, int, f"{where}.h2h")
        if h.get("n") != len(h.get("matches", [])) or h.get("n") != h.get("home_wins", 0) + h.get("draws", 0) + h.get("away_wins", 0):
            fail(f"{where}.h2h: counts don't add up")
    for i, r in enumerate(o.get("table_mini", [])):
        for k in ("team", "pos", "played", "w", "d", "l", "gf", "ga", "gd", "pts"):
            need(r, k, int, f"{where}.table_mini[{i}]")


def schema():
    idx = json.loads((API / "index.json").read_text(encoding="utf-8"))
    teams = json.loads((API / "teams.json").read_text(encoding="utf-8"))
    no_empty(idx, "index")
    no_empty(teams, "teams")
    need(idx, "v", int, "index")
    if idx.get("v") != 1:
        fail("index.v != 1")
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", idx.get("built", "")):
        fail(f"index.built: {idx.get('built')}")
    for i, lg in enumerate(idx.get("leagues", [])):
        need(lg, "code", str, f"index.leagues[{i}]")
        need(lg, "name", dict, f"index.leagues[{i}]")
        need(lg, "season", int, f"index.leagues[{i}]")
    for tid, t in teams.items():
        if not tid.isdigit():
            fail(f"teams: key {tid}")
        need(t, "name", dict, f"teams.{tid}")
        if "color" in t and not re.match(r"^#[0-9a-fA-F]{6}$", t["color"]):
            fail(f"teams.{tid}.color: {t['color']}")
    day_files = sorted((API / "days").glob("*.json"))
    if [d["date"] for d in idx["days"]] != [f.stem for f in day_files]:
        fail("index.days != days/*.json")
    listed = set()
    nfiles = 2
    for d in idx["days"]:
        f = API / "days" / f"{d['date']}.json"
        if not f.exists():
            continue
        b = f.read_bytes()
        nfiles += 1
        if hashlib.sha1(b).hexdigest()[:10] != d["hash"]:
            fail(f"days/{d['date']}: hash mismatch")
        lst = json.loads(b)
        if len(lst) != d["n"]:
            fail(f"days/{d['date']}: n {d['n']} != {len(lst)}")
        no_empty(lst, f"days/{d['date']}")
        for i, m in enumerate(lst):
            check_core(m, f"days/{d['date']}[{i}]", teams)
            if str(m.get("kickoff", m.get("date", "")))[:10] != d["date"]:
                fail(f"days/{d['date']}[{i}]: kickoff on another day")
            listed.add(m["id"])
    # leagues/<CODE>.json (المرحلة 2)
    lfiles = sorted((API / "leagues").glob("*.json"))
    if sorted(lg.get("file", "") for lg in idx["leagues"]) != sorted(f"leagues/{f.name}" for f in lfiles):
        fail("index.leagues[].file != leagues/*.json")
    for f in lfiles:
        o = json.loads(f.read_text(encoding="utf-8"))
        nfiles += 1
        w = f"leagues/{f.name}"
        no_empty(o, w)
        need(o, "code", str, w)
        need(o, "season", int, w)
        need(o, "name", dict, w)
        if o.get("scorers_from") not in ("player_stats", "goals"):
            fail(f"{w}.scorers_from: {o.get('scorers_from')}")
        for i, r in enumerate(o.get("table", [])):
            ww = f"{w}.table[{i}]"
            for k in ("rank", "team", "played", "w", "d", "l", "gf", "ga", "gd", "pts"):
                need(r, k, int, ww)
            if r.get("rank") != i + 1:
                fail(f"{ww}: rank {r.get('rank')}")
            if r.get("played") != r.get("w", 0) + r.get("d", 0) + r.get("l", 0) or r.get("pts") != 3 * r.get("w", 0) + r.get("d", 0) \
                    or r.get("gd") != r.get("gf", 0) - r.get("ga", 0):
                fail(f"{ww}: numbers don't add up {r}")
            if "form" in r and not (isinstance(r["form"], list) and len(r["form"]) <= 5 and set(r["form"]) <= {"w", "d", "l"}):
                fail(f"{ww}.form: {r['form']}")
            if "zone" in r and not (isinstance(r["zone"].get("code"), str) and "label" in r["zone"]):
                fail(f"{ww}.zone: {r['zone']}")
            if str(r.get("team")) not in teams:
                fail(f"{ww}: team {r.get('team')} not in teams.json")
        prev = None
        for i, s in enumerate(o.get("scorers", [])):
            ww = f"{w}.scorers[{i}]"
            for k in ("rank", "team", "goals"):
                need(s, k, int, ww)
            if need(s, "player", dict, ww):
                check_person(s["player"], f"{ww}.player")
            if prev is not None and s.get("goals", 0) > prev:
                fail(f"{ww}: not sorted by goals")
            prev = s.get("goals", 0)
            if str(s.get("team")) not in teams:
                fail(f"{ww}: team {s.get('team')} not in teams.json")
        seen = set()
        for i, rd in enumerate(o.get("rounds", [])):
            if not need(rd, "matches", list, f"{w}.rounds[{i}]"):
                continue
            for mid in rd["matches"]:
                if mid in seen:
                    fail(f"{w}.rounds: match {mid} twice")
                seen.add(mid)
                if not (API / "matches" / f"{mid}.json").exists():
                    fail(f"{w}.rounds: match {mid} has no file")
    mfiles = {int(f.stem): f for f in (API / "matches").glob("*.json")}
    if set(mfiles) != listed:
        fail(f"matches/*.json ({len(mfiles)}) != matches listed in days ({len(listed)})")
    for mid, f in mfiles.items():
        o = json.loads(f.read_text(encoding="utf-8"))
        nfiles += 1
        no_empty(o, f"matches/{mid}")
        check_match_file(o, f"matches/{mid}", teams)
    return idx, teams, mfiles, nfiles


# ── b/c. التطابق مع الصفحات ──
EV_RE = re.compile(r'<div class="ev (h|a)( minor)?">(.*?)<span class="min">([^<]*)</span>(.*?)</div>(?=<div class="ev |</div>)', re.S)
WHO_RE = re.compile(r'<span class="who[^"]*">(.*?)</span>(?:<span class="kind">(.*?)</span>)?</span>', re.S)
SPAN_TXT = re.compile(r"<[^>]+>")


def txt(s):
    return html.unescape(SPAN_TXT.sub("", s)).strip()


def page(mid, lang):
    p = R / ("matches" if lang == "ar" else "en/matches") / f"{mid}.html"
    if not p.exists():
        return None
    b = p.read_text(encoding="utf-8")
    return b[b.find("<body"):]


def page_facts(b):
    f = {}
    hb =b[b.find('<div class="head">'):]
    teams = re.findall(r'<a class="team" href="\.\./clubs/(\d+)\.html"><img[^>]*><span>(.*?)(?:<span class="rcm|</span>)', hb[:4000], re.S)
    f["teams"] = [(int(t), txt(n)) for t, n in teams[:2]]
    big = re.search(r'<div class="big[^"]*" data-mid="\d+">(.*?)</div>', hb, re.S)
    bg = big.group(1) if big else ""
    sc = re.search(r'<span class="score">(\d+) - (\d+)</span>', bg)
    f["score"] = (int(sc.group(1)), int(sc.group(2))) if sc else None
    ftb = re.search(r'<span class="ftb">([^<]+)</span>', bg)
    f["ftb"] = ftb.group(1) if ftb else None
    pko = re.search(r'class="pko" data-utc="([^"]+)"', bg)
    f["pko"] = pko.group(1) if pko else None
    pstl = re.search(r'<span class="pstl">([^<]+)</span>', bg)
    f["pstl"] = html.unescape(pstl.group(1)) if pstl else None
    utc = re.search(r'<span class="score" data-utc="([^"]+)"', bg)
    f["up_utc"] = utc.group(1) if utc else None
    ko = re.search(r'data-ko="([^"]+)"', b)
    f["ko"] = ko.group(1) if ko else None
    evbox = b[b.find('id="evbox"'):] if 'id="evbox"' in b else ""
    rows = []
    for side, _minor, left, mn, right in EV_RE.findall(evbox):
        cell = left if side == "h" else right
        ic = re.search(r'<span class="ic">(.*?)</span>', cell, re.S)
        w = WHO_RE.search(cell)
        rows.append({"side": side, "min": mn.rstrip("'"), "icon": ic.group(1) if ic else "",
                     "who": txt(w.group(1)) if w else "", "kind": txt(w.group(2) or "") if w else "",
                     "names": [txt(x) for x in re.findall(r'<span class="sr (?:in|out)"><i class="sa"></i><span>(.*?)</span>', cell)]})
    f["events"] = rows
    return f


def disp(p, lang):
    """الاسم المعروض لشخص من الـJSON (المختصر إن وُجد)"""
    if not p:
        return "—"
    return (p.get("short") or p["name"])[lang]


def parity_one(mid, o, teams):
    for lang in ("ar", "en"):
        b = page(mid, lang)
        if b is None:
            fail(f"parity {mid} {lang}: no page")
            continue
        f = page_facts(b)
        w = f"parity {mid} {lang}"
        # الفريقان
        exp_t = [(o["home"], disp(teams[str(o["home"])], lang)), (o["away"], disp(teams[str(o["away"])], lang))]
        if f["teams"] != exp_t:
            fail(f"{w}: teams page {f['teams']} json {exp_t}")
        # النتيجة/الحالة
        sc = o.get("score")
        if (f["score"] != ((sc["h"], sc["a"]) if sc else None)):
            fail(f"{w}: score page {f['score']} json {sc}")
        exp_ftb = o["status"] if (sc and o["status"] in ("FT", "AET", "PEN")) else None
        if f["ftb"] != exp_ftb:
            fail(f"{w}: FT label page {f['ftb']} json {exp_ftb}")
        # الموعد
        ko = o.get("kickoff")
        if "postponed" in o:
            # المؤجّلة: الصفحة تُفرغ الساعة (off) فتضع data-ko = «التاريخ T23:59» بديلاً (make_matches: clock or '23:59')؛
            # الموعد الفعلي = الوقت المشطوب .pko (PST)
            page_ko = f["pko"]
            if f["ko"] and ko and f["ko"] != ko[:10] + "T23:59:00Z":
                fail(f"{w}: postponed data-ko placeholder page {f['ko']} json date {ko[:10]}")
        else:
            page_ko = f["ko"] or f["up_utc"]
        if page_ko != ko and not ("postponed" in o and o["status"] != "PST"):
            fail(f"{w}: kickoff page {page_ko} json {ko}")
        if "postponed" in o:
            if o["status"] == "PST" and f["pko"] != ko:
                fail(f"{w}: postponed strike page {f['pko']} json {ko}")
            lbl = o["postponed"]["label"][lang]
            if f["pstl"] is not None and f["pstl"] != lbl:
                fail(f"{w}: postponed label page {f['pstl']} json {lbl}")
        elif f["pstl"] or f["pko"]:
            fail(f"{w}: page shows postponed, json has none")
        # الأحداث
        side = {o["home"]: "h", o["away"]: "a"}
        evs = o.get("events", [])

        def mstr(e):
            return str(e["minute"]) if "minute" in e else "؟"
        exp_goals = sorted((side[e["team"]], mstr(e), disp(e.get("player"), lang))
                           for e in evs if e["type"] == "goal")
        got_goals = sorted((r["side"], r["min"], r["who"]) for r in f["events"] if r["icon"] == "⚽")
        if exp_goals != got_goals:
            fail(f"{w}: goals page {got_goals} json {exp_goals}")
        exp_red = sorted((side[e["team"]], mstr(e), disp(e.get("player"), lang)) for e in evs
                         if e["type"] == "card" and e.get("detail") in ("Red Card", "Second Yellow card"))
        got_red = sorted((r["side"], r["min"], r["who"]) for r in f["events"] if r["icon"] in ("🟥", "🟨🟥"))
        if exp_red != got_red:
            fail(f"{w}: red cards page {got_red} json {exp_red}")
        if len(f["events"]) != len(evs):
            fail(f"{w}: event rows page {len(f['events'])} json {len(evs)}")
        # c. كل اسم عربي بالصفحة العربية موجود عربياً بالـJSON
        if lang == "ar":
            json_ar = set()
            for e in evs:
                for k in ("player", "assist"):
                    if k in e:
                        json_ar.add(disp(e[k], "ar"))
                if "label" in e:   # أسطر VAR (📺/🚫 «هدف ملغى…») تعرض التسمية لا الاسم
                    json_ar.add(e["label"]["ar"])
            for r in f["events"]:
                for nm in ([r["who"]] if not r["names"] else r["names"]):
                    if nm and AR_RE.search(nm) and r["icon"] != "📺" and nm not in json_ar:
                        fail(f"{w}: Arabic name on page missing in json ar: {nm}")


TR_RE = re.compile(r'<tr class="[^"]*" data-t="(\d+)"><td class="pos">(\d+)</td><td class="team">.*?</td>'
                   r'<td>(\d+)</td><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td><td>([+-]?\d+)</td><td class="pts">(\d+)</td></tr>', re.S)
LI_RE = re.compile(r'<li class="[^"]*"><span class="num">(\d+)</span><span class="pname">(.*?)</span>'
                   r'<span class="pteam">.*?</span><span class="pgoals">(\d+)</span></li>', re.S)
PSR_RE = re.compile(r'<div class="psr[^"]*"><span class="rk">(\d+)</span>.*?<span class="pn">(.*?)<small>.*?</small></span>'
                    r'<span class="pv">(\d+)</span></div>', re.S)


def league_parity(lfile):
    """صفحة الدوري الحالية (عربي + إنجليزي): كل صف بالجدول (المركز، الفريق، لعب، النقاط، الفارق) + أول 10 هدّافين
    (الاسم المعروض + الأهداف؛ ومركز التعادل لقائمة البطاقات). بطاقات player_stats: القائمة الكاملة <code>-goals.html."""
    o = json.loads(lfile.read_text(encoding="utf-8"))
    code = o["code"].lower()
    for lang in ("ar", "en"):
        d = R / ("leagues" if lang == "ar" else "en/leagues")
        w = f"league {o['code']} {lang}"
        p = d / f"{code}.html"
        if not p.exists():
            fail(f"{w}: no page")
            continue
        b = p.read_text(encoding="utf-8")
        got = [(int(t), int(rk), int(pl), int(pts), int(gd)) for t, rk, pl, _w, _d, _l, gd, pts in TR_RE.findall(b)]
        exp = [(r["team"], r["rank"], r["played"], r["pts"], r["gd"]) for r in o.get("table", [])]
        if got != exp:
            diff = [(g, e) for g, e in zip(got, exp) if g != e][:5]
            fail(f"{w}: table rows page {len(got)} json {len(exp)}; first diffs {diff}")
        exp_s = [(s["rank"], disp(s["player"], lang), s["goals"]) for s in o.get("scorers", [])][:10]
        if o.get("scorers_from") == "player_stats":
            lp = d / f"{code}-goals.html"
            if not lp.exists():
                fail(f"{w}: no {lp.name}")
                continue
            got_s = [(int(rk), txt(nm), int(v)) for rk, nm, v in PSR_RE.findall(lp.read_text(encoding="utf-8"))][:10]
        else:
            got_s = [(int(rk), txt(nm), int(v)) for rk, nm, v in LI_RE.findall(b)][:10]
        if got_s != exp_s:
            fail(f"{w}: top-10 scorers page {got_s} json {exp_s}")


def snapshot_check(lfile):
    """الجدول = لقطة assets/table_<CODE>_<season>.json (make_live_tables.py) بنفس الفرق والترتيب والنقاط (JOR بلا لقطة)."""
    o = json.loads(lfile.read_text(encoding="utf-8"))
    p = R / "assets" / f"table_{o['code']}_{o['season']}.json"
    if not p.exists():
        return "no snapshot"
    snap = json.loads(p.read_text(encoding="utf-8"))
    got = [(r["team_id"], r["played"], r["points"], r["diff"]) for r in snap["rows"]]
    exp = [(r["team"], r["played"], r["pts"], r["gd"]) for r in o.get("table", [])]
    if got != exp:
        fail(f"snapshot {o['code']}: {p.name} differs: first {[(g, e) for g, e in zip(got, exp) if g != e][:3]} "
             f"(rows {len(got)} vs {len(exp)})")
    return "ok"


def pick(conn, mfiles, n):
    """عيّنة ثابتة (seed 7): حصص لكل فئة ثم تعبئة متوازنة بالدوريات"""
    ids = set(mfiles)
    q = lambda s: [r[0] for r in conn.execute(s) if r[0] in ids]
    cats = {
        "penalty_goal": q("SELECT DISTINCT match_id FROM goals WHERE detail='Penalty'"),
        "own_goal": q("SELECT DISTINCT match_id FROM goals WHERE detail='Own Goal'"),
        "red_card": q("SELECT DISTINCT match_id FROM events WHERE type='Card' AND detail IN ('Red Card','Second Yellow card')"),
        "shootout": q("SELECT match_id FROM matches WHERE status IN ('PEN','AET')"),
        "postponed": q("SELECT match_id FROM matches WHERE status IN ('PST','SUSP','INT','CANC','ABD')"),
        "upcoming": q("SELECT match_id FROM matches WHERE home_goals IS NULL AND status NOT IN ('PST','SUSP','INT','CANC','ABD')"),
        "finished": q("SELECT match_id FROM matches WHERE status='FT'"),
    }
    rnd = random.Random(7)
    chosen = []
    for k, lst in cats.items():
        lst = sorted(lst)
        rnd.shuffle(lst)
        chosen += [x for x in lst[:25] if x not in chosen]
    lg = {}
    for mid, code in conn.execute("SELECT match_id, league_code FROM matches"):
        if mid in ids:
            lg.setdefault(code, []).append(mid)
    for code in lg:
        lg[code].sort()
        rnd.shuffle(lg[code])
    i = 0
    while len(chosen) < n and any(lg.values()):
        code = sorted(lg)[i % len(lg)]
        if lg[code]:
            x = lg[code].pop()
            if x not in chosen:
                chosen.append(x)
        i += 1
    chosen = chosen[:n]
    have = {k: sum(1 for x in chosen if x in set(v)) for k, v in cats.items()}
    leagues = sorted({c for c, l in conn.execute("SELECT league_code, match_id FROM matches") if l in set(chosen)})
    return chosen, have, leagues


def main():
    idx, teams, mfiles, nfiles = schema()
    nschema = len(FAILS)
    print(f"a. schema: {nfiles} files, {nschema} problems")
    conn = sqlite3.connect(f"file:{(R / 'football.db').as_posix()}?mode=ro", uri=True)
    chosen, have, leagues = pick(conn, mfiles, N_PARITY)
    print(f"b. parity sample: {len(chosen)} matches, leagues {leagues}, categories {have}")
    for mid in chosen:
        o = json.loads(mfiles[mid].read_text(encoding="utf-8"))
        parity_one(mid, o, teams)
    print(f"b+c. parity problems: {len(FAILS) - nschema}")
    n0 = len(FAILS)
    snaps = {}
    for lf in sorted((API / "leagues").glob("*.json")):
        league_parity(lf)
        snaps[lf.stem] = snapshot_check(lf)
    print(f"d. league parity (table + top-10 scorers, ar+en) + snapshots {snaps}: {len(FAILS) - n0} problems")
    for x in FAILS[:60]:
        print("  FAIL", x)
    if len(FAILS) > 60:
        print(f"  … +{len(FAILS) - 60}")
    print(f"\nTOTAL FAILS: {len(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
