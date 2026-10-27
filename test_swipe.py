#!/usr/bin/env python3
"""
Swipe with live drag (swipe_view.py, 27 Oct 2026, Amr #3 batch 2) — Playwright with real touch input (CDP Input.dispatchTouchEvent),
ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_swipe.py [frames_dir]
Needs the site built (make_assets, make_site3, make_leagues, make_following, make_search_page, make_notifications, make_matches SAU).
Serves the repo on 127.0.0.1:8787, mocks the live worker. Mid-drag frames go to frames_dir (and frames_dir/pages).

  tabs (match page, league page, Following, Notifications):
    drag 20% -> snaps back · drag 50% -> next tab · fast flick -> next tab · vertical drag scrolls the page (no tab change)
    tab tap still works · RTL: in Arabic the next tab is to the LEFT (drag right) · during the drag the neighbour panel and the
    underline move · no inline styles left after the gesture, container height = the active panel
  pages (bottom nav, only pages with <meta name=sw-page>): drag past the threshold -> the adjacent nav page (bottom-nav order, mirrored
    in RTL) with the slide direction recorded for the View Transition; below the threshold -> back, preview removed; at a tab set's
    edge the page swipe takes over; inner pages (league detail) never page-swipe
"""
import functools
import http.server
import json
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "swipe"
(OUT / "pages").mkdir(parents=True, exist_ok=True)
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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8787), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8787"
W = 390


class Touch:
    def __init__(self, pg):
        self.pg, self.cdp = pg, pg.context.new_cdp_session(pg)

    def ev(self, kind, pts):
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y} for x, y in pts]})

    def drag(self, x0, y0, dx, dy=0, steps=14, ms=280, release=True, shot=None):
        self.ev("touchStart", [(x0, y0)])
        for i in range(1, steps + 1):
            self.ev("touchMove", [(x0 + dx * i / steps, y0 + dy * i / steps)])
            self.pg.wait_for_timeout(ms / steps)
        if shot:
            self.pg.screenshot(path=str(shot))
        if release:
            self.ev("touchEnd", [])
            self.pg.wait_for_timeout(320)


def ctx_page(br, lang_pre, path, init=""):
    ctx = br.new_context(viewport={"width": W, "height": 844}, has_touch=True, is_mobile=True, service_workers="block")
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbLeaguesV2','1');" + init + "}catch(e){}")
    ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*",
                                                                                                    "Content-Type": "application/json"}, body='{"t":0,"m":{}}'))
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"{BASE}{lang_pre}/{path}", wait_until="load")
    pg.wait_for_timeout(400)
    return ctx, pg, errs


def active(pg, sel, on):
    return pg.evaluate(f"()=>[...document.querySelectorAll('{sel}')].findIndex(b=>b.classList.contains('{on}'))")


def leftovers(pg, panels):
    return pg.evaluate(f"()=>[...document.querySelectorAll('{panels}')].filter(p=>p.style.transform||p.style.position==='absolute').length"
                       "+document.querySelectorAll('.swind,.swpv').length")


TAB_SETS = [   # (page, tab selector, active class, panel selector) — the drag starts inside the active panel's visible box
    ("matches/1603069.html", ".mtabs .mtab", "on", ".mp"),
    ("leagues/sau.html", ".cattabs .tab", "active", ".panel"),
    ("notifications.html?push=1", ".ntab", "on", ".nview"),
]


