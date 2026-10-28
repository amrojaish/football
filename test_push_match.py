"""Playwright test of the MATCH-page star (fbMatches) + goal-alert bell (fbPushMatches, ?push=1), 13 Oct 2026. Run:
    python C:\\Users\\User\\Projects\\Football\\test_push_match.py
Needs regenerated assets + pages (make_assets.py, make_matches.py EGY, make_clubs.py, make_site3.py). No real push service:
Notification / PushManager / serviceWorker.ready are stubbed and the worker URL is mocked (same stubs as test_push_toggle.py)."""
import functools
import http.server
import json
import re
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
KEY = "B" + "A" * 86
sys_path = __import__('sys').path.insert(0, str(Path(__file__).resolve().parent))
import make_clubs  # noqa: E402
REPO_PUBLIC = bool(make_clubs.PUSH_PUBLIC)
sys_path = __import__('sys').path.insert(0, str(ROOT / "test_data"))
from upcoming_match import upcoming_matches, skip  # noqa: E402
# a real upcoming match (the bell/star need one not started yet), EGY first; hard-coded 1612257 broke once it was played
_up = upcoming_matches(league="EGY") or upcoming_matches()
if not _up:
    skip("test_push_match.py", "no upcoming match (NS, kickoff > 2 h away) with AR + EN pages built — run make_matches.py")
MID = _up[0][0]
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Quiet, directory=str(ROOT))
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8767), handler)
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8767"

STUB = (ROOT / "test_push_toggle.py").read_text(encoding="utf-8")
STUB = re.search(r'STUB = """(.*?)"""', STUB, re.S).group(1)


