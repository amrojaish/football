#!/usr/bin/env python3
"""
Batch 6 (30 Oct 2026) — match page lineups / coach + bench / icon legend / red cards / SAU zones / header / live table dot /
live stats / H2H summary / season card header. Playwright, ar + en, 390px (+ 360px overflow checks). Run:
    python C:\\Users\\User\\Projects\\Football\\test_batch6.py
Needs the site built (make_assets, make_site3, make_leagues, make_matches). Serves the repo on 127.0.0.1:8787, mocks the live worker.
Reads football.db (read-only) for expected values.

  1  lineups: no "Official lineups" pill; team bar (logo + name + formation) full width outside the pitch; rating badge colours
     green >= 7, orange 6-6.9, red < 6 (values = player_stats.rating)
  2  coach card (both coaches) + bench card in two columns (avatar, number + name, position, sub-in minute)
  3  icon legend at the bottom: two columns, only icons used in this page's events
  4  red card mark next to the score in league rows + match header (static from events; LIVE from worker v)
  5  SAU 2026 zones: 1-3 cl, 4-5 clq, 6 cl2, 7-8 reg, 16-18 rel; legend 5 entries
  6  match header: no box (transparent background, no border)
  7  live table dot: 8px, green winning / red losing / grey drawing (mocked live)
  8  live stats card from worker st (mocked): possession bar + shots + on target + corners
  9  H2H: date at the start, league at the end; 3 pills in team colours (grey draws) + bar in the same colours
 10  season-so-far: league logo + bold name as the middle of the header row
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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8787), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8787"
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


RED = 1603078   # Al-Shabab 6-1 Al-Ahli (SAU 2026, 30 Oct): one red card for Al-Ahli, lineups + ratings + H2H
hm, aw = conn.execute("SELECT home_id, away_id FROM matches WHERE match_id = ?", (RED,)).fetchone()
reds = dict(conn.execute("SELECT team_id, COUNT(*) FROM events WHERE match_id = ? AND type='Card' AND detail='Red Card' GROUP BY team_id",
                         (RED,)).fetchall())
ratings = [r[0] for r in conn.execute("SELECT rating FROM player_stats WHERE match_id = ? AND rating IS NOT NULL", (RED,))]
coaches = conn.execute("SELECT COUNT(*) FROM lineups WHERE match_id = ? AND coach_name IS NOT NULL AND coach_name != ''", (RED,)).fetchone()[0] \
    if "coach_name" in [c[1] for c in conn.execute("PRAGMA table_info(lineups)")] else None
used_types = {r[0] for r in conn.execute("SELECT DISTINCT type FROM events WHERE match_id = ?", (RED,))}
WANT_Z = {**{i: "cl" for i in (1, 2, 3)}, 4: "clq", 5: "clq", 6: "cl2", 7: "reg", 8: "reg", 16: "rel", 17: "rel", 18: "rel"}


def cls_of(r):
    return "hi" if r >= 7 else ("mid" if r >= 6 else "lo")


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        pre = "" if lang == "ar" else "/en"
        for w in (390, 360):
            ctx, pg, errs = page(br, f"{pre}/matches/{RED}.html", w=w)
            # 6 header
            hd = pg.evaluate("""()=>{const h=document.querySelector('.head');const s=getComputedStyle(h);
                return {bg:s.backgroundColor, bw:s.borderTopWidth, sh:s.boxShadow}}""")
            check(f"{lang} 6 @{w}: header has no box (transparent bg, no border, no shadow)",
                  hd["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and hd["bw"] == "0px" and hd["sh"] == "none", hd)
            # 4 header red mark
            hr = pg.evaluate("()=>[...document.querySelectorAll('.head .team > span')].map(s=>s.querySelectorAll('.rcm').length)")
            check(f"{lang} 4 @{w}: header red mark only on the side with a red card ({reds})",
                  hr == [1 if reds.get(hm) else 0, 1 if reds.get(aw) else 0], hr)
            # 3 legend
            lg = pg.evaluate("""()=>{const l=document.querySelector('.iclg');if(!l)return null;const g=l.querySelector('.iclgg');
                const it=[...l.querySelectorAll('.lgi')];const xs=new Set(it.map(i=>Math.round(i.getBoundingClientRect().left)));
                return {n:it.length, cols:getComputedStyle(g).gridTemplateColumns.split(' ').length, x:xs.size, ic:it.map(i=>i.querySelector('.lgic').textContent), sub:l.querySelectorAll('.lgic .sr').length,
                  last:l===document.querySelector('main')?.lastElementChild || !l.nextElementSibling || l.nextElementSibling.tagName==='SCRIPT'}}""")
            ics = pg.evaluate("()=>[...new Set([...document.querySelectorAll('#evbox .eicon, #evbox .ic, #evbox [class*=icon]')].map(e=>e.textContent.trim()).filter(Boolean))]")
            check(f"{lang} 3 @{w}: icon legend, two columns, {lg and lg['n']} icons, all from events",
                  lg and lg["cols"] == 2 and lg["x"] == 2 and lg["n"] >= 3 and "⚽" in lg["ic"] and "🟥" in lg["ic"]
                  and (lg["sub"] == 2) == ("subst" in used_types) and ("📺" in lg["ic"]) == ("Var" in used_types), [lg, ics])
            # 1 + 2 lineups
            pg.click('.mtab[data-tab="lineups"]'); pg.wait_for_timeout(300)
            lu = pg.evaluate("""()=>{const p=document.querySelector('.mp[data-tab="lineups"]');const pit=p.querySelector('.fpitch');
                const bars=[...p.querySelectorAll('.fpt')];const pr=pit.getBoundingClientRect();
                return {badge:p.querySelectorAll('.lubadge').length, txt:p.textContent.includes('Official lineups')||p.textContent.includes('التشكيلة الرسمية'),
                  bars:bars.map(b=>({img:!!b.querySelector('img'), txt:b.textContent.trim(), w:Math.round(b.getBoundingClientRect().width), inside:pit.contains(b),
                    top:b.getBoundingClientRect().top<pr.top})), pw:Math.round(pr.width),
                  rt:[...p.querySelectorAll('.fi.r')].map(r=>[parseFloat(r.textContent), r.classList.contains('hi')?'hi':r.classList.contains('mid')?'mid':r.classList.contains('lo')?'lo':'', getComputedStyle(r).backgroundColor])}}""")
            check(f"{lang} 1 @{w}: no 'Official lineups' pill", lu["badge"] == 0 and not lu["txt"], lu["badge"])
            check(f"{lang} 1 @{w}: 2 team bars (logo + name + formation) full width, above/below the pitch, outside it",
                  len(lu["bars"]) == 2 and all(b["img"] and re.search(r"\d-\d", b["txt"]) and not b["inside"] and abs(b["w"] - lu["pw"]) <= 2 for b in lu["bars"])
                  and lu["bars"][0]["top"] and not lu["bars"][1]["top"], lu["bars"])
            bad = [r for r in lu["rt"] if r[1] != cls_of(r[0])]
            cols = {r[1]: r[2] for r in lu["rt"]}
            check(f"{lang} 1 @{w}: {len(lu['rt'])} rating badges coloured >=7 green / 6-6.9 orange / <6 red ({len(ratings)} ratings in DB)",
                  lu["rt"] and not bad and len(set(cols.values())) == len(cols) and len(lu["rt"]) <= len(ratings), [bad[:3], cols])
            cb = pg.evaluate("""()=>{const c=document.querySelector('.lucoachc'),b=document.querySelector('.lubench');
                if(!c||!b)return null;const it=[...b.querySelectorAll('.lup')];const xs=new Set(it.map(i=>Math.round(i.getBoundingClientRect().left)));
                return {co:c.querySelectorAll('.lup').length, coav:c.querySelectorAll('.lup .av svg').length, n:it.length, x:xs.size,
                  num:it.every(i=>/^\\d+ · /.test(i.querySelector('.tx b').textContent)), pos:it.filter(i=>i.querySelector('.tx small')&&i.querySelector('.tx small').textContent.trim()).length,
                  ins:it.filter(i=>i.querySelector('.in')).map(i=>i.querySelector('.in').textContent.trim())}}""")
            nsub_in = conn.execute("SELECT COUNT(*) FROM events WHERE match_id = ? AND type='subst'", (RED,)).fetchone()[0]
            check(f"{lang} 2 @{w}: coach card (2 coaches, avatars) + bench in 2 columns ({cb and cb['n']} players, {cb and len(cb['ins'])} sub-ins of {nsub_in})",
                  cb and cb["co"] == 2 and cb["coav"] == 2 and cb["x"] == 2 and cb["n"] >= 10 and cb["num"] and cb["pos"] >= cb["n"] - 2
                  and len(cb["ins"]) == nsub_in and all(re.match(r"^\d+'", s) for s in cb["ins"]), cb)
            # 9 + 10
            pg.click('.mtab[data-tab="h2h"]'); pg.wait_for_timeout(300)
            h2 = pg.evaluate("""()=>{const s=document.querySelector('.h2hsum');if(!s)return null;
                const pills=[...s.querySelectorAll('.h2hp')].map(p=>[p.textContent, getComputedStyle(p).backgroundColor]);
                const bar=[...document.querySelectorAll('.h2hbar span')].map(b=>getComputedStyle(b).backgroundColor);
                const meta=[...document.querySelectorAll('.h2hmeta')].slice(0,3).map(m=>{const sp=m.querySelectorAll(':scope > span');
                  const r=m.getBoundingClientRect(),a=sp[0].getBoundingClientRect(),b=sp[1].getBoundingClientRect();
                  return {d:sp[0].textContent, lg:sp[1].textContent, n:sp.length, startGap:Math.round(document.dir==='rtl'?r.right-a.right:a.left-r.left),
                          endGap:Math.round(document.dir==='rtl'?b.left-r.left:r.right-b.right)}});
                return {pills, bar, meta}}""")
            ok_meta = h2 and all(m["n"] == 2 and re.fullmatch(r"\d{4}-\d\d-\d\d", m["d"]) and m["lg"] and m["startGap"] <= 2 and m["endGap"] <= 2 for m in h2["meta"])
            check(f"{lang} 9 @{w}: H2H rows: date only at the start, league at the end", ok_meta, h2 and h2["meta"])
            check(f"{lang} 9 @{w}: 3 pills (home / draws grey / away) in the same colours as the bar below",
                  h2 and len(h2["pills"]) == 3 and [c for _, c in h2["pills"]] == h2["bar"] and h2["pills"][1][1] == "rgb(107, 114, 128)"
                  and h2["pills"][0][1] != h2["pills"][2][1], h2)
            ss = pg.evaluate("""()=>{const h=document.querySelector('.ssfh');if(!h)return null;const c=h.querySelector('.ssfc');
                const k=[...h.children].map(x=>x.getBoundingClientRect());const b=c&&c.querySelector('b');
                return {mid:!!c&&h.children[1]===c, img:!!(c&&c.querySelector('img')), fw:b?getComputedStyle(b).fontWeight:null, fs:b?parseFloat(getComputedStyle(b).fontSize):0,
                  txt:b?b.textContent:'', centred:c?Math.abs((k[1].left+k[1].right)/2-(h.getBoundingClientRect().left+h.getBoundingClientRect().right)/2)<=4:false}}""")
            check(f"{lang} 10 @{w}: season card header row: logos at the ends, league logo + bold bigger name centred",
                  ss and ss["mid"] and ss["img"] and int(ss["fw"]) >= 700 and ss["fs"] >= 14 and ss["txt"] and ss["centred"], ss)
            ov = pg.evaluate("()=>document.documentElement.scrollWidth>document.documentElement.clientWidth")
            check(f"{lang} @{w}: match page no horizontal overflow, no page errors", not ov and not errs, [ov, errs])
            ctx.close()

        # ── 4 league row + 5 zones ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        zs = pg.evaluate("""()=>{const t=document.querySelector('table.lt, .standings table, table');
            return [...t.querySelectorAll('tr')].filter(r=>r.querySelector('td')&&/^\\d+$/.test(r.querySelector('td').textContent.trim()))
              .map(r=>[parseInt(r.querySelector('td').textContent),(r.className.match(/z-(\\w+)/)||[])[1]||''])}""")
        got = {i: z for i, z in zs if z}
        check(f"{lang} 5: SAU 2026 zones 1-3 cl / 4-5 clq / 6 cl2 / 7-8 reg / 16-18 rel", got == WANT_Z, got)
        leg = pg.evaluate("()=>[...document.querySelectorAll('.zleg .zli')].map(z=>z.textContent.trim())")
        want_leg = (["دوري أبطال آسيا للنخبة", "دوري أبطال آسيا للنخبة – الملحق", "دوري أبطال آسيا 2", "دوري أبطال الخليج للأندية", "الهبوط"] if lang == "ar"
                    else ["AFC Champions League Elite", "AFC Champions League Elite – play-off", "AFC Champions League Two", "Gulf Club Champions League", "Relegation"])
        check(f"{lang} 5: zone legend (5 entries, {lang})", leg == want_leg, leg)
        pg.click('.cattabs .tab[data-cat="matches"]'); pg.wait_for_timeout(400)
        rr = pg.evaluate(f"""()=>{{const c=document.querySelector('.match[data-mid="{RED}"] .score');if(!c)return null;
            const k=[...c.childNodes].map(n=>n.nodeType===1&&n.classList.contains('rcm')?'R':(n.textContent.trim()?'S':'')).filter(Boolean).join('');
            const r=c.querySelector('.rcm');return {{k, w:r?Math.round(r.getBoundingClientRect().width):0}}}}""")
        check(f"{lang} 4: league row red mark on the away side of the score ({rr})", rr and rr["k"] == "SR" and 0 < rr["w"] <= 14, rr)
        check(f"{lang} 4-5: no page errors (league)", not errs, errs)
        ctx.close()

        # ── LIVE (mocked): 4 live red, 7 table dot, 8 live stats ──
        up = upcoming_matches(league="SAU")
        if not up:
            print("SKIP live checks: no upcoming SAU match built locally")
            continue
        mid, hid, aid = up[0][0], up[0][2], up[0][3]
        LIVE["body"] = json.dumps({"t": 0, "ve": 1,
                                   "m": {str(mid): {"h": 2, "a": 1, "e": 60, "s": "2H", "th": hid, "ta": aid, "lg": LEAGUES["SAU"]["id"]}},
                                   "v": {str(mid): [[30, 0, "c", "r", "X", "", "a", None, None], [50, 0, "c", "yr", "Y", "", "a", None, None]]},
                                   "st": {str(mid): {"t": 0, "h": [58, 12, 5, 6], "a": [42, 7, 2, 3]}}})
        ctx, pg, errs = page(br, f"{pre}/matches/{mid}.html")
        pg.wait_for_timeout(2500)
        sm = pg.evaluate("""()=>{const s=document.querySelector('.mp[data-tab="events"] .stsum');if(!s)return null;
            return {bar:[...s.querySelectorAll('.sspb span')].map(x=>x.textContent), rows:[...s.querySelectorAll('.ssr')].map(r=>[...r.children].map(c=>c.textContent))}}""")
        check(f"{lang} 8 live: stats card (possession 58/42, shots, on target, corners)",
              sm and sm["bar"] == ["58%", "42%"] and len(sm["rows"]) == 3 and sm["rows"][0][0] == "12" and sm["rows"][2][2] == "3", sm)
        hr = pg.evaluate("()=>[...document.querySelectorAll('.head .team > span')].map(s=>s.querySelector('.rcm')?(s.querySelector('.rcm b')||{}).textContent||'1':'')")
        check(f"{lang} 4 live: header red mark on the away side with count 2", hr == ["", "2"], hr)
        check(f"{lang} live match: no page errors", not errs, errs)
        ctx.close()
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        pg.wait_for_timeout(2500)
        dots = pg.evaluate("""()=>[...document.querySelectorAll('tr.lvrow')].map(r=>{const a=r.querySelector('td:nth-child(2) a');const s=getComputedStyle(a,'::after');
            return [r.className.match(/lv[wld]/)[0], s.width, s.backgroundColor, s.marginInlineStart||s.marginLeft]})""")
        cs = {d[0]: d for d in dots}
        check(f"{lang} 7 live: table dots 8px, winner green / loser red, different colours",
              len(dots) == 2 and "lvw" in cs and "lvl" in cs and all(d[1] == "8px" for d in dots) and cs["lvw"][2] != cs["lvl"][2], dots)
        pg.click('.cattabs .tab[data-cat="matches"]'); pg.wait_for_timeout(400)
        lr = pg.evaluate(f"""()=>{{const c=document.querySelector('.match[data-mid="{mid}"] .score');return c?[c.querySelectorAll('.rcm').length,(c.querySelector('.rcm b')||{{}}).textContent]:null}}""")
        check(f"{lang} 4 live: league row red mark (count 2)", lr == [1, "2"], lr)
        check(f"{lang} live league: no page errors", not errs, errs)
        ctx.close()
        LIVE["body"] = '{"t":0,"m":{}}'
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