def panel_y(pg, psel):
    """a y inside the active panel and inside the viewport (below any sticky header)"""
    return pg.evaluate(f"""()=>{{const a=[...document.querySelectorAll('{psel}')].find(p=>getComputedStyle(p).display!=='none'&&!p.hidden);
        const r=a.getBoundingClientRect(); const st=[...document.querySelectorAll('.lstick')].map(x=>x.getBoundingClientRect().bottom); const top=Math.max(r.top,0,...st)+12, bot=Math.min(r.bottom,innerHeight-90)-12;
        return Math.round(top+Math.max(0,Math.min(60,(bot-top)/2)));}}""")

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        fwd = 1 if lang == "en" else -1   # finger direction toward the NEXT tab: left in en (dx<0), right in ar (dx>0)
        for page, tsel, on, psel in TAB_SETS:
            tag = f"{lang} {page.split('/')[0].split('.')[0]}"
            ctx, pg, errs = ctx_page(br, pre, page)
            T = Touch(pg)
            n = pg.locator(tsel).count()
            a0 = active(pg, tsel, on)
            x0 = W / 2 + fwd * 120   # start on the side we drag away from
            y = panel_y(pg, psel)
            T.drag(x0, y, -fwd * W * 0.2)
            check(f"{tag}: drag 20% -> snaps back (tab {a0})", active(pg, tsel, on) == a0 and leftovers(pg, psel) == 0, [active(pg, tsel, on), a0])
            mid = pg.evaluate("()=>0")
            T.drag(x0, y, -fwd * W * 0.5, release=False, shot=OUT / f"{tag.replace(' ', '_')}_mid_drag.png")
            mid = pg.evaluate(f"""()=>{{const ps=[...document.querySelectorAll('{psel}')].filter(p=>getComputedStyle(p).display!=='none');
                return {{shown:ps.length, moved:ps.filter(p=>p.style.transform).length, ind:!!document.querySelector('.swind')}};}}""")
            check(f"{tag}: mid-drag: current + neighbour panels shown and moving", mid["shown"] == 2 and mid["moved"] == 2, mid)
            if page.startswith(("matches", "leagues")):
                check(f"{tag}: mid-drag: the tab underline follows the finger", mid["ind"], mid)
            T.ev("touchEnd", []); pg.wait_for_timeout(350)
            a1 = active(pg, tsel, on)
            check(f"{tag}: drag 50% -> next tab ({a0} -> {a0 + 1})", a1 == a0 + 1 and leftovers(pg, psel) == 0, [a0, a1])
            # flick back toward the previous tab: 90px (under the 30% distance threshold) in 3 back-to-back moves (no waits)
            y = panel_y(pg, psel)
            T.drag(W / 2 - fwd * 60, y, fwd * 90, steps=3, ms=0)
            check(f"{tag}: fast flick -> previous tab", active(pg, tsel, on) == a0, active(pg, tsel, on))
            # vertical drag inside the panel scrolls the page (when it can scroll), tab unchanged
            pg.evaluate("()=>window.scrollTo(0,0)"); pg.wait_for_timeout(100)
            y0 = pg.evaluate("()=>window.scrollY")
            can = pg.evaluate("()=>document.documentElement.scrollHeight-innerHeight>200")
            T.drag(W / 2, panel_y(pg, psel) + 200, 6, dy=-300, steps=10, ms=200)
            pg.wait_for_timeout(300)
            y1 = pg.evaluate("()=>window.scrollY")
            check(f"{tag}: vertical drag {'scrolls' if can else 'is left to the browser'} (no tab change, no hijack)",
                  (y1 > y0 + 50 or not can) and active(pg, tsel, on) == a0 and leftovers(pg, psel) == 0, [y0, y1, can])
            pg.evaluate("()=>window.scrollTo(0,0)")
            # tab tap still works
            last = n - 1
            pg.locator(tsel).nth(last).click(); pg.wait_for_timeout(200)
            check(f"{tag}: tab tap still switches (-> {last})", active(pg, tsel, on) == last)
            # container height = active panel (no huge blank): the active panel's parent is not taller than its content
            gap = pg.evaluate(f"""()=>{{const a=[...document.querySelectorAll('{psel}')].find(p=>getComputedStyle(p).display!=='none'); const w=a.parentNode;
                const kids=[...w.children].filter(c=>getComputedStyle(c).display!=='none'&&getComputedStyle(c).position!=='absolute');
                const bottom=Math.max(...kids.map(c=>c.getBoundingClientRect().bottom)); return Math.round(w.getBoundingClientRect().bottom-bottom);}}""")
            check(f"{tag}: container height follows the active panel (no blank below)", abs(gap) < 40, gap)
            # inner pages never page-swipe: at the last tab, dragging further does nothing
            if page.startswith(("matches", "leagues")):
                url = pg.url
                T.drag(x0, panel_y(pg, psel), -fwd * W * 0.6)
                check(f"{tag}: last tab + drag on an inner page -> stays (no page swipe)", pg.url == url and active(pg, tsel, on) == last
                      and leftovers(pg, psel) == 0)
            check(f"{tag}: no page errors", not errs, errs)
            ctx.close()

        # ---- Following: tabs, then the page swipe at the first tab
        ctx, pg, errs = ctx_page(br, pre, "following.html", "localStorage.setItem('fbLeagues','[\"SAU\"]');")
        T = Touch(pg)
        x0 = W / 2 + fwd * 120
        y = panel_y(pg, ".fview")
        T.drag(x0, y, -fwd * W * 0.5)
        check(f"{lang} following: drag 50% -> Leagues tab", active(pg, ".ftab", "active") == 1, active(pg, ".ftab", "active"))
        T.drag(W / 2 - fwd * 120, panel_y(pg, ".fview"), fwd * W * 0.5)
        check(f"{lang} following: back to Teams", active(pg, ".ftab", "active") == 0)
        # at the first tab, dragging toward the previous one = page swipe to Leagues (previous in nav order)
        T.drag(W / 2 - fwd * 120, panel_y(pg, ".fview"), fwd * W * 0.35, release=False, shot=OUT / "pages" / f"{lang}_following_to_leagues_mid.png")
        pv = pg.evaluate("()=>{const v=document.querySelector('.swpv');return v?{t:v.querySelector('.swh').textContent,x:v.style.transform}:null}")
        check(f"{lang} following: first tab edge -> page swipe preview of Leagues", pv and pv["t"] == ("الدوريات" if lang == "ar" else "Leagues"), pv)
        T.ev("touchEnd", []); pg.wait_for_timeout(1200)
        check(f"{lang} following: release past threshold -> leagues.html, slide direction recorded",
              pg.url.endswith("leagues.html") and pg.evaluate("()=>document.documentElement.className").find("vt-") >= 0,
              [pg.url, pg.evaluate("()=>document.documentElement.className")])
        ctx.close()

        # ---- page swipe from Leagues (root): below threshold snaps back, past threshold -> Following (next)
        ctx, pg, errs = ctx_page(br, pre, "leagues.html")
        T = Touch(pg)
        x0 = W / 2 + fwd * 120
        T.drag(x0, 300, -fwd * W * 0.2)
        st = pg.evaluate("()=>({pv:document.querySelectorAll('.swpv').length, tf:document.querySelector('.wrap').style.transform, on:[...document.querySelectorAll('.nav a')].findIndex(a=>a.classList.contains('on'))})")
        check(f"{lang} leagues.html: page drag 20% -> snaps back (preview removed, nav unchanged)", st["pv"] == 0 and not st["tf"] and st["on"] == 1 and pg.url.endswith("leagues.html"), st)
        T.drag(x0, 300, -fwd * W * 0.6, release=False, shot=OUT / "pages" / f"{lang}_leagues_to_following_mid.png")
        mid = pg.evaluate("()=>({on:[...document.querySelectorAll('.nav a')].findIndex(a=>a.classList.contains('on')), pv:!!document.querySelector('.swpv')})")
        check(f"{lang} leagues.html: past the middle the bottom nav highlights the target (Following)", mid["on"] == 2 and mid["pv"], mid)
        T.ev("touchEnd", []); pg.wait_for_timeout(1200)
        check(f"{lang} leagues.html: release -> following.html", pg.url.endswith("following.html"), pg.url)
        # back: bfcache/back restores a clean page
        pg.go_back(); pg.wait_for_timeout(800)
        st = pg.evaluate("()=>({pv:document.querySelectorAll('.swpv').length, tf:document.querySelector('.wrap').style.transform, on:[...document.querySelectorAll('.nav a')].findIndex(a=>a.classList.contains('on'))})")
        check(f"{lang} back -> leagues.html clean (no preview, no transform, nav on Leagues)", pg.url.endswith("leagues.html") and st == {"pv": 0, "tf": "", "on": 1}, st)
        # first nav page edge: Matches has no previous page
        ctx.close()
        ctx, pg, errs = ctx_page(br, pre, "index.html")
        T = Touch(pg)
        T.drag(W / 2 - fwd * 120, 40, fwd * W * 0.6)   # from the top bar, toward the previous page (none)
        check(f"{lang} home: no page before Matches -> stays", pg.url.endswith("index.html") or pg.url.endswith("/"), pg.url)
        T.drag(W / 2 + fwd * 120, 40, -fwd * W * 0.6, release=False, shot=OUT / "pages" / f"{lang}_home_to_leagues_mid.png")
        T.ev("touchEnd", []); pg.wait_for_timeout(1200)
        check(f"{lang} home: drag on the top bar -> Leagues", pg.url.endswith("leagues.html"), pg.url)
        ctx.close()
        # day panels on home keep their own day swipe (no page swipe from there)
        ctx, pg, errs = ctx_page(br, pre, "index.html")
        T = Touch(pg)
        d0 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        T.drag(W / 2 + fwd * 120, 520, -fwd * 200, steps=6, ms=150)
        pg.wait_for_timeout(300)
        d1 = pg.evaluate("()=>(document.querySelector('.daytab.active')||{dataset:{}}).dataset.day")
        check(f"{lang} home: swipe on the day list changes the day (unchanged), no page swipe", pg.url.endswith("index.html") and d1 != d0 and
              pg.evaluate("()=>document.querySelectorAll('.swpv').length") == 0, [d0, d1, pg.url])
        check(f"{lang} home: no page errors", not errs, errs)
        ctx.close()

    # reduced motion: the tab switch happens without a transition
    ctx = br.new_context(viewport={"width": W, "height": 844}, has_touch=True, is_mobile=True, reduced_motion="reduce")
    pg = ctx.new_page(); pg.goto(f"{BASE}/en/matches/1603069.html"); pg.wait_for_timeout(300)
    T = Touch(pg)
    T.ev("touchStart", [(310, 520)])
    for i in range(1, 9):
        T.ev("touchMove", [(310 - 25 * i, 520)]); pg.wait_for_timeout(15)
    T.ev("touchEnd", [])
    trans = pg.evaluate("()=>[...document.querySelectorAll('.mp')].map(p=>p.style.transition).filter(Boolean)")
    pg.wait_for_timeout(60)
    check("reduced motion: no transform animation (transition none) and the switch is immediate", all(t == "none" for t in trans)
          and active(pg, ".mtabs .mtab", "on") == 1, [trans, active(pg, ".mtabs .mtab", "on")])
    ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (frames: {OUT})")
sys.exit(1 if fails else 0)
