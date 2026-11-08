#!/usr/bin/env python3
"""
Cups wave 0 (prep, 3 Nov 2026) — registry, season labels, round labels, score columns + shootout filter, AET/PEN/WO/AWD fetch paths,
pens/ET line on the match page, no league machinery for cup codes, no KeyError for unknown codes. No network.
Provider data: test_data/cups_wave0.json (real fixtures from cups_check.md + ONE events call on 1645511, a 2-2 / 4-3 pens match).
Pages are rendered from a TEMP COPY of football.db only (md5 of football.db checked at the end). Nothing is written to the repo.
Run from the repo root:
    python C:\\Users\\User\\Projects\\Football\\test_cups_wave0.py
"""
import copy
import hashlib
import json
import shutil
import sqlite3
import sys
from _test_tmp import make_tmp
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import competitions as CP  # noqa: E402
import match_round as mr  # noqa: E402
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
DATA = json.loads((ROOT / "test_data" / "cups_wave0.json").read_text(encoding="utf-8"))
FX = DATA["fixtures"]
EV = DATA["events_1645511"]

# ── 1) registry ─────────────────────────────────────────────────────────────────────────────────────────────
NAMES = {   # Amr's list (3 Nov 2026): code -> (id, ar, en)
    "SAU-KC": (504, "كأس الملك", "King's Cup"), "SAU-SC": (826, "كأس السوبر السعودي", "Saudi Super Cup"),
    "UAE-PC": (560, "كأس رئيس الدولة", "UAE President's Cup"), "UAE-LC": (302, "كأس رابطة المحترفين", "UAE League Cup"),
    "UAE-SC": (896, "كأس السوبر الإماراتي", "UAE Super Cup"), "EGY-C": (714, "كأس مصر", "Egypt Cup"),
    "EGY-LC": (895, "كأس الرابطة المصرية", "Egyptian League Cup"), "EGY-SC": (539, "كأس السوبر المصري", "Egyptian Super Cup"),
    "KUW-EC": (720, "كأس أمير الكويت", "Kuwait Emir Cup"), "KUW-CPC": (820, "كأس ولي العهد الكويتي", "Kuwait Crown Prince Cup"),
    "KUW-SC": (719, "كأس السوبر الكويتي", "Kuwait Super Cup"), "JOR-C": (863, "كأس الأردن", "Jordan Cup"),
    "JOR-SH": (816, "درع الاتحاد الأردني", "Jordan Shield Cup"), "JOR-SC": (838, "كأس السوبر الأردني", "Jordan Super Cup"),
    "QAT-EC": (824, "كأس أمير قطر", "Qatar Emir Cup"), "QAT-SLC": (677, "كأس نجوم قطر", "QSL Cup"),
    "QAT-QC": (825, "كأس قطر", "Qatar Cup"), "MAR-C": (822, "كأس العرش", "Moroccan Throne Cup"),
    "TUN-C": (511, "كأس تونس", "Tunisian Cup"), "TUN-SC": (1194, "كأس السوبر التونسي", "Tunisian Super Cup"),
    "ALG-C": (514, "كأس الجمهورية الجزائرية", "Algerian Cup"), "ALG-SC": (516, "كأس السوبر الجزائري", "Algerian Super Cup"),
    "AFC-CLE": (17, "دوري أبطال آسيا للنخبة", "AFC Champions League Elite"), "AFC-CL2": (18, "دوري أبطال آسيا 2", "AFC Champions League Two"),
    "CAF-CL": (12, "دوري أبطال أفريقيا", "CAF Champions League"), "CAF-CC": (20, "كأس الكونفدرالية الأفريقية", "CAF Confederation Cup"),
    "GCC-CL": (1162, "دوري أبطال الخليج", "Gulf Champions League"),
}
check("1 registry: exactly the 27 codes of cups_plan.md 3.1", set(COMPETITIONS) == set(NAMES) and len(COMPETITIONS) == 27,
      sorted(set(COMPETITIONS) ^ set(NAMES)))
bad = [k for k, (i, ar, en) in NAMES.items()
       if k in COMPETITIONS and (COMPETITIONS[k]["id"], COMPETITIONS[k]["name_ar"], COMPETITIONS[k]["name_en"]) != (i, ar, en)]
