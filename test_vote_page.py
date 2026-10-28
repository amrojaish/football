#!/usr/bin/env python3
"""
«مين رح يفوز؟» card on the match page Preview (27 Oct 2026, vote_view.py) — Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_vote_page.py [screenshot_dir]
Needs make_assets.py + make_matches.py (the upcoming match below built). Serves the repo on 127.0.0.1:8781 and mocks the worker
(/votes, /vote) — no real D1. The clock is pinned before / after the match's kickoff.

  1) before voting: title, «Total votes: N», three bordered buttons (home logo / Draw / away logo)
  2) vote: POST {fixture, choice, device UUID}; results replace the buttons — %s sum to 100, the chosen side green
  3) device that already voted (fbVotes) -> results straight away, no buttons; a 409 reply also shows results with the server's choice
  4) after kickoff: results only (no buttons); 0 votes -> card hidden
  5) worker down / bad reply -> card hidden silently
  6) position (28 Oct 2026): before kickoff right under the tab heading; once started/finished the LAST block of the Events tab —
     at build time (a finished page), when opened after kickoff, when kickoff passes with the page open, and when live_view flips
     the page to live (worker payload says live while the clock is still before the scheduled kickoff) — all without a reload
"""
import functools
import http.server
import json
import re
import socketserver
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "vote_page"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8781), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8781"

# an upcoming built match page with a real kickoff time (data-ko on the card). Since 28 Oct 2026 finished pages carry the card too
# (bottom of Events), so "upcoming" = kickoff still in the future; the soonest one
MID, KO = None, None
_now = datetime.now(timezone.utc)
for f in sorted((ROOT / "matches").glob("*.html")):
    m = re.search(r'id="vote" data-fx="(\d+)" data-ko="([^"]+)"', f.read_text(encoding="utf-8", errors="ignore"))
    if m and not m.group(2).endswith("T23:59:00Z"):
        ko = datetime.fromisoformat(m.group(2).replace("Z", "+00:00"))
        if ko > _now and (KO is None or ko < KO):
            MID, KO = int(m.group(1)), ko
check("an upcoming match page with the vote card is built", MID is not None)
if MID is None:
    sys.exit(1)
BEFORE, AFTER = KO - timedelta(hours=3), KO + timedelta(minutes=20)

STATE = {}


def mock(ctx, totals, post_status=200, post_reply=None, fail_get=False, live=False):
    STATE.update(posts=[], totals=dict(totals))

    def votes(route):
        if fail_get:
            return route.fulfill(status=500, body="{}")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(STATE["totals"]))

    def vote(route):
        b = json.loads(route.request.post_data or "{}")
        STATE["posts"].append(b)
        if post_status == 200:
            t = STATE["totals"]; t[b["choice"]] += 1; t["total"] += 1
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "choice": b["choice"], **t}))
        route.fulfill(status=post_status, content_type="application/json", body=json.dumps(post_reply or {}))
    ctx.route("**/saffara-live.abujaishamr.workers.dev/votes?*", votes)
    ctx.route("**/saffara-live.abujaishamr.workers.dev/vote", vote)
    root = {"t": 0, "m": {str(MID): {"s": "1H", "e": 12, "h": 0, "a": 0}} if live else {}}
    # live_view polls SRC + "?_=<ms>" — the glob needs the query part, or the real worker answers
    for pat in ("**/saffara-live.abujaishamr.workers.dev/", "**/saffara-live.abujaishamr.workers.dev/?*"):
        ctx.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(root)))


def card(pg):
    return pg.evaluate("""()=>{const v=document.getElementById('vote'); if(!v) return null;
        const vis=e=>!!e && !e.hidden && e.offsetParent!==null;
        return {shown: vis(v), btns: vis(v.querySelector('.vbtns')), res: vis(v.querySelector('.vres')),
                n: v.querySelector('.vn').textContent, title: v.querySelector('.vtt').textContent,
                tot: v.querySelector('.vtot').textContent,
                pct: [...v.querySelectorAll('.vres .vb')].map(b=>[b.dataset.c, b.querySelector('.vp').textContent, b.classList.contains('me')]),
                draw: v.querySelector('.vbtns .vb[data-c="d"]').textContent,
                logos: v.querySelectorAll('.vbtns img').length,
                bordered: getComputedStyle(v.querySelector('.vbtns .vb')).borderTopWidth}}""")


