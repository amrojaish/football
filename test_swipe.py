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
  home day tabs (28 Oct 2026, batch C): the day panel follows the finger, underline follows; 20% -> back; 50% -> next day; flick ->
    previous; vertical drag scrolls (same day); RTL mirrored (next day = drag right in Arabic)
  bottom-nav PAGE swipe is REMOVED (batch C): dragging on Leagues / at the Following first-tab edge / on the home top bar stays on the
    page (no preview, nav unchanged)
  horizontally scrollable table (player stats .stw): the drag scrolls the table, the tab stays
  reduced motion: no transition; on home no panel follows the finger and the day switches instantly on release
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

        # ---- Following: tabs; at the first tab's edge nothing happens (no page swipe any more)
        ctx, pg, errs = ctx_page(br, pre, "following.html", "localStorage.setItem('fbLeagues','[\"SAU\"]');")
        T = Touch(pg)
        x0 = W / 2 + fwd * 120
        y = panel_y(pg, ".fview")
        T.drag(x0, y, -fwd * W * 0.5)
        check(f"{lang} following: drag 50% -> Leagues tab", active(pg, ".ftab", "active") == 1, active(pg, ".ftab", "active"))
        T.drag(W / 2 - fwd * 120, panel_y(pg, ".fview"), fwd * W * 0.5)
        check(f"{lang} following: back to Teams", active(pg, ".ftab", "active") == 0)
        T.drag(W / 2 - fwd * 120, panel_y(pg, ".fview"), fwd * W * 0.6)
        pg.wait_for_timeout(600)
        check(f"{lang} following: first tab + drag toward 'previous' -> stays (no page swipe, no preview)",
              pg.url.endswith("following.html") and active(pg, ".ftab", "active") == 0 and pg.locator(".swpv").count() == 0, pg.url)
        check(f"{lang} following: no page errors", not errs, errs)
        ctx.close()

        # ---- bottom-nav page swipe is gone: Leagues (root page) and the home top bar stay put
        ctx, pg, errs = ctx_page(br, pre, "leagues.html")
        T = Touch(pg)
        for k in (-1, 1):
            T.drag(W / 2 + k * fwd * 120, 300, -k * fwd * W * 0.6)
            pg.wait_for_timeout(600)
        st = pg.evaluate("()=>({pv:document.querySelectorAll('.swpv').length, tf:document.querySelector('.wrap').style.transform, on:[...document.querySelectorAll('.nav a')].findIndex(a=>a.classList.contains('on'))})")
        check(f"{lang} leagues.html: 60% drags both ways -> stays (no page swipe, no preview, nav on Leagues)",
              pg.url.endswith("leagues.html") and st == {"pv": 0, "tf": "", "on": 1}, [pg.url, st])
        check(f"{lang} leagues.html: no sw-page meta / view-transition head any more", pg.locator('meta[name="sw-page"]').count() == 0)
        ctx.close()
        ctx, pg, errs = ctx_page(br, pre, "index.html")
        T = Touch(pg)
        T.drag(W / 2 + fwd * 120, 40, -fwd * W * 0.6)   # top bar, toward the next nav page (Leagues)
        pg.wait_for_timeout(600)
        check(f"{lang} home: drag on the top bar -> stays (no page swipe)", pg.url.endswith("index.html") or pg.url.endswith("/"), pg.url)
        ctx.close()

        # ---- home day tabs: finger-following swipe
        ctx, pg, errs = ctx_page(br, pre, "index.html")
        T = Touch(pg)
        day = lambda: pg.evaluate("()=>[...document.querySelectorAll('.daytab')].findIndex(b=>b.classList.contains('active'))")
        d0 = day()
        y = 520
        T.drag(W / 2 + fwd * 120, y, -fwd * W * 0.2)
        check(f"{lang} home: day drag 20% -> snaps back (same day, nothing left over)", day() == d0 and leftovers(pg, ".daypanel") == 0,
              [day(), d0, leftovers(pg, ".daypanel")])
        T.drag(W / 2 + fwd * 120, y, -fwd * W * 0.4, release=False, shot=OUT / f"{lang}_home_day_mid.png")
        mid = pg.evaluate("""()=>({shown:[...document.querySelectorAll('.daypanel')].filter(p=>getComputedStyle(p).display!=='none').length,
            moved:[...document.querySelectorAll('.daypanel')].filter(p=>p.style.transform).length, ind:!!document.querySelector('.daytabs .swind')})""")
        check(f"{lang} home: mid-drag the current + next day panels move with the finger and the underline follows",
              mid["shown"] == 2 and mid["moved"] == 2 and mid["ind"], mid)
        T.ev("touchEnd", []); pg.wait_for_timeout(400)
        d1 = day()
        check(f"{lang} home: drag 40% (> 25%) -> NEXT day ({d0} -> {d0 + 1}; {'drag right' if lang == 'ar' else 'drag left'})",
              d1 == d0 + 1 and leftovers(pg, ".daypanel") == 0 and pg.url.endswith("index.html"), [d0, d1])
        T.drag(W / 2 - fwd * 120, y, fwd * 90, steps=4, ms=60)   # short fast flick back
        check(f"{lang} home: fast flick -> previous day", day() == d0, [day(), d0])
        sy0 = pg.evaluate("()=>window.scrollY")
        T.drag(W / 2, 600, 8, dy=-260, steps=10, ms=200)
        check(f"{lang} home: vertical drag scrolls the list, the day stays", day() == d0 and pg.evaluate("()=>window.scrollY") >= sy0, day())
        check(f"{lang} home: no page errors", not errs, errs)
        ctx.close()

        # ---- a horizontally scrollable table inside a panel scrolls, the tab stays
        ctx, pg, errs = ctx_page(br, pre, "players/mohamed-hany-2.html")
        T = Touch(pg)
        pg.click('.mtab[data-tab="stats"]'); pg.wait_for_timeout(250)
        pg.locator(".stw").scroll_into_view_if_needed()
        box = pg.locator(".stw").bounding_box()
        t0 = active(pg, ".mtabs .mtab", "on")
        s0 = pg.evaluate("()=>document.querySelector('.stw').scrollLeft")
        T.drag(box["x"] + box["width"] / 2 + fwd * 100, box["y"] + box["height"] / 2, -fwd * 200)
        s1 = pg.evaluate("()=>document.querySelector('.stw').scrollLeft")
        check(f"{lang} player stats table: horizontal drag scrolls the table ({s0} -> {s1}), the Stats tab stays",
              active(pg, ".mtabs .mtab", "on") == t0 and s1 != s0, [t0, active(pg, ".mtabs .mtab", "on"), s0, s1])
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
    # reduced motion on home: no panel follows the finger, the day switches instantly on release
    ctx = br.new_context(viewport={"width": W, "height": 844}, has_touch=True, is_mobile=True, reduced_motion="reduce")
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');}catch(e){}")
    pg = ctx.new_page(); pg.goto(f"{BASE}/en/index.html"); pg.wait_for_timeout(400)
    T = Touch(pg)
    d0 = pg.evaluate("()=>[...document.querySelectorAll('.daytab')].findIndex(b=>b.classList.contains('active'))")
    T.drag(310, 520, -160, release=False)
    moved = pg.evaluate("()=>[...document.querySelectorAll('.daypanel')].filter(p=>p.style.transform).length")
    T.ev("touchEnd", []); pg.wait_for_timeout(30)
    d1 = pg.evaluate("()=>[...document.querySelectorAll('.daytab')].findIndex(b=>b.classList.contains('active'))")
    check("reduced motion (home): no panel moves during the drag, next day right after release (no animation)", moved == 0 and d1 == d0 + 1,
          [moved, d0, d1])
    ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (frames: {OUT})")
sys.exit(1 if fails else 0)
