#!/usr/bin/env python3
"""
UI batch 3 fix 2 (26 Oct 2026, Amr's phone shots of 25 Oct) — Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_ui_fix2.py [screenshot_dir]
Needs the site built (make_assets, make_site3, make_leagues, make_matches, make_search_page). Serves the repo itself on
127.0.0.1:8779 and mocks the live worker. Screenshots go to screenshot_dir, else <system temp>/football_test_shots/ui_fix2.

  2) match page header while live: running clock mm:ss from the provider minute at the pull time (t), ticking every second, normal
     text colour (not green, no dot); HT frozen; 45+N:SS in added time; list cards keep the minute circle
  3) Matches page bell = status only: <span>, blue filled when alerts are on for that match, grey slashed when off; no tap action,
     no toast, the tap opens the match
  4) league page: tab row stays on screen while scrolling and when switching tabs (header collapses on scroll down, batch 3)
  5) Matches page league header: flag/name open the league page; count/chevron collapse; «Following» header has no link
  6) search: Leagues in the results (all enabled leagues incl. TUN, ar + en names, country too) + a «Leagues» chip; tap opens the page
(1, long names wrapping, is covered by test_match_rows.py and test_card_overflow.py.)
"""
import functools
import http.server
import json
import re
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_site3 as ms  # noqa: E402
from config import LEAGUES  # noqa: E402
from i18n import T, league_name  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "ui_fix2"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8779), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8779"

# two upcoming EGY fixtures on the same Amman day (built pages): the first is «live» in the mocks / alerted in the bell test
sys.path.insert(0, str(ROOT / "test_data"))
from upcoming_match import upcoming_matches, skip  # noqa: E402
ups = upcoming_matches(2, league="EGY", same_day=True)
if not ups:
    skip("test_ui_fix2.py", "no two upcoming EGY matches (NS, kickoff > 2 h away, pages built) on the same Amman day")
MID, MID2 = ups[0][0], ups[1][0]
KO_MS = int(time.mktime(time.strptime(ups[0][1][:16], "%Y-%m-%d %H:%M")) * 1000 - time.timezone * 1000)
DAY = time.strftime("%Y-%m-%d", time.gmtime(KO_MS / 1000 + 3 * 3600))      # Amman day of the first fixture
LIVE = {"payload": {}}


def live_route(route):
    u = route.request.url
    body = LIVE["payload"] if re.match(r"https://saffara-live\.abujaishamr\.workers\.dev/(\?|$)", u) else {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body), headers={"Access-Control-Allow-Origin": "*"})


def payload(e, s, ago, x=None):
    d = {"h": 1, "a": 0, "e": e, "s": s, "lg": 233}
    if x is not None:
        d["x"] = x                                                  # provider added time (worker step 11 prep, 26 Oct 2026)
    return {"t": int(time.time()) - ago, "m": {str(MID): d}, "f": {}}


