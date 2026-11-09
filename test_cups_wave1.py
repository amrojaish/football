#!/usr/bin/env python3
"""
Cups wave 1 (4 Nov 2026) — import from cached provider responses, knockout bracket, cup page (Matches / Bracket / Scorers, no
table), match page (round label, pens/ET, no shootout kicks in the goal list), club «Competitions» card + this-season window,
api/v1 cups, home day sections. No network.
Provider data: test_data/cups_wave1.json (real responses, 3 Nov 2026: EGY-SC 539, QAT-QC 825, UAE-SC 896, TUN-SC 1194).
Everything is rendered from a TEMP COPY of football.db (md5 checked at the end); nothing is written to the repo.
Optional section 8 checks a built api/v1 (make_api.py run from a DB with cups) with test_make_api's schema check.
    python C:\\Users\\User\\Projects\\Football\\test_cups_wave1.py
"""
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from _test_tmp import make_tmp
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
argv0 = sys.argv[:]
sys.argv = sys.argv[:1]   # make_matches reads sys.argv[1] as ONLY at import
import competitions as CP  # noqa: E402
import cup_bracket as B  # noqa: E402
import import_cups as IC  # noqa: E402
import match_score as MS  # noqa: E402
from config import COMPETITIONS, DB_FILE, LEAGUES  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()  # noqa: E731
DB_MD5 = md5(DB_FILE)
DATA = json.loads((ROOT / "test_data" / "cups_wave1.json").read_text(encoding="utf-8"))
CODES = ("EGY-SC", "QAT-QC", "UAE-SC", "TUN-SC")
TMPD = make_tmp("cups_w1_")
CACHE = TMPD / "cache"
CACHE.mkdir()
for k, v in list(DATA["lists"].items()) + list(DATA["ids"].items()):
    (CACHE / f"{k}.json").write_text(json.dumps({"response": v}, ensure_ascii=False), encoding="utf-8")
TMP = TMPD / "football.db"
shutil.copy(DB_FILE, TMP)
con = sqlite3.connect(TMP)
con.row_factory = sqlite3.Row
if not MS.has_score(con):
    MS.migrate(con)
cup_ph = ", ".join("?" * len(CODES))
for t in ("goals", "events", "lineups", "lineup_players", "match_stats", "player_stats"):
    con.execute(f"DELETE FROM {t} WHERE match_id IN (SELECT match_id FROM matches WHERE league_code IN ({cup_ph}))", CODES)
con.execute(f"DELETE FROM matches WHERE league_code IN ({cup_ph})", CODES)
con.commit()

# ── 1) import (no API) ─────────────────────────────────────────────────────────────────────────────────────
lists, full = IC.load_cache(CACHE)
from datetime import datetime, timezone  # noqa: E402
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)
need = {c: IC.missing(lists[COMPETITIONS[c]["id"]], full, NOW) for c in CODES}
check("1 nothing missing in the cache (0 API calls)", not any(need.values()), need)
fake = [{"fixture": {"id": 1, "date": "2026-11-01T18:00:00+00:00", "status": {"short": "NS"}}},
        {"fixture": {"id": 2, "date": "2026-12-01T18:00:00+00:00", "status": {"short": "NS"}}}]
check("1 missing(): a past fixture still NS, or one with no ids= details, is listed",
      IC.missing(fake, {2: fake[1]}, NOW) == [1] and IC.missing(fake, {}, NOW) == [1, 2], IC.missing(fake, {}, NOW))
reps = {c: IC.import_code(con, c, lists[COMPETITIONS[c]["id"]], full) for c in CODES}
con.commit()
want = {"EGY-SC": 4, "QAT-QC": 3, "UAE-SC": 1, "TUN-SC": 2}
got = {c: con.execute("SELECT COUNT(*) FROM matches WHERE league_code = ? AND season = ?", (c, COMPETITIONS[c]["season"])).fetchone()[0]
       for c in CODES}
check("1 every fixture stored at the registry (provider) season", got == want, got)
bad = con.execute(f"""SELECT m.match_id, m.home_goals + m.away_goals, (SELECT COUNT(*) FROM goals g WHERE g.match_id = m.match_id)
                      FROM matches m WHERE m.league_code IN ({cup_ph}) AND m.status IN ('FT','AET','PEN')""", CODES).fetchall()
check("1 finished matches: goal rows == score (shootout kicks never become goals)", all(r[1] == r[2] for r in bad), [tuple(r) for r in bad])
r = con.execute("SELECT * FROM matches WHERE match_id = 1635605").fetchone()
check("1 QAT-QC 1635605 PEN: 3-3, pens 4-5, round Semi-finals, 6 goal rows, 12 shootout kicks dropped",
      (r["status"], r["home_goals"], r["away_goals"], r["pen_home"], r["pen_away"], r["round"]) == ("PEN", 3, 3, 4, 5, "Semi-finals")
      and con.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1635605").fetchone()[0] == 6
      and reps["QAT-QC"]["shootout_dropped"] == 12, (dict(r), reps["QAT-QC"]))