check("1 registry: provider id + Arabic + English names exactly as Amr's list", not bad, bad)
check("1 registry: every type in cup|super|continental", all(v["type"] in ("cup", "super", "continental") for v in COMPETITIONS.values()))
check("1 registry: country = a league code, continental = None + region",
      all((v["country"] in LEAGUES) if v["type"] != "continental" else (v["country"] is None and v.get("region") in ("AFC", "CAF", "GCC"))
          for v in COMPETITIONS.values()))
check("1 LEAGUES unchanged (10 codes, same ids)", {k: v["id"] for k, v in LEAGUES.items()} ==
      {"JOR": 387, "IRQ": 542, "SAU": 307, "EGY": 233, "UAE": 301, "QAT": 305, "MAR": 200, "TUN": 202, "ALG": 186, "KUW": 330})
check("1 no provider id shared between a league and a cup", not ({v["id"] for v in LEAGUES.values()} & {v["id"] for v in COMPETITIONS.values()}))
check("1 comp_type: league / cup / super / continental / None",
      [CP.comp_type(c) for c in ("SAU", "SAU-KC", "SAU-SC", "AFC-CLE", "XYZ")] == ["league", "cup", "super", "continental", None])
check("1 provider_id / code_of round-trip", all(CP.code_of(CP.provider_id(c)) == c for c in list(LEAGUES) + list(COMPETITIONS)))
check("1 is_cup only for registry codes (unknown codes keep league behaviour)",
      CP.is_cup("UAE-PC") and not CP.is_cup("UAE") and not CP.is_cup("XYZ"))

# ── 2) season labels ────────────────────────────────────────────────────────────────────────────────────────
cases = [("SAU-KC", 2027, "2026/27"),    # provider 2027, Aug 2026 – May 2027 (registry end fixed 4 Nov 2026: final, not last scheduled)
         ("SAU-KC", 2026, "2025/26"),    # previous edition, same shape
         ("UAE-PC", 2026, "2026/27"),    # Sep 2026 – Feb 2027
         ("UAE-PC", 2025, "2025/26"),
         ("SAU-SC", 2026, "2025"),       # provider 2026 = Aug 2025
         ("KUW-EC", 2026, "2026/27"),    # Feb 2026 – (final not scheduled; registry end 2027-06-30, 4 Nov 2026)
         ("TUN-C", 2025, "2026"),        # provider 2025, Jan–May 2026
         ("ALG-C", 2025, "2025/26"),     # Dec 2025 – May 2026
         ("AFC-CLE", 2026, "2026/27")]
for code, s, want in cases:
    check(f"2 season_label({code}, {s}) = {want}", CP.season_label(code, s) == want, CP.season_label(code, s))
check("2 season_label for a league / unknown = None (league keeps «2026/27»)", CP.season_label("SAU", 2026) is None and CP.season_label("X", 1) is None)
check("2 label_from_dates", CP.label_from_dates("2026-01-10", "2026-05-09") == "2026" and CP.label_from_dates("2026-09-22", "2027-02-28") == "2026/27")
import player_layout as PLY  # noqa: E402
import make_clubs as MC  # noqa: E402
check("2 player_layout.season_label: league unchanged, cup from registry",
      PLY.season_label(2026) == "2026/27" and PLY.season_label(2026, "SAU") == "2026/27" and PLY.season_label(2027, "SAU-KC") == "2026/27")
check("2 make_clubs.season_label: league unchanged, cup label", MC.season_label("SAU", 2026, "ar") == "الدوري السعودي - 2026/2027"
      and MC.season_label("SAU-KC", 2027, "ar") == "كأس الملك - 2026/27" and MC.season_label("UAE-PC", 2026, "en") == "UAE President's Cup - 2026/27",
      [MC.season_label("SAU", 2026, "ar"), MC.season_label("SAU-KC", 2027, "ar"), MC.season_label("UAE-PC", 2026, "en")])