def place(pg):
    """where the card sits in its tab panel: index among the panel's children, and whether it is the last one"""
    return pg.evaluate("""()=>{const v=document.getElementById('vote'); if(!v) return null; const p=v.closest('.mp')||v.parentNode;
        const k=[...p.children]; return {i: k.indexOf(v), last: p.lastElementChild===v, tab: p.dataset ? p.dataset.tab : null}}""")


def open_page(br, lang, when, totals, prior=None, **kw):
    ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    init = "try{localStorage.setItem('fbSetupDone','1');" + (f"localStorage.setItem('fbVotes',{json.dumps(json.dumps(prior))});" if prior else "") + "}catch(e){}"
    ctx.add_init_script(init)
    mock(ctx, totals, **kw)
    pg = ctx.new_page()
    pg.clock.set_fixed_time(when)
    pg.goto(f"{BASE}{'' if lang == 'ar' else '/en'}/matches/{MID}.html", wait_until="load")
    pg.wait_for_timeout(500)
    return ctx, pg


def total_pct(c):
    return sum(int(p[1].rstrip("%")) for p in c["pct"])


T0 = {"h": 3, "d": 1, "a": 2, "total": 6}
with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        title, totw, draw = (("مين رح يفوز؟", "مجموع الأصوات", "تعادل") if lang == "ar" else ("Who will win?", "Total votes", "Draw"))
        # 1) before voting
        ctx, pg = open_page(br, lang, BEFORE, T0)
        c = card(pg)
        check(f"{lang} 1: card shown with title, «{totw}: 6», 3 bordered buttons (2 logos + {draw})",
              c and c["shown"] and c["btns"] and not c["res"] and c["title"] == title and c["tot"].startswith(totw) and c["n"] == "6"
              and c["logos"] == 2 and draw in c["draw"] and c["bordered"] != "0px", c)
        pg.locator("#vote").scroll_into_view_if_needed()
        pg.screenshot(path=str(SHOTS / f"1_before_vote_{lang}.png"))
        # 2) vote home
        pg.locator('#vote .vbtns .vb[data-c="h"]').click()
        pg.wait_for_timeout(300)
        c = card(pg)
        post = STATE["posts"][0] if STATE["posts"] else {}
        check(f"{lang} 2: POST /vote {{fixture, choice h, device UUID}}", post.get("fixture") == MID and post.get("choice") == "h"
              and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", post.get("device", "")), post)
        check(f"{lang} 2: results replace the buttons, total 7, %s = 57/14/29 (sum 100), home highlighted",
              c["res"] and not c["btns"] and c["n"] == "7" and total_pct(c) == 100
              and [x[1] for x in c["pct"]] == ["57%", "14%", "29%"] and [x[2] for x in c["pct"]] == [True, False, False], c)
        stored = pg.evaluate("()=>[localStorage.getItem('fbDevice'), localStorage.getItem('fbVotes')]")
        check(f"{lang} 2: device id + choice kept in localStorage", stored[0] == post.get("device") and json.loads(stored[1]).get(str(MID)) == "h", stored)
        pg.screenshot(path=str(SHOTS / f"2_after_vote_{lang}.png"))
        pg.reload(wait_until="load"); pg.wait_for_timeout(400)
        c = card(pg)
        check(f"{lang} 3: reload -> results directly (this device voted), no buttons", c["res"] and not c["btns"] and c["pct"][0][2], c)
        ctx.close()
        # 3b) 409 from the server (localStorage was cleared, the server remembers the device)
        ctx, pg = open_page(br, lang, BEFORE, T0, post_status=409, post_reply={"error": "already voted", "choice": "a", **T0})
        pg.locator('#vote .vbtns .vb[data-c="d"]').click(); pg.wait_for_timeout(300)
        c = card(pg)
        check(f"{lang} 3b: 409 -> results with the server's choice (away) highlighted", c["res"] and [x[2] for x in c["pct"]] == [False, False, True], c)
        ctx.close()
        # 4) after kickoff: results only
        ctx, pg = open_page(br, lang, AFTER, T0)
        c = card(pg)
        check(f"{lang} 4: after kickoff -> results only (no buttons), sum 100, nothing highlighted", c["shown"] and c["res"] and not c["btns"]
              and total_pct(c) == 100 and not any(x[2] for x in c["pct"]), c)
        pg.locator("#vote").scroll_into_view_if_needed()
        pg.screenshot(path=str(SHOTS / f"4_after_kickoff_{lang}.png"))
        ctx.close()
        ctx, pg = open_page(br, lang, AFTER, {"h": 0, "d": 0, "a": 0, "total": 0})
        c = card(pg)
        check(f"{lang} 4: after kickoff with 0 votes -> card hidden", c and not c["shown"], c)
        ctx.close()
        # 4b) kickoff passes while the page is open -> buttons go, results stay
        ctx, pg = open_page(br, lang, KO - timedelta(seconds=2), T0)
        c1 = card(pg)
        pg.clock.set_fixed_time(KO + timedelta(seconds=5)); pg.wait_for_timeout(3200)
        c2 = card(pg)
        check(f"{lang} 4b: page open across kickoff -> buttons then results", c1["btns"] and c2["res"] and not c2["btns"], [c1, c2])
        ctx.close()
        # 6) position: top before kickoff, last block of the Events tab once started (no reload in any case)
        ctx, pg = open_page(br, lang, BEFORE, T0)
        p0 = place(pg)
        check(f"{lang} 6: before kickoff -> right under the tab heading (not last)", p0 and p0["i"] == 1 and not p0["last"] and p0["tab"] == "events", p0)
        ctx.close()
        ctx, pg = open_page(br, lang, AFTER, T0)
        p1 = place(pg)
        check(f"{lang} 6: opened after kickoff -> last block of the Events tab", p1 and p1["last"] and p1["tab"] == "events", p1)
        ctx.close()
        ctx, pg = open_page(br, lang, KO - timedelta(seconds=2), T0)
        pa = place(pg)
        pg.clock.set_fixed_time(KO + timedelta(seconds=5)); pg.wait_for_timeout(3200)
        pb = place(pg)
        check(f"{lang} 6: kickoff passes with the page open -> moves to the bottom", not pa["last"] and pb["last"], [pa, pb])
        ctx.close()
        ctx, pg = open_page(br, lang, BEFORE, T0, live=True)
        pg.wait_for_timeout(1500)
        pl = place(pg)
        check(f"{lang} 6: live_view flips the page to live (3 h before the scheduled kickoff) -> moves to the bottom", pl and pl["last"], pl)
        pg.screenshot(path=str(SHOTS / f"6_live_flip_{lang}.png"), full_page=True)
        ctx.close()
        # 5) worker failures
        ctx, pg = open_page(br, lang, BEFORE, T0, fail_get=True)
        c = card(pg)
        check(f"{lang} 5: GET /votes 500 -> card hidden", c and not c["shown"], c)
        ctx.close()
        ctx, pg = open_page(br, lang, BEFORE, T0, post_status=429, post_reply={"error": "rate_limited"})
        pg.locator('#vote .vbtns .vb[data-c="h"]').click(); pg.wait_for_timeout(300)
        c = card(pg)
        check(f"{lang} 5: POST 429 -> card hidden silently", c and not c["shown"], c)
        ctx.close()
    # 6) finished page (built after FT): the card is built as the LAST block of the Events tab
    fin = None
    for f in sorted((ROOT / "matches").glob("*.html"), reverse=True):
        h = f.read_text(encoding="utf-8", errors="ignore")
        if 'id="vote"' in h and 'id="evbox"' in h:
            fin = f.stem
            break
    check("a finished match page with events and the vote card is built", fin is not None)
    if fin:
        ctx = br.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page(); pg.goto(f"{BASE}/matches/{fin}.html")
        pf = place(pg)
        check(f"finished {fin}: vote card built as the last block of the Events tab (after the events list and form)",
              pf and pf["last"] and pf["tab"] == "events" and pg.evaluate("()=>!!document.querySelector('.mp[data-tab=\"events\"] #evbox')"), pf)
        ctx.close()
    # no JS: the card stays hidden
    ctx = br.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
    pg = ctx.new_page(); pg.goto(f"{BASE}/matches/{MID}.html")
    check("no JS -> card stays hidden", pg.evaluate("()=>document.getElementById('vote').hidden"))
    ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
