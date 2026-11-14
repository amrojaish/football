#!/usr/bin/env python3
"""
Batch 8 (1 Nov 2026). Playwright, ar + en, iPhone 13 size (390x844, touch), dark theme. Run alone:
    python C:/Users/User/Projects/Football/test_batch8.py
Needs the site built (make_assets + update_all --generate-only). Serves the repo on 127.0.0.1:8789, mocks the live worker.
Reads football.db read-only to pick a postponed (PST) and an upcoming match.

  1  PST: list row = struck-through grey kickoff time (s.pko), no label; match header = big struck time + «مؤجلة»/"Postponed",
     not blue, no date; live f={id:{s:PST}} renders the same (does not restore the label)
  2  team form card: first column at the start edge, second at the end edge; pills 64px wide, 22px line, centred
  3  match header: no date line (meta-top only for an old season)
  4  list rows: time without box (transparent background, no radius); upcoming time keeps the accent colour
  5  viewport-fit=cover on every page type; body top padding 28px without a safe area (batch 9: --top-safe); .appbar.home 0 (was -14px) then
  6  home: a horizontal swipe on the empty area below the day's cards changes the day
  7  day tabs: "weekday D Month" for every day except Today/Yesterday/Tomorrow; the active day stays centred in the strip
  8  following "+": sheet opens at ~60% without focusing the field; drag up on the grab = full; drag down from 60% = closed
"""
import functools
import http.server
import json
import re
import socketserver
import sqlite3
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
fails = 0
W, H = 390, 844


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:700]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8789), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8789"
LIVE = {"body": '{"t":0,"m":{}}'}
conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
PST = conn.execute("SELECT match_id, date, home_id FROM matches WHERE status='PST' AND date >= date('now') "
                   "AND length(date) >= 16 ORDER BY date LIMIT 1").fetchone()
UP = conn.execute("SELECT match_id, date FROM matches WHERE COALESCE(status,'') IN ('NS','TBD','') AND home_goals IS NULL "
                  "AND date > datetime('now','+30 minutes') AND date < date('now','+2 day') ORDER BY date LIMIT 1").fetchone()


class Touch:
    def __init__(self, pg):
        self.pg, self.cdp = pg, pg.context.new_cdp_session(pg)

    def drag(self, x0, y0, dx, dy=0, steps=14, ms=280):
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
        for i in range(1, steps + 1):
            self.cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + dx * i / steps, "y": y0 + dy * i / steps}]})
            self.pg.wait_for_timeout(ms / steps)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        self.pg.wait_for_timeout(450)