# ── 3) round labels (Amr's list) ────────────────────────────────────────────────────────────────────────────
ROUNDS = [("Preliminary Round", "الدور التمهيدي"), ("1st Preliminary Round", "الدور التمهيدي الأول"),
          ("2nd Preliminary Round", "الدور التمهيدي الثاني"), ("Round of 128", "دور الـ128"), ("Round of 64", "دور الـ64"),
          ("Round of 32", "دور الـ32"), ("Round of 16", "دور الـ16"), ("Quarter-finals", "ربع النهائي"),
          ("Semi-finals", "نصف النهائي"), ("3rd place", "مباراة المركز الثالث"), ("Final", "النهائي"),
          ("Group Stage - 3", "دور المجموعات - الجولة 3"), ("Group Stage", "دور المجموعات"),
          ("League Phase - 5", "مرحلة الدوري - الجولة 5"), ("Regular season - 2", "دور المجموعات - الجولة 2"),
          ("Caf Confederation Cup - 4", "دور المجموعات - الجولة 4")]
bad = [(r, mr.label(r, "ar")) for r, ar in ROUNDS if mr.label(r, "ar") != ar]
check("3 every cup round has its Arabic label", not bad, bad)
EN = {"3rd place": "Third-place match", "Group Stage": "Group stage", "League Phase - 5": "League phase - Round 5",
      "Regular season - 2": "Group stage - Round 2", "Caf Confederation Cup - 4": "Group stage - Round 4",
      "1st Preliminary Round": "1st preliminary round", "Round of 128": "Round of 128"}
bad = [(r, mr.label(r, "en")) for r, en in EN.items() if mr.label(r, "en") != en]
check("3 English labels (provider wording normalised)", not bad, bad)
check("3 league rounds unchanged", mr.label("Regular Season - 8", "ar") == "الجولة 8" and mr.label("Regular Season - 8", "en") == "Round 8")
check("3 i18n strings: leg 1/2, aggregate, penalties", all(k in __import__("i18n").T[lg] for lg in ("ar", "en")
                                                          for k in ("leg1", "leg2", "aggregate", "penalties", "after_et")))

# ── 4) score columns + shootout filter + fetch paths (small temp DB, no network) ─────────────────────────────
TMPD = make_tmp("cups_w0_")
SMALL = TMPD / "small.db"
con = sqlite3.connect(SMALL)
con.row_factory = sqlite3.Row
con.executescript("""
    CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                          home_goals INTEGER, away_goals INTEGER, status TEXT);
    CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, player_en TEXT,
                        player_ar TEXT, detail TEXT);
""")
check("4 score_of(PEN 1645511) = fulltime 1-1, extratime 1-1, penalty 4-3", MS.score_of(FX["pen"]) == (1, 1, 1, 1, 4, 3), MS.score_of(FX["pen"]))
check("4 score_of(AET) = fulltime 0-0, extratime 1-0, no pens", MS.score_of(FX["aet"]) == (0, 0, 1, 0, None, None), MS.score_of(FX["aet"]))
shoot = [e for e in EV if MS.is_shootout(e)]
check("4 provider sends the shootout as 10 Goal events with comments='Penalty Shootout' (7 scored, 3 missed)",
      len(shoot) == 10 and all(e["type"] == "Goal" for e in shoot) and sum(e["detail"] == "Penalty" for e in shoot) == 7,
      [(e["detail"], e["time"]) for e in shoot])