r = con.execute("SELECT * FROM matches WHERE league_code = 'UAE-SC'").fetchone()
check("1 UAE-SC: one NS row, no score, raw round kept", (r["status"], r["home_goals"], r["round"]) == ("NS", None, "Group Stage"), dict(r))
check("1 TUN-SC: CANC + NS stored", sorted(x[0] for x in con.execute("SELECT status FROM matches WHERE league_code='TUN-SC'")) == ["CANC", "NS"])
before = [con.execute(f"SELECT COUNT(*) FROM {t} WHERE match_id IN (SELECT match_id FROM matches WHERE league_code IN ({cup_ph}))",
                      CODES).fetchone()[0] for t in ("goals", "events", "lineups", "lineup_players")]
for c in CODES:
    IC.import_code(con, c, lists[COMPETITIONS[c]["id"]], full)
con.commit()
after = [con.execute(f"SELECT COUNT(*) FROM {t} WHERE match_id IN (SELECT match_id FROM matches WHERE league_code IN ({cup_ph}))",
                     CODES).fetchone()[0] for t in ("goals", "events", "lineups", "lineup_players")]
check(f"1 idempotent: a second import leaves goals/events/lineups/lineup_players at {before}", before == after and before[1] > 0, after)

# ── 2) bracket (synthetic + real) ──────────────────────────────────────────────────────────────────────────


def m(mid, rnd, d, h, a, hg=None, ag=None, st="FT", ph=None, pa=None):
    return {"match_id": mid, "round": rnd, "date": d, "home_id": h, "away_id": a, "home_goals": hg, "away_goals": ag,
            "status": st if hg is not None or st != "FT" else "NS", "pen_home": ph, "pen_away": pa}


syn = [m(1, "Quarter-finals", "2026-01-01 18:00", 1, 2, 1, 0), m(2, "Quarter-finals", "2026-01-08 18:00", 2, 1, 2, 1, "PEN", 3, 4),
       m(3, "Quarter-finals", "2026-01-02 18:00", 3, 4, 0, 2), m(4, "Quarter-finals", "2026-01-03 18:00", 5, 6, 1, 1, "PEN", 5, 4),
       m(5, "Quarter-finals", "2026-01-04 18:00", 7, 8), m(6, "Quarter-finals", "2026-01-05 18:00", 7, 8, st="CANC"),
       m(7, "Quarter-finals", "2026-01-06 18:00", 9, 10, 2, 0), m(8, "Semi-finals", "2026-02-01 18:00", 4, 1)]
bk = B.build(syn, "cup")
qf = bk["rounds"][0]["ties"]
two = next(t for t in qf if {t["a"], t["b"]} == {1, 2})
check("2 two legs = one tie: aggregate 2-2 (team 1 first), pens 4-3 from the 2nd leg, winner 1", (len(two["legs"]), two["agg"], two["pens"],
      two["winner"]) == (2, (2, 2), (4, 3), 1), two)
t56 = next(t for t in qf if {t["a"], t["b"]} == {5, 6})
check("2 single match PEN 1-1 (5-4): winner by pens", t56["winner"] == 5, t56)
t78 = next(t for t in qf if {t["a"], t["b"]} == {7, 8})
check("2 CANC leg ignored (one NS leg), undecided", len(t78["legs"]) == 1 and t78["winner"] is None, t78)
check("2 tree order: ties feeding the known semi (4 v 1) first", {qf[0]["a"], qf[0]["b"]} | {qf[1]["a"], qf[1]["b"]} == {1, 2, 3, 4},
      [(t["a"], t["b"]) for t in qf])
check("2 a known semi with one tie ends the tree (no Final placeholder until the provider lists it)",
      [r["round"] for r in bk["rounds"]] == ["Quarter-finals", "Semi-finals"] and len(bk["rounds"][1]["ties"]) == 1,
      [(r["round"], len(r["ties"])) for r in bk["rounds"]])
bk2 = B.build([m(1, "Round of 16", "2026-01-01 18:00", 1, 2, 1, 0), m(2, "Round of 16", "2026-01-02 18:00", 3, 4, 0, 1),
               m(3, "Round of 16", "2026-01-03 18:00", 5, 6), m(4, "Round of 16", "2026-01-04 18:00", 7, 8)], "cup")
check("2 placeholders: QF 2 / SF 1 … fed by known winners (1 v 4), Final absent when SF has one tie",
      [(r["round"], len(r["ties"])) for r in bk2["rounds"]] == [("Round of 16", 4), ("Quarter-finals", 2), ("Semi-finals", 1)]
      and (bk2["rounds"][1]["ties"][0]["a"], bk2["rounds"][1]["ties"][0]["b"]) == (1, 4)
      and all(t["placeholder"] for t in bk2["rounds"][1]["ties"]), [(r["round"], [(t["a"], t["b"]) for t in r["ties"]]) for r in bk2["rounds"]])
sup = B.build([m(1, "Group Stage", "2026-11-29 16:00", 1, 2)], "super")
check("2 super cup with one match: shown as «Final» (provider says «Group Stage»)", B.display_round("Group Stage", sup) == "Final")
check("2 team_stage: alive / out / champion", (B.team_stage(bk, 4)[1], B.team_stage(bk, 3)[1], B.team_stage(bk, 99)) == ("alive", "out", (None, None)))
rows_e = con.execute("SELECT * FROM matches WHERE league_code = 'EGY-SC'").fetchall()
be = B.build(rows_e, "super")
check("2 real EGY-SC: Semi-finals → Final, champion = Final winner (Al Ahly 1577), 3rd-place match outside the tree",
      [r["round"] for r in be["rounds"]] == ["Semi-finals", "Final"] and be["champion"] == 1577 and len(be["extra"]) == 1, be["champion"])
