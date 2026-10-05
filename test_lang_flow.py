"""Playwright (390px): the language must never change while browsing, and the settings menu
switches to the same page in the other language. Run (after generating the site):
    python C:\\Users\\User\\Projects\\Football\\test_lang_flow.py [screenshots_dir]
Flow per language: home -> leagues -> league -> club -> match -> player -> back x5."""
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8767), functools.partial(Quiet, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8767"


def state(pg):
    return pg.evaluate("document.documentElement.lang"), urlparse(pg.url).path


def assert_lang(pg, lang, label):
    l, path = state(pg)
    in_en = path.startswith("/en/") or path == "/en"
    check(f"[{lang}] {label}: html lang={lang} and path {'under /en/' if lang == 'en' else 'not under /en/'} ({path})",
          l == lang and (in_en == (lang == "en")), (l, path))


def first_href(pg, needle):
    """first <a> whose href contains `needle`, outside the settings overlay"""
    return pg.evaluate("""(n) => {
      const a = [...document.querySelectorAll('a[href]')].find(x => !x.closest('#sovl2') && x.getAttribute('href').includes(n));
      return a ? a.getAttribute('href') : null; }""", needle)


def click_first(pg, needle):
    h = first_href(pg, needle)
    if not h:
        return False
    with pg.expect_navigation():
        pg.evaluate("""(n) => [...document.querySelectorAll('a[href]')]
          .find(x => !x.closest('#sovl2') && x.getAttribute('href').includes(n)).click()""", h)
    pg.wait_for_load_state("load")
    return True


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, home in (("ar", "/"), ("en", "/en/")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.goto(BASE + home, wait_until="load")
        assert_lang(pg, lang, "home")
        check(f"[{lang}] no standalone language button in the top bar", pg.locator(".appbar .langbtn, .appbtns a[hreflang]").count() == 0)
        trail = [pg.url]

        steps = [("leagues page", "leagues.html"), ("league page", "leagues/"),
                 ("club page", "clubs/"), ("match page", "matches/")]
        for label, needle in steps:
            ok = click_first(pg, needle)
            check(f"[{lang}] found a '{needle}' link to click on previous page", ok)
            if not ok:
                break
            assert_lang(pg, lang, label)
            trail.append(pg.url)
        else:
            # player: from the match page, else from the club page
            if click_first(pg, "players/"):
                assert_lang(pg, lang, "player page (from match)")
                trail.append(pg.url)
            else:
                pg.go_back(wait_until="load")
                assert_lang(pg, lang, "club page again")
                ok = click_first(pg, "players/")
                check(f"[{lang}] found a players/ link on the club page", ok)
                if ok:
                    assert_lang(pg, lang, "player page (from club)")
                    trail.append(pg.url)

        # back all the way to the home page (history length differs when the player came from the club page)
        i = 0
        while urlparse(pg.url).path not in (home, home + "index.html") and i < 10:
            pg.go_back(wait_until="load")
            i += 1
            assert_lang(pg, lang, f"back #{i}")
        check(f"[{lang}] back chain ends at home without ever changing language", urlparse(pg.url).path in (home, home + "index.html"), pg.url)

        # settings: language row switches to the same page in the other language
        for label, url in (("home", BASE + home), ("club", trail[3] if len(trail) > 3 else None)):
            if not url:
                continue
            pg.goto(url, wait_until="load")
            pg.click("#navset")
            pg.wait_for_selector("#sovl2.on")
            row = pg.locator("#sovl2 a[hreflang]")
            check(f"[{lang}] settings ({label}): language row visible", row.count() == 1 and row.is_visible())
            if SHOTS and label == "home":
                pg.screenshot(path=str(SHOTS / f"settings_{lang}.png"))
            path = urlparse(pg.url).path
            want = ("/en" + path) if lang == "ar" else path[3:]
            if label == "home":
                want = "/en/" if lang == "ar" else "/"
            with pg.expect_navigation():
                row.click()
            pg.wait_for_load_state("load")
            other = "en" if lang == "ar" else "ar"
            got = urlparse(pg.url).path
            norm = lambda x: x[:-len("index.html")] if x.endswith("/index.html") else x
            check(f"[{lang}] settings ({label}): switches to the same page in {other} ({got})",
                  norm(got) == norm(want) and pg.evaluate("document.documentElement.lang") == other, (got, want))
        ctx.close()

    # league season page: switch keeps the season
    for lang, path in (("ar", "/leagues/egy-2022.html"), ("en", "/en/leagues/egy-2022.html")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.goto(BASE + path, wait_until="load")
        pg.click("#navset")
        pg.wait_for_selector("#sovl2.on")
        with pg.expect_navigation():
            pg.locator("#sovl2 a[hreflang]").click()
        want = "/en/leagues/egy-2022.html" if lang == "ar" else "/leagues/egy-2022.html"
        check(f"[{lang}] season page switch keeps the season ({urlparse(pg.url).path})", urlparse(pg.url).path == want)
        ctx.close()
    b.close()

srv.shutdown()
raise SystemExit(1 if fails else 0)
