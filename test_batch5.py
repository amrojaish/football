#!/usr/bin/env python3
"""
Batch 5 (30 Oct 2026) — player page FotMob layout, home Following star + match-row bell, match page order / stats summary /
mini table / team form. Playwright, ar + en, 390px (+ 360px overflow checks). Run:
    python C:\\Users\\User\\Projects\\Football\\test_batch5.py
Needs the site built (make_assets, make_site3, make_matches, make_players). Serves the repo on 127.0.0.1:8786, mocks the live worker.
Reads football.db (read-only) for expected values.

  1a header: round placeholder avatar (no player photo anywhere on the page), name, club pill with logo; Follow pill in the top bar
     (click -> "Following" + saved to fbPlayers)
  1b profile grid: only fields we have (no "-"), no preferred foot; values = player_info
  1c current league season card: league + season, Matches / Goals (+ Assists / Rating only when player_stats has them)
  1d matches tab: one row per played match, date + competition on top, opponent, W/D/L badge from the player's side, rating badge
  1e stats tab: season selector opens a sheet grouped by year; picking another season shows its card
  1f career tab: one row per (season, club); no "0" matches for a season without lineup data
  2  home Following header star is filled
  3  match-row bell: 12px, at the bottom of the row
  4+7 finished match: events -> stats summary -> mini table -> form -> info (vote last); upcoming page gone LIVE (mocked) reorders the same way
  5  form chips 56px wide, columns centred
  6  mini table: league logo + name header, PL W D L +/- GD PTS, 360px no overflow; LIVE (mocked 2-1): home dot green, away dot red
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test_data"))
from upcoming_match import upcoming_matches  # noqa: E402
from config import LEAGUES  # noqa: E402

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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8786), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8786"
LIVE = {"body": '{"t":0,"m":{}}'}
conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)


def page(br, url, w=390, init=""):
    ctx = br.new_context(viewport={"width": w, "height": 844}, service_workers="block")
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');" + init + "}catch(e){}")
    ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(
        status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"]))
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + url, wait_until="load")
    pg.wait_for_timeout(500)
    return ctx, pg, errs


RON = 874   # Cristiano Ronaldo (players/cristiano-ronaldo.html)
info = conn.execute("SELECT height_cm, birth_date, nationality, number, position FROM player_info WHERE player_id = ?", (RON,)).fetchone()
SAU_LATEST = conn.execute("SELECT MAX(season) FROM matches WHERE league_code='SAU'").fetchone()[0]
plays_cur = conn.execute("""SELECT COUNT(DISTINCT ps.match_id) FROM player_stats ps JOIN matches m ON m.match_id = ps.match_id
                            WHERE ps.player_id = ? AND m.league_code = 'SAU' AND m.season = ? AND ps.minutes > 0
                              AND m.home_goals IS NOT NULL""", (RON, SAU_LATEST)).fetchone()[0]

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        pre = "" if lang == "ar" else "/en"

        # ── 1: player page ──
        ctx, pg, errs = page(br, f"{pre}/players/cristiano-ronaldo.html")
        hd = pg.evaluate("""()=>({av:!!document.querySelector('.phd .pav svg'), photos:document.querySelectorAll('img[src*="media.api-sports.io/football/players"]').length,
            h1:(document.querySelector('.phd h1')||{}).textContent, pill:!!document.querySelector('.phd .pclub img'),
            fol:(document.querySelector('.appbar .pfol, header .pfol, .pfol')||{}).textContent})""")
        check(f"{lang} 1a: avatar placeholder, no player photo, name + club pill with logo, Follow pill",
              hd["av"] and hd["photos"] == 0 and hd["h1"] and hd["pill"] and hd["fol"], hd)
        pg.click(".pfol"); pg.wait_for_timeout(200)
        fol2 = pg.evaluate("()=>[document.querySelector('.pfol').textContent, JSON.parse(localStorage.getItem('fbPlayers')||'[]')]")
        check(f"{lang} 1a: Follow pill -> 'Following' text + saved", fol2[0] != hd["fol"] and "cristiano-ronaldo" in fol2[1], fol2)
        g = pg.evaluate("""()=>[...document.querySelectorAll('.pgrid .pgc')].map(c=>[c.querySelector('.v').textContent.trim(), c.querySelector('.k').textContent.trim()])""")
        txt = " ".join(v for v, _ in g)
        check(f"{lang} 1b: profile grid {len(g)} cells (<= 6), no '-' placeholder, height {info[0]} and shirt {info[3]} shown",
              0 < len(g) <= 6 and "-" not in [v for v, _ in g] and str(info[0]) in txt and str(info[3]) in [v for v, _ in g], g)
        foot = ("القدم" if lang == "ar" else "foot")
        check(f"{lang} 1b: no preferred-foot cell (no source for it)", not any(foot in k.lower() for _, k in g), g)
        cur = pg.evaluate("""()=>{const c=document.querySelector('.pscur');if(!c)return null;
            return {lg:c.querySelector('.pslg').textContent, img:!!c.querySelector('.pslg img'), v:[...c.querySelectorAll('.psv div')].map(d=>[d.querySelector('b').textContent,d.querySelector('span').textContent])}}""")
        check(f"{lang} 1c: current season card: league logo + name + season, Matches = {plays_cur}",
              cur and cur["img"] and "2026/27" in cur["lg"] and cur["v"][0][0] == str(plays_cur), cur)
        # 1d
        pg.click('.mtab[data-tab="matches"]'); pg.wait_for_timeout(300)
        mr = pg.evaluate("""()=>[...document.querySelectorAll('.pml2 .pmr')].slice(0,6).map(r=>({top:[...r.querySelectorAll('.pmt span')].map(s=>s.textContent),
            res:r.querySelector('.pmres').className, score:r.querySelector('.pmres').textContent, rt:!!r.querySelector('.prt'), href:r.getAttribute('href')}))""")
        nrows = pg.evaluate("()=>document.querySelectorAll('.pml2 .pmr').length")
        ok_res = True
        for r in mr:
            mid = int(re.search(r"(\d+)\.html", r["href"]).group(1))
            hm, aw, hg, ag = conn.execute("SELECT home_id, away_id, home_goals, away_goals FROM matches WHERE match_id = ?", (mid,)).fetchone()
            tm = conn.execute("SELECT team_id FROM player_stats WHERE match_id = ? AND player_id = ?", (mid, RON)).fetchone()[0]
            mine, opp = (hg, ag) if tm == hm else (ag, hg)
            want = "w" if mine > opp else ("l" if mine < opp else "d")
            ok_res &= r["res"].endswith(want) and r["score"] == f"{hg} - {ag}"
        check(f"{lang} 1d: {nrows} match rows, date + competition on top, W/D/L badge from his side, rating badge",
              nrows >= 10 and all(len(r["top"]) == 2 and r["top"][0] and r["top"][1] for r in mr) and ok_res and all(r["rt"] for r in mr), mr[:2])
        # 1e
        pg.click('.mtab[data-tab="stats"]'); pg.wait_for_timeout(300)
        s0 = pg.evaluate("()=>[document.getElementById('pselt').textContent, [...document.querySelectorAll('.pstc')].filter(c=>!c.hidden).length]")
        pg.click("#psel"); pg.wait_for_timeout(250)
        sh = pg.evaluate("""()=>({on:document.getElementById('pssh').classList.contains('on'), yrs:document.querySelectorAll('#pssh .yr').length,
            opts:[...document.querySelectorAll('#pssh button.opt')].map(o=>o.getAttribute('data-k'))})""")
        check(f"{lang} 1e: selector opens a sheet grouped by year ({sh['yrs']} years, {len(sh['opts'])} seasons)",
              sh["on"] and sh["yrs"] >= 3 and len(sh["opts"]) >= sh["yrs"] and s0[1] == 1, [s0, sh])
        pg.locator("#pssh button.opt").nth(1).click(); pg.wait_for_timeout(250)
        s1 = pg.evaluate("""()=>({t:document.getElementById('pselt').textContent, vis:[...document.querySelectorAll('.pstc')].filter(c=>!c.hidden).map(c=>c.getAttribute('data-k')),
            closed:!document.getElementById('pssh').classList.contains('on'),
            vals:[...document.querySelectorAll('.pstc:not([hidden]) .psv b')].map(b=>b.textContent)})""")
        check(f"{lang} 1e: picking another season shows its card only (no '-')",
              s1["closed"] and s1["vis"] == [sh["opts"][1]] and s1["t"] != s0[0] and "-" not in s1["vals"] and s1["vals"], s1)
        # 1f
        pg.click('.mtab[data-tab="career"]'); pg.wait_for_timeout(300)
        car = pg.evaluate("""()=>[...document.querySelectorAll('.pcar .pcr:not(.hd)')].map(r=>[r.querySelector('small').textContent, [...r.querySelectorAll('.c')].map(c=>c.textContent)])""")
        old = [r for r in car if r[0] == "2022/23"]
        check(f"{lang} 1f: career {len(car)} rows (season + club + columns); 2022/23 (no lineup data) has no '0' matches",
              len(car) >= 4 and old and old[0][1][0] == "", car)
        check(f"{lang} 1: no page errors (player)", not errs, errs)
        ctx.close()
        # a player page without player_id: no profile grid, no crash
        nopid = conn.execute("""SELECT 1""").fetchone()
        ctx, pg, errs = page(br, f"{pre}/players/r-aouani.html", w=360)
        ov = pg.evaluate("()=>document.documentElement.scrollWidth>document.documentElement.clientWidth")
        check(f"{lang} 1: 360px player page (R. Aouani): no horizontal overflow, no errors", not ov and not errs, [ov, errs])
        ctx.close()

        # ── 2 + 3: home ──
        ctx, pg, errs = page(br, f"{pre}/index.html", init="localStorage.setItem('fbClubs','[2939,2932,2934,2938]');")
        st = pg.evaluate("""()=>{const s=document.querySelector('.fstar');return s?getComputedStyle(s).fill:null}""")
        check(f"{lang} 2: Following star filled ({st})", st and st != "none", st)
        bl = pg.evaluate("""()=>{const b=[...document.querySelectorAll('.daypanel.visible .cbell')].find(x=>!x.hidden&&x.offsetParent);
            if(!b)return null;const r=b.getBoundingClientRect(),row=b.closest('.match').getBoundingClientRect(),s=b.querySelector('svg').getBoundingClientRect();
            return {w:Math.round(s.width), gap:Math.round(row.bottom-r.bottom), mid:Math.round((r.top+r.bottom)/2-(row.top+row.bottom)/2)}}""")
        check(f"{lang} 3: match-row bell 12px at the bottom of the row", bl is None or (bl["w"] <= 12 and bl["gap"] <= 8 and bl["mid"] > 0), bl)
        ctx.close()

        # ── 4-7: finished match ──
        for w in (390, 360):
            ctx, pg, errs = page(br, f"{pre}/matches/1603076.html", w=w)
            order = pg.evaluate("""()=>{const p=document.querySelector('.mp[data-tab="events"]');
                return [...p.children].map(c=>c.id==='evbox'?'events':(c.classList.contains('stsum')?'sum':c.classList.contains('ltpos')?'mini':
                c.classList.contains('tfcard')?'form':c.classList.contains('minfo')?'info':c.classList.contains('vote')||c.id==='vote'?'vote':''))
                .filter(Boolean)}""")
            want = ["events", "sum", "mini", "form", "info"]
            check(f"{lang} 4+7 @{w}: finished order = events -> stats summary -> mini table -> form -> info (vote last if shown)",
                  order[:5] == want and (len(order) == 5 or order[5] == "vote"), order)
            sm = pg.evaluate("""()=>{const s=document.querySelector('.stsum');return s?{bar:!!s.querySelector('.sspb'),rows:s.querySelectorAll('.ssr').length}:null}""")
            st = conn.execute("SELECT COUNT(*) FROM match_stats WHERE match_id=1603076 AND possession IS NOT NULL").fetchone()[0]
            check(f"{lang} 4 @{w}: stats summary: possession bar + shots + on target", sm and sm["bar"] == (st == 2) and sm["rows"] == 2, sm)
            mt = pg.evaluate("""()=>{const t=document.querySelector('.ltpos');const rows=[...t.querySelectorAll('.lprow')];
                return {hd:!!t.querySelector('.lphd img')&&t.querySelector('.lphd').textContent.trim().length>0, cols:t.querySelectorAll('.lph span').length,
                  n:rows.length, cells:rows.map(r=>r.children.length), over:rows.some(r=>r.scrollWidth>r.clientWidth+1),
                  page:document.documentElement.scrollWidth>document.documentElement.clientWidth}}""")
            check(f"{lang} 6 @{w}: mini table: league logo + name, 10 columns, 2 rows, no overflow",
                  mt["hd"] and mt["cols"] == 10 and mt["n"] == 2 and not mt["over"] and not mt["page"], mt)
            fm = pg.evaluate("""()=>{const c=document.querySelector('.tfcard');const ch=[...c.querySelectorAll('.tfp')].map(x=>Math.round(x.getBoundingClientRect().width));
                const cols=c.querySelector('.tfcols').getBoundingClientRect(),cc=[...c.querySelectorAll('.tfcol')].map(x=>x.getBoundingClientRect());
                return {w:[...new Set(ch)], left:Math.round(cc[0].left-c.getBoundingClientRect().left), right:Math.round(c.getBoundingClientRect().right-cc[cc.length-1].right),
                        mk:document.querySelectorAll('.tfcard .tfmk').length}}""")
            check(f"{lang} 5 @{w}: form chips all 56px, columns centred, latest-match underline kept",
                  fm["w"] == [56] and abs(fm["left"] - fm["right"]) <= 4 and fm["mk"] == 2, fm)
            check(f"{lang} 4-7 @{w}: no page errors", not errs, errs)
            ctx.close()

        # ── 4+7 / 6: upcoming page gone LIVE (mocked 2-1, minute 60) ──
        up = upcoming_matches(league="SAU")
        if not up:
            print("SKIP live checks: no upcoming SAU match built locally")
        else:
            mid, hid, aid = up[0][0], up[0][2], up[0][3]
            LIVE["body"] = json.dumps({"t": 0, "m": {str(mid): {"h": 2, "a": 1, "e": 60, "s": "2H", "th": hid, "ta": aid,
                                                                 "lg": LEAGUES["SAU"]["id"]}}})
            ctx, pg, errs = page(br, f"{pre}/matches/{mid}.html")
            pg.wait_for_timeout(2500)
            order = pg.evaluate("""()=>{const p=document.querySelector('.mp[data-tab="events"]');
                return [...p.children].map(c=>c.classList.contains('ltpos')?'mini':c.classList.contains('tfcard')?'form':c.classList.contains('minfo')?'info':
                c.classList.contains('vote')||c.id==='vote'||c.classList.contains('vcard')?'vote':'').filter(Boolean)}""")
            check(f"{lang} 4+7 live: page built upcoming reorders to mini table -> form -> info -> vote", order[:3] == ["mini", "form", "info"], order)
            dots = pg.evaluate("""()=>[...document.querySelectorAll('.ltpos .lprow')].map(r=>[r.getAttribute('data-side'), r.className,
                getComputedStyle(r.querySelector('.lpdot')).display])""")
            ok = {d[0]: d for d in dots}
            check(f"{lang} 6 live: dots shown, home (2-1 up) green, away red",
                  "h" in ok and "a" in ok and "lvw" in ok["h"][1] and "lvl" in ok["a"][1] and ok["h"][2] != "none", dots)
            check(f"{lang} live: no page errors", not errs, errs)
            ctx.close()
            LIVE["body"] = '{"t":0,"m":{}}'
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