check("2 real EGY-SC: Zamalek beat Pyramids on pens (0-0, 5-4) in the semi",
      any(t["pens"] and t["winner"] in (t["a"], t["b"]) and t["agg"] == (0, 0) for t in be["rounds"][0]["ties"]))
bq = B.build(con.execute("SELECT * FROM matches WHERE league_code = 'QAT-QC'").fetchall(), "cup")
check("2 real QAT-QC: final not played → no champion; Al-Rayyan through on pens", bq["champion"] is None
      and any(t["pens"] == (4, 5) for t in bq["rounds"][0]["ties"]))

# ── 3) cup page ────────────────────────────────────────────────────────────────────────────────────────────
import make_clubs as MC  # noqa: E402
import make_cups as MK  # noqa: E402
from make_site3 import load_overrides  # noqa: E402
LOGOS, TEAMS = load_overrides(), MC.load_teams()
pages = {(c, lg): MK.cup_page(con, lg, c, LOGOS, TEAMS) for c in CODES for lg in ("ar", "en")}
for (c, lg), h in pages.items():
    cats = re.findall(r'class="tab[^"]*" data-cat="([a-z-]+)"', h)
    if cats != ["matches", "bracket", "scorers"]:
        check(f"3 {c} {lg}: tabs Matches / Bracket / Scorers", False, cats)
check("3 every cup page: tabs exactly Matches / Bracket / Scorers, no standings table",
      all(re.findall(r'class="tab[^"]*" data-cat="([a-z-]+)"', h) == ["matches", "bracket", "scorers"] and "<table" not in h
          for h in pages.values()))
h = pages[("EGY-SC", "ar")]
check("3 EGY-SC ar: champion banner (الأهلي) + 2 round columns + third-place block",
      '<div class="champ">' in h and "البطل" in h and h.count('<section class="bkcol') == 2 and "مباراة المركز الثالث" in h)
h = pages[("UAE-SC", "en")]
check("3 UAE-SC en: one final card (.tie.fin) under «Final», no round buttons",
      h.count('class="tie fin"') == 1 and "<h3>Final</h3>" in h and 'class="bkn"' not in h)
h = pages[("QAT-QC", "ar")]
check("3 QAT-QC ar: the PEN semi card shows «ترجيح 4-5» under 3 - 3", re.search(r"3 - 3[^<]*<span class=\"pso\">ترجيح 4-5</span>", h) is not None)
check("3 QAT-QC ar: bracket mobile round = the unplayed Final (data-cur=1)", 'class="bkt" data-cur="1"' in h)
nsc = con.execute("""SELECT COUNT(*) FROM (SELECT g.player_en, t.short_name_ar FROM goals g JOIN matches m ON m.match_id = g.match_id
                     JOIN teams t ON t.team_id = g.team_id WHERE m.league_code = 'QAT-QC' AND g.player_en != ''
                     GROUP BY g.player_en, t.short_name_ar)""").fetchone()[0]
check(f"3 QAT-QC scorers tab: {nsc} scorers from goals (shootout kicks excluded)", h.count('<span class="pgoals">') == nsc,
      h.count('<span class="pgoals">'))
check("3 links: matches/clubs relative to leagues/ (../matches/)", 'href="../matches/1635605.html"' in pages[("QAT-QC", "ar")])

# ── 4) match page ─────────────────────────────────────────────────────────────────────────────────────────
import make_matches as mm  # noqa: E402
sys.argv = argv0
mm.LATEST_SEASON = con.execute("SELECT MAX(season) FROM matches WHERE " + CP.league_codes_sql()[0], CP.league_codes_sql()[1]).fetchone()[0]
mm.build_form_index(con)
mt = mm.load_teams()
row = con.execute("SELECT * FROM matches WHERE match_id = 1635605").fetchone()
for lg, chip, pens in (("ar", "كأس قطر - نصف النهائي", "ركلات الترجيح 4 - 5"), ("en", "Qatar Cup - Semi-finals", "Pens 4 - 5")):
    hh, aa = mt[row["home_id"]], mt[row["away_id"]]
    page = mm.build_page(row, hh, aa, mm.build_items(con, 1635605, lg), None, lg, "", "", "",
                         mm.build_table_panel(con, row, mt, lg), mm.build_form_card(row, hh, aa, mt, lg))
    ngoal = len(re.findall(r'<div class="ev [ha]">', page))
    check(f"4 {lg}: chip «{chip}», «{pens}» under FT, 6 goal rows (no shootout kicks), no table / form",
          f'<span class="chip">{chip}</span>' in page and f'data-x="sc">{pens}</span>' in page and ngoal == 6
          and '<table class="lgt"' not in page and 'class="fcard' not in page, (ngoal, re.findall(r'<span class="chip">(.*?)</span>', page)[:1]))

# ── 5) club page: this-season window + «Competitions» card ───────────────────────────────────────────────
ahly = MC.club_season_matches(con, 1577, 2026, "EGY")
check("5 Al Ahly 2026/27: last season's EGY Super Cup (Nov 2025) is NOT in this season's matches",
      not any(x["league_code"] == "EGY-SC" for x in ahly) and any(x["league_code"] == "EGY" for x in ahly))
