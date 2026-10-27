"""Playwright (390px): live lineup on the match page (19 Oct 2026). A page with no static lineup gets a hidden Lineups tab + #lulive;
LIVE_LINEUP_SCRIPT fetches the worker's /lineup?id= (mocked here) and draws the same pitch as the static view. Checks: AR/EN render,
Arabic name map used, unknown ids fall back to the provider name, badge, #lineups opens the tab after the render, 404 keeps the tab
hidden, no fetch outside the time window, no fetch when the static lineup exists.
The mocked /lineup JSON is built from each team's latest real lineup in football.db (+ one unknown player id), the clock is pinned
to 30 min before kick-off. Self-contained since 27 Oct 2026: the two pages are built into a temp site from FIXED fixtures
(test_data/live_pages_fixture.json, in-memory DB copy via test_data/match_page_kit.py) — no dependency on today's real matches.
Needs make_assets.py (the temp site copies /assets).
Run: python C:\\Users\\User\\Projects\\Football\\test_live_lineup_page.py [screenshot_dir]
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "live_lineup"
SHOTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "test_data"))
from match_page_kit import FIXTURE, Kit, epoch  # noqa: E402

MID = FIXTURE["upcoming"]["match_id"]              # made upcoming, no static lineup
STATIC_MID = FIXTURE["static_lineup"]["match_id"]  # static lineup in the DB
UNKNOWN = {"id": 999999901, "name": "Zed Unknown", "number": 99, "pos": "M", "grid": None}

KIT = Kit()
KIT.reshape()
con = KIT.con
KO_MS = epoch(FIXTURE["upcoming"]["date"]) * 1000
m = KIT.render(MID, now=KO_MS // 1000 - 1800)
KIT.render(STATIC_MID, now=KO_MS // 1000 - 1800)


def team_json(tid):
    last = con.execute("SELECT MAX(match_id) FROM lineups WHERE team_id = ?", (tid,)).fetchone()[0]
    lu = con.execute("SELECT formation, coach_en FROM lineups WHERE match_id = ? AND team_id = ?", (last, tid)).fetchone()
    ps = con.execute("SELECT player_id, player_en, player_ar, number, pos, grid, starter FROM lineup_players WHERE match_id = ? AND team_id = ?",
                     (last, tid)).fetchall()
    pj = lambda p: {"id": p["player_id"], "name": p["player_en"], "number": p["number"], "pos": p["pos"] or "", "grid": p["grid"]}
    return ({"id": tid, "formation": lu["formation"], "coach": lu["coach_en"], "xi": [pj(p) for p in ps if p["starter"]],
             "subs": [pj(p) for p in ps if not p["starter"]]}, [p for p in ps if p["starter"]])


HOME, home_rows = team_json(m["home_id"])
AWAY, _ = team_json(m["away_id"])
HOME["subs"].append(UNKNOWN)
LIVE = {"fixture": MID, "t": KO_MS // 1000 - 1800, "home": HOME, "away": AWAY}
known = next(p for p in home_rows if (p["player_ar"] or "").strip())   # a starter with an Arabic name in the DB
KNOWN_AR, KNOWN_EN = known["player_ar"].strip(), known["player_en"].strip()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(KIT.root)))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fail += 1


def context(b, now_ms, mode="ok"):
    """mode: ok = 200 with LIVE, 404 = nothing stored yet. Every /lineup request is recorded."""
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(f"(() => {{ const off = {now_ms} - Date.now(); const n = Date.now.bind(Date); Date.now = () => n() + off; }})();")
    hits = []

    def handle(route):
        hits.append(route.request.url)
        if mode == "ok":
            route.fulfill(status=200, body=json.dumps(LIVE), headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"})
        else:
            route.fulfill(status=404, body="{}", headers={"Access-Control-Allow-Origin": "*"})
    ctx.route("**/saffara-live.abujaishamr.workers.dev/lineup*", handle)
    ctx.route("**/saffara-live.abujaishamr.workers.dev/", lambda r: r.fulfill(status=200, body='{"t":0,"m":{}}'))
    return ctx, hits


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        url = f"{B}{pre}/matches/{MID}.html"
        # 1) inside the window, stored lineup -> rendered
        ctx, hits = context(b, KO_MS - 30 * 60000)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1200)
        check(f"{lang}: one /lineup?id={MID} request", len(hits) == 1 and hits[0].endswith(f"/lineup?id={MID}"), hits)
        btn = pg.locator('.mtab[data-tab="lineups"]')
        check(f"{lang}: Lineups tab button revealed, not the default tab", btn.is_visible() and pg.get_attribute(".mtab.on", "data-tab") != "lineups",
              [btn.is_visible(), pg.get_attribute(".mtab.on", "data-tab")])
        btn.click(); pg.wait_for_timeout(200)
        badge = pg.inner_text("#lulive .lubadge")
        check(f"{lang}: badge '{'التشكيلة الرسمية' if lang == 'ar' else 'Official lineups'}'", badge == ("التشكيلة الرسمية" if lang == "ar" else "Official lineups"), badge)
        n_fp = pg.locator("#lulive .fpitch .fp").count()
        check(f"{lang}: pitch view (same markup as the static one): 22 players on .fpitch", n_fp == 22, n_fp)
        txt = pg.inner_text("#lulive")
        if lang == "ar":
            check("ar: Arabic name from the embedded map for a known starter", KNOWN_AR in txt and KNOWN_EN not in txt, [KNOWN_AR, KNOWN_EN])
        else:
            check("en: provider (English) name for the same starter", KNOWN_EN in txt, KNOWN_EN)
        check(f"{lang}: unknown player id -> provider name", "Zed Unknown" in txt)
        check(f"{lang}: two team blocks with formation + substitutes", pg.locator("#lulive .luteam").count() == 2
              and pg.locator("#lulive .luteam .sublist .sub").count() >= 1 and HOME["formation"] in txt)
        if HOME["coach"]:
            check(f"{lang}: coach line", pg.locator("#lulive .lucoach").count() >= 1)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        check(f"{lang}: 390px, no horizontal scroll", sw <= 390, sw)
        pg.locator("#lulive").scroll_into_view_if_needed()
        pg.screenshot(path=str(SHOTS / f"live_lineup_{lang}.png"), full_page=True)
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()

        # 2) #lineups in the URL -> the tab opens once the live lineup is drawn
        ctx, hits = context(b, KO_MS - 30 * 60000)
        pg = ctx.new_page()
        pg.goto(url + "#lineups"); pg.wait_for_timeout(1200)
        check(f"{lang}: #lineups opens the live Lineups tab after the render",
              pg.get_attribute(".mtab.on", "data-tab") == "lineups" and pg.get_attribute(".mp.on", "data-tab") == "lineups",
              [pg.get_attribute(".mtab.on", "data-tab"), pg.get_attribute(".mp.on", "data-tab")])
        ctx.close()

        # 3) nothing stored yet (404) -> tab stays hidden, no badge
        ctx, hits = context(b, KO_MS - 30 * 60000, mode="404")
        pg = ctx.new_page()
        pg.goto(url + "#lineups"); pg.wait_for_timeout(1000)
        check(f"{lang}: 404 -> tab hidden, empty slot, default tab stays", len(hits) == 1 and not pg.locator('.mtab[data-tab="lineups"]').is_visible()
              and pg.locator("#lulive .lubadge").count() == 0 and pg.get_attribute(".mtab.on", "data-tab") != "lineups", hits)
        ctx.close()

        # 4) outside the window (3 h before kick-off) -> no request at all
        ctx, hits = context(b, KO_MS - 3 * 3600000)
        pg = ctx.new_page()
        pg.goto(url); pg.wait_for_timeout(800)
        check(f"{lang}: 3 h before kick-off -> no /lineup request, tab hidden", not hits and not pg.locator('.mtab[data-tab="lineups"]').is_visible(), hits)
        ctx.close()

        # 5) static lineup exists -> no live slot, no request (static wins)
        ctx, hits = context(b, KO_MS - 30 * 60000)
        pg = ctx.new_page()
        pg.goto(f"{B}{pre}/matches/{STATIC_MID}.html#lineups"); pg.wait_for_timeout(1000)
        check(f"{lang}: static lineup page -> no #lulive, no /lineup request, static pitch shown",
              not hits and pg.locator("#lulive").count() == 0 and pg.locator(".mp.on .fpitch, .mp.on .pitch").count() >= 1, hits)
        ctx.close()
    b.close()

httpd.shutdown()
print(f"screenshots: {SHOTS}")
print(f"TOTAL FAILS: {fail}")
sys.exit(1 if fail else 0)
