#!/usr/bin/env python3
"""
League page «Seasons» tab (seasons_view.py, 27 Oct 2026, Amr #2) — data rules + Playwright (ar + en, 390px). Run:
    python C:\\Users\\User\\Projects\\Football\\test_seasons_tab.py [screenshot_dir]
Needs make_leagues.py --all built (archive season pages). Serves the repo on 127.0.0.1:8792. football.db is only read.

  1) only finished seasons with a reliable final table: current season never; staged seasons without group data skipped (KUW/TUN 2022-23);
     newest first; champion/runner-up = top two of our final table (EGY 2024 split season: championship-group ranking -> Al Ahly)
  2) every league page (current + archive) has the tab; one card per shown season, newest first, «Winner»/«Runner-up» rows with logos;
     card link = that season's page, which exists; tapping opens it and its standings #1 is the champion
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import seasons_view as sv  # noqa: E402
from config import DB_FILE, LEAGUES  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "seasons"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
NEWEST = {r[0]: r[1] for r in con.execute("SELECT league_code, MAX(season) FROM matches GROUP BY 1")}
ALL = {}
for code in LEAGUES:
    shown, skipped = sv.season_list(con, code)
    ALL[code] = (shown, skipped)
    seasons = [x["season"] for x in shown]
    unfinished = [s for s in seasons if con.execute("SELECT COUNT(*) FROM matches WHERE league_code=? AND season=? AND home_goals IS NULL",
                                                    (code, s)).fetchone()[0]]
    check(f"1 {code}: shown {seasons}, all finished, newest first, current season ({NEWEST[code]}) not shown",
          not unfinished and seasons == sorted(seasons, reverse=True) and NEWEST[code] not in seasons and len(seasons) >= 2, [seasons, unfinished])
egy = {x["season"]: x for x in ALL["EGY"][0]}
check("1 EGY 2024 (split season): championship-group ranking -> Al Ahly winner, Pyramids runner-up",
      egy[2024]["basis"] == "group" and egy[2024]["champ"]["name_en"] == "Al Ahly" and egy[2024]["runner"]["name_en"] == "Pyramids FC", egy.get(2024))
for code, s in (("KUW", 2022), ("KUW", 2023), ("TUN", 2022), ("TUN", 2023)):
    check(f"1 {code} {s}: staged season without group data -> skipped", any(x[0] == s and "uneven" in x[1] for x in ALL[code][1]), ALL[code][1])


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8792), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8792"

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        S = sv.STR[lang]
        for code in LEAGUES:
            shown = ALL[code][0]
            ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbLeaguesV2','1');}catch(e){}")
            ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"},
                                                                                             body='{"t":0,"m":{}}'))
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"{BASE}{pre}/leagues/{code.lower()}.html", wait_until="load"); pg.wait_for_timeout(200)
            pg.locator('.cattabs .tab[data-cat="seasons"]').click(); pg.wait_for_timeout(250)
            cards = pg.evaluate("""()=>[...document.querySelectorAll('.panel[data-cat="seasons"] .scard')].map(a=>({s:+a.dataset.season,href:a.querySelector('a.sct').getAttribute('href'),
                rows:[...a.querySelectorAll('.srow')].map(r=>[r.className, r.querySelector('.sb').textContent, !!r.querySelector('img[src]'), r.querySelector('.sn').textContent, r.getAttribute('href')])}))""")
            check(f"2 {lang} {code}: tab text «{S['tab']}», one card per shown season, newest first",
                  pg.locator('.cattabs .tab[data-cat="seasons"]').inner_text() == S["tab"] and [c["s"] for c in cards] == [x["season"] for x in shown],
                  [[c["s"] for c in cards], [x["season"] for x in shown]])
            ok_rows = all(len(c["rows"]) == 2 and c["rows"][0][1] == S["winner"] and c["rows"][1][1] == S["runner"] and c["rows"][0][2] and c["rows"][1][2]
                          and c["rows"][0][3] and c["rows"][1][3] for c in cards)
            check(f"2 {lang} {code}: each card = Winner + Runner-up rows with logo and name", ok_rows, cards[:1])
            exist = all((ROOT / ("en/leagues" if lang == "en" else "leagues") / c["href"]).exists() for c in cards)
            check(f"2 {lang} {code}: every card links to an existing season page", exist, [c["href"] for c in cards])
            # (30 Oct 2026, batch 4 item 2) Winner / Runner-up rows link to that club's page (../clubs/<id>.html, existing)
            want = [[f"../clubs/{x['champ']['team_id']}.html", f"../clubs/{x['runner']['team_id']}.html"] for x in shown]
            got = [[r[4] for r in c["rows"]] for c in cards]
            clubs_ok = got == want and all((ROOT / ("en" if lang == "en" else "") / "clubs" / h.split("/")[-1]).exists() for g in got for h in g)
            check(f"2 {lang} {code}: Winner and Runner-up rows link to their (existing) club pages", clubs_ok, [got[:2], want[:2]])
            if code in ("EGY", "SAU", "JOR", "MAR"):
                pg.screenshot(path=str(SHOTS / f"{code}_{lang}.png"))
                pg.screenshot(path=str(SHOTS / f"{code}_{lang}_full.png"), full_page=True)
            if cards:
                first = cards[0]
                pg.locator('.panel[data-cat="seasons"] .scard a.sct').first.click(); pg.wait_for_load_state("load"); pg.wait_for_timeout(200)
                top = pg.evaluate("()=>{const r=document.querySelector('.panel[data-cat=\"standings\"] tr[data-t]');return r?+r.dataset.t:null}")
                champ = shown[0]["champ"]["team_id"]
                check(f"2 {lang} {code}: tap -> {first['href']}, its standings #1 = the champion", pg.url.endswith(first["href"]) and
                      (top == champ or shown[0]["basis"] == "group"), [pg.url, top, champ])
                # an archive season page carries the same tab, the viewed season highlighted
                cur = pg.evaluate("()=>{const c=document.querySelector('.scard.cur');return c?+c.dataset.season:null}")
                check(f"2 {lang} {code}: on that season's page the tab is there with its card highlighted", cur == first["s"], cur)
            check(f"2 {lang} {code}: no page errors", not errs, errs)
            ctx.close()
    br.close()

print("\nper league:")
for code in LEAGUES:
    print(f"  {code}: shown {[x['season'] for x in ALL[code][0]]}  skipped {ALL[code][1]}")
print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
