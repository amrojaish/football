#!/usr/bin/env python3
"""
League page, batch 3 (30 Oct 2026) — Playwright with real touch input (CDP Input.dispatchTouchEvent), ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_league_page_b3.py
Needs make_assets.py + make_leagues.py (SAU current season with player_stats). Serves the repo on 127.0.0.1:8783, mocks the worker.

  4  header collapse: scrolling down past the header hides it (transform, the tab strip pinned at the top); scrolling up shows it again;
     no layout change (the panel's top position in the document does not move)
  6a the tab strip: touch-action pan-x + overscroll contain (no vertical drag / bounce on the strip)
  6b tapping the last tab (Seasons) leaves it fully inside the strip
  6c/d swipe on the panel: during the drag (before release) the strip already scrolls towards the target tab; release at ~20% snaps
     back (same tab, strip back), release at ~40% moves to the next tab, a fast short flick also moves; RTL mirrored
  5  Player Stats: SAU shows the 3 cards (Top scorers 4 rows, Assists 5, Goals + Assists 5), each header links to its list page, the
     list page lists every player with rank/club/value; a league without player_stats (JOR) keeps the goals list and has no cards
  3  Matches rows: logo ~32px and name ~17px at 390px; nothing overflows its row at 360px
  2  league bell on: no "Alerts are on…" status line
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
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:500]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8783), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8783"


class Touch:
    def __init__(self, pg):
        self.pg, self.cdp = pg, pg.context.new_cdp_session(pg)

    def ev(self, kind, pts):
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y} for x, y in pts]})

    def drag(self, x0, y0, dx, steps=14, ms=280, release=True):
        self.ev("touchStart", [(x0, y0)])
        for i in range(1, steps + 1):
            self.ev("touchMove", [(x0 + dx * i / steps, y0)])
            self.pg.wait_for_timeout(ms / steps)
        if release:
            self.ev("touchEnd", [])
            self.pg.wait_for_timeout(400)


def page(br, url, w=390, touch=True, init=""):
    ctx = br.new_context(viewport={"width": w, "height": 844}, has_touch=touch, is_mobile=touch, service_workers="block")
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');" + init + "}catch(e){}")
    ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(
        status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body='{"t":0,"m":{}}'))
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + url, wait_until="load")
    pg.wait_for_timeout(500)
    return ctx, pg, errs


def active(pg):
    return pg.evaluate("()=>document.querySelector('.cattabs .tab.active').dataset.cat")


def strip(pg):
    return pg.evaluate("()=>document.querySelector('.cattabs').scrollLeft")


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        rtl = lang == "ar"
        # ── 4: header collapse ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html", touch=False)
        pg.click('.cattabs .tab[data-cat="matches"]'); pg.wait_for_timeout(500)
        top0 = pg.evaluate("()=>Math.round(document.querySelector('.panel.visible').getBoundingClientRect().top + scrollY)")
        pg.mouse.wheel(0, 700); pg.wait_for_timeout(600)
        st = pg.evaluate("""()=>{const s=document.querySelector('.lstick'),b=s.querySelector('.cattabs'),h=s.querySelector('.lhead').getBoundingClientRect();
            return {hid:s.classList.contains('hid'), tabsTop:Math.round(b.getBoundingClientRect().top), headBottom:Math.round(h.bottom),
                    lhh:getComputedStyle(s).getPropertyValue('--lhh'), panelTop:Math.round(document.querySelector('.panel.visible').getBoundingClientRect().top + scrollY)}}""")
        check(f"{lang} 4: scrolling down hides the header (header above the screen), the tab strip stays at the top (0px), no layout jump",
              st["hid"] and st["tabsTop"] == 0 and st["headBottom"] <= 0 and st["panelTop"] == top0, st)
        pg.mouse.wheel(0, -150); pg.wait_for_timeout(600)
        st2 = pg.evaluate("()=>({hid:document.querySelector('.lstick').classList.contains('hid'), headTop:Math.round(document.querySelector('.lhead').getBoundingClientRect().top)})")
        check(f"{lang} 4: scrolling up brings the header back", not st2["hid"] and st2["headTop"] >= 0, st2)
        for cat in ("standings", "player-stats", "seasons"):
            pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(200)
            pg.click(f'.cattabs .tab[data-cat="{cat}"]'); pg.wait_for_timeout(300)
            pg.mouse.wheel(0, 500); pg.wait_for_timeout(500)
            ok = pg.evaluate("()=>{const s=document.querySelector('.lstick');return !s.classList.contains('hid') || Math.round(s.querySelector('.cattabs').getBoundingClientRect().top)===0}")
            check(f"{lang} 4: tab «{cat}»: the strip is pinned at the top when the header hides", ok)
        check(f"{lang} 4: no page errors", not errs, errs)
        ctx.close()

        # ── 6a / 6b ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        css = pg.evaluate("()=>{const c=getComputedStyle(document.querySelector('.cattabs'));return [c.touchAction, c.overscrollBehaviorY, c.overscrollBehaviorX]}")
        check(f"{lang} 6a: strip touch-action pan-x, overscroll contained", css[0] == "pan-x" and css[1] == "contain", css)
        pg.click('.cattabs .tab[data-cat="seasons"]'); pg.wait_for_timeout(600)
        vis = pg.evaluate("""()=>{const b=document.querySelector('.cattabs').getBoundingClientRect(),t=document.querySelector('.cattabs .tab[data-cat="seasons"]').getBoundingClientRect();
            return [Math.round(t.left - b.left), Math.round(b.right - t.right)]}""")
        check(f"{lang} 6b: Seasons tab fully visible inside the strip after it becomes active", vis[0] >= -1 and vis[1] >= -1, vis)
        ctx.close()

        # ── 6c/d: swipe; the strip follows during the drag ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        tc = Touch(pg)
        nxt = 1 if rtl else -1          # finger direction for the NEXT tab (RTL mirrored)
        pg.click('.cattabs .tab[data-cat="player-stats"]'); pg.wait_for_timeout(400)
        pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(200)
        tc.drag(195, 600, nxt * 150)                       # ~38% of 390
        check(f"{lang} 6c: release at ~38% -> next tab (team-stats)", active(pg) == "team-stats", active(pg))
        # the strip back at its start: Seasons is cut off at the far edge -> the drag towards it must scroll the strip DURING the drag
        pg.evaluate("()=>{const b=document.querySelector('.cattabs');b.style.scrollBehavior='auto';b.scrollLeft=0;b.style.scrollBehavior='';}")
        cut = pg.evaluate("""()=>{const b=document.querySelector('.cattabs').getBoundingClientRect(),t=document.querySelector('.cattabs .tab[data-cat="seasons"]').getBoundingClientRect();
            return t.left<b.left-1||t.right>b.right+1}""")
        s0 = strip(pg)
        tc.drag(195, 600, nxt * 150, release=False)        # held
        mid = strip(pg)
        tc.ev("touchEnd", []); pg.wait_for_timeout(500)
        check(f"{lang} 6d: Seasons cut off at the start ({cut}); during the drag (before release) the strip scrolls towards it "
              f"(scrollLeft {s0} -> {mid})", cut and mid != s0, [cut, s0, mid])
        check(f"{lang} 6c: -> Seasons", active(pg) == "seasons", active(pg))
        vis = pg.evaluate("""()=>{const b=document.querySelector('.cattabs').getBoundingClientRect(),t=document.querySelector('.cattabs .tab.active').getBoundingClientRect();
            return [Math.round(t.left - b.left), Math.round(b.right - t.right)]}""")
        check(f"{lang} 6b: after the swipe the active tab (Seasons) is fully visible", vis[0] >= -1 and vis[1] >= -1, vis)
        s1 = strip(pg)
        tc.drag(195, 600, -nxt * 75)                       # ~19% back
        pg.wait_for_timeout(300)
        check(f"{lang} 6c: release at ~19% -> snaps back (stays on Seasons), strip back where it was",
              active(pg) == "seasons" and abs(strip(pg) - s1) <= 2, [active(pg), s1, strip(pg)])
        tc.drag(195 + nxt * 60, 600, -nxt * 90, steps=3, ms=0)   # fast short flick back (same method as test_swipe)
        check(f"{lang} 6c: fast short flick -> previous tab (team-stats)", active(pg) == "team-stats", active(pg))
        check(f"{lang} 6: no page errors", not errs, errs)
        ctx.close()

        # ── 5: player stats cards + list pages ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html", touch=False)
        pg.click('.cattabs .tab[data-cat="player-stats"]'); pg.wait_for_timeout(300)
        cards = pg.evaluate("""()=>[...document.querySelectorAll('.panel[data-cat="player-stats"] .pscard')].map(c=>
            [c.dataset.stat, c.querySelectorAll('.psr').length, c.querySelector('.psh').getAttribute('href'), c.querySelectorAll('.psr img').length])""")
        check(f"{lang} 5: SAU: 3 cards (goals 4 rows, assists 5, G+A 5), club logos, header links to the list pages",
              [x[0] for x in cards] == ["goals", "assists", "ga"] and [x[1] for x in cards] == [4, 5, 5]
              and [x[2] for x in cards] == ["sau-goals.html", "sau-assists.html", "sau-ga.html"] and all(x[3] == x[1] for x in cards), cards)
        check(f"{lang} 5: SAU: the old long scorers list is replaced by the cards", pg.locator('.panel[data-cat="player-stats"] ol').count() == 0)
        check(f"{lang} 5: layer-2 cards (rating/saves/key passes) still below", pg.locator('.panel[data-cat="player-stats"] .lcard').count() >= 1)
        pg.click('.pscard[data-stat="ga"] .psh'); pg.wait_for_load_state("load"); pg.wait_for_timeout(300)
        lst = pg.evaluate("""()=>({url:location.pathname, rows:document.querySelectorAll('.psr').length, ranks:[...document.querySelectorAll('.psr .rk')].slice(0,3).map(x=>x.textContent),
            vals:[...document.querySelectorAll('.psr .pv')].map(x=>+x.textContent), links:document.querySelectorAll('.psr .pn a').length, robots:(document.querySelector('meta[name=robots]')||{}).content})""")
        check(f"{lang} 5: G+A list page: {lst['rows']} players ranked, values never go up, linked names, noindex",
              lst["url"].endswith("/sau-ga.html") and lst["rows"] > 20 and lst["ranks"][0] == "1"
              and all(a >= b for a, b in zip(lst["vals"], lst["vals"][1:])) and lst["links"] > 0 and lst["robots"] == "noindex",
              {k: v for k, v in lst.items() if k != "vals"})
        ctx.close()
        ctx, pg, errs = page(br, f"{pre}/leagues/jor.html", touch=False)
        pg.click('.cattabs .tab[data-cat="player-stats"]'); pg.wait_for_timeout(300)
        check(f"{lang} 5: JOR (no player_stats): no cards, the goals list stays",
              pg.locator(".pscard").count() == 0 and pg.locator('.panel[data-cat="player-stats"] ol li').count() > 0)
        ctx.close()

        # ── 3: match rows ──
        for w in (390, 360):
            ctx, pg, errs = page(br, f"{pre}/leagues/sau.html", w=w, touch=False)
            pg.click('.cattabs .tab[data-cat="matches"]'); pg.wait_for_timeout(500)
            m = pg.evaluate("""()=>{const rows=[...document.querySelectorAll('.mdays .mday:not(.hidden) .match')].filter(r=>r.getBoundingClientRect().height>0);
                const s=rows[0].querySelector('.side span'), i=rows[0].querySelector('.side img');
                const bad=rows.filter(r=>{const cr=r.getBoundingClientRect();return [...r.querySelectorAll('.side span,.side img,.score')].some(e=>{const x=e.getBoundingClientRect();return x.left<cr.left-0.5||x.right>cr.right+0.5;})}).length;
                return {fs:parseFloat(getComputedStyle(s).fontSize), img:Math.round(parseFloat(getComputedStyle(i).width)), n:rows.length, bad,
                        hscroll:document.documentElement.scrollWidth>document.documentElement.clientWidth}}""")
            want = (16.5, 32) if w == 390 else (15.5, 29)
            check(f"{lang} 3 @{w}px: name {m['fs']}px, logo {m['img']}px, {m['n']} rows, none overflows, no horizontal scroll",
                  m["fs"] >= want[0] and m["img"] >= want[1] and m["bad"] == 0 and not m["hscroll"], m)
            ctx.close()

        # ── 2: no "alerts on" line ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html?push=1", touch=False, init="")
        pg.add_init_script("")
        line = pg.evaluate("()=>{const m=document.getElementById('pushmsg');return m?[m.hidden,m.textContent]:null}")
        check(f"{lang} 2: league page loads with no status line under the bell", line is None or line[0] or not line[1].strip(), line)
        ctx.close()
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
