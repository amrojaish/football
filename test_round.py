#!/usr/bin/env python3
"""
Round number on match pages (match_round.py, 27 Oct 2026, Amr) — on a TEMP COPY of football.db only. Run:
    python C:\\Users\\User\\Projects\\Football\\test_round.py [screenshot_dir]
  1) label(): "Regular Season - 8" -> «الجولة 8» / "Round 8"; known stages translated; unknown as-is
  2) before the migration: no column -> fetch code writes the old row shape (nothing breaks), page shows the league name only
  3) migrate() adds matches.round once (idempotent); save_finished (fetch_matches2/fetch_overdue) stores league.round;
     fetch_upcoming fills the round of EVERY fixture of the season from the same response (no extra request) and keeps it on REPLACE
  4) the Preview info card shows «<League> - Round N» (ar + en); screenshot of a real built page (390px)
football.db itself is never opened for writing (md5 checked).
"""
import functools
import hashlib
import http.server
import json
import shutil
import socketserver
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "round"
SHOTS.mkdir(parents=True, exist_ok=True)
import match_round as mr  # noqa: E402
from config import DB_FILE, LEAGUES  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()  # noqa: E731
DB_MD5 = md5(DB_FILE)

# 1) labels
cases = [("Regular Season - 8", "الجولة 8", "Round 8"), ("Championship Round - 3", "مرحلة البطولة - الجولة 3", "Championship round - Round 3"),
         ("Relegation Play-offs", "ملحق الهبوط", "Relegation play-offs"), ("Final", "النهائي", "Final"),
         ("Weird Stage - 2", "Weird Stage - الجولة 2", "Weird Stage - Round 2"), ("Something", "Something", "Something"), ("", "", "")]
for raw, ar, en in cases:
    check(f"1 label({raw!r}) -> «{ar}» / {en!r}", mr.label(raw, "ar") == ar and mr.label(raw, "en") == en, [mr.label(raw, "ar"), mr.label(raw, "en")])

