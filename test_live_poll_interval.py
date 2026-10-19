"""Playwright: live feed poll interval on a match page (19 Oct 2026). live_view starts at 60 s; once a fixture on the page is live it
switches to 30 s (the worker now fetches every 30 s during a match); with nothing live it stops polling as before. The live feed is
mocked; setInterval/clearInterval are wrapped to record the intervals the page registers. Needs regenerated assets + match pages
(make_assets.py, make_matches.py). Run: python C:\\Users\\User\\Projects\\Football\\test_live_poll_interval.py
"""
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
MID = 1612259
fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fail += 1


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{httpd.server_address[1]}"

RECORD = """(() => {
  window.__iv = []; window.__cleared = 0;
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (fn, ms, ...a) => { window.__iv.push(ms); return si(fn, ms, ...a); };
  window.clearInterval = (id) => { window.__cleared++; return ci(id); };
})();"""


def run(b, lang, pre, feeds):
    """feeds: list of live-feed bodies returned in order (last one repeats). Returns (intervals, feed hits, page errors)."""
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(RECORD)
    hits = []

    def feed(route):
        hits.append(1)
        body = feeds[min(len(hits) - 1, len(feeds) - 1)]
        route.fulfill(status=200, body=json.dumps(body), headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"})
    ctx.route("**/saffara-live.abujaishamr.workers.dev/?*", feed)
    for p in ("lineup", "events"):
        ctx.route(f"**/saffara-live.abujaishamr.workers.dev/{p}*", lambda r: r.fulfill(status=404, body="{}", headers={"Access-Control-Allow-Origin": "*"}))
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"{B}{pre}/matches/{MID}.html"); pg.wait_for_timeout(1200)
    first = pg.evaluate("window.__iv.slice()")
    # simulate later polls by calling the page's own load path again: visibilitychange triggers load()
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(600)
    after = pg.evaluate("window.__iv.slice()")
    cleared = pg.evaluate("window.__cleared")
    ctx.close()
    return first, after, cleared, len(hits), errs


LIVE = {"t": 1, "m": {str(MID): {"h": 0, "a": 0, "e": 12, "s": "1H", "th": 1, "ta": 2}}}
IDLE = {"t": 1, "m": {}}

with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        first, after, cleared, n, errs = run(b, lang, pre, [LIVE])
        live_iv = [ms for ms in first if ms in (30000, 60000)]
        check(f"{lang}: live match -> starts at 60 s then switches to 30 s after the first paint", live_iv[:2] == [60000, 30000], first)
        check(f"{lang}:   the 60 s timer is cleared when switching", cleared >= 1, cleared)
        check(f"{lang}:   another load while still live keeps ONE 30 s timer (no re-register)", [ms for ms in after if ms == 30000].count(30000) == 1, after)
        first, after, cleared, n, errs2 = run(b, lang, pre, [IDLE])
        check(f"{lang}: nothing live -> 60 s timer only, never 30 s, and polling stops (cleared)",
              [ms for ms in after if ms in (30000, 60000)] == [60000] and cleared >= 1, [after, cleared])
        first, after, cleared, n, errs3 = run(b, lang, pre, [LIVE, IDLE])
        check(f"{lang}: live then full time -> 30 s timer stopped (cleared, not re-armed)",
              30000 in after and [ms for ms in after if ms == 30000].count(30000) == 1 and cleared >= 2, [after, cleared])
        check(f"{lang}: no page errors", not (errs or errs2 or errs3), errs + errs2 + errs3)
    b.close()

httpd.shutdown()
print(f"TOTAL FAILS: {fail}")
sys.exit(1 if fail else 0)