import fetch_matches2 as FM  # noqa: E402
check("4 before migration: has_score False, save_finished writes the old row shape", not MS.has_score(con))
n = FM.save_finished(con, "UAE-PC", 2026, FX["pen"], EV, status="PEN")
real_goals = FX["pen"]["goals"]["home"] + FX["pen"]["goals"]["away"]
check(f"4 shootout kicks NOT stored as goals ({n} goals = the 2-2 score)", n == real_goals == 4 and
      con.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1645511").fetchone()[0] == 4, n)
check("4 migrate() adds the 6 columns", MS.migrate(con) == list(MS.COLS) and MS.has_score(con))
check("4 migrate() again = no-op", MS.migrate(con) == [])
FM.save_finished(con, "UAE-PC", 2026, FX["pen"], EV, status="PEN")
FM.save_finished(con, "KUW-CPC", 2025, FX["aet"], [], status="AET")
r = con.execute("SELECT * FROM matches WHERE match_id = 1645511").fetchone()
check("4 PEN row: goals 2-2 (incl. ET), ft 1-1, et 1-1, pens 4-3, status PEN",
      (r["home_goals"], r["away_goals"], r["ft_home"], r["ft_away"], r["et_home"], r["et_away"], r["pen_home"], r["pen_away"], r["status"])
      == (2, 2, 1, 1, 1, 1, 4, 3, "PEN"), dict(r))
r = con.execute("SELECT * FROM matches WHERE match_id = ?", (FX["aet"]["fixture"]["id"],)).fetchone()
check("4 AET row: goals 1-0, et 1-0, pens NULL", (r["home_goals"], r["et_home"], r["et_away"], r["pen_home"], r["status"]) == (1, 1, 0, None, "AET"), dict(r))
check("4 MS.save is a no-op for an upcoming fixture (no values)", MS.save(con, {"fixture": {"id": 1}, "score": {}}) == 0)
check("4 MS.save again with the same response = 0 rows changed", MS.save(con, FX["pen"]) == 0)
import refresh_goal_names as RG  # noqa: E402
check("4 refresh_goal_names.provider_goals skips shootout kicks", len(RG.provider_goals(EV)) == 4, len(RG.provider_goals(EV)))
con.commit()

# fetch_matches2.main(): asks FT-AET-PEN and stores each fixture with its own status
calls = []


def fake_get(endpoint, params, label=""):
    calls.append((endpoint, dict(params)))
    if endpoint == "fixtures":
        return True, [FX["ft"], FX["aet"], FX["pen"]], ""
    return True, (EV if params.get("fixture") == 1645511 else []), ""


con.execute("DELETE FROM matches")
con.execute("DELETE FROM goals")
con.commit()
con.close()
FM.get, FM.DB_FILE, FM.DELAY, FM.check_key = fake_get, SMALL, 0, (lambda: True)
argv0 = sys.argv
sys.argv = ["fetch_matches2.py", "UAE", "--season", "2026", "--budget", "10"]
try:
    FM.main()
finally:
    sys.argv = argv0
con = sqlite3.connect(SMALL)
con.row_factory = sqlite3.Row
check("4 fetch_matches2 requests status=FT-AET-PEN", calls and calls[0] == ("fixtures", {"league": 301, "season": 2026, "status": "FT-AET-PEN"}),
      calls[:1])
got = {r["match_id"]: r["status"] for r in con.execute("SELECT match_id, status FROM matches")}
check("4 fetch_matches2 stores FT / AET / PEN with the provider status (was always FT)",
      got == {FX["ft"]["fixture"]["id"]: "FT", FX["aet"]["fixture"]["id"]: "AET", 1645511: "PEN"}, got)
check("4 fetch_matches2: PEN match has 4 goals, pens 4-3", con.execute("SELECT COUNT(*) FROM goals WHERE match_id = 1645511").fetchone()[0] == 4
      and tuple(con.execute("SELECT pen_home, pen_away FROM matches WHERE match_id = 1645511").fetchone()) == (4, 3))

# fetch_overdue: WO and AWD are final
import fetch_overdue as FO  # noqa: E402
for k in ("wo", "awd"):
    f = FX[k]
    con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status) "
                "VALUES (?, 'TUN-C', 2026, '2026-01-01 12:00', ?, ?, NULL, NULL, 'NS')",
                (f["fixture"]["id"], f["teams"]["home"]["id"], f["teams"]["away"]["id"]))
for k in ("wo", "awd"):
    row = con.execute("SELECT * FROM matches WHERE match_id = ?", (FX[k]["fixture"]["id"],)).fetchone()
    line, done = FO.apply_fixture(con, row, copy.deepcopy(FX[k]))
    check(f"4 fetch_overdue {k.upper()} counts as finished", done, line)
wo = con.execute("SELECT home_goals, away_goals, status FROM matches WHERE match_id = ?", (FX["wo"]["fixture"]["id"],)).fetchone()
awd = con.execute("SELECT home_goals, away_goals, status FROM matches WHERE match_id = ?", (FX["awd"]["fixture"]["id"],)).fetchone()
check("4 WO stored with its status and NO score (never a 0-0 draw)", tuple(wo) == (None, None, "WO"), tuple(wo))
check("4 AWD stored with the awarded 3-0", tuple(awd) == (3, 0, "AWD"), tuple(awd))
due = [r["match_id"] for r in FO.overdue_rows(con, 2026, now=1_900_000_000)]
check("4 WO/AWD are no longer 'overdue' (no retry every run)", FX["wo"]["fixture"]["id"] not in due and FX["awd"]["fixture"]["id"] not in due, due)
con.close()

