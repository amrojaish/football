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
import tempfile
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
TMPD = Path(tempfile.mkdtemp(prefix="cups_w1_"))
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
check("5 Al Ahly: no «Competitions» card (no cup this season)", MC.competitions_card(con, 1577, "EGY", 2026, ahly, "ar") == "")
sadd = MC.club_season_matches(con, 2895, 2026, "QAT")
check("5 Al Sadd 2026/27: Qatar Cup (provider season 2025, played Sep–Dec 2026) IS in this season's matches",
      any(x["league_code"] == "QAT-QC" for x in sadd))
card = MC.competitions_card(con, 2895, "QAT", 2026, sadd, "ar")
rows_ = re.findall(r'<span class="cmn">(.*?)<small><bdi dir="ltr">(.*?)</bdi></small></span><span class="cms">(.*?)</span>', card)
check("5 Al Sadd card: QAT league (rank) + Qatar Cup «النهائي» (alive), links to the competition pages",
      [x[0] for x in rows_] == ["دوري نجوم قطر", "كأس قطر"] and rows_[0][2].startswith("المركز") and rows_[1][2] == "النهائي"
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
check("9 ENABLED_CUPS = the 9 wave-1 codes", set(ENABLED_CUPS) == {"SAU-KC", "SAU-SC", "UAE-SC", "EGY-SC", "KUW-SC", "JOR-SC", "QAT-QC", "TUN-SC", "ALG-SC"})

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
check("11 next_kickoffs.json: no cup match (no poll window, no reminder, no vote) — UAE-SC 29 Nov is 1 day ahead",
      not any(x[1] == uae[0][0] for x in ko["f"]) and str(uae[0][0]) not in ko["v"], [x[1] for x in ko["f"]][:5])
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


def plan_key(c):
    p = PPG.build_plan(c, dict(hist), mrg, pins)
    return (sorted((x["slug"], x["pid"], x["display_en"], x.get("stats_pid"), len(x["goals"])) for x in p["pages"]),
            sorted(p["stubs"].items()), sorted(p["name_slug"].items()), sorted(map(str, p["nt_slug"].items())))


check(f"12 build_plan with cups ({n_cup_goals} cup goals) == without cups (pages, stubs, name/nt slugs)",
      n_cup_goals > 0 and plan_key(con) == plan_key(c2))
hp = TMPD / "hist_a.json"
shutil.copy(PPG.HISTORY_FILE, hp)
before_h = md5(hp)
PPG.update_history(PPG.build_plan(con, PPG.load_history(hp, seed=None), mrg, pins), hp, seed=None)
hp2 = TMPD / "hist_b.json"
shutil.copy(PPG.HISTORY_FILE, hp2)
PPG.update_history(PPG.build_plan(c2, PPG.load_history(hp2, seed=None), mrg, pins), hp2, seed=None)
check("12 player_url_history update with cups == without cups (byte-identical result)", md5(hp) == md5(hp2), (before_h, md5(hp), md5(hp2)))
g1, g2 = MPL.gather(con), MPL.gather(c2)
check("12 make_players.gather (goals, bridge, stats, season rows) identical with/without cups",
      [dict(x) if isinstance(x, dict) else x for x in g1] == [dict(x) if isinstance(x, dict) else x for x in g2])
pids = {r[0] for r in con.execute("SELECT DISTINCT player_id FROM lineup_players WHERE player_id > 0 LIMIT 400")}
e1, e2 = MPL.gather_extra(con, pids), MPL.gather_extra(c2, pids)
check("12 make_players.gather_extra plays: no cup match in any player's match list", e1[1] == e2[1])
pg_links = set(re.findall(r'href="\.\./players/([^"]+)\.html"', pages[("QAT-QC", "ar")]))
on_disk = {p.stem for p in (ROOT / "players").glob("*.html")} if (ROOT / "players").exists() else set()
check("12 cup page scorers: a link only to a player page that already exists (else plain name)", pg_links <= on_disk, sorted(pg_links - on_disk))
check("12 cup match page: no player links", "players/" not in page)
c2.close()

con.close()
check("football.db untouched", md5(DB_FILE) == DB_MD5)
print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}  (temp dir {TMPD})")
sys.exit(1 if fails else 0)
