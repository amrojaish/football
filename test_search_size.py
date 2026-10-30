#!/usr/bin/env python3
"""
Smaller search index (30 Oct 2026, plan_search_size.md) — search results must stay IDENTICAL. Playwright + node, ar + en. Run:
    python C:\\Users\\User\\Projects\\Football\\test_search_size.py
Needs make_search.py + make_search_page.py run (assets/search_top.js, assets/search_full.js, search.html, en/search.html).

  1) slug parity: the page's own slug() (make_search_page.SLUG_JS, run by node) = player_slug.slug for EVERY row stored as «derive» (1)
  2) data identity: top (clubs + first TOP_N players) + full, decoded like the page does = make_search.collect() (the old
     search_data.js rows) — same rows, same order, same slugs
  3) old vs new: the OLD search page (frozen copy test_data/search_legacy/*.html, from commit 73addffce) fed the OLD single file built from
     today's data (collect()), against the NEW page — 30 AR/EN queries incl. hamza / ta-marbuta / alef-maqsura variants and 2-letter
     queries: the result list (kind, names, ids, slug, photo id, order) is identical
  4) sizes: top <= 16 KB gzip, top + full smaller than the old single file (raw and gzip); printed for the report
"""
import functools
import gzip
import http.server
import json
import re
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_search            # noqa: E402
from make_search_page import SLUG_JS   # noqa: E402
from player_slug import slug  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


def js_var(path, var):
    return json.loads(re.sub(r"^.*?window\." + var + "=", "", path.read_text(encoding="utf-8"), flags=re.S).rstrip().rstrip(";"))


top = js_var(ROOT / "assets" / "search_top.js", "FBSEARCH")
full = js_var(ROOT / "assets" / "search_full.js", "FBSEARCH_P")
clubs, players = make_search.collect()

# ── 1) slug parity (node runs the exact SLUG_JS string the page embeds) ──
derive = [p[1] for p in full if p[3] == 1]
node = subprocess.run(["node", "-e", SLUG_JS + ";const n=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                       "process.stdout.write(JSON.stringify(n.map(slug)))"],
                      input=json.dumps(derive), capture_output=True, text=True, encoding="utf-8")
js = json.loads(node.stdout or "[]")
bad = [(n, a, slug(n)) for n, a in zip(derive, js) if a != slug(n)]
check(f"slug parity: JS slug() = player_slug.slug for all {len(derive)} derived rows", len(js) == len(derive) and not bad, bad[:5] or node.stderr[-300:])

# ── 2) data identity ──
dec = lambda p: [p[0], p[1], p[2], slug(p[1]) if p[3] == 1 else (p[3] or ""), p[4] or 0]   # noqa: E731  (= dec() in the page)
check(f"full index decoded = the old rows exactly ({len(players)} players, same order)", [dec(p) for p in full] == [list(p) for p in players])
check(f"top index: all {len(clubs)} clubs = the old clubs list, players = the first {make_search.TOP_N} of the full list, n = total",
      top["c"] == [list(c) for c in clubs] and top["p"] == full[:make_search.TOP_N] and top["n"] == len(full))

# ── 3) old page + old data vs new page ──
LEG = ROOT / ".wrangler" / "tmp" / "search_legacy"
if LEG.exists():
    shutil.rmtree(LEG)
(LEG / "en").mkdir(parents=True)
(LEG / "search_data.js").write_text("window.FBSEARCH=" + json.dumps({"c": clubs, "p": players}, ensure_ascii=False,
                                                                   separators=(",", ":")) + ";\n", encoding="utf-8")
shutil.copy(ROOT / "test_data" / "search_legacy" / "ar.html", LEG / "search.html")       # UP="" -> search_data.js beside it
shutil.copy(ROOT / "test_data" / "search_legacy" / "en.html", LEG / "en" / "search.html")  # UP="../" -> the same file

QUERIES = ["احمد", "أحمد", "إبراهيم", "ابراهيم", "أسامة", "اسامه", "حمزة", "حمزه", "مصطفى", "مصطفي", "عبدالله", "عبد الله",
           "الهلال", "هلال", "الأهلي", "الاهلي", "النصر", "الترجي", "رجاء", "علي",
           "ali", "Mohamed", "salah", "Al Ahly", "ahly", "nassr", "ronaldo", "sal", "mo", "Tunis"]


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8797), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8797"


def run_all(pg, ready):
    pg.wait_for_function(ready, timeout=20000)
    out = {}
    for q in QUERIES:
        pg.fill("#q", ""); pg.fill("#q", q); pg.wait_for_timeout(120)
        out[q] = pg.evaluate("()=>[...document.querySelectorAll('#sbody .sp-item')].map(a=>a.dataset.rec)")
    return out


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, old_url, new_url in (("ar", "/.wrangler/tmp/search_legacy/search.html", "/search.html"),
                                   ("en", "/.wrangler/tmp/search_legacy/en/search.html", "/en/search.html")):
        res = {}
        for tag, url, ready in (("old", old_url, "window.FBSEARCH && document.readyState==='complete'"),
                                ("new", new_url, "window.FBSEARCH && window.FBSEARCH_P && document.readyState==='complete'")):
            ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            ctx.add_init_script("try{localStorage.clear();localStorage.setItem('fbSetupDone','1');}catch(e){}")
            pg = ctx.new_page()
            pg.goto(B + url, wait_until="load")
            if tag == "new":
                pg.fill("#q", "a")   # first keystroke starts the lazy full load (it also starts by itself ~1.2 s after load)
            res[tag] = run_all(pg, ready)
            ctx.close()
        diff = [q for q in QUERIES if res["old"][q] != res["new"][q]]
        n = sum(len(v) for v in res["new"].values())
        check(f"{lang}: 30 queries, old page + old data == new page ({n} result rows; every query has results: "
              f"{all(res['new'][q] for q in QUERIES)})", not diff and n > 0,
              {q: [len(res['old'][q]), len(res['new'][q])] for q in diff[:5]})
        empty = [q for q in QUERIES if not res["new"][q]]
        check(f"{lang}: every query returns something (hamza / ta-marbuta / alef-maqsura variants included)", not empty, empty)
        hv = [(a, b) for a, b in (("احمد", "أحمد"), ("إبراهيم", "ابراهيم"), ("أسامة", "اسامه"), ("حمزة", "حمزه"), ("مصطفى", "مصطفي"),
                                   ("الأهلي", "الاهلي")) if res["new"][a] != res["new"][b]]
        check(f"{lang}: spelling variants give the same results (أ/ا، ة/ه، ى/ي)", not hv, hv)
    br.close()
srv.shutdown()
shutil.rmtree(LEG, ignore_errors=True)

# ── 4) sizes ──
old = ("window.FBSEARCH=" + json.dumps({"c": clubs, "p": players}, ensure_ascii=False, separators=(",", ":")) + ";\n").encode("utf-8")
t_b, f_b = (ROOT / "assets" / "search_top.js").read_bytes(), (ROOT / "assets" / "search_full.js").read_bytes()
gz = lambda b: len(gzip.compress(b, 9))   # noqa: E731
print(f"SIZE old single file: raw {len(old)} gz {gz(old)} · top: raw {len(t_b)} gz {gz(t_b)} · full: raw {len(f_b)} gz {gz(f_b)}")
check("top index <= 16 KB gzip (first paint of the search page)", gz(t_b) <= 16 * 1024, gz(t_b))
check("top + full smaller than the old single file (raw and gzip)", len(t_b) + len(f_b) < len(old) and gz(t_b) + gz(f_b) < gz(old))

print("FAILS:", fails)
sys.exit(1 if fails else 0)