_card = MC.competitions_card(con, 1577, "EGY", 2026, ahly, "ar")
check("5 Al Ahly: «Competitions» card never shows last season's EGY Super Cup (empty before wave 2a; Egypt Cup only after it)",
      _card == "" or ("egy-c.html" in _card and "egy-sc.html" not in _card), re.findall(r'href="([^"]+)"', _card))
sadd = MC.club_season_matches(con, 2895, 2026, "QAT")
check("5 Al Sadd 2026/27: Qatar Cup (provider season 2025, played Sep–Dec 2026) IS in this season's matches",
      any(x["league_code"] == "QAT-QC" for x in sadd))
card = MC.competitions_card(con, 2895, "QAT", 2026, sadd, "ar")
rows_ = re.findall(r'<span class="cmn">(.*?)<small><bdi dir="ltr">(.*?)</bdi></small></span><span class="cms">(.*?)</span>', card)
by_name = {x[0]: x[2] for x in rows_}
check("5 Al Sadd card: contains QAT league (rank) AND Qatar Cup «النهائي» (alive), links to the competition pages (extra comps allowed)",
      by_name.get("دوري نجوم قطر", "").startswith("المركز") and by_name.get("كأس قطر") == "النهائي"
      and 'href="../leagues/qat-qc.html"' in card, rows_)
old = MC.club_season_matches(con, 2895, 2026)
check("5 no code = old behaviour (season = 2026 only: Qatar Cup provider season 2025 not included)",
      old and all(x["league_code"] != "QAT-QC" for x in old))

# ── 6) api/v1 pieces ──────────────────────────────────────────────────────────────────────────────────────
import make_api as MA  # noqa: E402
stub = {"pages": [], "nt_slug": {}, "name_slug": {}}
cj = MA.cup_json(con, "EGY-SC", COMPETITIONS["EGY-SC"]["season"], stub)
check("6 cups/EGY-SC.json: type, label, rounds (SF 2 + Final 1), third_place, champion 1577, no table",
      (cj["type"], cj["label"], [len(r["ties"]) for r in cj["rounds"]], len(cj["third_place"]), cj["champion"]) == ("super", "2025", [2, 1], 1, 1577)
      and "table" not in cj and all(set(r["round"]) == {"ar", "en"} for r in cj["rounds"]), {k: cj[k] for k in cj if k != "scorers"})
cq = MA.cup_json(con, "QAT-QC", COMPETITIONS["QAT-QC"]["season"], stub)
check("6 cups/QAT-QC.json: semi tie carries pen {h,a}, final has no winner", any(t.get("pen") == {"h": 4, "a": 5} for t in cq["rounds"][0]["ties"])
      and "winner" not in cq["rounds"][1]["ties"][0] and "champion" not in cq)
mrow = con.execute("SELECT * FROM matches WHERE match_id = 1635605").fetchone()
core = MA.match_core(mrow, {})
check("6 match object: pen {h:4, a:5}; league = cup code; round {ar,en}", core.get("pen") == {"h": 4, "a": 5} and core["league"] == "QAT-QC"
      and core["round"] == {"ar": "نصف النهائي", "en": "Semi-finals"}, core)
lrow = con.execute("SELECT * FROM matches WHERE league_code = 'SAU' AND home_goals IS NOT NULL LIMIT 1").fetchone()
check("6 league match object: no pen key", "pen" not in MA.match_core(lrow, {}))

# ── 7) home day sections + league output unchanged ────────────────────────────────────────────────────────
import make_site3 as M3  # noqa: E402
lg_rows = M3.get_matches(con, "SAU", 2026, limit=3)
check("7 league match card: no «pso» span (league rows carry no pen_home)", all("pso" not in M3.match_card(x, "ar", LOGOS) for x in lg_rows))
dv = M3.day_view(con, "ar", LOGOS, list(LEAGUES) + ["UAE-SC", "QAT-QC"], M3.T["ar"])
check("7 home: UAE-SC section (29 Nov) links to leagues/uae-sc.html", 'data-sec="UAE-SC"' in dv and 'href="leagues/uae-sc.html"' in dv)
check("7 get_table for a cup = []", M3.get_table(con, "QAT-QC", 2025) == [])

# ── 8) built api/v1 (optional: make_api.py run on a DB with cups) ─────────────────────────────────────────
API = ROOT / "api" / "v1"
idx = json.loads((API / "index.json").read_text(encoding="utf-8")) if (API / "index.json").exists() else {}
if idx.get("cups"):
    sys.argv = [sys.argv[0], str(API)]
    import test_make_api as TMA  # noqa: E402
    TMA.FAILS.clear()
    TMA.schema()
    check(f"8 built api/v1: test_make_api schema check ({len(idx['cups'])} cups in index)", not TMA.FAILS, TMA.FAILS[:5])
    for e in idx["cups"]:
        f = API / e["file"]
        o = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        ok = o.get("code") == e["code"] and "table" not in o and all("ties" in r for r in o.get("rounds", []))
        if not ok:
            check(f"8 {e['file']}", False, list(o))
    check("8 every index.cups[].file exists with code + rounds[].ties and no table", True)
else:
    print("SKIP 8 (no api/v1 with cups here)")

