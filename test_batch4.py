#!/usr/bin/env python3
"""
Batch 4 (30 Oct 2026) — league Team stats cards, Following "+" sheet, home match rows, device date. Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_batch4.py
Needs the site built (make_assets, make_site3, make_leagues, make_search, make_following). Serves the repo on 127.0.0.1:8785, mocks the
live worker. Reads football.db (read-only) for the expected numbers.

  1  SAU Team stats: 4 cards (goals/match, conceded/match, clean sheets, possession) x 3 rows = league_team_cards numbers, header links
     to a noindex list page with every team ranked; JOR (no match_stats) has 3 cards, no possession
  2  (test_seasons_tab.py) Winner / Runner-up rows link to the club pages
  3  "+" opens a half-height sheet: followed items (Following pill) and the search field at the BOTTOM; focusing the field expands the
     sheet to full height with the field at the TOP and results below, the followed list hidden; blur with nothing typed = half again
  4  each tab searches its own kind only: Clubs "J" = clubs only (no "Jordan Pro League"), Leagues = leagues only, Players = players only
  5  the sheet follows visualViewport (shrinking the visible viewport, as the iOS keyboard does, keeps the field on screen)
  6  Players tab has "+": followed player row (name + club + Following), search finds players, Follow adds the card behind the sheet
  7  Players tab "Edit": select + remove
  8  home rows: the live row (minute circle) and the rows around it share the same grid (same start padding, score centred alike)
  9  a match that finished after the page was built (live worker "f") looks like a static finished row: plain .score, no "Full time",
     no .soon / .time / bell
 10  device date: Asia/Amman at 01:30 local -> "Today" tab = the new date; Los Angeles -> Today = LA date; Asia/Tokyo -> a finished match
     at 18:00 UTC sits in the next day's panel; kickoff times in the device timezone; local midnight while open -> reload on the new day
"""
import datetime as dt
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
import league_team_cards as ltc  # noqa: E402
from tiebreak import STANDINGS_EXCLUDED  # noqa: E402

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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8785), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8785"
LIVE = {"body": '{"t":0,"m":{}}'}
conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)


def page(br, url, w=390, h=844, tz=None, init="", clock=None):
    kw = {"timezone_id": tz} if tz else {}
    ctx = br.new_context(viewport={"width": w, "height": h}, service_workers="block", **kw)
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');" + init + "}catch(e){}")
    ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(
        status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"]))
    pg = ctx.new_page()
    if clock:
        pg.clock.install(time=clock)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + url, wait_until="load")
    pg.wait_for_timeout(500)
    return ctx, pg, errs


FOLLOW = ("localStorage.setItem('fbClubs','[2939,2932]');localStorage.setItem('fbPlayers','[\"cristiano-ronaldo\"]');"
          "localStorage.setItem('fbLeaguesV2','1');localStorage.setItem('fbLeagues','[\"SAU\"]');")   # V2: else prefs.py's one-time migration clears fbLeagues


def sheet_state(pg):
    return pg.evaluate("""()=>{const s=document.getElementById('fsheet'), sh=s.querySelector('.fsheet'), f=s.querySelector('.sfield').getBoundingClientRect(),
        r=sh.getBoundingClientRect(), fol=document.getElementById('ffol'), res=document.getElementById('fres');
        return {on:s.classList.contains('on'), full:s.classList.contains('full'), top:Math.round(r.top), h:Math.round(r.height), vh:innerHeight,
                fieldTop:Math.round(f.top), fieldBottom:Math.round(f.bottom), sheetBottom:Math.round(r.bottom),
                folVis:fol.offsetParent!==null, resVis:res.offsetParent!==null,
                fol:[...fol.querySelectorAll('.fr')].map(x=>[x.querySelector('.frn').textContent, (x.querySelector('.frl')||{}).textContent||'', x.querySelector('.fpillb').textContent]),
                res:[...res.querySelectorAll('.fr')].map(x=>[x.querySelector('.frn').textContent, (x.querySelector('.frl')||{}).textContent||''])}}""")


