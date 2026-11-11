#!/usr/bin/env python3
"""
الشريط السفلي مثبَّت بأسفل الشاشة بكل الصفحات (2 نوفمبر 2026، متابعة دفعة 9) — Playwright، 390x844، عربي + إنجليزي.
    python C:\\Users\\User\\Projects\\Football\\test_nav_fixed.py
يحتاج الموقع مبنياً (make_assets + صفحات الرئيسية/الدوري/المباراة/اللاعب/النادي/البحث/المتابعة/الإشعارات). يخدم المستودع نفسه على
127.0.0.1:8793 ويحاكي الـworker الحيّ.

لكل صفحة: .nav ابن مباشر لـ<body>؛ لا transform/filter/backdrop-filter/perspective/contain/will-change على html أو body (ولا على
الشريط نفسه — طبقة تركيب زائدة على WebKit)؛ position fixed؛ و**getBoundingClientRect().bottom == innerHeight** بأعلى الصفحة وبعد
التمرير لمنتصفها ولآخرها. الرئيسية مرتين: يوم بمباراة واحدة ويوم بأكثر المباريات (المحتوى القصير والطويل — العَرَض على iPhone المثبَّت
كان الشريط يعلو مع المحتوى القصير وينزل مع الطويل). ⚠️ Chromium لا يحاكي safe-area (env = 0) ولا وضع iOS المثبَّت: الفحص يضمن غياب
أي سبب بالـCSS/DOM (حاوية تُنشئ containing block، ارتفاع جذر قصير)، والتحقق النهائي على الهاتف.
"""
import functools
import http.server
import json
import sys
import threading

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\User\Projects\Football"
PORT = 8793


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(_Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"
PAGES = [("match", "matches/1602976.html"), ("player", "players/cristiano-ronaldo.html"), ("league", "leagues/sau.html"),
         ("club", "clubs/2932.html"), ("search", "search.html"), ("following", "following.html"),
         ("notifications", "notifications.html")]
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {json.dumps(extra, ensure_ascii=False)}"))
    fails += 0 if cond else 1


STRUCT = """()=>{const n=document.querySelector('.nav');if(!n)return null;const props=['transform','filter','backdropFilter',
  'webkitBackdropFilter','perspective','contain','willChange'];const bad=[];
  for(const el of [document.documentElement,document.body,n]){const s=getComputedStyle(el);
    for(const p of props){const v=s[p];if(v&&v!=='none'&&v!=='auto'&&v!=='normal'&&v!=='')bad.push(el.tagName+'.'+p+'='+v);}}
  return {parent:n.parentElement.tagName, pos:getComputedStyle(n).position, bad}}"""
MEASURE = "()=>{const n=document.querySelector('.nav');return Math.round(n.getBoundingClientRect().bottom*10)/10-innerHeight}"


def pinned(pg, tag):
    st = pg.evaluate(STRUCT)
    check(f"{tag}: .nav is a direct child of <body>, position fixed, no containing-block property on html/body/nav",
          st and st["parent"] == "BODY" and st["pos"] == "fixed" and not st["bad"], st)
    gaps = {}
    for where, js in (("top", "window.scrollTo(0,0)"), ("middle", "window.scrollTo(0,document.documentElement.scrollHeight/2)"),
                      ("end", "window.scrollTo(0,document.documentElement.scrollHeight)")):
        pg.evaluate(js)
        pg.wait_for_timeout(120)
        gaps[where] = pg.evaluate(MEASURE)
    check(f"{tag}: nav bottom == innerHeight at top / middle / end of scroll", all(abs(g) < 0.6 for g in gaps.values()), gaps)


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        ctx.route("https://saffara-live.abujaishamr.workers.dev/**",
                  lambda r: r.fulfill(status=200, content_type="application/json", body='{"t":0,"m":{}}'))
        ctx.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
        pg = ctx.new_page()
        # الرئيسية: يوم بمباراة واحدة ويوم بأكثر المباريات
        pg.goto(f"{B}{pre}/index.html", wait_until="networkidle")
        days = pg.evaluate("""()=>[...document.querySelectorAll('.daypanel')].map(s=>({d:s.id.slice(1),
            n:s.querySelectorAll('[data-mid]').length})).filter(x=>x.n>0)""")
        one = next((d for d in days if d["n"] == 1), None) or min(days, key=lambda d: d["n"])
        many = max(days, key=lambda d: d["n"])
        for label, day in (("1-match day" if one["n"] == 1 else f"fewest ({one['n']})", one), (f"busiest day ({many['n']})", many)):
            pg.goto(f"{B}{pre}/index.html", wait_until="networkidle")
            pg.evaluate("d=>{const b=document.querySelector('.daytab[data-day=\"'+d+'\"]');if(b)b.click();}", day["d"])
            pg.wait_for_timeout(300)
            h = pg.evaluate("()=>document.documentElement.scrollHeight")
            pinned(pg, f"{lang} home {label} {day['d']} (page height {h}px)")
        for name, path in PAGES:
            pg.goto(f"{B}{pre}/{path}", wait_until="networkidle")
            pinned(pg, f"{lang} {name}")
        ctx.close()

    # (11 نوفمبر 2026، الإصلاح 2) «دفعة التمرير» بقيم مُحاكاة (Chromium لا يحاكي المثبَّت ولا safe-area). الإصلاح 1 (translateY/--navfix) أُزيل.
    def nd_mock(sa="nav", orient="portrait", sh=852, sw=393, ih=793, st=59, sy=None, fix=True):
        return ("window.__ih=%d;window.__calls=[];Object.defineProperty(window,'innerHeight',{get:()=>window.__ih,configurable:true});"
                "Object.defineProperty(screen,'height',{get:()=>%d});Object.defineProperty(screen,'width',{get:()=>%d});"
                "Object.defineProperty(screen,'orientation',{get:()=>({type:'%s-primary',addEventListener(){}})});"
                "const s=new CSSStyleSheet();s.replaceSync('#nudgeprobe{padding-top:%dpx !important}');document.adoptedStyleSheets=[s];"
                "const o=window.scrollTo.bind(window);window.scrollTo=function(x,y){window.__calls.push([x,y,document.body.style.minHeight,"
                "document.documentElement.scrollHeight]);return o(x,y);};"
                % (ih, sh, sw, orient, st)
                + ("window.addEventListener('scroll',()=>{window.__ih=%d;});" % sh if fix else "")
                + ("Object.defineProperty(window,'pageYOffset',{get:()=>%d});" % sy if sy is not None else "")
                + ("Object.defineProperty(navigator,'standalone',{get:()=>true});" if sa == "nav" else "")
                + ("const mm=window.matchMedia.bind(window);window.matchMedia=q=>/display-mode: *standalone/.test(q)?"
                   "{matches:true,media:q,addEventListener(){},addListener(){}}:mm(q);" if sa == "mm" else ""))
    ND = """()=>{const h=document.documentElement,n=document.querySelector('.nav');
      const css=[...document.styleSheets].map(s=>{try{return [...s.cssRules].map(r=>r.cssText).join(' ')}catch(e){return ''}}).join(' ');
      return {calls:window.__calls.map(c=>[c[0],c[1]]),grew:window.__calls.length?window.__calls[0][2]:null,min:document.body.style.minHeight,
              y:window.scrollY,var:h.style.getPropertyValue('--navfix'),cls:h.classList.contains('navfix'),v1css:css.includes('navfix'),
              t:[getComputedStyle(h).transform,getComputedStyle(document.body).transform,getComputedStyle(n).transform]}}"""

    def nd_run(init, path="index.html", h=844):
        ctx = br.new_context(viewport={"width": 390, "height": h}, is_mobile=True, has_touch=True)
        ctx.route("https://saffara-live.abujaishamr.workers.dev/**",
                  lambda r: r.fulfill(status=200, content_type="application/json", body='{"t":0,"m":{}}'))
        ctx.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
        ctx.add_init_script(init)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{B}/{path}", wait_until="load")
        pg.wait_for_timeout(700)
        return ctx, pg, errs, pg.evaluate(ND)

    clean = lambda r: r["t"] == ["none", "none", "none"] and not r["var"] and not r["cls"] and not r["v1css"] and r["min"] == ""  # noqa: E731
    nudged = lambda r: r["calls"] == [[0, 1], [0, 0]] and r["y"] == 0 and clean(r)  # noqa: E731
    skipped = lambda r: r["calls"] == [] and clean(r)  # noqa: E731
    for path in ("index.html", "matches/1602976.html", "en/leagues/sau.html"):
        ctx, pg, errs, r = nd_run(nd_mock(), path)
        check(f"nudge {path}: standalone 852/793 safe-top 59 -> scrollTo(0,1) then (0,0), back at top, no transform, v1 gone", nudged(r) and not errs, [r, errs])
        ctx.close()
    ctx, pg, errs, r = nd_run(nd_mock(sh=3059, ih=3000), "search.html", h=3000)
    check("nudge: a page that does not scroll gets a temporary min-height during the nudge, removed after",
          nudged(r) and r["grew"] in ("calc(100vh + 1px)", "calc(1px + 100vh)") and not errs, [r, errs])
    for label, init, ok in (
            ("display-mode: standalone (matchMedia) 852/793/59 -> nudged", nd_mock(sa="mm"), nudged),
            ("not standalone -> skipped", nd_mock(sa="no"), skipped),
            ("restored scroll position (scrollY 120) -> skipped", nd_mock(sy=120), skipped),
            ("standalone 852/852 (no gap) -> skipped", nd_mock(ih=852), skipped),
            ("deficit 59 != safe-top 47 -> skipped", nd_mock(st=47), skipped),
            ("deficit 60 vs safe-top 59 (within 2px) -> nudged", nd_mock(ih=792), nudged),
            ("landscape uses screen.width (393 - 793 < 0) -> skipped", nd_mock(orient="landscape"), skipped),
            ("landscape when the same rule matches (393/334/59) -> nudged", nd_mock(orient="landscape", ih=334), nudged)):
        ctx, pg, errs, r = nd_run(init)
        check(f"nudge: {label}", ok(r) and not errs, [r, errs])
        ctx.close()
    ctx, pg, errs, r = nd_run(nd_mock())
    pg.evaluate("window.__calls=[];window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:false}))")
    pg.wait_for_timeout(500)
    check("nudge: a plain pageshow (not from bfcache) does not nudge again", pg.evaluate("window.__calls.length") == 0)
    pg.evaluate("window.__ih=793;window.__calls=[];window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
    pg.wait_for_timeout(500)
    check("nudge: pageshow restored from bfcache nudges once more", pg.evaluate("window.__calls.map(c=>[c[0],c[1]])") == [[0, 1], [0, 0]],
          pg.evaluate("window.__calls"))
    ctx.close()
    br.close()
srv.shutdown()
print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
