#!/usr/bin/env python3
"""
Mobile speed regression (390px): home logos are 64px WebP thumbs with fixed dimensions + lazy below the first
screen, nothing else changes visually, search_data.js is requested ONLY by the search pages, and search works from
the first tap (with a short loading message if the data isn't there yet).

Needs the built site served locally (python -m http.server 8765 from the repo root, after make_logo_thumbs.py,
make_assets.py, make_site3.py, make_search_page.py). Run: python test_mobile_speed.py [screenshot_dir]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8765"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
UA = "Mozilla/5.0 (Linux; Android 11; moto g power) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " " + json.dumps(extra, ensure_ascii=False, default=str)))
    if not cond:
        fails += 1


def ctx_of(br):
    return br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, user_agent=UA)


# unit check of the markup rule (the built today-panel has no matches right now)
sys.path.insert(0, str(Path(__file__).parent))
import make_site3 as ms
_m = {"match_id": 1, "date": "2026-10-08 20:00", "home_goals": None, "away_goals": None, "league_code": "MAR", "season": 2026,
      "status": "NS", "home_id": 962, "home": "a", "home_en": "a", "home_logo": "x.png", "away_id": 964, "away": "b", "away_en": "b", "away_logo": "y.png"}
class _R(dict):
    def keys(self): return list(dict.keys(self))
_card = lambda **k: ms.match_card(_R(_m), "en", {}, show_league=False, upcoming=True, club_ids=True, **k)
check("markup: eager card logos have no loading attr, lazy ones have loading=lazy, both fixed 26x26 + async",
      'loading="lazy"' not in _card(thumbs=True, eager=True) and _card(thumbs=True).count('loading="lazy"') == 2
      and _card(thumbs=True, eager=True).count('width="26" height="26" decoding="async"') == 2)
check("markup: other pages' cards (thumbs=False) are unchanged (original src, no extra attributes)",
      'width=' not in _card() and 'thumbs/' not in _card())

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, path in (("ar", "/index.html"), ("en", "/en/index.html")):
        ctx = ctx_of(br)
        pg = ctx.new_page()
        reqs, errs = [], []
        pg.on("request", lambda r: reqs.append(r.url))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + path, wait_until="networkidle"); pg.wait_for_timeout(800)
        info = pg.evaluate("""() => {
          const vis = [...document.querySelectorAll('.daypanel.visible .match .side img')];
          const all = [...document.querySelectorAll('.match .side img')];
          const first = vis.slice(0, 16);
          return {
            total: all.length,
            thumbs: all.filter(i => /thumbs\\/\\d+\\.webp/.test(i.getAttribute('src'))).length,
            nonThumbs: all.filter(i => !/thumbs\\/\\d+\\.webp/.test(i.getAttribute('src'))).map(i => i.getAttribute('src')).slice(0, 3),
            dims: all.every(i => i.getAttribute('width') === '26' && i.getAttribute('height') === '26'),
            async: all.every(i => i.decoding === 'async'),
            lazyAll: all.filter(i => i.loading === 'lazy').length,
            eagerVisible: vis.filter(i => i.loading !== 'lazy').length,
            firstScreenLoaded: first.length ? first.every(i => i.complete && i.naturalWidth > 0) : null,
            firstScreenCount: first.length,
            sizes: [...new Set(first.map(i => { const r = i.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height); }))],
            hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
          };
        }""")
        check(f"{lang} home: every card logo is a thumbs/<id>.webp", info["total"] > 100 and info["thumbs"] == info["total"], info)
        check(f"{lang} home: fixed width/height=26 + decoding=async on all", info["dims"] and info["async"], info)
        check(f"{lang} home: every card logo has loading=lazy (today's panel built empty here, so none eager)", info["lazyAll"] == info["total"], info)
        check(f"{lang} home: no horizontal scroll", info["hscroll"] is False)
        img_reqs = [u for u in reqs if "thumbs/" in u or "media.api-sports" in u or "/logos/" in u]
        check(f"{lang} home: only first-screen logos requested at load (<= 20, none from api-sports)", len(img_reqs) <= 20 and not any("media.api-sports" in u for u in img_reqs), img_reqs[:5])
        check(f"{lang} home: search_data.js is NOT requested", not any("search_data" in u for u in reqs), [u for u in reqs if "search_data" in u])
        pg.screenshot(path=str(SHOTS / f"speed_home_{lang}.png"))
        # open a day that has matches: its lazy logos load on show, decoded, rendered at the same 26x26
        pg.evaluate("""() => document.querySelector('.daytab[data-day="2026-10-08"]').click()""")
        pg.wait_for_timeout(1500)
        r = pg.evaluate("""() => { const im=[...document.querySelectorAll('.daypanel.visible .match .side img')].slice(0,16);
          return {n: im.length, bad: im.filter(i => !(i.complete && i.naturalWidth > 0)).length,
                  sizes: [...new Set(im.map(i => { const b=i.getBoundingClientRect(); return Math.round(b.width)+'x'+Math.round(b.height); }))]}; }""")
        check(f"{lang} home: a day with matches -> logos load after switching tabs, none broken, rendered 26x26", r["n"] > 0 and r["bad"] == 0 and r["sizes"] == ["26x26"], r)
        pg.screenshot(path=str(SHOTS / f"speed_home_{lang}_day.png"))
        check(f"{lang} home: no console errors", not errs, errs[:3])
        ctx.close()

    # other pages must not pull search_data.js
    for url in ("/clubs/4531.html", "/matches/1644205.html", "/leagues.html", "/following.html", "/en/index.html"):
        ctx = ctx_of(br); pg = ctx.new_page(); seen = []
        pg.on("request", lambda r: seen.append(r.url))
        pg.goto(B + url, wait_until="networkidle")
        check(f"{url}: search_data.js not requested", not any("search_data" in u for u in seen), seen[:3])
        ctx.close()

    # search: tap the bottom-nav search button -> page opens focused; typing finds results from the first tap
    for lang, home, q, want in (("ar", "/index.html", "الفيصلي", "الفيصلي"), ("en", "/en/index.html", "Faisaly", "Faisaly")):
        ctx = ctx_of(br); pg = ctx.new_page(); seen = []
        pg.on("request", lambda r: seen.append(r.url))
        pg.goto(B + home, wait_until="networkidle")
        pg.tap('a[href$="search.html"]'); pg.wait_for_url("**/search.html"); pg.wait_for_load_state("networkidle")
        check(f"{lang} search: opened from the nav on first tap, input focused", pg.evaluate("document.activeElement && document.activeElement.id") == "q")
        pg.keyboard.type(q, delay=40); pg.wait_for_timeout(500)
        txt = pg.evaluate("document.getElementById('sbody').innerText")
        check(f"{lang} search: typing right away shows results", want in txt, txt[:120])
        check(f"{lang} search: search_data.js requested only here", sum("search_data" in u for u in seen) == 1, seen)
        pg.screenshot(path=str(SHOTS / f"speed_search_{lang}.png"))
        ctx.close()
        # slow data: loading message first, results when it arrives
        ctx = ctx_of(br); pg = ctx.new_page()
        held = []
        pg.route("**/search_data.js", lambda route: held.append(route))
        pg.goto(B + ("/search.html" if lang == "ar" else "/en/search.html"), wait_until="commit")
        pg.wait_for_selector("#q"); pg.keyboard.type(q, delay=30); pg.wait_for_timeout(400)
        msg = pg.evaluate("document.getElementById('sbody').innerText.trim()")
        check(f"{lang} search: before the data arrives a short loading message shows", msg in ("جاري التحميل…", "Loading…"), msg)
        pg.screenshot(path=str(SHOTS / f"speed_search_{lang}_loading.png"))
        for rt in held:
            rt.continue_()
        pg.wait_for_function("document.getElementById('sbody').innerText.includes(%s)" % json.dumps(want), timeout=15000)
        check(f"{lang} search: results appear once the data is ready", True)
        ctx.close()
    br.close()

print("FAILS:", fails)
sys.exit(1 if fails else 0)