with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        pre = "" if lang == "ar" else "/en"

        # ── 1: team stats cards ──
        ctx, pg, errs = page(br, f"{pre}/leagues/sau.html")
        pg.click('.cattabs .tab[data-cat="team-stats"]'); pg.wait_for_timeout(300)
        cards = pg.evaluate("""()=>[...document.querySelectorAll('.panel[data-cat="team-stats"] .pscard[data-tstat]')].map(c=>
            [c.dataset.tstat, c.querySelector('.psh').getAttribute('href'), [...c.querySelectorAll('.psr')].map(r=>[r.querySelector('.pn a').getAttribute('href'), r.querySelector('.pv').textContent])])""")
        season = conn.execute("SELECT MAX(season) FROM matches WHERE league_code='SAU'").fetchone()[0]
        teams = ltc.team_rows(conn, "SAU", season, tuple(STANDINGS_EXCLUDED))
        want = []
        for stat in ltc.STATS:
            lst = ltc.ranked(teams, stat, lambda tid: str(tid))
            want.append([stat, f"sau-team-{stat}.html", [v for _r, _t, v in lst[:3]]])
        check(f"{lang} 1: SAU team stats: 4 cards in order, 3 rows each, links to sau-team-<stat>.html",
              [c[0] for c in cards] == list(ltc.STATS) and all(len(c[2]) == 3 for c in cards) and [c[1] for c in cards] == [w[1] for w in want], cards)
        check(f"{lang} 1: SAU values = league_team_cards (top 3 of each card)", [[r[1] for r in c[2]] for c in cards] == [w[2] for w in want],
              [[[r[1] for r in c[2]] for c in cards], [w[2] for w in want]])
        check(f"{lang} 1: SAU card rows link to club pages", all(re.fullmatch(r"\.\./clubs/\d+\.html", r[0]) for c in cards for r in c[2]), cards[:1])
        check(f"{lang} 1: streak cards still below the new cards", pg.locator('.panel[data-cat="team-stats"] .lgrid .lcard').count() >= 1)
        pg.click('.pscard[data-tstat="poss"] .psh'); pg.wait_for_load_state("load"); pg.wait_for_timeout(200)
        lst = pg.evaluate("""()=>({url:location.pathname, rows:document.querySelectorAll('.psr').length, robots:(document.querySelector('meta[name=robots]')||{}).content,
            vals:[...document.querySelectorAll('.psr .pv')].map(x=>parseFloat(x.textContent))})""")
        check(f"{lang} 1: possession list page: every team ({len(teams)}), values never go up, noindex",
              lst["url"].endswith("/sau-team-poss.html") and lst["rows"] == len(teams) and lst["robots"] == "noindex"
              and all(a >= b for a, b in zip(lst["vals"], lst["vals"][1:])), lst)
        check(f"{lang} 1: no page errors (SAU)", not errs, errs)
        ctx.close()
        ctx, pg, errs = page(br, f"{pre}/leagues/jor.html")
        pg.click('.cattabs .tab[data-cat="team-stats"]'); pg.wait_for_timeout(300)
        jor = pg.evaluate("()=>[...document.querySelectorAll('.pscard[data-tstat]')].map(c=>c.dataset.tstat)")
        check(f"{lang} 1: JOR (no match stats): 3 cards, no possession", jor == ["scored", "conceded", "cs"], jor)
        ctx.close()

        # ── 3-7: Following sheet ──
        ctx, pg, errs = page(br, f"{pre}/following.html", init=FOLLOW)
        pg.click("#fadd"); pg.wait_for_timeout(700)
        s = sheet_state(pg)
        check(f"{lang} 3: '+' (Clubs) opens a half-height sheet ({s['h']}px of {s['vh']}) with the field at the bottom",
              s["on"] and not s["full"] and 0.45 * s["vh"] <= s["h"] <= 0.65 * s["vh"] and s["sheetBottom"] - s["fieldBottom"] <= 40, s)
        check(f"{lang} 3: half sheet lists the 2 followed clubs with their league and a 'Following' pill",
              len(s["fol"]) == 2 and all(x[1] and x[2] == s["fol"][0][2] for x in s["fol"]) and s["folVis"] and not s["resVis"], s["fol"])
        pg.click("#fsq"); pg.wait_for_timeout(500)
        s = sheet_state(pg)
        check(f"{lang} 3: focusing the field -> full height, field at the top, results area below, followed list hidden",
              s["full"] and s["h"] >= s["vh"] - 2 and s["fieldTop"] - s["top"] <= 120 and s["resVis"] and not s["folVis"], s)
        pg.keyboard.type("J"); pg.wait_for_timeout(400)
        s = sheet_state(pg)
        res_names = [r[0] for r in s["res"]]
        jordan = "الدوري الأردني" if lang == "ar" else "Jordan Pro League"
        check(f"{lang} 4: Clubs tab 'J': {len(res_names)} results, clubs only (no '{jordan}')",
              len(res_names) > 3 and jordan not in res_names and all(r[1] for r in s["res"]), res_names[:6])
        pg.fill("#fsq", ""); pg.locator("#fsq").blur(); pg.wait_for_timeout(400)
        s = sheet_state(pg)
        check(f"{lang} 3: blur with nothing typed -> back to half height with the followed list", not s["full"] and s["folVis"], s)
        # 5: visualViewport — shrink the visible viewport like the iOS keyboard does
        pg.click("#fsq"); pg.wait_for_timeout(300)
        pg.set_viewport_size({"width": 390, "height": 420}); pg.wait_for_timeout(400)
        vv = pg.evaluate("""()=>{const s=document.getElementById('fsheet'), f=s.querySelector('.sfield').getBoundingClientRect();
            return {h:Math.round(s.getBoundingClientRect().height), vvh:Math.round(visualViewport.height), fieldBottom:Math.round(f.bottom)}}""")
        check(f"{lang} 5: sheet height follows visualViewport ({vv['h']} = {vv['vvh']}), field on screen",
              abs(vv["h"] - vv["vvh"]) <= 1 and vv["fieldBottom"] <= vv["vvh"], vv)
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(200)
        pg.click("#fx"); pg.wait_for_timeout(300)
        # 4: leagues tab = leagues only
        pg.click("#tab-leagues"); pg.wait_for_timeout(200); pg.click("#fadd"); pg.wait_for_timeout(400)
        s = sheet_state(pg)
        sau = "الدوري السعودي" if lang == "ar" else "Saudi Pro League"
        check(f"{lang} 3: Leagues '+': followed league ({sau}) listed", [x[0] for x in s["fol"]] == [sau], s["fol"])
        pg.click("#fsq"); pg.keyboard.type("a"); pg.wait_for_timeout(300)
        s = sheet_state(pg)
        n_lg = len(s["res"])
        check(f"{lang} 4: Leagues tab search: leagues only ({n_lg} rows, at most the 10 leagues)", 0 < n_lg <= 10, [r[0] for r in s["res"]])
        pg.click("#fx"); pg.wait_for_timeout(300)
        # 6: players tab
        pg.click("#tab-players"); pg.wait_for_timeout(200)
        check(f"{lang} 6: Players tab shows '+' and 'Edit'", pg.locator("#fadd").is_visible() and pg.locator("#fedit").is_visible())
        pg.click("#fadd"); pg.wait_for_timeout(500)
        s = sheet_state(pg)
        ron = "كريستيانو رونالدو" if lang == "ar" else "Cristiano Ronaldo"
        nassr = "النصر" if lang == "ar" else "Al-Nassr"
        check(f"{lang} 6: players sheet: followed player row (name + club + Following)",
              len(s["fol"]) == 1 and s["fol"][0][0] == ron and s["fol"][0][1] == nassr, s["fol"])
        pg.click("#fsq"); pg.keyboard.type("toney"); pg.wait_for_timeout(400)
        s = sheet_state(pg)
        toney = "إيفان توني" if lang == "ar" else "Ivan Toney"
        check(f"{lang} 4/6: Players tab 'toney' -> players only, {toney} with his club", any(r[0] == toney and r[1] for r in s["res"]), s["res"][:5])
        pg.locator("#fres .fr", has_text=toney).first.locator(".fpillb").click(); pg.wait_for_timeout(300)
        n_cards = pg.locator("#playerCards .fcard").count()
        saved = pg.evaluate("()=>JSON.parse(localStorage.getItem('fbPlayers')||'[]')")
        check(f"{lang} 6: Follow from the sheet -> saved and the card appears behind the sheet", n_cards == 2 and len(saved) == 2, [n_cards, saved])
        pg.click("#fx"); pg.wait_for_timeout(300)
        # 7: edit = select + remove
        pg.click("#fedit"); pg.wait_for_timeout(200)
        pg.locator("#playerCards .fcard").first.click(); pg.wait_for_timeout(200)
        pg.click("#frm"); pg.wait_for_timeout(300)
        saved2 = pg.evaluate("()=>JSON.parse(localStorage.getItem('fbPlayers')||'[]')")
        check(f"{lang} 7: Players Edit: select one + remove -> 1 player left", len(saved2) == 1 and pg.locator("#playerCards .fcard").count() == 1, saved2)
        check(f"{lang} 3-7: no page errors", not errs, errs)
        ctx.close()

        # ── 8 + 9: home rows with one live and one just-finished match ──
        ctx, pg, errs = page(br, f"{pre}/index.html")
        mids = pg.evaluate("()=>[...document.querySelectorAll('.daypanel.visible .match')].filter(c=>c.querySelector('.score.time')).map(c=>c.dataset.mid).slice(0,2)")
        if len(mids) < 2:
            check(f"{lang} 8/9: need 2 upcoming matches on today's panel", False, mids)
        else:
            LIVE["body"] = json.dumps({"t": 0, "m": {mids[0]: {"h": 1, "a": 0, "e": 57, "s": "2H"}}, "f": {mids[1]: {"h": 5, "a": 3, "s": "FT"}}})
            pg.reload(wait_until="load"); pg.wait_for_timeout(1500)
            r = pg.evaluate("""(m)=>{const rows=[...document.querySelectorAll('.daypanel.visible .match')].filter(c=>c.getBoundingClientRect().height>0);
                const info=c=>{const sc=c.querySelector('.score').getBoundingClientRect(), cs=getComputedStyle(c);
                  return {mid:c.dataset.mid, live:c.classList.contains('live'), pad:cs.paddingInlineStart, mid_x:Math.round(sc.left+sc.width/2)}};
                const fin=document.querySelector('.match[data-mid="'+m[1]+'"]'), st=[...document.querySelectorAll('.daypanel.visible .match')].find(c=>!c.dataset.lvOrig&&/^\\d+ - \\d+$/.test(c.querySelector('.score').textContent.trim()));
                const sty=e=>{const s=getComputedStyle(e);return [s.color,s.fontSize,s.fontWeight,s.backgroundColor]};
                return {rows:rows.map(info), fin:{cls:fin.className, sc:fin.querySelector('.score').className, txt:fin.querySelector('.score').textContent,
                        lvend:!!fin.querySelector('.lvend'), bell:!!fin.querySelector('.cbell'), sty:sty(fin.querySelector('.score'))},
                        stat:st?{cls:st.className, sc:st.querySelector('.score').className, sty:sty(st.querySelector('.score'))}:null}}""", mids)
            pads = {x["pad"] for x in r["rows"]}
            xs = {x["mid_x"] for x in r["rows"]}
            check(f"{lang} 8: live row and the other {len(r['rows']) - 1} rows: same start padding {pads}, score centres within 1px",
                  len(pads) == 1 and any(x["live"] for x in r["rows"]) and max(xs) - min(xs) <= 1, r["rows"][:4])
            check(f"{lang} 9: finished-after-build row: plain '5 - 3', class 'score', no 'Full time', no .soon/.time, no bell",
                  r["fin"]["txt"] == "5 - 3" and r["fin"]["sc"] == "score" and not r["fin"]["lvend"] and "soon" not in r["fin"]["cls"]
                  and not r["fin"]["bell"], r["fin"])
            check(f"{lang} 9: ... and styled exactly like a static finished row (colour/size/weight/background)",
                  r["stat"] is not None and r["fin"]["sty"] == r["stat"]["sty"], [r["fin"], r["stat"]])
        LIVE["body"] = '{"t":0,"m":{}}'
        check(f"{lang} 8/9: no page errors", not errs, errs)
        ctx.close()

        # ── 10: device date / timezone ──
        # no tzdata on Windows Python: Amman (UTC+3) and Tokyo (UTC+9) have fixed offsets; Los Angeles is computed by the browser (Intl)
        AMMAN, TOKYO = dt.timezone(dt.timedelta(hours=3)), dt.timezone(dt.timedelta(hours=9))
        now_utc = dt.datetime.now(dt.timezone.utc)
        amman_0130 = dt.datetime.combine(now_utc.astimezone(AMMAN).date() + dt.timedelta(days=1), dt.time(1, 30), AMMAN)
        ctx, pg, errs = page(br, f"{pre}/index.html", tz="Asia/Amman", clock=amman_0130)
        act = pg.evaluate("()=>{const b=document.querySelector('.daytab.active');return b?b.dataset.day:null}")
        check(f"{lang} 10: Asia/Amman at 01:30 local -> Today tab = {amman_0130.date()}", act == amman_0130.date().isoformat(), act)
        ctx.close()
        ctx, pg, errs = page(br, f"{pre}/index.html", tz="America/Los_Angeles")
        st = pg.evaluate("""()=>{const b=document.querySelector('.daytab.active'); const t=[...document.querySelectorAll('.daypanel .match .score.time[data-utc]')]
              .filter(e=>/^\\d\\d:\\d\\d$/.test(e.textContent.trim())).slice(0,5).map(e=>[e.dataset.utc,e.textContent.trim()]);
              const LA={timeZone:'America/Los_Angeles'};
              const want=t.map(x=>[x[0], new Intl.DateTimeFormat('en-GB',Object.assign({hour:'2-digit',minute:'2-digit',hourCycle:'h23'},LA)).format(new Date(x[0]))]);
              return {act:b?b.dataset.day:null, la:new Date().toLocaleDateString('en-CA',LA), times:t, want:want}}""")
        la, want_t = st["la"], st["want"]
        check(f"{lang} 10: Los Angeles -> Today tab = LA date {la}", st["act"] == la, st)
        check(f"{lang} 10: Los Angeles -> kickoff times shown in LA time", st["times"] and st["times"] == want_t, [st["times"], want_t])
        ctx.close()
        ctx, pg, errs = page(br, f"{pre}/index.html", tz="Asia/Tokyo")
        fin = conn.execute("""SELECT match_id, date FROM matches WHERE home_goals IS NOT NULL AND length(date) > 10 AND substr(date, 12, 2) >= '15'
                              AND date >= ? ORDER BY date DESC LIMIT 1""", ((now_utc - dt.timedelta(days=20)).strftime("%Y-%m-%d"),)).fetchone()
        if fin:
            mid, d = fin
            tok = dt.datetime.fromisoformat(d.replace(" ", "T") + "+00:00").astimezone(TOKYO).date().isoformat()
            where = pg.evaluate("(m)=>{const c=document.querySelector('.daypanel .match[data-mid=\"'+m+'\"]');return c?c.closest('.daypanel').id:null}", str(mid))
            check(f"{lang} 10: Asia/Tokyo: finished match {mid} ({d} UTC) sits in the Tokyo day d{tok}", where == f"d{tok}", [where, tok])
        ctx.close()
        # midnight while the page is open -> reload on the new date (LA, 23:59:30 -> 00:00:30)
        #    (the UTC offset at that moment comes from the browser, so PDT and PST both work)
        ctx, pg, errs = page(br, f"{pre}/index.html", tz="America/Los_Angeles")
        off = pg.evaluate("(d)=>new Date(d+'T23:59:00').getTimezoneOffset()", la)
        ctx.close()
        late = dt.datetime.fromisoformat(la + "T23:59:00+00:00") + dt.timedelta(minutes=off)
        ctx, pg, errs = page(br, f"{pre}/index.html", tz="America/Los_Angeles", clock=late)
        a0 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        with pg.expect_navigation(timeout=15000):
            pg.clock.run_for(130000)
        pg.wait_for_timeout(600)
        a1 = pg.evaluate("()=>document.querySelector('.daytab.active').dataset.day")
        check(f"{lang} 10: open page at LA midnight reloads onto the new day ({a0} -> {a1})",
              a0 == la and a1 == (dt.date.fromisoformat(la) + dt.timedelta(days=1)).isoformat(), [a0, a1])
        ctx.close()
    br.close()
srv.shutdown()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