def page(br, url, init=""):
    ctx = br.new_context(viewport={"width": W, "height": H}, has_touch=True, is_mobile=True, service_workers="block",
                         color_scheme="dark", device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbLeaguesV2','1');" + init + "}catch(e){}")
    ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(
        status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"]))
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + url, wait_until="load")
    pg.wait_for_timeout(600)
    return ctx, pg, errs


# ── 5 (static): viewport-fit=cover on every page type ──
samples = ["index.html", "en/index.html", "following.html", "leagues.html", "search.html", "notifications.html", "about.html", "404.html"]
for d in ("matches", "players", "clubs", "leagues"):
    f = next((ROOT / d).glob("*.html"), None)
    if f:
        samples += [f"{d}/{f.name}", f"en/{d}/{f.name}"]
nofit = [s for s in samples if (ROOT / s).exists() and 'viewport-fit=cover' not in (ROOT / s).read_text(encoding="utf-8")[:4000]]
check(f"5 viewport-fit=cover on {len(samples)} sampled pages (all page types, ar + en)", not nofit, nofit)

# ── 3 (static): no date in the match header line ──
DATE = re.compile(r'class="meta-top">[^<]*(\d{4}-\d{2}-\d{2}|data-utcd)')
bad3 = [p.name for p in list((ROOT / "matches").glob("*.html"))[:400] if DATE.search(p.read_text(encoding="utf-8"))]
check("3 match pages (400 sampled): header line has no date", not bad3, bad3[:5])

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        lbl = "مؤجلة" if lang == "ar" else "Postponed"
        # ── 1 static PST: club row + match header ──
        if PST:
            mid, dt, hid = PST
            ctx, pg, errs = page(br, f"{pre}/matches/{mid}.html")
            r = pg.evaluate("""()=>{const b=document.querySelector('.big[data-mid]');if(!b)return null;const s=b.querySelector('s.pko'),l=b.querySelector('.pstl');
                return {cls:b.className,s:s&&s.textContent.trim(),sc:s&&getComputedStyle(s).textDecorationLine,col:getComputedStyle(b).color,
                acc:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),lbl:l&&l.textContent.trim(),
                meta:(document.querySelector('.meta-top')||{}).textContent||''};}""")
            check(f"{lang} 1 PST match header: big struck time + label under it, not blue, no date",
                  r and "pstd" in r["cls"] and "soon" not in r["cls"] and r["s"] and re.match(r"^\d{1,2}:\d{2}", r["s"])
                  and "line-through" in (r["sc"] or "") and r["lbl"] == (lbl if lang == "en" else r["lbl"]) and r["lbl"]
                  and not re.search(r"\d{4}|\d{1,2} [A-Za-z\u0600-\u06FF]", r["meta"]), r)
            check(f"{lang} 1 PST page: no errors", not errs, errs)
            ctx.close()
            ctx, pg, errs = page(br, f"{pre}/clubs/{hid}.html")
            r = pg.evaluate(f"""()=>{{const c=document.querySelector('[data-mid="{mid}"]');if(!c)return null;const sc=c.querySelector('.score');
                return {{html:sc&&sc.innerHTML,txt:sc&&sc.textContent.trim(),dec:(sc&&sc.querySelector('s'))?getComputedStyle(sc.querySelector('s')).textDecorationLine:''}};}}""")
            check(f"{lang} 1 PST club row: struck-through kickoff time, no label",
                  r is not None and r["html"] and "<s" in r["html"] and "line-through" in r["dec"] and re.match(r"^\d{1,2}:\d{2}", r["txt"]), r)
            ctx.close()
        else:
            check(f"{lang} 1 PST match exists in the next days (needed for the PST checks)", False, "no PST match")

        # ── 1 live: f={id:{s:PST}} on an upcoming match -> same struck time on the page and in the home row ──
        if UP:
            umid = UP[0]
            LIVE["body"] = json.dumps({"t": 0, "m": {}, "f": {str(umid): {"s": "PST"}}})
            ctx, pg, errs = page(br, f"{pre}/matches/{umid}.html")
            pg.wait_for_timeout(2500)
            r = pg.evaluate("""()=>{const b=document.querySelector('.big[data-mid]');return b&&{cls:b.className,s:!!b.querySelector('s.pko'),
                l:(b.querySelector('.pstl')||{}).textContent||'',end:!!b.querySelector('.lvend')};}""")
            check(f"{lang} 1 live PST on the match page: struck time + label, not the label alone", r and r["s"] and r["l"] and not r["end"] and "pstd" in r["cls"], r)
            ctx.close()
            ctx, pg, errs = page(br, f"{pre}/index.html")
            pg.wait_for_timeout(2500)
            r = pg.evaluate(f"""()=>{{const c=document.querySelector('[data-mid="{umid}"]');return c&&{{s:!!c.querySelector('s.pko'),end:!!c.querySelector('.lvend')}};}}""")
            check(f"{lang} 1 live PST in the home row: struck time, no label", r is None or (r["s"] and not r["end"]), r)
            check(f"{lang} 1 live pages: no errors", not errs, errs)
            ctx.close()
            LIVE["body"] = '{"t":0,"m":{}}'

        # ── 2 team form card ──
        fm = next((x for x in ([PST[0]] if PST else []) + [r[0] for r in conn.execute(
            "SELECT match_id FROM matches WHERE home_goals IS NOT NULL ORDER BY date DESC LIMIT 40")]
            if 'class="tfcard"' in (ROOT / ("matches" if lang == "ar" else "en/matches") / f"{x}.html").read_text(encoding="utf-8")), None)
        if fm:
            ctx, pg, errs = page(br, f"{pre}/matches/{fm}.html")
            r = pg.evaluate("""()=>{const c=document.querySelector('.tfcard');c.scrollIntoView();const cb=c.getBoundingClientRect(),cs=getComputedStyle(c);
                const cols=[...c.querySelectorAll('.tfcol')].map(x=>{const r=[...x.querySelectorAll('.tfr')].map(e=>e.getBoundingClientRect());
                  return {l:Math.min(...r.map(z=>z.left)),r:Math.max(...r.map(z=>z.right))};});
                const p=c.querySelector('.tfp'),ps=getComputedStyle(p);
                return {cl:cb.left+parseFloat(cs.paddingLeft),cr:cb.right-parseFloat(cs.paddingRight),cols,w:p.getBoundingClientRect().width,
                  lh:ps.lineHeight,pad:ps.paddingTop,ta:ps.textAlign,rtl:document.documentElement.dir==='rtl'};}""")
            first, second = r["cols"][0], r["cols"][1]
            start_ok = abs((first["r"] if r["rtl"] else first["l"]) - (r["cr"] if r["rtl"] else r["cl"])) <= 2
            end_ok = abs((second["l"] if r["rtl"] else second["r"]) - (r["cl"] if r["rtl"] else r["cr"])) <= 2
            check(f"{lang} 2 form card: home column at the start edge, away column at the end edge", start_ok and end_ok, r)
            # (15 نوفمبر 2026) الدفعة 10 (d1660544f) صغّرت القرص عمداً: 46px عرضاً وسطر 26px (make_matches.py .tfp)
            check(f"{lang} 2 form pills: 46px wide, 26px line, no padding, centred",
                  abs(r["w"] - 46) < 0.6 and r["lh"] == "26px" and r["pad"] == "0px" and r["ta"] == "center", r)
            ctx.close()
        else:
            check(f"{lang} 2 a match page with a form card exists", False)

        # ── home: 4 time rows, 5 header, 7 labels, 6 swipe ──
        ctx, pg, errs = page(br, f"{pre}/index.html")
        r = pg.evaluate("""()=>{const t=document.querySelector('.daypanel:not([style*="none"]) .match .score.time')||document.querySelector('.match .score.time');
            if(!t)return null;const s=getComputedStyle(t);return {bg:s.backgroundColor,rad:s.borderTopLeftRadius,col:s.color,
            acc:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()};}""")
        check(f"{lang} 4 list time: no box (transparent, no radius)", r and r["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and r["rad"] == "0px", r)
        r2 = pg.evaluate("()=>({pt:getComputedStyle(document.body).paddingTop, mt:getComputedStyle(document.querySelector('.appbar.home')).marginTop})")
        check(f"{lang} 5 home: body padding-top 28px and .appbar.home 0 without a safe area (batch 9: one --top-safe rule)", r2["pt"] == "28px" and r2["mt"] == "0px", r2)
        labels = pg.evaluate("""()=>[...document.querySelectorAll('.daytab')].map(b=>({d:b.dataset.day,n:b.querySelector('.dn').textContent.trim(),a:b.classList.contains('active')}))""")
        rel = {"ar": ("اليوم", "أمس", "غداً"), "en": ("Today", "Yesterday", "Tomorrow")}[lang]
        pat = re.compile(r"^\S+ \d{1,2} \S+$")
        badl = [x for x in labels if x["n"] not in rel and not pat.match(x["n"])]
        check(f"{lang} 7 day tabs: weekday + day + month except Today/Yesterday/Tomorrow ({len(labels)} tabs, e.g. "
              f"{[x['n'] for x in labels if x['n'] not in rel][:2]})", labels and not badl, badl[:4])
        pg.wait_for_timeout(2500)   # the strip re-centres after layout settles (fonts/logos); measured once it is stable
        cen = pg.evaluate("""()=>{const bar=document.querySelector('.daytabs'),a=bar.querySelector('.daytab.active');const br=bar.getBoundingClientRect(),
            ar=a.getBoundingClientRect();return {off:Math.round((ar.left+ar.width/2)-(br.left+br.width/2)),sl:bar.scrollLeft,max:bar.scrollWidth-bar.clientWidth};}""")
        check(f"{lang} 7 active day centred in the strip (offset {cen['off']}px)", abs(cen["off"]) <= 24, cen)
        # 6 swipe on the empty area below the active panel's cards: pick a nearby day with the fewest cards (empty space on screen)
        pg.evaluate("""()=>{const tabs=[...document.querySelectorAll('.daytab')],i=tabs.findIndex(b=>b.classList.contains('active'));
            let best=null,bn=1e9;for(let k=Math.max(0,i-7);k<Math.min(tabs.length,i+8);k++){const p=document.getElementById('d'+tabs[k].dataset.day);
              const n=p?p.querySelectorAll('.match').length:1e9;if(n<bn){bn=n;best=tabs[k];}}if(best)best.click();}""")
        pg.wait_for_timeout(700)
        a0 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        y_empty = pg.evaluate("""()=>{const p=[...document.querySelectorAll('.daypanel')].find(x=>getComputedStyle(x).display!=='none');
            const b=p.getBoundingClientRect();window.scrollTo(0,0);return Math.min(b.bottom+40, innerHeight-120);}""")
        target = pg.evaluate(f"()=>{{const e=document.elementFromPoint({W // 2},{y_empty});return e&&(e.closest('.daypanel')?'panel':(e.closest('.nav')?'nav':e.tagName+'.'+e.className));}}")
        T = Touch(pg)
        fwd = 1 if lang == "en" else -1
        T.drag(W / 2 + fwd * 120, y_empty, -fwd * W * 0.5)
        a1 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        check(f"{lang} 6 swipe on the empty area below the cards ({target}) changes the day", a1 != a0 and target not in ("panel", "nav"), [a0, a1, target, y_empty])
        T.drag(W / 2, 400, 0, -160)   # vertical drag must not switch days
        a2 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        check(f"{lang} 6 vertical drag does not change the day", a2 == a1, [a1, a2])
        check(f"{lang} home: no page errors", not errs, errs)
        ctx.close()

        # ── 8 following sheet ──
        ctx, pg, errs = page(br, f"{pre}/following.html")
        pg.click("#fadd")
        pg.wait_for_timeout(500)
        r = pg.evaluate("""()=>{const s=document.querySelector('.fsheet');return {h:s.getBoundingClientRect().height,vh:innerHeight,
            full:document.getElementById('fsheet').classList.contains('full'),foc:document.activeElement&&document.activeElement.id};}""")
        check(f"{lang} 8 sheet opens at ~60% without focusing the field", abs(r["h"] / r["vh"] - 0.60) < 0.03 and not r["full"] and r["foc"] != "fsq", r)
        g = pg.locator(".fsheet .grab").bounding_box()
        pg.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
        pg.mouse.down()
        pg.mouse.move(g["x"] + g["width"] / 2, g["y"] - 200, steps=8)
        mid_h = pg.evaluate("()=>document.querySelector('.fsheet').getBoundingClientRect().height")
        pg.mouse.up()
        pg.wait_for_timeout(450)
        full = pg.evaluate("()=>document.getElementById('fsheet').classList.contains('full')")
        check(f"{lang} 8 drag up on the grab: sheet follows ({round(mid_h)}px > {round(r['h'])}px) then goes full", full and mid_h > r["h"] + 100, [mid_h, full])
        hh = pg.locator(".fsheet .fsh-h h3").bounding_box()
        pg.mouse.move(hh["x"] + 10, hh["y"] + 5)
        pg.mouse.down()
        pg.mouse.move(hh["x"] + 10, hh["y"] + 160, steps=8)
        pg.mouse.up()
        pg.wait_for_timeout(450)
        st = pg.evaluate("()=>{const s=document.getElementById('fsheet');return {on:s.classList.contains('on'),full:s.classList.contains('full')}}")
        check(f"{lang} 8 drag down from full (header) = back to 60%", st["on"] and not st["full"], st)
        g = pg.locator(".fsheet .grab").bounding_box()
        pg.mouse.move(g["x"] + g["width"] / 2, g["y"] + 2)
        pg.mouse.down()
        pg.mouse.move(g["x"] + g["width"] / 2, g["y"] + 200, steps=8)
        pg.mouse.up()
        pg.wait_for_timeout(450)
        st = pg.evaluate("()=>document.getElementById('fsheet').classList.contains('on')")
        check(f"{lang} 8 drag down from 60% = closed", not st, st)
        pg.click("#fadd")
        pg.wait_for_timeout(300)
        pg.focus("#fsq")
        pg.wait_for_timeout(400)
        check(f"{lang} 8 focus on the field still goes full", pg.evaluate("()=>document.getElementById('fsheet').classList.contains('full')"))
        check(f"{lang} following: no page errors", not errs, errs)
        ctx.close()
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
