"""Playwright (390px): match-page events after full time (19 Oct 2026). Pages with no saved `events` rows and a kick-off within 36 h carry
#evlive {id, ko, src}; once the match is out of the live feed's m, live_view fetches the worker's /events?id= (ev:<id>, mocked here) once
and draws the rows with the same renderer as live.v. A goals-only list (goals table, e.g. Iraq) is replaced by the full copy; saved
events (events table) always win. Arabic names come from the shared #pidmap (provider-name fallback).
Checks AR/EN: after-FT render, Arabic map + fallback, live.v still used while live (no /events request), goals-only replaced,
saved events -> no request, no request before kick-off / after 36 h, 404 keeps the page as built, no page errors.
Needs regenerated assets + match pages (make_assets.py, make_matches.py). Run: python C:\\Users\\User\\Projects\\Football\\test_live_events_page.py
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
con = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row


def ko_ms(mid):
    d = con.execute("SELECT date FROM matches WHERE match_id = ?", (mid,)).fetchone()[0]
    return int(datetime.strptime(d[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)


def pick(sql, args):
    r = con.execute(sql, args).fetchone()
    return r


# a page with #evlive and no static list (upcoming in the build), one goals-only page (IRQ), one with saved events (events table)
UP = pick("""SELECT m.match_id, m.home_id, m.away_id FROM matches m WHERE m.status = 'NS' AND m.league_code NOT IN ('IRQ','JOR')
             AND m.date >= strftime('%Y-%m-%d %H:%M', 'now') ORDER BY m.date LIMIT 1""", ())
GO = pick("""SELECT m.match_id FROM matches m WHERE m.league_code IN ('IRQ','JOR') AND m.status = 'FT'
             AND m.date >= strftime('%Y-%m-%d %H:%M', 'now', '-30 hours') AND EXISTS (SELECT 1 FROM goals g WHERE g.match_id = m.match_id)
             ORDER BY m.date DESC LIMIT 1""", ())
SV = pick("""SELECT m.match_id FROM matches m WHERE m.status = 'FT' AND m.date >= strftime('%Y-%m-%d %H:%M', 'now', '-30 hours')
             AND EXISTS (SELECT 1 FROM events e WHERE e.match_id = m.match_id AND e.type != 'none') ORDER BY m.date DESC LIMIT 1""", ())
known = con.execute("""SELECT player_id, player_en, player_ar FROM lineup_players WHERE team_id = ? AND player_id > 0
                       AND COALESCE(player_ar,'') <> '' ORDER BY match_id DESC LIMIT 2""", (UP["home_id"],)).fetchall()
P1, P2 = known[0], known[1]
UNKNOWN_ID, UNKNOWN_NAME = 999999902, "Zed Provider"


def ev_json(mid, ft=1):
    # [min, extra, type, detail, player, assist/in, side, player id, assist id]
    rows = [[12, 0, "g", "n", P1["player_en"], P2["player_en"], "h", P1["player_id"], P2["player_id"]],
            [40, 0, "c", "y", UNKNOWN_NAME, "", "a", UNKNOWN_ID, None],
            [63, 0, "s", "", P2["player_en"], UNKNOWN_NAME, "h", P2["player_id"], UNKNOWN_ID],
            [70, 0, "v", "Goal cancelled", "", "", "a", None, None]]
    return {"fixture": mid, "t": 1, "th": 1, "ta": 2, "ft": ft, "l": rows}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{httpd.server_address[1]}"
fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fail += 1


def context(b, now_ms, feed, events_mode="ok", ev_mid=None):
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(f"(() => {{ const off = {now_ms} - Date.now(); const n = Date.now.bind(Date); Date.now = () => n() + off; }})();")
    hits = []

    def events(route):
        hits.append(route.request.url)
        if events_mode == "ok":
            route.fulfill(status=200, body=json.dumps(ev_json(ev_mid)), headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"})
        else:
            route.fulfill(status=404, body="{}", headers={"Access-Control-Allow-Origin": "*"})
    ctx.route("**/saffara-live.abujaishamr.workers.dev/events*", events)
    ctx.route("**/saffara-live.abujaishamr.workers.dev/lineup*", lambda r: r.fulfill(status=404, body="{}", headers={"Access-Control-Allow-Origin": "*"}))
    ctx.route("**/saffara-live.abujaishamr.workers.dev/?*", lambda r: r.fulfill(status=200, body=json.dumps(feed),
              headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}))
    return ctx, hits


def open_events(pg):
    tab = pg.locator('.mtab[data-tab="events"]')
    if tab.count():
        tab.click(); pg.wait_for_timeout(150)


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        mid = UP["match_id"]; ko = ko_ms(mid)
        url = f"{B}{pre}/matches/{mid}.html"
        # 1) after full time (out of m, in f), no static list -> one /events request, rows drawn
        ctx, hits = context(b, ko + 2 * 3600000, {"t": 1, "m": {}, "f": {str(mid): {"h": 1, "a": 0, "s": "FT", "ft": 1}}}, ev_mid=mid)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1500); open_events(pg)
        rows = pg.locator("#evbox .ev")
        check(f"{lang}: after FT -> one /events?id={mid} request, 4 rows drawn", len(hits) == 1 and hits[0].endswith(f"/events?id={mid}") and rows.count() == 4,
              [hits, rows.count()])
        txt = pg.inner_text("#evbox") if rows.count() else ""
        if lang == "ar":
            check("ar: scorer + assist/sub names from #pidmap (Arabic)", P1["player_ar"].strip() in txt and P2["player_ar"].strip() in txt
                  and P1["player_en"] not in txt, [P1["player_ar"], P2["player_ar"]])
        else:
            check("en: provider (English) names", P1["player_en"] in txt and P2["player_en"] in txt)
        check(f"{lang}: unknown player id -> provider name", UNKNOWN_NAME in txt)
        check(f"{lang}: no page errors", not errs, errs)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        check(f"{lang}: 390px, no horizontal scroll", sw <= 390, sw)
        ctx.close()

        # 2) while live: live.v (with ids) drawn, Arabic map applied, NO /events request
        live_rows = ev_json(mid)["l"][:2]
        ctx, hits = context(b, ko + 20 * 60000, {"t": 1, "m": {str(mid): {"h": 1, "a": 0, "e": 20, "s": "1H", "th": UP["home_id"], "ta": UP["away_id"]}},
                                                  "v": {str(mid): live_rows}}, ev_mid=mid)
        pg = ctx.new_page()
        pg.goto(url); pg.wait_for_timeout(1500); open_events(pg)
        txt = pg.inner_text("#evbox") if pg.locator("#evbox").count() else ""
        check(f"{lang}: live -> live.v drawn (2 rows), no /events request", not hits and pg.locator("#evbox .ev").count() == 2, [hits, pg.locator("#evbox .ev").count()])
        if lang == "ar":
            check("ar: live rows also get Arabic names via ids", P1["player_ar"].strip() in txt, txt[:120])
        ctx.close()

        # 3) before kick-off and after 36 h -> no request
        for label, now in (("30 min before kick-off", ko - 30 * 60000), ("37 h after kick-off", ko + 37 * 3600000)):
            ctx, hits = context(b, now, {"t": 1, "m": {}}, ev_mid=mid)
            pg = ctx.new_page(); pg.goto(url); pg.wait_for_timeout(1000)
            check(f"{lang}: {label} -> no /events request", not hits, hits)
            ctx.close()

        # 4) 404 -> page stays as built (empty message)
        ctx, hits = context(b, ko + 2 * 3600000, {"t": 1, "m": {}}, events_mode="404", ev_mid=mid)
        pg = ctx.new_page(); pg.goto(url); pg.wait_for_timeout(1200)
        check(f"{lang}: /events 404 -> one request, #evempty kept, no rows", len(hits) == 1 and pg.locator("#evempty").count() == 1
              and pg.locator("#evbox .ev").count() == 0, hits)
        ctx.close()

        # 5) goals-only page (IRQ/JOR, goals table only) -> replaced by the full copy
        if GO:
            gmid = GO["match_id"]
            ctx, hits = context(b, ko_ms(gmid) + 3 * 3600000, {"t": 1, "m": {}}, ev_mid=gmid)
            pg = ctx.new_page(); pg.goto(f"{B}{pre}/matches/{gmid}.html"); pg.wait_for_timeout(1500); open_events(pg)
            n = pg.locator("#evbox .ev").count()
            check(f"{lang}: goals-only page {gmid} -> /events fetched, list replaced by the full copy (card + sub + VAR rows)",
                  len(hits) == 1 and n == 4 and pg.locator("#evbox[data-lvsig]").count() == 1, [hits, n])
            ctx.close()
        else:
            check(f"{lang}: goals-only IRQ/JOR page within 30 h found", False, "no fixture in the data")

        # 6) saved events (events table) -> no #evlive, no request, static rows untouched
        if SV:
            smid = SV["match_id"]
            ctx, hits = context(b, ko_ms(smid) + 3 * 3600000, {"t": 1, "m": {}}, ev_mid=smid)
            pg = ctx.new_page(); pg.goto(f"{B}{pre}/matches/{smid}.html"); pg.wait_for_timeout(1200)
            check(f"{lang}: saved events page {smid} -> no #evlive, no /events request, static list kept",
                  not hits and pg.locator("#evlive").count() == 0 and pg.locator("#evbox[data-lvsig]").count() == 0 and pg.locator("#evbox .ev").count() > 0, hits)
            ctx.close()
    b.close()

httpd.shutdown()
print(f"TOTAL FAILS: {fail}")
sys.exit(1 if fail else 0)
