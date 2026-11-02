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
    br.close()
srv.shutdown()
print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
