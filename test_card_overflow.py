#!/usr/bin/env python3
"""
Match-card name overflow (360px and 390px, ar + en): no club name outside its card, no clipped logo, no horizontal
page scroll, names wrap to at most 2 lines (then an ellipsis), fonts never below 13px.

1) a harness page built from the REAL `make_site3.match_card` + `STYLE` pairs the 15 longest club names (Arabic card
   names = short_name_ar, English = official name) on both sides of a card and in worst-case long-vs-long pairs;
2) real pages: home (day tab with Moroccan matches), club page, league page, following.

Needs the site built and served from the repo root (python -m http.server 8765).
Run: python test_card_overflow.py [screenshot_dir] [prefix]      e.g.  ... scratch before   |   ... scratch after
Exit code 1 if any card breaks the rules.
"""
import json
import sqlite3
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import make_site3 as ms  # noqa: E402
from config import DB_FILE  # noqa: E402

B = "http://127.0.0.1:8765"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "cards"
WIDTHS = (360, 390)
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " " + json.dumps(extra, ensure_ascii=False, default=str)[:700]))
    if not cond:
        fails += 1


def teams():
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    rows = con.execute("SELECT team_id, league_code, short_name_ar, COALESCE(NULLIF(name_en_official,''), name_en) FROM teams").fetchall()
    con.close()
    return rows


def harness(lang):
    """cards with the longest names: long-vs-short, short-vs-long, long-vs-long (worst case)"""
    rows = teams()
    key = (lambda r: len(r[2] or "")) if lang == "ar" else (lambda r: len(r[3] or ""))
    longest = sorted(rows, key=lambda r: -key(r))[:15]
    short = sorted(rows, key=key)[:3]
    cards, n = [], 0

    def mk(h, a, played):
        nonlocal n
        n += 1
        m = {"match_id": 9000000 + n, "date": "2026-10-08 20:00", "home_goals": 2 if played else None, "away_goals": 1 if played else None,
             "league_code": h[1], "season": 2026, "status": "FT" if played else "NS",
             "home_id": h[0], "home": h[2], "home_en": h[3], "home_logo": "", "away_id": a[0], "away": a[2], "away_en": a[3], "away_logo": ""}

        class R(dict):
            def keys(self):
                return list(dict.keys(self))
        logos = {str(h[0]): f"/thumbs/{h[0]}.webp", str(a[0]): f"/thumbs/{a[0]}.webp"}
        return ms.match_card(R(m), lang, logos, show_league=False, upcoming=not played, club_ids=True, thumbs=False)

    for i, r in enumerate(longest):
        s = short[i % 3]
        cards.append(mk(r, s, False))          # long on the home side
        cards.append(mk(s, r, True))           # long on the away side
        cards.append(mk(r, longest[(i + 1) % 15], i % 2 == 0))   # long vs long
    t = ms.T[lang]
    html = (f'<!DOCTYPE html><html lang="{lang}" dir="{ms.DIR[lang]}"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">' + ms.THEME_HEAD + ms.STYLE + '</head><body><div class="wrap">'
            '<details class="lgsec" open><summary><span class="lgname">harness</span></summary><div class="lgbody">'
            + "".join(cards).replace(" UTC</div>", "</div>") + '</div></details></div></body></html>')
    out = ROOT / ".wrangler" / "tmp"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"card_harness_{lang}.html").write_text(html, encoding="utf-8")
    return longest, key


SCAN = """() => {
  const near = (a, b) => a >= b - 0.5;
  const bad = [], names = [];
  const cards = [...document.querySelectorAll('.match')].filter(c => c.getBoundingClientRect().width > 0);
  cards.forEach((c, idx) => {
    const cr = c.getBoundingClientRect();
    const inside = (el, what) => { const r = el.getBoundingClientRect(); if (r.width === 0) return;
      if (!(near(r.left, cr.left) && near(cr.right, r.right) && near(r.top, cr.top) && near(cr.bottom, r.bottom))) bad.push([idx, what, Math.round(r.left - cr.left), Math.round(cr.right - r.right)]); };
    c.querySelectorAll('.side').forEach(side => {
      inside(side, 'side');
      const img = side.querySelector('img'), sp = side.querySelector('span');
      if (img) { inside(img, 'logo'); const ir = img.getBoundingClientRect();
        const want = parseFloat(getComputedStyle(img).width);
        if (ir.width < 23.5 || ir.height < 23.5) bad.push([idx, 'logo-shrunk', Math.round(ir.width), Math.round(ir.height)]); }
      if (sp) { inside(sp, 'name'); const cs = getComputedStyle(sp); const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.25;
        const lines = Math.round(sp.scrollHeight / lh), fs = parseFloat(cs.fontSize);
        const clipped = sp.scrollHeight > sp.clientHeight + 1 || sp.scrollWidth > sp.clientWidth + 1;
        if (fs < 13) bad.push([idx, 'font<13', fs]);
        names.push({card: idx, text: sp.textContent.trim(), lines, shown: Math.round(sp.clientHeight / lh), clipped, fs, w: Math.round(sp.getBoundingClientRect().width)}); }
    });
    const sc = c.querySelector('.score'); if (sc) inside(sc, 'score');
  });
  return {n: cards.length, bad, names, hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
          sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth};
}"""


