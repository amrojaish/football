#!/usr/bin/env python3
"""
Batch 7 (31 Oct 2026) — season card header / logos / labels, header scorer lines colour, FotMob substitution rows, short names.
Playwright, ar + en, 390px (+ 360px overflow checks). Run:
    python C:\\Users\\User\\Projects\\Football\\test_batch7.py
Needs the site built (make_assets + update_all --generate-only). Serves the repo on 127.0.0.1:8788, mocks the live worker.
Reads football.db (read-only) for expected values.

  1  season-so-far header row = league logo + bold name centred between the team logos (built by batch 6 #10; verified here)
  2  season card team logos ~48px; middle labels in the primary text colour
  3  header scorer lines (live, mocked) in the primary text colour
  4  substitutions: two stacked rows — green in-arrow + player in (green), red out-arrow + player out (red); no 🔄, no → / ←;
     same for live events (mocked); legend shows "player in" / "player out"
  5  names of 3+ words shown first + last on match pages (events, lineups) and list rows (league scorers); full name kept on the
     player page title and in links; collision guard keeps both full names when two would collide
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
import short_names as SN  # noqa: E402

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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8788), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8788"
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


# ── 5: helper rules + collision guard (no browser) ──
check("5 helper: 3+ words -> first + last; 2 words unchanged; compound first / particle last kept",
      SN.short_name("Makaya Ibrahima Diaby") == "Makaya Diaby" and SN.short_name("Josh Brownhill") == "Josh Brownhill"
      and SN.short_name("عبد الله أحمد موسى الهوساوي") == "عبد الله الهوساوي" and SN.short_name("Mohammed Al Shwirekh") == "Mohammed Al Shwirekh"
      and SN.short_name("محمد عبد الرحمن يوسف") == "محمد يوسف")
mp = SN.page_map(["Mohammed Ali Saleh", "Mohammed Ahmed Saleh", "Ali Hassan Omar", "Ali Omar"])
check("5 guard: two players with the same short name keep full names; short name equal to another player's name -> kept",
      mp["Mohammed Ali Saleh"] == "Mohammed Ali Saleh" and mp["Mohammed Ahmed Saleh"] == "Mohammed Ahmed Saleh"
      and mp["Ali Hassan Omar"] == "Ali Hassan Omar", mp)

RED = 1603078   # Al-Shabab 6-1 Al-Ahli: 10 substitutions, 3+ word names (Makaya Ibrahima Diaby, Mohammed Abdulrahman Yousef)
nsub = conn.execute("SELECT COUNT(*) FROM events WHERE match_id = ? AND type = 'subst'", (RED,)).fetchone()[0]
TXT = "rgb(230, 237, 243)"

with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        pre = "" if lang == "ar" else "/en"
        for w in (390, 360):
            ctx, pg, errs = page(br, f"{pre}/matches/{RED}.html", w=w)
            text = pg.evaluate("()=>getComputedStyle(document.body).color")
            # 4 subs
            sb = pg.evaluate("""()=>[...document.querySelectorAll('#evbox .who.subw')].map(s=>{const r=[...s.querySelectorAll(':scope > .sr')];
                return {cls:r.map(x=>x.classList.contains('in')?'in':x.classList.contains('out')?'out':''),
                  col:r.map(x=>getComputedStyle(x).color), chip:r.map(x=>getComputedStyle(x.querySelector('.sa')).backgroundColor),
                  stacked:r.length===2&&r[1].getBoundingClientRect().top>=r[0].getBoundingClientRect().bottom-1,
                  border:getComputedStyle(s).borderTopWidth, bg:getComputedStyle(s).backgroundColor}})""")
            evt = pg.evaluate("()=>document.getElementById('evbox').textContent")
            check(f"{lang} 4 @{w}: {len(sb)} substitution rows (= {nsub}) as 2 stacked lines: in (green, green chip) then out (red, red chip), no box",
                  len(sb) == nsub and all(s["cls"] == ["in", "out"] and s["stacked"] and s["col"][0] == s["chip"][0] and s["col"][1] == s["chip"][1]
                                           and s["col"][0] != s["col"][1] and s["border"] == "0px" and s["bg"] in ("rgba(0, 0, 0, 0)", "transparent") for s in sb), sb[:2])
            check(f"{lang} 4 @{w}: no 🔄 and no → / ← in events", "🔄" not in evt and "→" not in evt and "←" not in evt)
            lg = pg.evaluate("()=>[...document.querySelectorAll('.iclg .lgi')].map(l=>l.textContent.trim())")
            want = ["دخول لاعب", "خروج لاعب"] if lang == "ar" else ["Player in", "Player out"]
            check(f"{lang} 4 @{w}: legend has player in / player out, no 🔄", all(x in lg for x in want) and not any("🔄" in x for x in lg), lg)
            # 5 events
            if lang == "en":
                check(f"en 5 @{w}: events show 'Makaya Diaby' / 'Mohammed Yousef', not the full 3-word names",
                      "Makaya Diaby" in evt and "Makaya Ibrahima Diaby" not in evt and "Mohammed Yousef" in evt
                      and "Mohammed Abdulrahman Yousef" not in evt, evt[:300])
            # 5 lineups
            pg.click('.mtab[data-tab="lineups"]'); pg.wait_for_timeout(300)
            names = pg.evaluate("()=>[...document.querySelectorAll('.mp[data-tab=\"lineups\"] .fn, .mp[data-tab=\"lineups\"] .lup .tx b')].map(x=>x.textContent.replace(/^\\d+ · /,'').trim())")
            long3 = [n for n in names if len(n.split()) >= 3]
            mpm = SN.match_map(conn, RED)
            kept = [n for n in long3 if mpm.get(n) == n]
            check(f"{lang} 5 @{w}: lineups: no 3+ word names except those kept by the guard or compound/particle rules ({len(names)} names)",
                  len(names) >= 30 and all(SN.short_name(n) == n or mpm.get(n) == n for n in long3), [long3, kept])
            # 1 + 2
            pg.click('.mtab[data-tab="h2h"]'); pg.wait_for_timeout(300)
            ss = pg.evaluate("""()=>{const h=document.querySelector('.ssfh');const c=h.querySelector('.ssfc');
                const logos=[...h.children].filter(x=>x!==c).map(x=>{const i=x.querySelector('img');return i?Math.round(i.getBoundingClientRect().width):0});
                const b=c.querySelector('b');const k=[...document.querySelectorAll('.ssfr .k')].map(x=>getComputedStyle(x).color);
                return {mid:h.children[1]===c, img:!!c.querySelector('img'), fw:getComputedStyle(b).fontWeight, logos, k:[...new Set(k)]}}""")
            check(f"{lang} 1 @{w}: season header = league logo + bold name in the middle (batch 6 #10)", ss["mid"] and ss["img"] and int(ss["fw"]) >= 700, ss)
            check(f"{lang} 2 @{w}: team logos ~48px, middle labels in the primary text colour ({text})",
                  all(46 <= x <= 50 for x in ss["logos"]) and ss["k"] == [text], ss)
            ov = pg.evaluate("()=>document.documentElement.scrollWidth>document.documentElement.clientWidth")
            check(f"{lang} @{w}: no horizontal overflow, no page errors", not ov and not errs, [ov, errs])
            ctx.close()

        # 5 league scorers list: short display, full name in the link target
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        sc = pg.evaluate("()=>[...document.querySelectorAll('.pcards .pn')].map(x=>{const a=x.querySelector('a,.nm');return [a?a.textContent.trim():'', a&&a.getAttribute('href')||'']})")
        long3 = [s for s in sc if len(s[0].split()) >= 3 and SN.short_name(s[0]) != s[0]]
        check(f"{lang} 5: league scorers list ({len(sc)} rows): no shortenable 3+ word names left (guard keeps are allowed)",
              sc and all(SN.page_map([x[0] for x in sc]).get(s[0]) == s[0] for s in long3), long3[:5])
        check(f"{lang} 5: league page no errors", not errs, errs)
        ctx.close()

        # 5 player page title keeps the full name
        pp = None
        for f in sorted((ROOT / ("players" if lang == "ar" else "en/players")).glob("*.html"))[:4000]:
            t = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', t)
            if m and len(m.group(1).split()) >= 3 and SN.short_name(m.group(1)) != m.group(1):
                pp = (f.name, m.group(1))
                break
        check(f"{lang} 5: player page title keeps the full 3+ word name ({pp})", pp is not None, pp)

        # ── LIVE (mocked): 3 scorer lines colour, 4 + 5 live subst rows with short names ──
        up = upcoming_matches(league="SAU")
        if not up:
            print("SKIP live checks: no upcoming SAU match built locally")
            continue
        mid, hid, aid = up[0][0], up[0][2], up[0][3]
        LIVE["body"] = json.dumps({"t": 0, "ve": 1,
                                   "m": {str(mid): {"h": 1, "a": 0, "e": 60, "s": "2H", "th": hid, "ta": aid, "lg": LEAGUES["SAU"]["id"]}},
                                   "s": {str(mid): [["h", 33, 0, "Abdullah Ahmed Musa Al Hawsawi", "عبد الله أحمد موسى الهوساوي", ""]]},
                                   "v": {str(mid): [[33, 0, "g", "n", "Abdullah Ahmed Musa Al Hawsawi", "", "h", None, None],
                                                    [55, 0, "s", "", "Player Out Longname", "Makaya Ibrahima Diaby", "a", None, None]]}})
        ctx, pg, errs = page(br, f"{pre}/matches/{mid}.html")
        pg.wait_for_timeout(2500)
        scl = pg.evaluate("()=>[...document.querySelectorAll('.scl div')].map(d=>[d.textContent, getComputedStyle(d).color])")
        text = pg.evaluate("()=>getComputedStyle(document.body).color")
        check(f"{lang} 3 live: header scorer line in the primary text colour", scl and all(c == text for _, c in scl), [scl, text])
        if lang == "en":
            check("en 5 live: scorer line uses the short name", scl and scl[0][0].startswith("Abdullah Al Hawsawi"), scl)
        lv = pg.evaluate("""()=>{const s=document.querySelector('#evbox .who.subw');if(!s)return null;
            return {r:[...s.querySelectorAll(':scope > .sr')].map(x=>[x.className, x.textContent]), txt:document.getElementById('evbox').textContent}}""")
        check(f"{lang} 4+5 live: substitution = in row (short name) then out row; no 🔄 / arrows",
              lv and [r[0] for r in lv["r"]] == ["sr in", "sr out"] and lv["r"][0][1] == "Makaya Diaby" and lv["r"][1][1] == "Player Longname"
              and "🔄" not in lv["txt"] and "→" not in lv["txt"] and "←" not in lv["txt"], lv)
        check(f"{lang} live: no page errors", not errs, errs)
        ctx.close()
        LIVE["body"] = '{"t":0,"m":{}}'
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