# ── 5) pages on a TEMP COPY of football.db: no league machinery for cups, pens/ET line, no KeyError ─────────
BIG = TMPD / "football_cups_w0.db"
shutil.copy(DB_FILE, BIG)
con = sqlite3.connect(BIG)
con.row_factory = sqlite3.Row
MS.migrate(con)
FM.save_finished(con, "UAE-PC", 2026, FX["pen"], EV, status="PEN")
FM.save_finished(con, "UAE-PC", 2026, FX["ft"], [], status="FT")
FM.save_finished(con, "KUW-CPC", 2025, FX["aet"], [], status="AET")
# a King's Cup row with provider season 2027 between two SAU league clubs (must not become "latest season" or a club's current)
sau = con.execute("SELECT home_id, away_id FROM matches WHERE league_code = 'SAU' AND season = 2026 AND home_goals IS NOT NULL LIMIT 1").fetchone()
con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status) "
            "VALUES (990000001, 'SAU-KC', 2027, '2099-01-01 18:00', ?, ?, 1, 1, 'PEN')", (sau[0], sau[1]))
con.commit()

import make_site3 as M3  # noqa: E402
import make_matches as mm  # noqa: E402
import i18n  # noqa: E402

check("5 available(): cup codes excluded (no league page, no 2027 season)",
      not [r for r in M3.available(con) if CP.is_cup(r["league_code"])] and max(r["season"] for r in M3.available(con)) == 2026)
check("5 get_table(cup) = []", M3.get_table(con, "UAE-PC", 2026) == [] and M3.get_table(con, "SAU-KC", 2027) == [])
check("5 get_table(league) still a table", len(M3.get_table(con, "UAE", 2026)) > 10)
w, a_ = CP.league_codes_sql()
check("5 latest season (league-only query) stays 2026 with a 2027 cup row",
      con.execute(f"SELECT MAX(season) FROM matches WHERE {w}", a_).fetchone()[0] == 2026 and
      con.execute("SELECT MAX(season) FROM matches").fetchone()[0] == 2027)
mm.LATEST_SEASON = 2026
mm.build_form_index(con)
teams = mm.load_teams()
cols = "match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round, " + ", ".join(MS.COLS)
rows = {k: con.execute(f"SELECT {cols} FROM matches WHERE match_id = ?", (FX[k]["fixture"]["id"],)).fetchone() for k in ("pen", "ft", "aet")}
lg_row = con.execute(f"SELECT {cols} FROM matches WHERE league_code = 'UAE' AND season = 2026 AND home_goals IS NOT NULL "
                     "ORDER BY date DESC LIMIT 1").fetchone()
for k, row in rows.items():
    h, a = teams.get(row["home_id"]), teams.get(row["away_id"])
    for lang in ("ar", "en"):
        pieces = {"table": mm.build_table_panel(con, row, teams, lang), "positions": mm.build_positions(con, row, teams, lang),
                  "season card": mm.build_season_card(con, row, h, a, teams, lang), "form dots": mm.build_form_card(row, h, a, teams, lang)}
        check(f"5 {k} {lang}: no table / position / season card / form dots for a cup match", not any(pieces.values()),
              [n for n, v in pieces.items() if v])
for lang in ("ar", "en"):
    h, a = teams.get(lg_row["home_id"]), teams.get(lg_row["away_id"])
    check(f"5 league match {lang}: table + form still built", bool(mm.build_table_panel(con, lg_row, teams, lang))
          and bool(mm.build_form_card(lg_row, h, a, teams, lang)))
want = {("pen", "ar"): "ركلات الترجيح 4 - 3", ("pen", "en"): "Pens 4 - 3", ("aet", "ar"): "بعد التمديد", ("aet", "en"): "ET"}
for (k, lang), txt in want.items():
    got = mm.score_extra_html(rows[k], lang)
    check(f"5 score line {k} {lang}: «{txt}»", got == f'<span class="ftb" data-x="sc">{txt}</span>', got)
