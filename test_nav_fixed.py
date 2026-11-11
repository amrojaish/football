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

    # (11 نوفمبر 2026) --navfix: فجوة iOS المثبَّت بقيم مُحاكاة (Chromium لا يحاكي المثبَّت ولا safe-area)
    def nf_mock(sa="nav", orient="portrait", sh=852, sw=393, ih=793, st=59):
        return ("window.__ih=%d;Object.defineProperty(window,'innerHeight',{get:()=>window.__ih,configurable:true});"
                "Object.defineProperty(screen,'height',{get:()=>%d});Object.defineProperty(screen,'width',{get:()=>%d});"
                "Object.defineProperty(screen,'orientation',{get:()=>({type:'%s-primary',addEventListener(){}})});"
                "const s=new CSSStyleSheet();s.replaceSync('#navfixprobe{padding-top:%dpx !important}');document.adoptedStyleSheets=[s];"
                % (ih, sh, sw, orient, st)
                + ("Object.defineProperty(navigator,'standalone',{get:()=>true});" if sa == "nav" else "")
                + ("const mm=window.matchMedia.bind(window);window.matchMedia=q=>/display-mode: *standalone/.test(q)?"
                   "{matches:true,media:q,addEventListener(){},addListener(){}}:mm(q);" if sa == "mm" else ""))
    NF = """()=>{const h=document.documentElement,n=document.querySelector('.nav'),cs=getComputedStyle(h);
      return {v:h.style.getPropertyValue('--navfix'),cls:h.classList.contains('navfix'),nav:getComputedStyle(n).transform,
              html:cs.transform,body:getComputedStyle(document.body).transform}}"""

    def nf_run(init, path="index.html"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        ctx.route("https://saffara-live.abujaishamr.workers.dev/**",
                  lambda r: r.fulfill(status=200, content_type="application/json", body='{"t":0,"m":{}}'))
        ctx.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
        ctx.add_init_script(init)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{B}/{path}", wait_until="load")
        pg.wait_for_timeout(400)
        return ctx, pg, errs

    on = lambda r, px: r["v"] == f"{px}px" and r["cls"] and r["nav"] == f"matrix(1, 0, 0, 1, 0, {px})"  # noqa: E731
    off = lambda r: r["v"] in ("", "0px") and not r["cls"] and r["nav"] == "none"  # noqa: E731
    for path in ("index.html", "matches/1602976.html", "en/leagues/sau.html"):
        ctx, pg, errs = nf_run(nf_mock(), path)
        r = pg.evaluate(NF)
        check(f"navfix {path}: standalone 852/793 safe-top 59 -> 59px on .nav only", on(r, 59) and r["html"] == "none" and r["body"] == "none", r)
        check(f"navfix {path}: no script errors", not errs, errs)
        ctx.close()
    ctx, pg, errs = nf_run(nf_mock())
    pg.evaluate("window.__ih=852;window.dispatchEvent(new Event('scroll'))")
    r = pg.evaluate(NF)
    check("navfix: viewport corrected after scroll (852/852) -> back to 0, class removed", r["v"] == "0px" and off(r), r)
    pg.evaluate("window.__ih=793")
    pg.wait_for_timeout(500)   # ما زال داخل نافذة الـ3 ثوانٍ: الفحص الدوري يعيده
    check("navfix: 250ms re-check inside the first 3 s picks the short viewport up again", on(pg.evaluate(NF), 59), pg.evaluate(NF))
    ctx.close()
    for label, init, ok in (
            ("display-mode: standalone (matchMedia) 852/793/59 -> 59", nf_mock(sa="mm"), lambda r: on(r, 59)),
            ("standalone 852/852 -> 0", nf_mock(ih=852), lambda r: r["v"] == "0px" and off(r)),
            ("not standalone 852/793/59 -> untouched (0)", nf_mock(sa="no"), lambda r: r["v"] == "" and off(r)),
            ("landscape 393 wide, innerHeight 393 -> 0", nf_mock(orient="landscape", ih=393), off),
            ("landscape uses screen.width (393 - 793 < 0) -> 0", nf_mock(orient="landscape"), off),
            ("landscape when the same rule matches (393/334/59) -> 59", nf_mock(orient="landscape", ih=334), lambda r: on(r, 59)),
            ("deficit 59 != safe-top 47 -> 0", nf_mock(st=47), off),
            ("deficit 60 vs safe-top 59 (within 2px) -> 60", nf_mock(ih=792), lambda r: on(r, 60)),
            ("deficit 152 > 80 -> 0", nf_mock(ih=700, st=152), off)):
        ctx, pg, errs = nf_run(init)
        r = pg.evaluate(NF)
        check(f"navfix: {label}", ok(r) and not errs, [r, errs])
        ctx.close()
    br.close()
srv.shutdown()
print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