def ctx_page(br, lang, init=""):
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", timezone_id="Asia/Amman")
    if init:
        ctx.add_init_script(init)
    pg = ctx.new_page()
    pg.route("https://saffara-live.abujaishamr.workers.dev/**", live_route)
    pg.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
    return ctx, pg


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        t = T[lang]

        # ── 2) live clock in the match page header ──
        ctx, pg = ctx_page(br, lang)
        LIVE["payload"] = payload(7, "1H", 93)                     # provider: minute 7, pulled 93 s ago -> 8:33
        pg.goto(f"{BASE}{pre}/matches/{MID}.html"); pg.wait_for_selector(".big .lvclk", timeout=8000)
        a = pg.inner_text(".big .lvclk"); pg.wait_for_timeout(2100); b = pg.inner_text(".big .lvclk")
        sec = lambda x: int(x.split(":")[0]) * 60 + int(x.split(":")[1])  # noqa: E731
        check(f"2 {lang}: header clock starts from provider minute + time since the pull (7' + 93 s -> {a})",
              re.fullmatch(r"8:3[3-5]", a) is not None, a)
        check(f"2 {lang}: the clock ticks every second ({a} -> {b})", 1 <= sec(b) - sec(a) <= 3, [a, b])
        col = pg.evaluate("() => [getComputedStyle(document.querySelector('.big .lvclk')).color, getComputedStyle(document.body).color,"
                          " !!document.querySelector('.big .lvclk .dot')]")
        check(f"2 {lang}: normal text colour (not green), no pulsing dot", col[0] == col[1] and not col[2], col)
        pg.screenshot(path=str(SHOTS / f"match_live_clock_{lang}.png"))
        LIVE["payload"] = payload(45, "HT", 30)
        pg.reload(); pg.wait_for_selector(".big .lvclk", timeout=8000)
        h1 = pg.inner_text(".big .lvclk"); pg.wait_for_timeout(1500); h2 = pg.inner_text(".big .lvclk")
        check(f"2 {lang}: half-time = frozen label ({h1})", h1 == h2 and not re.search(r"\d:\d\d", h1), [h1, h2])
        LIVE["payload"] = payload(47, "1H", 5)                     # provider minute 47 in the 1st half = 2 min of added time
        pg.reload(); pg.wait_for_selector(".big .lvclk", timeout=8000)
        x = pg.inner_text(".big .lvclk")
        check(f"2 {lang}: added time shown 45+N ({x})", re.fullmatch(r"45\+2:0[5-8]", x) is not None, x)
        LIVE["payload"] = payload(45, "1H", 5, x=2)                 # provider sends 45 + extra 2 (status.extra -> x)
        pg.reload(); pg.wait_for_selector(".big .lvclk", timeout=8000)
        xx = pg.inner_text(".big .lvclk")
        check(f"2 {lang}: provider added-time field x used (45 + x 2 -> {xx})", re.fullmatch(r"45\+2:0[5-8]", xx) is not None, xx)
        LIVE["payload"] = payload(90, "2H", 70, x=4)
        pg.reload(); pg.wait_for_selector(".big .lvclk", timeout=8000)
        xy = pg.inner_text(".big .lvclk")
        check(f"2 {lang}: 2nd half 90 + x 4, 70 s since the pull -> {xy}", re.fullmatch(r"90\+5:1[0-3]", xy) is not None, xy)
        LIVE["payload"] = payload(63, "2H", 0)
        pg.reload(); pg.wait_for_selector(".big .lvclk", timeout=8000)
        y = pg.inner_text(".big .lvclk")
        check(f"2 {lang}: 2nd half from the provider minute ({y})", re.fullmatch(r"63:0[0-3]", y) is not None, y)
        LIVE["payload"] = payload(7, "1H", 30)                     # list card on the Matches page keeps the minute circle
        pg.goto(f"{BASE}{pre}/index.html"); pg.wait_for_timeout(600)
        pg.click(f'.daytab[data-day="{DAY}"]'); pg.wait_for_timeout(500)
        pill = pg.evaluate(f"() => {{ const c = document.querySelector('.daypanel.visible [data-mid=\"{MID}\"]'); return c ? [(c.querySelector('.lvpill') || {{}}).textContent || '', !!c.querySelector('.lvclk')] : null; }}")
        check(f"2 {lang}: Matches page card keeps the small minute circle (no clock)", pill == ["7", False], pill)
        ctx.close()

        # ── 3) bell on the Matches page cards = status only ──
        LIVE["payload"] = {}
        init = f"try{{localStorage.setItem('fbPushMatches', JSON.stringify([[{MID}, {KO_MS}]]));}}catch(e){{}}"
        ctx, pg = ctx_page(br, lang, init)
        pg.goto(f"{BASE}{pre}/index.html?push=1"); pg.wait_for_timeout(600)
        pg.click(f'.daytab[data-day="{DAY}"]'); pg.wait_for_timeout(500)
        bells = pg.evaluate(f"""() => [{MID}, {MID2}].map(id => {{ const b = document.querySelector('.daypanel.visible [data-mid="' + id + '"] .cbell');
            if (!b) return null; const cs = getComputedStyle(b), x = b.querySelector('.pbx');
            return {{tag: b.tagName, on: b.getAttribute('data-on'), hidden: b.hidden, pe: cs.pointerEvents, color: cs.color,
                     fill: getComputedStyle(b.querySelector('svg')).fill, slash: x ? getComputedStyle(x).display : null, label: b.getAttribute('aria-label')}}; }})""")
        acc = pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
        check(f"3 {lang}: bells are non-interactive status icons (span, pointer-events:none, visible)",
              all(b and b["tag"] == "SPAN" and b["pe"] == "none" and not b["hidden"] for b in bells), bells)
        check(f"3 {lang}: alerted match = filled (accent colour), no slash", bells[0]["on"] == "1" and bells[0]["fill"] != "none" and bells[0]["slash"] == "none", bells[0])
        check(f"3 {lang}: other match = grey slashed outline", bells[1]["on"] == "0" and bells[1]["fill"] == "none" and bells[1]["slash"] != "none"
              and bells[0]["color"] != bells[1]["color"], bells[1])
        check(f"3 {lang}: readable state label", bells[0]["label"] == ms.push_ui.STR[lang]["card_on"] and bells[1]["label"] == ms.push_ui.STR[lang]["card_off"], bells)
        pg.screenshot(path=str(SHOTS / f"home_bells_{lang}.png"))
        before = pg.evaluate("() => localStorage.getItem('fbPushMatches')")
        pg.evaluate(f"() => document.querySelector('.daypanel.visible [data-mid=\"{MID2}\"] .cbell').click()"); pg.wait_for_timeout(400)
        st = pg.evaluate("() => [localStorage.getItem('fbPushMatches'), !!(document.getElementById('ptoast') && !document.getElementById('ptoast').hidden)]")
        check(f"3 {lang}: a click on the bell changes nothing and shows no toast", st == [before, False], st)
        # ⚠️ scroll the card into view first: a mouse click at coordinates below the 844px viewport hits nothing (28 Oct 2026:
        #    with TUN/ALG/KUW on the day, the EGY cards sat at y 906/970 and the tap timed out — not a page bug)
        r = pg.evaluate(f"() => {{ const e = document.querySelector('.daypanel.visible [data-mid=\"{MID2}\"] .cbell'); e.scrollIntoView({{block: 'center'}}); const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }}")
        pg.mouse.click(r[0], r[1]); pg.wait_for_url(f"**/matches/{MID2}.html", timeout=5000)
        check(f"3 {lang}: tapping where the bell is opens the match", pg.url.endswith(f"matches/{MID2}.html"), pg.url)
        ctx.close()

        # ── 4) league page header stays on screen ──
        ctx, pg = ctx_page(br, lang)
        pg.goto(f"{BASE}{pre}/leagues/egy.html"); pg.wait_for_timeout(600)
        top0 = pg.evaluate("() => document.querySelector('.lstick').getBoundingClientRect().top")
        pg.evaluate("() => window.scrollTo(0, 900)"); pg.wait_for_timeout(300)
        hd = pg.evaluate("""() => { const s = document.querySelector('.lstick').getBoundingClientRect(), q = x => document.querySelector(x).getBoundingClientRect();
            const vis = r => r.bottom > 0 && r.top >= -1 && r.height > 0;
            return {scrollY: Math.round(scrollY), top: Math.round(s.top), back: vis(q('.lstick .appbar')), name: vis(q('.lstick .lhead h1')),
                    season: vis(q('.lstick .sdd')), bell: vis(q('.lstick #pushbtn')), tabs: vis(q('.lstick .cattabs'))}; }""")
        # (30 Oct 2026, batch 3 item 4) scrolling down past the header collapses it: only the tab row stays at the top
        hd["tabtop"] = pg.evaluate("() => Math.round(document.querySelector('.lstick .cattabs').getBoundingClientRect().top)")
        check(f"4 {lang}: scrolled 900px -> header collapsed (back, league, season, bell off screen), tab row still at the top",
              hd["scrollY"] > 0 and hd["tabtop"] == 0 and hd["tabs"] and not any(hd[k] for k in ("back", "name", "season", "bell")), hd)
        pg.screenshot(path=str(SHOTS / f"league_scrolled_{lang}.png"))
        pg.click('.cattabs .tab[data-cat="player-stats"]'); pg.wait_for_timeout(300)
        sw = pg.evaluate("() => [Math.round(scrollY), Math.round(document.querySelector('.lstick').getBoundingClientRect().top),"
                         " Math.round(document.querySelector('.panel.visible').getBoundingClientRect().top - document.querySelector('.lstick').getBoundingClientRect().bottom)]")
        check(f"4 {lang}: switching tab keeps the header in place and starts the new tab at its top (no jump)",
              sw[0] == 0 and sw[1] == round(top0) and 0 <= sw[2] <= 20, sw)
        pg.click('.cattabs .tab[data-cat="matches"]'); pg.wait_for_timeout(500)
        mt = pg.evaluate("() => [Math.round(document.querySelector('.lstick .cattabs').getBoundingClientRect().top), scrollY > 0]")
        check(f"4 {lang}: Matches tab (scrolls to today) -> tab row still at the top", mt == [0, True], mt)
        pg.screenshot(path=str(SHOTS / f"league_matches_{lang}.png"))
        ctx.close()

        # ── 5) league section header on the Matches page ──
        ctx, pg = ctx_page(br, lang)
        pg.goto(f"{BASE}{pre}/index.html"); pg.wait_for_timeout(600)
        pg.click(f'.daytab[data-day="{DAY}"]'); pg.wait_for_timeout(400)
        sec_ = '.daypanel.visible details.lgsec[data-sec="EGY"]'
        lk = pg.evaluate(f"() => {{ const a = document.querySelector('{sec_} > summary a.lglink'); return a ? [a.getAttribute('href'), !!a.querySelector('.flagr'), !!a.querySelector('.lgname'), !!a.querySelector('.lgnum')] : null; }}")
        check(f"5 {lang}: flag + league name are one link to the league page (count/chevron outside it)", lk == ["leagues/egy.html", True, True, False], lk)
        pg.evaluate(f"() => document.querySelector('{sec_} a.lglink').addEventListener('click', e => e.preventDefault(), {{once: true}})")
        pg.click(f"{sec_} a.lglink .lgname"); pg.wait_for_timeout(200)
        check(f"5 {lang}: tapping the name does not collapse the section", pg.evaluate(f"() => document.querySelector('{sec_}').open"))
        pg.click(f"{sec_} > summary .lgnum"); pg.wait_for_timeout(200)
        c1 = pg.evaluate(f"() => document.querySelector('{sec_}').open"); pg.click(f"{sec_} > summary .chev"); pg.wait_for_timeout(200)
        c2 = pg.evaluate(f"() => document.querySelector('{sec_}').open")
        check(f"5 {lang}: count collapses, chevron expands again (page stays)", c1 is False and c2 is True and pg.url.endswith("index.html"), [c1, c2, pg.url])
        pg.click(f"{sec_} a.lglink .lgname"); pg.wait_for_url("**/leagues/egy.html", timeout=5000)
        check(f"5 {lang}: tapping the flag/name opens the league page", pg.url.endswith(f"{pre}/leagues/egy.html"), pg.url)
        ctx.close()

        # ── 6) search: leagues ──
        ctx, pg = ctx_page(br, lang)
        pg.goto(f"{BASE}{pre}/search.html"); pg.wait_for_timeout(500)
        chips = pg.evaluate("() => [...document.querySelectorAll('.sp-chip')].map(c => [c.dataset.f, c.textContent.trim()])")
        check(f"6 {lang}: chips All / Clubs / Players / Leagues", [c[0] for c in chips] == ["all", "clubs", "players", "leagues"]
              and chips[3][1] == t["s_leagues"], chips)
        q = "تونس" if lang == "ar" else "Tunis"
        pg.fill("#q", q); pg.wait_for_timeout(400)
        hits = pg.evaluate("() => [...document.querySelectorAll('.sp-item')].filter(a => a.getAttribute('href').indexOf('leagues/') >= 0).map(a => [a.getAttribute('href'), a.querySelector('.sp-nm').textContent, a.querySelector('.sp-sub').textContent, !!a.querySelector('img')])")
        check(f"6 {lang}: «{q}» finds the Tunisian league (name, country line, flag/logo)",
              len(hits) == 1 and hits[0][0].endswith("leagues/tun.html") and hits[0][1] == league_name("TUN", lang) and hits[0][3], hits)
        pg.screenshot(path=str(SHOTS / f"search_tun_{lang}.png"))
        # «دوري» is in every Arabic league name; «a» is in every English name/country (and in many clubs/players: the chip must drop them)
        pg.click('.sp-chip[data-f="leagues"]'); pg.fill("#q", "دوري" if lang == "ar" else "a"); pg.wait_for_timeout(400)
        rows = pg.evaluate("() => [...document.querySelectorAll('.sp-item')].map(a => a.getAttribute('href'))")
        check(f"6 {lang}: «Leagues» chip -> the {len(LEAGUES)} enabled leagues only (incl. TUN), no clubs/players",
              sorted(h.split("leagues/")[-1] for h in rows) == sorted(f"{c.lower()}.html" for c in LEAGUES) and all("leagues/" in h for h in rows), rows)
        pg.screenshot(path=str(SHOTS / f"search_leagues_chip_{lang}.png"))
        pg.click('.sp-chip[data-f="all"]'); pg.fill("#q", q); pg.wait_for_timeout(300)
        pg.click('.sp-item[href$="leagues/tun.html"]'); pg.wait_for_url("**/leagues/tun.html", timeout=5000)
        check(f"6 {lang}: tapping the result opens the league page", pg.url.endswith(f"{pre}/leagues/tun.html"), pg.url)
        pg.go_back(); pg.wait_for_timeout(400); pg.fill("#q", ""); pg.wait_for_timeout(300)
        rec = pg.evaluate("() => [...document.querySelectorAll('.sp-item')].map(a => a.getAttribute('href'))")
        check(f"6 {lang}: the league joins «Recent searches»", any(h.endswith("leagues/tun.html") for h in rec), rec)
        ctx.close()
    br.close()

# «Following» header only collapses: its summary is built in make_site3's follow script without a link
src = (ROOT / "make_site3.py").read_text(encoding="utf-8")
fs = src[src.index("sec.className='lgsec followsec'"):][:500]
check("5: «Following» section header has no league link (collapse only)", "lglink" not in fs and "<a " not in fs, fs[:200])

print(f"\nscreenshots: {SHOTS}")
print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