check("5 score line: FT cup match / league match / pre-migration row = none",
      mm.score_extra_html(rows["ft"], "ar") == "" and mm.score_extra_html(lg_row, "en") == ""
      and mm.score_extra_html({"status": "PEN", "home_goals": 1}, "ar") == "")
for lang in ("ar", "en"):
    row = rows["pen"]
    html = mm.build_page(row, teams.get(row["home_id"]), teams.get(row["away_id"]), [], None, lang)
    check(f"5 PEN match page {lang}: pens line under the FT badge + cup name + round label",
          want[("pen", lang)] in html and mm.html_escape(i18n.league_name("UAE-PC", lang)) in html and mr.label("Round of 16", lang) in html,
          [want[("pen", lang)] in html, mm.html_escape(i18n.league_name("UAE-PC", lang)) in html, mr.label("Round of 16", lang) in html])
row = rows["aet"]
html = mm.build_page(row, teams.get(row["home_id"]), teams.get(row["away_id"]), [], None, "en")
check("5 AET page (KUW-CPC provider season 2025 = current) has no old-season line", "meta-top" not in html.split('class="head"')[0])

# no KeyError for cup / continental / unknown codes
check("5 flag_path: league unchanged, cup -> its country, continental/unknown -> ''",
      [M3.flag_path(c) for c in ("SAU", "SAU-KC", "AFC-CLE", "XYZ")] == ["flags/sa.svg", "flags/sa.svg", "", ""]
      and M3.flag_path("MAR-C", "flags4x3") == "flags4x3/ma.svg")
check("5 league_name: cup from registry, unknown = code", i18n.league_name("SAU-KC", "ar") == "كأس الملك"
      and i18n.league_name("GCC-CL", "en") == "Gulf Champions League" and i18n.league_name("XYZ", "ar") == "XYZ"
      and i18n.league_name("SAU", "en") == "Saudi Pro League")
try:
    srcs = [mm.league_logo_src(c, "../") for c in ("AFC-CLE", "XYZ", "SAU-KC")] + [MC.league_logo_src(c, "../") for c in ("AFC-CLE", "XYZ")]
    check("5 league_logo_src for cup / unknown codes: no KeyError", True)
except KeyError as e:
    check("5 league_logo_src for cup / unknown codes: no KeyError", False, e)

# club pages: current = league, cup seasons never "current"
mct = MC.load_teams()
seasons = [(r["league_code"], r["season"]) for r in MC.club_seasons(con, sau[0])]
check("5 club_seasons ordered by last match date (the 2099 King's Cup row first)", seasons[0] == ("SAU-KC", 2027), seasons[:3])
check("5 current_of = the newest LEAGUE season, not the cup", MC.current_of(seasons) == ("SAU", 2026), MC.current_of(seasons))
check("5 current_of for a club with only cup rows = its first row", MC.current_of([("AFC-CLE", 2026)]) == ("AFC-CLE", 2026))
for tid in (sau[0], rows["pen"]["home_id"], rows["aet"]["home_id"]):
    for lang in ("ar", "en"):
        try:
            html = MC.build_page(con, tid, mct, lang)
            cur = MC.current_of([(r["league_code"], r["season"]) for r in MC.club_seasons(con, tid)])
            check(f"5 club {tid} {lang}: builds, current pane = {cur[0]}_{cur[1]}", html is not None and f'data-k="{cur[0]}_{cur[1]}">' in html
                  and not CP.is_cup(cur[0]))
        except Exception as e:  # noqa: BLE001
            check(f"5 club {tid} {lang}: builds", False, repr(e))
check("5 club stats/table blocks are empty for a cup code", MC.table_block(con, sau[0], mct, "SAU-KC", 2027, "ar") == ""
      and MC.stats_block(con, sau[0], "SAU-KC", 2027, "ar") == "")
con.close()

check("football.db untouched", md5(DB_FILE) == DB_MD5)
print(f"\n{'ALL PASS' if not fails else f'{fails} FAIL'}  (temp dir {TMPD})")
sys.exit(1 if fails else 0)
