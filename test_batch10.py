#!/usr/bin/env python3
"""
Batch 10 (9 Nov 2026), site side. Playwright against the built site (make_assets, make_site3, make_leagues, make_cups, make_clubs, make_matches), 390px, ar + en,
live worker mocked. Reads football.db read-only.
  A  vote: a 404 or network error after a tap keeps the card and re-enables the buttons (league + cup); every cup match has a vote row
  B  home: a match still live after local midnight also shows in Today (league section + Following), and leaves Today at FT; fake clock 00:30
  C  live pill: 20px high, at least 30px wide, never touches the name
  D  team form: no team-name lines, 46 x 26 boxes, 14px bold
  E  match page: compact header past the head, tabs stay under it, back to full at the top, no layout change
  F  league + cup pages: compact row (back, name, country, season) above the tabs when scrolled
  G  match rows 24px / 14px on home, league, cup and club pages
  H  ?navdebug=1 overlay, nothing on normal URLs
Run: python C:\\Users\\User\\Projects\\Football\\test_batch10.py
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8791), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8791"
W = "https://saffara-live.abujaishamr.workers.dev"
conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
now_s = time.strftime("%Y-%m-%d %H:%M", time.gmtime())


def built(q, *a):
    for (mid,) in conn.execute(q, a):
        if (ROOT / "matches" / f"{mid}.html").exists():
            return mid
    return None


LEAGUE_UP = built("SELECT match_id FROM matches WHERE league_code IN ('SAU','UAE') AND status='NS' AND date > ? ORDER BY date", now_s)
CUP_UP = built("SELECT match_id FROM matches WHERE league_code IN ('EGY-LC','SAU-KC','CAF-CL','UAE-LC') AND status='NS' AND date > ? ORDER BY date", now_s)
LEAGUE_FT = built("SELECT match_id FROM matches WHERE league_code='SAU' AND status='FT' ORDER BY date DESC")
LIVE = {"body": '{"t":0,"m":{}}'}


def page(br, url, w=390, init="", tz="Asia/Amman", votes=None):
    ctx = br.new_context(viewport={"width": w, "height": 844}, service_workers="block", timezone_id=tz, is_mobile=True, has_touch=True)
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');" + init + "}catch(e){}")
    H = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    def route(r):
        u = r.request.url
        if "/votes" in u:
            return r.fulfill(status=200, headers=H, body=json.dumps({"total": 3, "h": 1, "d": 1, "a": 1}))
        if u.endswith("/vote"):
            if votes and votes.get("abort"):
                return r.abort()
            return r.fulfill(status=(votes or {}).get("status", 404), headers=H, body=(votes or {}).get("body", '{"error":"unknown fixture"}'))
        return r.fulfill(status=200, headers=H, body=LIVE["body"])
    ctx.route(W + "/**", route)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + url, wait_until="load")
    pg.wait_for_timeout(450)
    return ctx, pg, errs


FAKE = """(function(){var T=%d,R=Date;function D(){var a=[].slice.call(arguments);if(!a.length)return new R(T);return new (Function.prototype.bind.apply(R,[null].concat(a)));}
D.now=function(){return T;};D.parse=R.parse;D.UTC=R.UTC;D.prototype=R.prototype;window.Date=D;})();"""

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ── A ──
    import make_kickoffs as MK  # noqa: E402
    k = MK.build(conn, int(time.time()))
    cups_due = [str(r[0]) for r in conn.execute("""SELECT match_id FROM matches WHERE status='NS' AND home_goals IS NULL AND date BETWEEN ? AND ?
        AND league_code IN (SELECT DISTINCT league_code FROM matches WHERE league_code LIKE '%-%')""",
                                                (now_s, time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 13 * 86400))))]
    check(f"A every cup match inside the window has a vote row ({len(cups_due)})", cups_due and all(x in k["v"] for x in cups_due), [x for x in cups_due if x not in k["v"]][:5])
    for label, mid in (("league", LEAGUE_UP), ("cup", CUP_UP)):
        if not mid:
            check(f"A {label}: an upcoming built page exists", False)
            continue
        for how, votes in (("404", {"status": 404}), ("network error", {"abort": True})):
            ctx, pg, errs = page(br, f"/matches/{mid}.html", votes=votes)
            pg.wait_for_selector("#vote:not([hidden]) .vbtns button.vb", timeout=6000)
            pg.locator(".vbtns button.vb").first.click()
            pg.wait_for_timeout(400)
            st = pg.evaluate("()=>({hid:document.getElementById('vote').hidden, dis:[...document.querySelectorAll('.vbtns button')].map(b=>b.disabled), res:document.querySelector('.vres').hidden})")
            check(f"A {label} {how}: card stays, buttons work again", st["hid"] is False and st["dis"] == [False, False, False] and not errs, st)
            ctx.close()
        ctx, pg, errs = page(br, f"/matches/{mid}.html", votes={"status": 200, "body": json.dumps({"total": 4, "h": 2, "d": 1, "a": 1, "choice": "h"})})
        pg.wait_for_selector("#vote:not([hidden]) .vbtns button.vb", timeout=6000)
        pg.locator(".vbtns button.vb").first.click()
        pg.wait_for_timeout(400)
        st = pg.evaluate("()=>({btn:document.querySelector('.vbtns').hidden, res:document.querySelector('.vres').hidden, p:[...document.querySelectorAll('.vres .vp')].map(x=>x.textContent)})")
        check(f"A {label} vote accepted: percentages show", st["btn"] and not st["res"] and st["p"][0] == "50%", st)
        ctx.close()

    # ── B ──
    probe_ctx = br.new_context(service_workers="block", timezone_id="Asia/Amman")
    probe_ctx.route(W + "/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"]))
    pp = probe_ctx.new_page()
    pp.goto(B + "/index.html", wait_until="load")
    pp.wait_for_timeout(300)
    info = pp.evaluate("""()=>{const ps=[...document.querySelectorAll('.daypanel')].map(p=>[p.id.slice(1),p.querySelectorAll('.lgsec:not(.followsec) .match[data-mid]').length]);
      const out=[];for(let i=0;i+1<ps.length;i++){if(ps[i][1]>0){const c=document.querySelector('#d'+ps[i][0]+' .lgsec:not(.followsec) .match[data-mid]');out.push([ps[i][0],ps[i+1][0],c.getAttribute('data-mid'),c.closest('.lgsec').getAttribute('data-sec'),c.dataset.h]);}}return out;}""")
    probe_ctx.close()
    yest, today, mid, sec, home = info[0]
    T = int(time.mktime(time.strptime(today + " 00:30", "%Y-%m-%d %H:%M")) * 1000)
    # the machine's zone is not assumed: express 00:30 in Amman (UTC+3) directly
    T = int(__import__("calendar").timegm(time.strptime(today + " 00:30", "%Y-%m-%d %H:%M")) * 1000 - 3 * 3600 * 1000)
    feed = {"t": 1, "m": {str(mid): {"h": 1, "a": 0, "e": 80, "s": "2H", "th": 1, "ta": 2, "lg": 3}}}
    for lang, pre in (("ar", ""), ("en", "/en")):
        LIVE["body"] = json.dumps(feed)
        ctx, pg, errs = page(br, f"{pre}/index.html", init=FAKE % T + f"localStorage.setItem('fbClubs', JSON.stringify([{home}]));")
        pg.wait_for_timeout(900)
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_timeout(500)
        q = lambda s: pg.evaluate("s=>document.querySelectorAll(s).length", s)  # noqa: E731
        check(f"B {lang}: Today is the active tab at 00:30", pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day") == today)
        check(f"B {lang}: live match copied into Today, inside its league", q(f"#d{today} .lgsec[data-sec='{sec}'] .match[data-carry][data-mid='{mid}']") == 1, q(f"#d{today} .match[data-mid='{mid}']"))
        check(f"B {lang}: followed, so also in Today's Following", q(f"#d{today} .followsec .match[data-mid='{mid}']") == 1, q(f"#d{today} .followsec .match"))
        check(f"B {lang}: it stays in its kickoff day too", q(f"#d{yest} .lgsec:not(.followsec) .match[data-mid='{mid}']") == 1)
        check(f"B {lang}: the copy shows the live score and pill", q(f"#d{today} .match.live[data-mid='{mid}'] .lvpill") >= 1)
        cnt = pg.evaluate("([d,s])=>{const e=document.querySelector('#d'+d+' .lgsec[data-sec=\"'+s+'\"]');return [+e.querySelector('.lgnum').textContent,e.querySelectorAll('.match').length];}", [today, sec])
        check(f"B {lang}: section counter includes it", cnt[0] == cnt[1], cnt)
        LIVE["body"] = '{"t":2,"m":{},"f":{"%s":{"h":1,"a":0,"s":"FT","ft":2}}}' % mid
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_timeout(600)
        check(f"B {lang}: at FT it leaves Today", q(f"#d{today} .match[data-mid='{mid}']") == 0, q(f"#d{today} .match[data-mid='{mid}']"))
        check(f"B {lang}: at FT it stays in its kickoff day", q(f"#d{yest} .lgsec:not(.followsec) .match[data-mid='{mid}']") == 1)
        check(f"B {lang}: no script errors", not errs, errs)
        ctx.close()
    # a match that kicked off today is not copied
    LIVE["body"] = json.dumps(feed)
    Tsame = int(__import__("calendar").timegm(time.strptime(yest + " 23:50", "%Y-%m-%d %H:%M")) * 1000 - 3 * 3600 * 1000)
    ctx, pg, errs = page(br, "/index.html", init=FAKE % Tsame)
    pg.wait_for_timeout(700)
    check("B before midnight: no copy", pg.evaluate("()=>document.querySelectorAll('.match[data-carry]').length") == 0)
    ctx.close()

    # ── C + G home ──
    def pill(pg, sel):
        return pg.evaluate("""(sel)=>{const c=document.querySelector(sel);if(!c)return null;const p=c.querySelector('.lvpill').getBoundingClientRect(),n=c.querySelector('.side span').getBoundingClientRect(),r=document.createRange();
          const rtl=document.documentElement.dir==='rtl';const cs=getComputedStyle(c.querySelector('.lvpill'));
          return {h:Math.round(p.height),w:Math.round(p.width),fs:cs.fontSize,fw:cs.fontWeight,gapOK:rtl?(n.right<=p.left+0.5||p.right<=n.left+0.5):(p.right<=n.left+0.5||n.right<=p.left+0.5),bg:cs.backgroundColor};}""", sel)

    for lang, pre, tz_day in (("ar", "", today), ("en", "/en", today)):
        for s, m_ in (("2H", 80), ("HT", 45)):
            feed2 = {"t": 1, "m": {str(mid): {"h": 1, "a": 0, "e": m_, "s": s, "th": 1, "ta": 2, "lg": 3}}}
            LIVE["body"] = json.dumps(feed2)
            ctx, pg, errs = page(br, f"{pre}/index.html", init=FAKE % Tsame)
            pg.wait_for_timeout(800)
            p = pill(pg, f"#d{yest} .match.live[data-mid='{mid}']")
            check(f"C {lang} {s}: pill 20px high, >=30 wide, 12px bold, clear of the name", p and p["h"] == 20 and p["w"] >= 30 and p["fs"] == "12px" and p["fw"] == "700" and p["gapOK"], p)
            ctx.close()
    LIVE["body"] = '{"t":0,"m":{}}'
    ctx, pg, errs = page(br, "/index.html")
    g = pg.evaluate("()=>{const c=document.querySelector('.daypanel .match'),i=getComputedStyle(c.querySelector('.side img')),s=getComputedStyle(c.querySelector('.side span'));return [i.width,s.fontSize];}")
    check("G home rows 24px / 14px", g == ["24px", "14px"], g)
    ctx.close()

    # ── D, E ──
    if LEAGUE_FT:
        for lang, pre in (("ar", ""), ("en", "/en")):
            ctx, pg, errs = page(br, f"{pre}/matches/{LEAGUE_FT}.html")
            d = pg.evaluate("()=>{const b=document.querySelector('.tfp');if(!b)return null;const r=b.getBoundingClientRect(),s=getComputedStyle(b);return {w:Math.round(r.width),h:Math.round(r.height),fs:s.fontSize,fw:s.fontWeight,rad:s.borderRadius,names:document.querySelectorAll('.tfh').length};}")
            check(f"D {lang}: no team-name lines, 46x26 boxes, 14px bold, radius 6", d and d["names"] == 0 and d["w"] == 46 and d["h"] == 26 and d["fs"] == "14px" and d["fw"] == "700" and d["rad"] == "6px", d)
            big = pg.evaluate("()=>document.querySelector('.big .score').textContent.trim()")
            h0 = pg.evaluate("()=>document.documentElement.scrollHeight")
            s0 = pg.evaluate("()=>{const m=getComputedStyle(document.getElementById('mch'));return [m.opacity,document.getElementById('mch').classList.contains('on')];}")
            check(f"E {lang}: compact header hidden at the top", s0 == ["0", False], s0)
            pg.evaluate("window.scrollTo(0,500)")
            pg.wait_for_timeout(450)
            s1 = pg.evaluate("""()=>{const m=document.getElementById('mch'),r=m.getBoundingClientRect(),t=document.querySelector('.mtabs').getBoundingClientRect();
              return {on:m.classList.contains('on'),op:getComputedStyle(m).opacity,top:Math.round(r.top),h:Math.round(r.height),tabs:Math.round(t.top),logos:m.querySelectorAll('.mchm img').length,txt:m.querySelector('.mchs').textContent,back:!!m.querySelector('.mchb'),sh:document.documentElement.scrollHeight};}""")
            check(f"E {lang}: scrolled: compact header at the top with back, two logos, the score", s1["on"] and s1["op"] == "1" and s1["top"] == 0 and s1["logos"] == 2 and s1["txt"] == big and s1["back"], s1)
            check(f"E {lang}: tabs stay right under it", abs(s1["tabs"] - s1["h"]) <= 1, s1)
            check(f"E {lang}: no layout jump", s1["sh"] == h0, [s1["sh"], h0])
            pg.evaluate("window.scrollTo(0,0)")
            pg.wait_for_timeout(450)
            check(f"E {lang}: top again = full header", pg.evaluate("()=>[getComputedStyle(document.getElementById('mch')).opacity,document.querySelector('.head').getBoundingClientRect().top>0]") == ["0", True])
            check(f"E {lang}: no script errors", not errs, errs)
            ctx.close()
        fx = LEAGUE_FT
        LIVE["body"] = json.dumps({"t": 1, "m": {str(LEAGUE_UP): {"h": 2, "a": 1, "e": 55, "s": "2H", "th": 1, "ta": 2, "lg": 3}}})
        ctx, pg, errs = page(br, f"/matches/{LEAGUE_UP}.html")
        pg.wait_for_timeout(500)
        pg.evaluate("window.scrollTo(0,500)")
        pg.wait_for_timeout(450)
        st = pg.evaluate("()=>{const s=document.querySelector('#mch .mchs');return [s.textContent,s.classList.contains('lv')];}")
        check("E live: compact header shows the live score", st[1] and "2" in st[0] and "1" in st[0], st)
        ctx.close()
        LIVE["body"] = '{"t":0,"m":{}}'

    # ── F, G pages ──
    def lpage(url, name_hint, want_season):
        ctx, pg, errs = page(br, url)
        pg.evaluate("(document.querySelector('.cattabs .tab[data-cat=\"matches\"]')||{click(){}}).click()")
        pg.wait_for_timeout(500)
        pg.evaluate("window.scrollBy(0,300)")   # downwards from wherever the Matches anchor landed
        pg.wait_for_timeout(600)
        s = pg.evaluate("""()=>{const st=document.querySelector('.lstick'),c=st.querySelector('.lcomp'),t=st.querySelector('.cattabs').getBoundingClientRect(),r=c.getBoundingClientRect();
          return {hid:st.classList.contains('hid'),op:getComputedStyle(c).opacity,top:Math.round(r.top),bot:Math.round(r.bottom),tabs:Math.round(t.top),name:c.querySelector('b').textContent,pill:(c.querySelector('.lcpill')||{}).textContent||'',back:!!c.querySelector('.lcback'),h1:Math.round(document.querySelector('.lhead h1').getBoundingClientRect().bottom)};}""")
        check(f"F {url}: compact row visible at the very top, tabs right under it", s["hid"] and s["op"] == "1" and s["top"] == 0 and s["tabs"] == s["bot"] and s["back"], s)
        check(f"F {url}: name + season, big header gone", s["name"] and (not want_season or s["pill"]) and s["h1"] <= s["bot"], s)
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(500)
        check(f"F {url}: top again = full header", pg.evaluate("()=>[document.querySelector('.lstick').classList.contains('hid'),getComputedStyle(document.querySelector('.lcomp')).opacity]") == [False, "0"])
        check(f"F {url}: no script errors", not errs, errs)
        ctx.close()

    for u in ("/leagues/sau.html", "/en/leagues/sau.html"):
        lpage(u, "", True)
    for u in ("/leagues/caf-cl.html", "/en/leagues/caf-cl.html"):
        lpage(u, "", True)

    def row_size(url, sel):
        ctx, pg, errs = page(br, url)
        v = pg.evaluate("""(sel)=>{const c=document.querySelector(sel);if(!c)return null;const i=getComputedStyle(c.querySelector('.side img')),s=getComputedStyle(c.querySelector('.side span'));return [i.width,s.fontSize];}""", sel)
        ctx.close()
        return v

    for label, url, sel in (("league", "/leagues/sau.html", ".mdays .match"), ("cup", "/leagues/caf-cl.html", ".mdays .match"), ("club", "/clubs/2932.html", ".mlist .match")):
        v = row_size(url, sel)
        check(f"G {label} rows 24px / 14px", v == ["24px", "14px"], v)

    # ── H ──
    ctx, pg, errs = page(br, "/index.html?navdebug=1")
    t = pg.evaluate("()=>{const d=document.getElementById('navdebug');return d?d.textContent:'';}")
    for key in ("innerHeight:", "visualViewport.height:", "visualViewport.offsetTop:", "documentElement.clientHeight:", "screen.height:", "nav top:", "nav bottom:", "env(safe-area-inset-top):", "env(safe-area-inset-bottom):", "standalone: no", "gap (innerHeight - nav bottom):", "updated:"):
        check(f"H overlay shows {key}", key in t, t)
    pg.evaluate("window.dispatchEvent(new Event('scroll'))")
    pg.wait_for_timeout(200)
    check("H overlay refreshes on scroll", pg.evaluate("()=>document.getElementById('navdebug').textContent.split('\\n')[0]") == "event: scroll", pg.evaluate("()=>document.getElementById('navdebug').textContent.split('\\n')[0]"))
    check("H overlay cannot be tapped", pg.evaluate("()=>getComputedStyle(document.getElementById('navdebug')).pointerEvents") == "none")
    check("H overlay shows nudge skipped in a browser tab", "nudge: skipped (not standalone), innerHeight " in t, t)
    check("H browser tab: v1 navfix gone (no --navfix, no navfix class, no rule), nav/html/body not transformed",
          pg.evaluate("""()=>{const h=document.documentElement,css=[...document.styleSheets].map(s=>{try{return [...s.cssRules].map(r=>r.cssText).join(' ')}catch(e){return ''}}).join(' ');
            return !h.style.getPropertyValue('--navfix')&&!h.classList.contains('navfix')&&!css.includes('navfix')
              &&[h,document.body,document.querySelector('.nav')].every(e=>getComputedStyle(e).transform==='none')}"""))
    ctx.close()
    # (11 نوفمبر 2026) سطر push id: بلا service worker = none؛ باشتراك مُحاكى = … + آخر 16 حرفاً من endpoint
    pidline = "()=>{const m=/push id: (.*)/.exec(document.getElementById('navdebug').textContent);return m&&m[1];}"
    ctx, pg, errs = page(br, "/index.html?navdebug=1")
    check("H push id: none without a service worker / subscription", pg.evaluate(pidline) == "none" and not errs, [pg.evaluate(pidline), errs])
    ctx.close()
    EP = "https://web.push.apple.com/QAbcdefTEST0123456789suffixXYZ_9876543210ab"
    SWM = ("const sub={endpoint:'%s'};const reg={pushManager:{getSubscription:()=>Promise.resolve(sub)}};"
           "Object.defineProperty(navigator,'serviceWorker',{get:()=>({getRegistration:()=>Promise.resolve(reg),ready:Promise.resolve(reg),"
           "register:()=>Promise.resolve(reg),addEventListener(){},controller:null})});")
    for u in ("/index.html?navdebug=1", f"/matches/{LEAGUE_FT}.html?navdebug=1"):
        ctx, pg, errs = page(br, u, init=SWM % EP)
        pg.wait_for_timeout(200)
        got = pg.evaluate(pidline)
        check(f"H push id {u.split('?')[0]}: last 16 chars of the endpoint", got == "…" + EP[-16:] and not errs, [got, errs])
        ctx.close()
    ctx, pg, errs = page(br, "/index.html?navdebug=1", init="const reg={pushManager:{getSubscription:()=>Promise.resolve(null)}};"
                         "Object.defineProperty(navigator,'serviceWorker',{get:()=>({getRegistration:()=>Promise.resolve(reg),ready:Promise.resolve(reg),register:()=>Promise.resolve(reg),addEventListener(){},controller:null})});")
    check("H push id: registered worker without a subscription -> none", pg.evaluate(pidline) == "none" and not errs, [pg.evaluate(pidline), errs])
    ctx.close()
    # (11 نوفمبر 2026، الإصلاح 2) iOS المثبَّت مُحاكى (screen 852، innerHeight 793، safe-area-top 59): سطر nudge بلوحة القياس
    NDM = ("window.__ih=%d;Object.defineProperty(window,'innerHeight',{get:()=>window.__ih,configurable:true});"
           "Object.defineProperty(screen,'height',{get:()=>852});Object.defineProperty(screen,'width',{get:()=>393});"
           "Object.defineProperty(screen,'orientation',{get:()=>({type:'portrait-primary',addEventListener(){}})});"
           "Object.defineProperty(navigator,'standalone',{get:()=>%s});const so=window.scrollTo.bind(window);window.scrollTo=function(x,y){window.__ih=852;return so(x,y);};"
           "const s=new CSSStyleSheet();s.replaceSync('#nudgeprobe{padding-top:%dpx !important}');document.adoptedStyleSheets=[s];%s")
    ndline = "()=>{const m=/nudge: (.*)/.exec(document.getElementById('navdebug').textContent);return m&&m[1];}"
    for label, args, want in (("852/793/59", (793, "true", 59, ""), "done, innerHeight 793 -> 852"),
                              ("852/852", (852, "true", 59, ""), "skipped (deficit 0, safe-top 59), innerHeight 852"),
                              ("not standalone", (793, "false", 59, ""), "skipped (not standalone), innerHeight 793"),
                              ("deficit != safe-top", (793, "true", 40, ""), "skipped (deficit 59, safe-top 40), innerHeight 793"),
                              ("scrollY 120", (793, "true", 59, "Object.defineProperty(window,'pageYOffset',{get:()=>120});"),
                               "skipped (scrollY 120), innerHeight 793")):
        for u in ("/index.html?navdebug=1", f"/matches/{LEAGUE_FT}.html?navdebug=1"):
            ctx, pg, errs = page(br, u, init=NDM % args)
            pg.wait_for_timeout(300)
            got = pg.evaluate(ndline)
            check(f"H nudge {label} {u.split('?')[0]}: overlay says {want}", got == want and not errs, [got, errs])
            ctx.close()
    for u in ("/index.html", f"/matches/{LEAGUE_FT}.html", "/leagues/sau.html"):
        ctx, pg, errs = page(br, u)
        check(f"H normal URL {u}: no overlay", pg.evaluate("()=>!document.getElementById('navdebug')"))
        ctx.close()

    # five taps on Search, the flag across pages, and the URL switches
    flag = lambda pg: pg.evaluate("()=>localStorage.getItem('fbNavDebug')")  # noqa: E731
    shown = lambda pg: pg.evaluate("()=>!!document.getElementById('navdebug')")  # noqa: E731

    def tap(pg, n):
        for _ in range(n):
            pg.locator("#navsearch").click()
            pg.wait_for_timeout(60)

    ctx, pg, errs = page(br, "/search.html")
    tap(pg, 4)
    check("H 4 taps on Search: nothing yet", not shown(pg) and flag(pg) is None, flag(pg))
    tap(pg, 1)
    check("H 5th tap turns the overlay on and stores the flag", shown(pg) and flag(pg) == "1", flag(pg))
    check("H the 5th tap does not navigate", pg.url.endswith("/search.html"), pg.url)
    gapv = pg.evaluate("""()=>{const t=document.getElementById('navdebug').textContent,m=/gap \\(innerHeight - nav bottom\\): (-?[0-9.]+)/.exec(t),r=document.querySelector('.nav').getBoundingClientRect();return [m&&parseFloat(m[1]),Math.round((innerHeight-r.bottom)*10)/10];}""")
    check("H gap = innerHeight - nav bottom", gapv[0] == gapv[1], gapv)
    pg.goto(B + "/leagues/sau.html", wait_until="load")
    pg.wait_for_timeout(400)
    check("H flag keeps it on across pages", shown(pg))
    pg.goto(B + f"/matches/{LEAGUE_FT}.html", wait_until="load")
    pg.wait_for_timeout(400)
    check("H on a page using the site.js bundle too", shown(pg))
    pg.goto(B + "/search.html", wait_until="load")
    pg.wait_for_timeout(300)
    tap(pg, 5)
    check("H 5 more taps turn it off and clear the flag", not shown(pg) and flag(pg) is None, flag(pg))
    tap(pg, 4)
    pg.wait_for_timeout(3200)
    tap(pg, 1)
    check("H taps spread over more than 3 seconds do not toggle", not shown(pg) and flag(pg) is None, flag(pg))
    check("H no script errors", not errs, errs)
    ctx.close()

    ctx, pg, errs = page(br, "/index.html")
    pg.locator("#navsearch").click()
    pg.wait_for_url("**/search.html", timeout=6000)
    check("H single tap from another page still navigates to Search", pg.url.endswith("/search.html") and not shown(pg), pg.url)
    pg.wait_for_timeout(300)
    tap(pg, 4)
    check("H taps count across the navigation (1 before + 4 here)", shown(pg) and flag(pg) == "1", flag(pg))
    ctx.close()

    ctx, pg, errs = page(br, "/index.html?navdebug=1")
    check("H ?navdebug=1 sets the same flag", flag(pg) == "1" and shown(pg), flag(pg))
    pg.goto(B + "/leagues/sau.html", wait_until="load")
    pg.wait_for_timeout(300)
    check("H the URL flag carries to other pages", shown(pg))
    pg.goto(B + "/index.html?navdebug=0", wait_until="load")
    pg.wait_for_timeout(300)
    check("H ?navdebug=0 clears it", flag(pg) is None and not shown(pg), flag(pg))
    ctx.close()
    br.close()

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