# ── 9) fetch_cups (CI step): gate, daily discovery, never rewrite a complete finished match, ids= only when needed ─────
import fetch_cups as FC  # noqa: E402
from datetime import timedelta  # noqa: E402
T0 = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)   # UAE-SC 29 Nov inside the window; QAT-QC final 11 Dec outside
g = dict(FC.gated(con, T0, CODES))
check("9 gate: only cups with a match yesterday..today+7 (UAE-SC 29 Nov), none else at 12:00 UTC", g == {"UAE-SC": "window"}, g)
g0 = dict(FC.gated(con, T0.replace(hour=0, minute=5), CODES))
check("9 gate: the 00:05 UTC run adds every enabled cup once (daily discovery)",
      g0.get("UAE-SC") == "window" and all(g0.get(c) == "daily" for c in ("EGY-SC", "QAT-QC", "TUN-SC")), g0)
uae_list = DATA["lists"]["list_896_2026"]
done = [dict(x, fixture=dict(x["fixture"], status={"short": "FT", "long": "Match Finished", "elapsed": 90}),
             goals={"home": 1, "away": 0}, score=dict(x["score"], fulltime={"home": 1, "away": 0})) for x in uae_list]
calls = []


def fake(endpoint, params, rem=5000):
    calls.append(dict(params))
    if "league" in params:
        return True, done, rem, ""
    fx = dict(done[0], events=[{"type": "Goal", "detail": "Normal Goal", "comments": None, "time": {"elapsed": 10, "extra": None},
                                "team": {"id": done[0]["teams"]["home"]["id"]}, "player": {"id": 1, "name": "X. Scorer"},
                                "assist": {"id": None, "name": None}}], lineups=[], statistics=[], players=[])
    return True, [fx], rem, ""


mid = uae_list[0]["fixture"]["id"]
check("9 needs_details: provider FT vs our NS row = yes", FC.needs_details(con, done[0]))
rep = FC.run(con, T0, 6, fetch=fake, codes=CODES)
r = con.execute("SELECT status, home_goals, away_goals, (SELECT COUNT(*) FROM goals WHERE match_id = ?) FROM matches WHERE match_id = ?",
                (mid, mid)).fetchone()
check("9 run: list + one ids= call, the finished match written with its goal", rep["calls"] == 2 and tuple(r) == ("FT", 1, 0, 1)
      and "ids" in calls[1], (rep, tuple(r), calls))
calls.clear()
rep = FC.run(con, T0, 6, fetch=fake, codes=CODES)
r2 = con.execute("SELECT COUNT(*) FROM goals WHERE match_id = ?", (mid,)).fetchone()[0]
check("9 second run: complete finished match NOT rewritten (list only, no ids=, goal kept)", rep["calls"] == 1 and r2 == 1, (rep, r2))
calls.clear()
rep = FC.run(con, T0.replace(hour=0, minute=5), 6, fetch=lambda e, p: fake(e, p, rem=1500), codes=CODES)
check("9 quota: remaining < 2,000 after the first call = stop (no further calls)", rep["calls"] == 1 and rep["stopped"], rep)
rep = FC.run(con, T0.replace(hour=0, minute=5), 2, fetch=fake, codes=CODES)
check("9 budget 2: at most 2 calls in a discovery run", rep["calls"] <= 2, rep)
# (5 Nov 2026, wave 2a) provider sent no events for an old finished match (3 MAR-C games): goal rows < score must not be re-requested forever
con.execute("DELETE FROM goals WHERE match_id = ?", (mid,))
_ts = datetime.fromtimestamp(done[0]["fixture"]["timestamp"], timezone.utc)
check("9 needs_details: ours finished, goal rows < score, 2 days old = yes (events may still arrive)", FC.needs_details(con, done[0], _ts + timedelta(days=2)))
check("9 needs_details: ours finished, goal rows < score, 4 days old = no (provider has no events)", not FC.needs_details(con, done[0], _ts + timedelta(days=4)))
check("9 needs_details: no `now` = old behaviour (yes)", FC.needs_details(con, done[0]))
calls.clear()
_late = (_ts + timedelta(days=5)).replace(hour=0, minute=5)
rep = FC.run(con, _late, 6, fetch=fake, codes=["UAE-SC"])
check("9 discovery run 5 days later: list only, no ids= for the old event-less match", rep["calls"] == 1 and not any("ids" in c for c in calls),
      (rep, calls))
# (5 Nov 2026, wave 2a) correction badge: score numbers in <bdi dir="ltr"> so «ترجيح 4-3» can't flip in RTL
check("9 ltr_nums: 4-3, 2-2, 120+1 wrapped; text kept", mm.ltr_nums("2-2 بعد التمديد، ترجيح 4-3 (120+1 كاظمة)")
      == '<bdi dir="ltr">2-2</bdi> بعد التمديد، ترجيح <bdi dir="ltr">4-3</bdi> (<bdi dir="ltr">120+1</bdi> كاظمة)')
check("9 ltr_nums: no numbers = unchanged, None = empty", mm.ltr_nums("حسم إداري") == "حسم إداري" and mm.ltr_nums(None) == "")
# (5 Nov 2026, wave 2a) cup-only club (King's Cup club, no league rows): no Standings / Stats tabs; a league club keeps both
_cup_only = next(t for t in (10503, 10524, 26357, 2947, 2958, 2966) if t in TEAMS)
_p1 = MC.build_page(con, _cup_only, TEAMS, "ar") or ""
_p2 = MC.build_page(con, 2932, TEAMS, "ar") or ""
check("9 cup-only club page: no tb / st tabs, overview + matches kept",
      'data-tab="tb"' not in _p1 and 'data-tab="st"' not in _p1 and 'data-tab="ov"' in _p1 and 'data-tab="mt"' in _p1, _cup_only)
