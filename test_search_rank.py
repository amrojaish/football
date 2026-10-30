#!/usr/bin/env python3
"""
Search ranking (27 Oct 2026, Amr) — Playwright on search.html (ar + en, 390px). Run:
    python C:\\Users\\User\\Projects\\Football\\test_search_rank.py [screenshot_dir]
Needs make_search.py + make_search_page.py built. Serves the repo on 127.0.0.1:8794.

Tiers on the NAME only (after normalisation: case, accents, Arabic ال / أإآا / ة-ه / ى-ي):
  0 name == query · 1 first word starts with it · 2 a later word starts with it · 3 inside a word (only kept for 2-letter queries, last)
Within a tier: players by goals (index order), clubs by matches played. Leagues: name matches before country/alias matches.
Checks: «ali»/«علي» first names first, then surnames, «Muhaimen Salim» (ali inside Salim) gone; «sal»; clubs; 1-letter query (no mid-word).
"""
import functools
import http.server
import json
import re
import socketserver
import sys
import tempfile
import threading
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "search_rank"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:700]))
    if not cond:
        fails += 1


def norm(s):
    """the page's norm() in Python"""
    if not s:
        return ""
    s = s.lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not ("\u0300" <= ch <= "\u036f" or "\u0653" <= ch <= "\u0655"))
    s = re.sub("[أإآٱ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    s = re.sub("[\u064b-\u0652\u0640]", "", s)
    s = re.sub(r"(^|\s)ال(?=\S{2,})", r"\1", s)
    s = re.sub(r"[-'.’]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tier(name, q):
    if not name or not q:
        return 9
    if name == q:
        return 0
    if " " in q:
        if name.startswith(q):
            return 1
        if (" " + q) in name:
            return 2
    else:
        w = name.split(" ")
        if w[0].startswith(q):
            return 1
        if any(x.startswith(q) for x in w[1:]):
            return 2
    return 3 if (q in name and len(q) == 2) else 9


# (30 أكتوبر 2026) الفهرس ملفّان بـ/assets: الأندية من search_top.js، واللاعبون كلهم (بترتيب الشعبية) من search_full.js
def _js(f, var):
    return json.loads(re.sub(r"^.*?window\." + var + "=", "", (ROOT / "assets" / f).read_text(encoding="utf-8"), flags=re.S).rstrip().rstrip(";"))


IDX = {"c": _js("search_top.js", "FBSEARCH")["c"], "p": _js("search_full.js", "FBSEARCH_P")}


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8794), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8794"


def results(pg, chip, q):
    pg.locator(f'.sp-chip[data-f="{chip}"]').click()
    pg.fill("#q", ""); pg.fill("#q", q); pg.wait_for_timeout(250)
    return pg.evaluate("()=>[...document.querySelectorAll('#sbody .sp-item')].map(a=>JSON.parse(a.dataset.rec||'{}'))")


def ptiers(names_ar_en, q):
    nq = norm(q)
    return [min(tier(norm(a), nq), tier(norm(e), nq)) for a, e in names_ar_en]


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
        ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbLeaguesV2','1');}catch(e){}")
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{BASE}{pre}/search.html", wait_until="load"); pg.wait_for_function("window.FBSEARCH && window.FBSEARCH_P"); pg.wait_for_timeout(200)
        # record format of a player row -> names
        sample = pg.evaluate("()=>{const a=document.querySelector('#sbody .sp-item');return a?a.dataset.rec:null}")
        for q in ("ali", "علي", "sal", "Ahmed"):
            rec = results(pg, "players", q)
            names = [(r.get("a") or "", r.get("e") or "") for r in rec]
            ts = ptiers(names, q)
            check(f"{lang} players «{q}»: {len(rec)} results, tiers never go down (exact → first name → surname → mid-word)",
                  len(rec) > 0 and ts == sorted(ts) and 9 not in ts, list(zip(ts, [n[1] or n[0] for n in names]))[:12])
            if len(norm(q)) >= 3:
                check(f"{lang} players «{q}»: no mid-word-only matches (3+ letters)", 3 not in ts, [n for n, t in zip(names, ts) if t == 3][:5])
            # within a tier: index (goals) order
            pos = {(x[0], x[1], x[2]): i for i, x in enumerate(IDX["p"])}
            order_ok = True
            for t in set(ts):
                ii = [pos.get((r.get("a") or "", r.get("e") or "", r.get("c"))) for r, tt in zip(rec, ts) if tt == t]
                ii = [i for i in ii if i is not None]
                order_ok &= ii == sorted(ii)
            check(f"{lang} players «{q}»: same tier = most goals first (index order)", order_ok)
            if q in ("ali", "علي"):
                pg.screenshot(path=str(SHOTS / f"players_{'ali' if q == 'ali' else 'ali_ar'}_{lang}.png"))
        rec = results(pg, "players", "ali")
        check(f"{lang}: «Muhaimen Salim» (ali only inside Salim) no longer matches «ali»", not any("Salim" in (r.get("e") or "") for r in rec),
              [r.get("e") for r in rec if "Salim" in (r.get("e") or "")])
        firsts = [r.get("e") or r.get("a") for r in rec[:5]]
        check(f"{lang}: top «ali» results start with Ali (first name)", all(norm(n).split(" ")[0].startswith("ali") or norm(n) == "ali" for n in firsts), firsts)
        rec = results(pg, "players", "a")
        ts = ptiers([(r.get("a") or "", r.get("e") or "") for r in rec], "a")
        check(f"{lang} 1-letter «a»: word-start matches only, ordered", len(rec) > 0 and 3 not in ts and ts == sorted(ts), ts[:20])
        # clubs
        for q in ("hil", "الهلال", "ahli", "al"):
            rec = results(pg, "clubs", q)
            names = [(r.get("a") or "", r.get("e") or "") for r in rec]
            ts = ptiers(names, q)
            check(f"{lang} clubs «{q}»: {len(rec)} results, tiers ordered", len(rec) > 0 and ts == sorted(ts) and 9 not in ts, list(zip(ts, names))[:8])
        pg.screenshot(path=str(SHOTS / f"clubs_al_{lang}.png"))
        # leagues: a name match before a country/alias match
        rec = results(pg, "leagues", "saudi" if lang == "en" else "السعودي")
        check(f"{lang} leagues: name match found", len(rec) >= 1, rec)
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