def mock_worker(page, posts):
    def handle(route):
        req = route.request
        headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Content-Type": "application/json"}
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=headers)
        if req.url.endswith("/push/key"):
            return route.fulfill(status=200, headers=headers, body=json.dumps({"key": KEY}))
        if "/push/" in req.url:
            posts.append((req.url.rsplit("/", 1)[1], json.loads(req.post_data)))
            return route.fulfill(status=200, headers=headers, body='{"ok":true}')
        return route.fulfill(status=200, headers=headers, body='{"t":0,"m":{}}')
    page.route("https://saffara-live.abujaishamr.workers.dev/**", handle)


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script(STUB)
        if REPO_PUBLIC:   # exercise the CLOSED gate for the hidden-without-param check (the shipped asset says PUB=true)
            ctx.route("**/assets/match.*.js*", lambda r: r.fulfill(response=r.fetch(), body=r.fetch().text().replace(",PUB=true,", ",PUB=false,")))
        pg = ctx.new_page()
        posts = []
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        mock_worker(pg, posts)

        # 1) star works without ?push=1; bell hidden without it
        pg.goto(f"{BASE}{pre}/matches/{MID}.html")
        pg.wait_for_timeout(500)
        check(f"{lang}: star visible, bell hidden without ?push=1", pg.is_visible("#mstar") and not pg.is_visible("#pushbtn"))
        pg.click("#mstar")
        check(f"{lang}: star click -> aria-pressed true, fbMatches=[{MID}], kickoff stored",
              pg.get_attribute("#mstar", "aria-pressed") == "true" and pg.evaluate("localStorage.getItem('fbMatches')") == f"[{MID}]"
              and f'"{MID}":' in pg.evaluate("localStorage.getItem('fbMatchKo')"))
        pg.reload(); pg.wait_for_timeout(400)
        check(f"{lang}: state survives reload", pg.get_attribute("#mstar", "aria-pressed") == "true")
        pg.click("#mstar")
        check(f"{lang}: second click unfollows", pg.get_attribute("#mstar", "aria-pressed") == "false" and pg.evaluate("localStorage.getItem('fbMatches')") == "[]")

        # 2) expiry: a followed match 15 days past kickoff is dropped on read
        pg.evaluate(f"localStorage.setItem('fbMatches','[{MID}]');localStorage.setItem('fbMatchKo',JSON.stringify({{'{MID}':Date.now()-15*86400000}}))")
        pg.reload(); pg.wait_for_timeout(400)
        check(f"{lang}: 14-day expiry after kickoff", pg.get_attribute("#mstar", "aria-pressed") == "false" and pg.evaluate("localStorage.getItem('fbMatches')") == "[]")
        pg.evaluate(f"localStorage.setItem('fbMatches','[{MID}]');localStorage.setItem('fbMatchKo',JSON.stringify({{'{MID}':Date.now()-13*86400000}}))")
        pg.reload(); pg.wait_for_timeout(400)
        check(f"{lang}: 13 days after kickoff still followed", pg.get_attribute("#mstar", "aria-pressed") == "true")
        pg.evaluate("localStorage.clear()")

        # 3) bell with ?push=1: enable -> subscribe carries this match only; toggling again -> unsubscribe (no teams)
        pg.goto(f"{BASE}{pre}/matches/{MID}.html?push=1")
        pg.wait_for_timeout(600)
        check(f"{lang}: bell visible with ?push=1", pg.is_visible("#pushbtn"))
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sub = [x for x in posts if x[0] == "subscribe"]
        check(f"{lang}: bell on -> POST /push/subscribe teams=[] matches=[{MID}] lang={lang}",
              len(sub) == 1 and sub[0][1]["teams"] == [] and sub[0][1]["matches"] == [MID] and sub[0][1]["lang"] == lang, posts)
        check(f"{lang}: bell pressed + fbPushMatches stored", pg.get_attribute("#pushbtn", "aria-pressed") == "true"
              and json.loads(pg.evaluate("localStorage.getItem('fbPushMatches')"))[0][0] == MID)
        check(f"{lang}: bell does NOT follow the match (alerts and follow are independent)", pg.get_attribute("#mstar", "aria-pressed") == "false")
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        check(f"{lang}: bell off with no clubs -> POST /push/unsubscribe", [x[0] for x in posts][-1] == "unsubscribe"
              and pg.evaluate("localStorage.getItem('fbPushMatches')") is None, posts)

        # 4) with a club alert already on: match bell sends BOTH lists; turning it off keeps the club subscription
        posts.clear()
        pg.reload(); pg.wait_for_timeout(600)   # (the stub forgets its subscription on every navigation, so the load-time cleanup runs first)
        pg.evaluate("localStorage.setItem('fbPushTeams','[962]');localStorage.setItem('fbPushOn','1')")
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sub = [x for x in posts if x[0] == "subscribe"]
        check(f"{lang}: with club alerts on, the subscribe carries teams=[962] AND matches=[{MID}]", len(sub) == 1 and sub[0][1]["teams"] == [962] and sub[0][1]["matches"] == [MID], posts)
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sub = [x for x in posts if x[0] == "subscribe"]
        check(f"{lang}: bell off with clubs remaining -> re-subscribe teams=[962] matches=[] (NOT unsubscribe)",
              len(sub) == 2 and sub[1][1]["teams"] == [962] and sub[1][1]["matches"] == [] and "unsubscribe" not in [x[0] for x in posts], posts)

        # 5) club bell afterwards keeps the match list in its posts
        posts.clear()
        pg.goto(f"{BASE}{pre}/clubs/964.html?push=1"); pg.wait_for_timeout(700)
        # (the stub forgets its subscription on every navigation, so the page's load-time cleanup ran first; set the list now)
        pg.evaluate(f"localStorage.setItem('fbPushMatches','[[{MID},0]]')")
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sub = [x for x in posts if x[0] == "subscribe"]
        check(f"{lang}: club bell subscribe also carries matches=[{MID}]", len(sub) == 1 and sub[0][1]["matches"] == [MID] and 964 in sub[0][1]["teams"], posts)
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()
    b.close()

print("FAILS:", fails)
raise SystemExit(1 if fails else 0)