check("9 league club (Al Hilal): tb + st tabs kept", 'data-tab="tb"' in _p2 and 'data-tab="st"' in _p2)
# no import yet = nothing at all (the live DB before import_cups.py): every enabled cup without rows is skipped, even at 00:05
TMP3 = TMPD / "pre_import.db"
con.commit()
shutil.copy(TMP, TMP3)
c3 = sqlite3.connect(TMP3)
c3.execute(f"DELETE FROM matches WHERE league_code IN ({', '.join(repr(c) for c in sorted(COMPETITIONS))})")
c3.commit()
calls3 = []
rep3 = FC.run(c3, T0.replace(hour=0, minute=5), 6, fetch=lambda e, p: calls3.append(p) or (True, [], 5000, ""))
check("9 before the manual import (no cup rows): gate empty, 0 API calls, 0 rows written — even the 00:05 discovery run",
      rep3["gated"] == [] and calls3 == [] and c3.execute("SELECT COUNT(*) FROM matches WHERE league_code LIKE '%-%'").fetchone()[0] == 0,
      (rep3, calls3))
c3.close()
from config import ENABLED_CUPS  # noqa: E402
check("ENABLED_CUPS includes the 9 wave-1 codes", set(ENABLED_CUPS) >= {"SAU-KC", "SAU-SC", "UAE-SC", "EGY-SC", "KUW-SC", "JOR-SC", "QAT-QC", "TUN-SC", "ALG-SC"})
# (6 Nov 2026, wave 2b) Tunisia + Algeria cups, season 2025 (the finished 2025/26 edition)
check("ENABLED_CUPS includes wave 2b TUN-C + ALG-C at season 2025", {"TUN-C", "ALG-C"} <= set(ENABLED_CUPS)
      and all(COMPETITIONS[c]["season"] == 2025 for c in ("TUN-C", "ALG-C")))

# ── 10) leagues index: cups section ───────────────────────────────────────────────────────────────────────
import make_leagues as ML  # noqa: E402
lg_logos, lg_local = M3.load_league_logos()
fp = ML.flags_page("ar", list(LEAGUES), lg_logos, lg_local, ["EGY-SC", "QAT-QC"])
fp0 = ML.flags_page("ar", list(LEAGUES), lg_logos, lg_local)
check("10 leagues.html: «الكؤوس» heading + one card per cup page, after the leagues", 'class="lgsech"' in fp and "الكؤوس</h2>" in fp and fp.count('class="lcard"') == len(LEAGUES) + 2
      and fp.index('href="leagues/egy-sc.html"') > fp.index(f'href="leagues/{list(LEAGUES)[-1].lower()}.html"'))
check("10 leagues.html without cups: no cups section", 'class="lgsech"' not in fp0 and fp0.count('class="lcard"') == len(LEAGUES))
check("10 update_all: fetch_cups.py step (gated) + make_cups.py step", all(x in (ROOT / "update_all.py").read_text(encoding="utf-8")
      for x in ('["fetch_cups.py", "--budget", "6"]', '["make_cups.py"]')))

# ── 11) cups stay out of live polling / alerts until the worker has their ids ─────────────────────────────
import make_kickoffs as MKO  # noqa: E402
ko = MKO.build(con, int(datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc).timestamp()))
uae = [x for x in con.execute("SELECT match_id FROM matches WHERE league_code = 'UAE-SC'")]
check("11 next_kickoffs.json: a finished cup match (UAE-SC, faked FT above) has no reminder and no vote row",
      not any(x[1] == uae[0][0] for x in ko["f"]) and str(uae[0][0]) not in ko["v"], [x[1] for x in ko["f"]][:5])
# (8 نوفمبر 2026، بثّ الكؤوس مرحلة 1) كأس بـLIVE_CUPS: نافذة السحب k فقط — لا f (تذكير/تشكيلات) ولا v (تصويت)؛ غيرها والدوريات كما هي
from config import LIVE_CUPS  # noqa: E402
_now = int(datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc).timestamp())
_mk = sqlite3.connect(":memory:")
_mk.execute("CREATE TABLE teams (team_id INTEGER PRIMARY KEY, name_en TEXT, name_en_official TEXT)")
_mk.executemany("INSERT INTO teams VALUES (?, ?, '')", [(1, "H"), (2, "A")])
_mk.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, date TEXT, league_code TEXT, home_id INT, away_id INT, status TEXT, home_goals INT)")
_mk.executemany("INSERT INTO matches VALUES (?, ?, ?, 1, 2, 'NS', NULL)", [
    (9001, "2026-11-28 14:00", "UAE-LC"), (9002, "2026-11-28 16:00", "UAE-SC"), (9003, "2026-11-28 18:00", "SAU")])
_ko = MKO.build(_mk, _now)
_ts = lambda h: int(datetime(2026, 11, 28, h, 0, tzinfo=timezone.utc).timestamp())
check("11 LIVE_CUPS = UAE-LC only (pilot)", tuple(LIVE_CUPS) == ("UAE-LC",), LIVE_CUPS)
check("11 live-only UAE-LC: poll window (k) yes, reminder/lineups (f) no, vote (v) yes (batch 10)",
      _ts(14) in _ko["k"] and not any(x[1] == 9001 for x in _ko["f"]) and "9001" in _ko["v"], _ko)