def ctx_of(br, w):
    return br.new_context(viewport={"width": w, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, user_agent=UA)


def report(tag, r):
    ok = r["n"] > 0 and not r["bad"] and not r["hscroll"]
    check(f"{tag}: {r['n']} cards, none outside / logo intact / font>=13px, no horizontal scroll", ok,
          {"bad": r["bad"][:6], "hscroll": r["hscroll"], "sw": r["sw"], "cw": r["cw"]})
    two = [x for x in r["names"] if x["lines"] > 2 and not x["clipped"]]
    check(f"{tag}: names never exceed 2 lines (3+ lines would be clamped with an ellipsis)", not [x for x in r["names"] if x["shown"] > 2], [x for x in r["names"] if x["shown"] > 2][:3])


table = {}
with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        longest, key = harness(lang)
        for w in WIDTHS:
            ctx = ctx_of(br, w); pg = ctx.new_page()
            pg.goto(f"{B}/.wrangler/tmp/card_harness_{lang}.html", wait_until="networkidle"); pg.wait_for_timeout(500)
            r = pg.evaluate(SCAN)
            report(f"harness {lang} {w}px", r)
            pg.screenshot(path=str(SHOTS / f"{PREFIX}_harness_{lang}_{w}.png"), full_page=True)
            by = {}
            for x in r["names"]:
                by.setdefault(x["text"], []).append(x)
            for row in longest:
                nm = (row[2] if lang == "ar" else row[3])
                xs = by.get(nm, [])
                real = [x for x in xs if x["card"] % 3 != 2]      # long-vs-short cards (name on the home / on the away side)
                worst = [x for x in xs if x["card"] % 3 == 2]     # long-vs-long
                table[(lang, w, nm)] = (max((x["shown"] for x in real), default=0), any(x["clipped"] for x in real),
                                        any(x["clipped"] for x in worst), min((x["fs"] for x in xs), default=0))
            ctx.close()
    # real pages
    for lang, pre in (("ar", ""), ("en", "/en")):
        for w in WIDTHS:
            ctx = ctx_of(br, w); pg = ctx.new_page()
            pg.goto(f"{B}{pre}/index.html", wait_until="networkidle"); pg.wait_for_timeout(500)
            pg.evaluate("""() => document.querySelector('.daytab[data-day="2026-10-08"]').click()"""); pg.wait_for_timeout(600)
            report(f"home 8 Oct {lang} {w}px", pg.evaluate(SCAN))
            pg.screenshot(path=str(SHOTS / f"{PREFIX}_home_{lang}_{w}.png"))
            for url, label in ((f"{pre}/clubs/962.html", "club 962"), (f"{pre}/clubs/25058.html", "club 25058"), (f"{pre}/leagues/mar.html", "league MAR")):
                pg.goto(B + url, wait_until="networkidle"); pg.wait_for_timeout(500)
                # season/inner tabs hide most cards: show them all so every card is measured
                pg.add_style_tag(content=".spanel,.iview,.panel{display:block!important}.match.hidden{display:grid!important}")
                pg.wait_for_timeout(200)
                report(f"{label} {lang} {w}px", pg.evaluate(SCAN))
                if label == "club 962":
                    pg.screenshot(path=str(SHOTS / f"{PREFIX}_club_{lang}_{w}.png"))
            ctx.close()
            ctx = ctx_of(br, w)
            ctx.add_init_script("localStorage.setItem('fbClubs', JSON.stringify([962,1074,15570,18036,2870,25058]))")
            pg = ctx.new_page(); pg.goto(f"{B}{pre}/following.html", wait_until="networkidle"); pg.wait_for_timeout(800)
            r = pg.evaluate("""() => { const bad=[]; document.querySelectorAll('.fcard').forEach((c,i)=>{ const cr=c.getBoundingClientRect();
                c.querySelectorAll('*').forEach(e=>{ const r=e.getBoundingClientRect(); if(r.width&&(r.left<cr.left-0.5||r.right>cr.right+0.5)) bad.push([i,e.className]); }); });
                return {n: document.querySelectorAll('.fcard').length, bad, hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth}; }""")
            check(f"following {lang} {w}px: {r['n']} tiles, nothing outside a tile, no horizontal scroll", r["n"] > 0 and not r["bad"] and not r["hscroll"], r)
            pg.screenshot(path=str(SHOTS / f"{PREFIX}_following_{lang}_{w}.png"))
            ctx.close()
    # settings: language value looks like a button
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = ctx_of(br, 390); pg = ctx.new_page()
        pg.goto(f"{B}{pre}/index.html", wait_until="networkidle")
        pg.evaluate("document.getElementById('sovl2').classList.add('on')"); pg.wait_for_timeout(300)
        pg.screenshot(path=str(SHOTS / f"{PREFIX}_settings_{lang}.png"))
        ctx.close()
    br.close()

print("\nlongest names: lines shown / ellipsis in a normal card (long vs short) / ellipsis in the worst case (long vs long) / font:")
for (lang, w, nm), (lines, clipped, wclip, fs) in sorted(table.items(), key=lambda kv: (kv[0][0], kv[0][1])):
    print(f"  {lang} {w}px  {nm:28s} lines={lines} ellipsis={'yes' if clipped else 'no ':3s} worst-case-ellipsis={'yes' if wclip else 'no'} font={fs}px")
print("FAILS:", fails)
sys.exit(1 if fails else 0)