# temp copy
TMP = Path(tempfile.mkdtemp(prefix="round_")) / "football_round.db"
shutil.copy(DB_FILE, TMP)
con = sqlite3.connect(TMP); con.row_factory = sqlite3.Row
up = con.execute("SELECT * FROM matches WHERE league_code='SAU' AND home_goals IS NULL AND date >= '2026-10-28' ORDER BY date LIMIT 1").fetchone()
ft = con.execute("SELECT * FROM matches WHERE league_code='SAU' AND home_goals IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()


def fx_of(row, rnd, goals=None):
    return {"fixture": {"id": row["match_id"], "date": str(row["date"]).replace(" ", "T") + ":00+00:00",
                        "status": {"short": "FT" if goals else "NS"}},
            "league": {"id": LEAGUES["SAU"]["id"], "round": rnd},
            "teams": {"home": {"id": row["home_id"]}, "away": {"id": row["away_id"]}},
            "goals": {"home": goals[0] if goals else None, "away": goals[1] if goals else None}}


import fetch_matches2 as fm  # noqa: E402
import fetch_upcoming as fu  # noqa: E402

# 2) before the migration
check("2 temp copy has no round column yet", not mr.has_round(con))
fm.save_finished(con, "SAU", ft["season"], fx_of(ft, "Regular Season - 9", (ft["home_goals"], ft["away_goals"])), [], status="FT")
check("2 save_finished without the column -> old row shape, no error", con.execute("SELECT COUNT(*) FROM matches WHERE match_id=?", (ft["match_id"],)).fetchone()[0] == 1)

# 3) migration + writes
check("3 migrate() adds the column", mr.migrate(con) is True and mr.has_round(con))
check("3 migrate() again = no-op", mr.migrate(con) is False)
fm.save_finished(con, "SAU", ft["season"], fx_of(ft, "Regular Season - 9", (ft["home_goals"], ft["away_goals"])), [], status="FT")
check("3 save_finished stores league.round", con.execute("SELECT round FROM matches WHERE match_id=?", (ft["match_id"],)).fetchone()[0] == "Regular Season - 9")
con.commit()   # fetch_upcoming opens its own connection
# fetch_upcoming main() against the temp DB with a mocked provider (one request per league = the same as today)
season = up["season"]
all_sau = con.execute("SELECT * FROM matches WHERE league_code='SAU' AND season=?", (season,)).fetchall()
resp = [fx_of(r, f"Regular Season - {(i % 34) + 1}", (r["home_goals"], r["away_goals"]) if r["home_goals"] is not None else None)
        for i, r in enumerate(all_sau)]
calls = []
fu.get_fixtures = lambda lid, s: (calls.append(lid), (True, resp if lid == LEAGUES["SAU"]["id"] else [], ""))[1]
fu.DB_FILE = TMP
fu.DELAY = 0
argv0 = sys.argv
sys.argv = ["fetch_upcoming.py", "SAU", "--season", str(season)]
try:
    fu.main()
finally:
    sys.argv = argv0
con.close(); con = sqlite3.connect(TMP); con.row_factory = sqlite3.Row
filled = con.execute("SELECT COUNT(*) FROM matches WHERE league_code='SAU' AND season=? AND round IS NOT NULL", (season,)).fetchone()[0]
check(f"3 fetch_upcoming: one provider request, round filled for every fixture of the season ({filled}/{len(all_sau)}, finished + upcoming)",
      calls == [LEAGUES["SAU"]["id"]] and filled == len(all_sau), [calls, filled, len(all_sau)])
want = resp[[r["match_id"] for r in all_sau].index(up["match_id"])]["league"]["round"]
check("3 the upcoming match row (INSERT OR REPLACE) keeps its round", con.execute("SELECT round FROM matches WHERE match_id=?", (up["match_id"],)).fetchone()[0] == want)
check("football.db untouched", md5(DB_FILE) == DB_MD5)

# 4) the page: render the upcoming match from the temp DB with the real make_matches pipeline (one match, both languages)
import make_matches as mm  # noqa: E402
mm.LATEST_SEASON = con.execute("SELECT MAX(season) FROM matches").fetchone()[0]
mm.build_form_index(con)
teams = mm.load_teams()
row = con.execute("SELECT match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round FROM matches WHERE match_id=?",
                  (up["match_id"],)).fetchone()
h, a = teams[row["home_id"]], teams[row["away_id"]]
for lang in ("ar", "en"):
    form = mm.build_form_card(row, h, a, teams, lang) + mm.build_positions(con, row, teams, lang)
    html = mm.build_page(row, h, a, [], None, lang, "", "", mm.build_h2h(con, row, h, a, lang, mm.tname, mm.logo_url, teams),
                         mm.build_table_panel(con, row, teams, lang), form)
    out = ROOT / ("matches" if lang == "ar" else "en/matches") / f"{row['match_id']}.html"
    out.write_text(html, encoding="utf-8")
    lab = mr.label(want, lang)
    check(f"4 {lang}: info card shows «<League> - {lab}»", f" - {lab}</span>" in html, html[html.find('class="minfo"'):html.find('class="minfo"') + 500])


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8796), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
        ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"},
                                                                                         body='{"h":0,"d":0,"a":0,"total":0}'))
        pg = ctx.new_page(); pg.goto(f"http://127.0.0.1:8796{pre}/matches/{row['match_id']}.html", wait_until="load"); pg.wait_for_timeout(400)
        chip = pg.evaluate("()=>{const c=document.querySelectorAll('.minfo .chip');return c.length?c[c.length-1].textContent:null}")
        check(f"4 {lang}: rendered chip «{chip}»", chip and chip.endswith(mr.label(want, lang)), chip)
        pg.locator(".minfo").scroll_into_view_if_needed()
        pg.screenshot(path=str(SHOTS / f"round_{lang}.png"))
        ctx.close()
    br.close()
con.close()
print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (temp db: {TMP}; screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