check("11 UAE-SC (not live): vote only (batch 10); league SAU in k, f and v as before",
      _ts(16) not in _ko["k"] and "9002" in _ko["v"] and _ts(18) in _ko["k"] and any(x[1] == 9003 for x in _ko["f"]) and "9003" in _ko["v"], _ko)
_ww = (ROOT / "worker.js").read_text(encoding="utf-8")
_ids = set(map(int, re.findall(r"\d+", re.search(r"const LIVE_ONLY_LEAGUE_IDS = new Set\(\[(.*?)\]\)", _ww).group(1))))
check("11 worker LIVE_ONLY_LEAGUE_IDS = config.LIVE_CUPS provider ids", _ids == {CP.provider_id(c) for c in LIVE_CUPS}, _ids)
_cg = MC.follow_group(5400, dict(MC.load_teams()[5400], league=""), "ar") if 5400 in MC.load_teams() else ""
_lg = MC.follow_group(1577, MC.load_teams()[1577], "ar")
check("11 club header: cup-only club has Follow but no alert bell; a league club keeps the bell",
      "pushbtn" not in _cg and "fclubbtn" in _cg and 'id="pushbtn"' in _lg and "fclubbtn" in _lg, (_cg[:120], _lg[:120]))
from live_view import live_script as _ls  # noqa: E402
_lsj = _ls(mm.T["ar"] if hasattr(mm, "T") else {}, 1)
check("11 live page: AWD and WO render as final; WO with no score shows the end label, not 0 - 0",
      "e.s==='AWD'||e.s==='WO'" in _lsj and "(e.h==null&&e.a==null)?LB.END" in _lsj)
up = con.execute("SELECT * FROM matches WHERE league_code = 'UAE-SC'").fetchone()
hu, au = mt[up["home_id"]], mt[up["away_id"]]
pg_up = mm.build_page(up, hu, au, [], None, "ar")
check("11 cup match page: follow star kept, no alert bell", 'id="mstar"' in pg_up and 'id="pushbtn"' not in pg_up and "pushbtn" not in pg_up.split("</header>")[0])
lrow2 = con.execute("SELECT * FROM matches WHERE league_code = 'SAU' AND home_goals IS NULL LIMIT 1").fetchone()
if lrow2:
    pg_l = mm.build_page(lrow2, mt[lrow2["home_id"]], mt[lrow2["away_id"]], [], None, "ar")
    check("11 league match page: bell still there", "pushbtn" in pg_l)
dv2 = M3.day_view(con, "ar", LOGOS, list(LEAGUES) + ["UAE-SC"], M3.T["ar"])
sec = dv2[dv2.index('data-sec="UAE-SC"'):]
sec = sec[:sec.index("</details>")]
check("11 home: cup card without the match bell", "cbell" not in sec and "data-bell" not in sec and "pushbtn" not in sec, sec[:300])
check("11 shared row CSS unchanged (no .pso outside cup pages)", ".pso" not in __import__("match_row").ROW_CSS and ".pso" in MK.CUP_CSS)

# ── 12) player gate: player pages / slugs / history / player data ignore cup matches ──────────────────────
import player_pages as PPG  # noqa: E402
import make_players as MPL  # noqa: E402
TMP2 = TMPD / "no_cups.db"
con.commit()
shutil.copy(TMP, TMP2)
c2 = sqlite3.connect(TMP2)
c2.row_factory = sqlite3.Row
cupw = f"SELECT match_id FROM matches WHERE league_code IN ({', '.join(repr(c) for c in sorted(COMPETITIONS))})"
for t in ("goals", "events", "lineups", "lineup_players", "match_stats", "player_stats"):
    c2.execute(f"DELETE FROM {t} WHERE match_id IN ({cupw})")
c2.execute(f"DELETE FROM matches WHERE match_id IN ({cupw})")
c2.commit()
n_cup_goals = con.execute(f"SELECT COUNT(*) FROM goals WHERE match_id IN ({cupw})").fetchone()[0]
hist = PPG.load_history(PPG.HISTORY_FILE, seed=None)
mrg, pins = PPG.load_id_merges(), PPG.load_pins()


# (8 نوفمبر 2026، صفحات اللاعبين بالكؤوس) الكؤوس تضيف ولا تغيّر: كل ما بخطة «بلا كؤوس» باقٍ حرفياً بخطة «بالكؤوس»
_p_with, _p_without = PPG.build_plan(con, dict(hist), mrg, pins), PPG.build_plan(c2, dict(hist), mrg, pins)
_cupset = set(COMPETITIONS)
_lg_view = lambda x: (x["slug"], x["kind"], x["pid"], x["display_en"], x["display_ar"], x.get("stats_pid"), sorted(g["gid"] for g in x["goals"] if g["league_code"] not in _cupset))
_w = {x["slug"]: x for x in _p_with["pages"]}
check(f"12 every league page unchanged by cups ({n_cup_goals} cup goals): slug, id, names, stats id, same league goals",
      n_cup_goals > 0 and all(x["slug"] in _w and _lg_view(_w[x["slug"]]) == _lg_view(x) for x in _p_without["pages"]))
check("12 cups add cup scorers' pages only", len(_p_with["pages"]) >= len(_p_without["pages"]) and all(
    not any(g["league_code"] not in _cupset for g in x["goals"]) for s, x in _w.items() if s not in {y["slug"] for y in _p_without["pages"]}))
check("12 stubs, name links, name+club links of the league plan all unchanged",
      all(_p_with["stubs"].get(k) == v for k, v in _p_without["stubs"].items() if k not in _w)   # صفحات الكؤوس المسجَّلة بالسجلّ (منذ 8 نوفمبر) تصير stub بخطة «بلا كؤوس»
      and all(_p_with["name_slug"].get(k) == v for k, v in _p_without["name_slug"].items())
      and all(_p_with["nt_slug"].get(k) == v for k, v in _p_without["nt_slug"].items()))
hp = TMPD / "hist_a.json"
shutil.copy(PPG.HISTORY_FILE, hp)
before_h = md5(hp)
PPG.update_history(PPG.build_plan(con, PPG.load_history(hp, seed=None), mrg, pins), hp, seed=None)
hp2 = TMPD / "hist_b.json"
shutil.copy(PPG.HISTORY_FILE, hp2)
PPG.update_history(PPG.build_plan(c2, PPG.load_history(hp2, seed=None), mrg, pins), hp2, seed=None)
import player_layout as PLY  # noqa: E402
_gr = lambda s, c: {"detail": "", "season": s, "league_code": c}
_tab = PLY.stats_tab(PLY.season_agg([], [_gr(2026, "AFC-CLE"), _gr(2025, "QAT"), _gr(2026, "QAT-EC")]), "ar", "../", lambda *a: "")
check("12 stats tab: default selection is the latest league even when a newer cup exists", 'data-k="2025-QAT">' in _tab and 'data-k="2026-AFC-CLE" hidden>' in _tab, _tab[:200])
_tab2 = PLY.stats_tab(PLY.season_agg([], [_gr(2026, "AFC-CLE")]), "ar", "../", lambda *a: "")
check("12 stats tab: a cup-only player still gets the cup selected", 'data-k="2026-AFC-CLE">' in _tab2, _tab2[:200])
_tab3 = PLY.stats_tab(PLY.season_agg([], [_gr(2027, "SAU-KC"), _gr(2026, "SAU")]), "ar", "../", lambda *a: "")
_car = PLY.career_rows([], [dict(_gr(2027, "SAU-KC"), team_id=1), dict(_gr(2026, "SAU"), team_id=1), dict(_gr(2025, "TUN-C"), team_id=1)], {}, "ar", "../", lambda t: "", lambda t, l: "")
check("12 career tab: cup rows use the league season of the edition (King's Cup provider 2027 joins 2026/27; TUN-C Jan-May 2026 = 2025/26)", _car.count('<small dir="ltr">') == 2 and ">2026/27<" in _car and ">2025/26<" in _car and "2027/28" not in _car, _car[:400])
check("12 stats tab: season heading uses the display season (King's Cup provider 2027 = 2026/27, no 2027/28)", '>2026/27</div>' in _tab3 and "2027/28" not in _tab3, _tab3[:300])
_ha, _hb = PPG.load_history(hp, seed=None), PPG.load_history(hp2, seed=None)
_p2 = PPG.build_plan(con, dict(_ha), mrg, pins)
_p1 = PPG.build_plan(con, PPG.load_history(PPG.HISTORY_FILE, seed=None), mrg, pins)
check("12 second build after recording history: same pages, URLs and redirects (cup pages do not move)",
      sorted((x["slug"], x["kind"], x["pid"], x["display_en"]) for x in _p2["pages"]) == sorted((x["slug"], x["kind"], x["pid"], x["display_en"]) for x in _p1["pages"])
      and _p2["stubs"] == _p1["stubs"] and _p2["aliases"] == _p1["aliases"])
check("12 player_url_history: cups only add entries, none of the league ones changes", all(_ha.get(k) == v for k, v in _hb.items() if k not in _w), (before_h, len(_ha), len(_hb)))
g1, g2 = MPL.gather(con), MPL.gather(c2)
check("12 make_players.gather: goals by name and name bridge identical with/without cups", g1[0] == g2[0] and g1[1] == g2[1])
_ssrow = [x for rows in g1[3].values() for x in rows if x["league_code"] in _cupset]
check("12 make_players season rows now include cups; league rows identical",
      all([x for x in g1[3].get(k, []) if x["league_code"] not in _cupset] == v for k, v in g2[3].items()))
pids = {r[0] for r in con.execute("SELECT DISTINCT player_id FROM lineup_players WHERE player_id > 0 LIMIT 400")}
e1, e2 = MPL.gather_extra(con, pids), MPL.gather_extra(c2, pids)
check("12 make_players.gather_extra plays: league matches identical; cups only add rows",
      all([x for x in e1[1].get(k, []) if x["m"]["league_code"] not in _cupset] == [x for x in v] for k, v in e2[1].items()))
pg_links = set(re.findall(r'href="\.\./players/([^"]+)\.html"', pages[("QAT-QC", "ar")]))
on_disk = {p.stem for p in (ROOT / "players").glob("*.html")} if (ROOT / "players").exists() else set()
check("12 cup page scorers: a link only to a player page that already exists (else plain name)", pg_links <= on_disk, sorted(pg_links - on_disk))
check("12 cup match page: no player links", "players/" not in page)
c2.close()

con.close()
check("football.db untouched", md5(DB_FILE) == DB_MD5)
print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}  (temp dir {TMPD})")
sys.exit(1 if fails else 0)
