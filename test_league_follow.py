#!/usr/bin/env python3
"""
Follow a league + «All leagues» alerts (27 Oct 2026, Amr #4 + #8) — Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_league_follow.py [screenshot_dir]
Needs make_assets.py + make_leagues.py + make_following.py + make_notifications.py built. Serves the repo on 127.0.0.1:8784; the push
stack is stubbed (test_push_toggle.STUB) and the worker mocked — the subscribe bodies are captured, nothing reaches a server.

  A) league page: «Follow»/«متابعة» pill next to the bell -> fbLeagues gets the code, pill turns «Following»/«متابَع» filled; again = off.
     It is NOT alerts: no /push/ request.
  B) Following page: «Leagues» tab lists followed leagues (logo + name + country, tap -> league page); Edit mode removes; the «+» sheet
     (batch 4, 30 Oct 2026) opens at half height with the followed leagues, focusing the field lists the 10 leagues and finds them by
     country; the Clubs tab search returns clubs only (no leagues).
  C) Notifications, Leagues tab: «All leagues» card -> sheet (types, banner, ✓) -> ONE subscribe with every followed league and the chosen
     mask; 0 followed = card asks to follow leagues first (link to Leagues); list = followed first, then the rest, all 10 leagues.
  D) isolation: alerts on an UNFOLLOWED league (SAU goals only), a team (Abha) and a match (1603075) are sent unchanged by the All-leagues save;
     only the followed leagues (EGY, MAR) get the new types.
  E) one-time migration: old storage (clubs + auto-added leagues, no fbLeaguesV2) -> leagues cleared, clubs and alerts untouched, flag set;
     second load does nothing; a league followed after the migration stays.
"""
import functools
import http.server
import json
import re
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from config import LEAGUES  # noqa: E402
import push_ui  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "league_follow"
SHOTS.mkdir(parents=True, exist_ok=True)
STUB = re.search(r'STUB = """(.*?)"""', (ROOT / "test_push_toggle.py").read_text(encoding="utf-8"), re.S).group(1)
KEY = "B" + "A" * 86
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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8784), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8784"


def mock_worker(page, posts):
    def handle(route):
        req = route.request
        h = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Content-Type": "application/json"}
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=h)
        if req.url.endswith("/push/key"):
            return route.fulfill(status=200, headers=h, body=json.dumps({"key": KEY}))
        if "/push/" in req.url:
            posts.append((req.url.rsplit("/", 1)[1], json.loads(req.post_data)))
            return route.fulfill(status=200, headers=h, body='{"ok":true}')
        return route.fulfill(status=200, headers=h, body='{"t":0,"m":{}}')
    page.route("https://saffara-live.abujaishamr.workers.dev/**", handle)


def new_page(br, init="", push=False):
    ctx = br.new_context(viewport={"width": 390, "height": 844})
    if push:
        ctx.add_init_script(STUB)
    # fbLeaguesV2: the one-time clear of auto-added leagues already ran (section E tests the migration itself)
    ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbLeaguesV2','1');" + init + "}catch(e){}")
    pg = ctx.new_page()
    posts, errs = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    mock_worker(pg, posts)
    return ctx, pg, posts, errs


def stored(pg, k):
    return pg.evaluate(f"()=>JSON.parse(localStorage.getItem('{k}')||'null')")


IDS = {c: v["id"] for c, v in LEAGUES.items()}
with sync_playwright() as p:
    br = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        F, U = (("متابعة", "متابَع") if lang == "ar" else ("Follow", "Following"))
        S = push_ui.STR[lang]
        # ---------------- A) league page pill
        ctx, pg, posts, errs = new_page(br, push=True)
        pg.goto(f"{BASE}{pre}/leagues/mar.html?push=1", wait_until="load"); pg.wait_for_timeout(500)
        pill = pg.locator("#lfolbtn")
        side = pg.evaluate("()=>{const a=document.getElementById('lfolbtn'),b=document.getElementById('pushbtn');"
                           "return a&&b&&a.parentElement===b.parentElement.parentElement||a.nextElementSibling===b.parentElement}")
        check(f"{lang} A: pill «{F}» next to the bell, outlined (not on)", pill.inner_text() == F and "on" not in (pill.get_attribute("class") or "")
              and side, [pill.inner_text(), side])
        pg.screenshot(path=str(SHOTS / f"A_league_follow_off_{lang}.png"))
        pill.click(); pg.wait_for_timeout(200)
        bg = pg.evaluate("()=>getComputedStyle(document.getElementById('lfolbtn')).backgroundColor")
        check(f"{lang} A: tap -> «{U}» filled, fbLeagues=['MAR'], aria-pressed", pill.inner_text() == U and stored(pg, "fbLeagues") == ["MAR"]
              and pill.get_attribute("aria-pressed") == "true" and bg not in ("rgba(0, 0, 0, 0)", "transparent"), [pill.inner_text(), stored(pg, "fbLeagues"), bg])
        check(f"{lang} A: following is not alerts (no /push/ request)", not posts, posts)
        pg.screenshot(path=str(SHOTS / f"A_league_follow_on_{lang}.png"))
        pill.click(); pg.wait_for_timeout(200)
        check(f"{lang} A: tap again -> unfollowed", pill.inner_text() == F and stored(pg, "fbLeagues") == [], stored(pg, "fbLeagues"))
        for c in ("sau", "egy"):
            pg.goto(f"{BASE}{pre}/leagues/{c}.html", wait_until="load"); pg.locator("#lfolbtn").click()
        check(f"{lang} A: two more leagues followed in order", stored(pg, "fbLeagues") == ["SAU", "EGY"], stored(pg, "fbLeagues"))
        check(f"{lang} A: no page errors", not errs, errs)
        ctx.close()

        # ---------------- B) Following page
        ctx, pg, posts, errs = new_page(br, "localStorage.setItem('fbLeagues','[\"SAU\",\"MAR\"]');localStorage.setItem('fbClubs','[962]');")
        pg.goto(f"{BASE}{pre}/following.html", wait_until="load"); pg.wait_for_timeout(600)
        tabs = pg.evaluate("()=>[...document.querySelectorAll('.ftab')].map(b=>b.id)")
        check(f"{lang} B: tabs Teams / Leagues / Players", tabs == ["tab-teams", "tab-leagues", "tab-players"], tabs)
        pg.click("#tab-leagues"); pg.wait_for_timeout(200)
        cards = pg.evaluate("()=>[...document.querySelectorAll('#leagueCards .fleague')].map(a=>[a.getAttribute('href'),a.querySelector('.fname').textContent,"
                            "!!a.querySelector('img.flogo')])")
        check(f"{lang} B: Leagues tab = followed leagues (SAU, MAR) with logo + name, tap -> league page",
              [c[0].split("/")[-1] for c in cards] == ["sau.html", "mar.html"] and all(c[2] for c in cards), cards)
        pg.screenshot(path=str(SHOTS / f"B_following_leagues_{lang}.png"))
        pg.click("#fedit"); pg.locator("#leagueCards .fleague").nth(0).click(); pg.click("#frm"); pg.wait_for_timeout(200)
        check(f"{lang} B: Edit mode removes a league (SAU) -> fbLeagues=['MAR']", stored(pg, "fbLeagues") == ["MAR"], stored(pg, "fbLeagues"))
        pg.click("#fdone") if pg.is_visible("#fdone") else None
        pg.click("#fadd"); pg.wait_for_timeout(400)
        fol = pg.locator("#ffol .fr").count()
        title = pg.inner_text("#fshh")
        check(f"{lang} B: «+» on the Leagues tab opens with the followed league (MAR) listed (title «{title}»)", fol == 1, fol)
        pg.click("#fsq"); pg.wait_for_timeout(400)
        n = pg.locator("#fres .fr").count()
        check(f"{lang} B: focusing the field lists the {len(LEAGUES)} leagues", n == len(LEAGUES), n)
        pg.screenshot(path=str(SHOTS / f"B_following_add_leagues_{lang}.png"))
        pg.locator("#fres .fr", has_text="Saudi" if lang == "en" else "السعودي").first.click(); pg.wait_for_timeout(200)
        check(f"{lang} B: follow from the sheet -> SAU back in fbLeagues, card list refreshed", stored(pg, "fbLeagues") == ["MAR", "SAU"]
              and pg.locator("#leagueCards .fleague").count() == 2, stored(pg, "fbLeagues"))
        pg.fill("#fsq", "المغرب" if lang == "ar" else "Morocco"); pg.wait_for_timeout(400)
        hits = pg.evaluate("()=>[...document.querySelectorAll('#fres .fr .frn')].map(x=>x.textContent)")
        check(f"{lang} B: league search finds leagues by country", len(hits) == 1, hits)
        pg.click("#fx"); pg.click("#tab-teams"); pg.click("#fadd"); pg.wait_for_timeout(300)
        pg.click("#fsq"); pg.fill("#fsq", "المغرب" if lang == "ar" else "Morocco"); pg.wait_for_timeout(600)
        lg = pg.evaluate("()=>{const L=['الدوري المغربي','Botola Pro'];return [...document.querySelectorAll('#fres .fr .frn')].map(x=>x.textContent).filter(t=>L.indexOf(t)>=0)}")
        check(f"{lang} B: Clubs tab search returns clubs only (no league row for the country)", lg == [], lg)
        check(f"{lang} B: no page errors", not errs, errs)
        ctx.close()

        # ---------------- C) Notifications: 0 followed
        ctx, pg, posts, errs = new_page(br, push=True)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1", wait_until="load"); pg.wait_for_timeout(500)
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(200)
        card = pg.evaluate("()=>{const c=document.querySelector('#nl .nall');return c?{t:c.innerText,link:(c.querySelector('a')||{}).href||'',tap:c.classList.contains('tap')}:null}")
        check(f"{lang} C: 0 followed -> «{S['all_l']}» card asks to follow first, links to Leagues, not tappable",
              card and S["all_l_none"] in card["t"] and card["link"].endswith("leagues.html") and not card["tap"], card)
        rows = pg.evaluate("()=>[...document.querySelectorAll('#nl .nrow')].map(r=>(r.querySelector('img')||{}).className||'')")
        check(f"{lang} C: all {len(LEAGUES)} leagues listed, each with a logo/flag badge (no trophy)", len(rows) == len(LEAGUES)
              and all("lgbadge" in x for x in rows) and "\U0001F3C6" not in pg.inner_text("#nl"), rows)
        pg.screenshot(path=str(SHOTS / f"C_notifications_none_followed_{lang}.png"))
        ctx.close()

        # ---------------- C) Notifications: 3 followed (one already alerted with goals only)
        init = ("localStorage.setItem('fbLeagues','[\"MAR\",\"SAU\",\"KUW\"]');"
                f"localStorage.setItem('fbPushLeagues','[{IDS['SAU']}]');localStorage.setItem('fbPushTypes','{{\"l:{IDS['SAU']}\":2}}');")
        ctx, pg, posts, errs = new_page(br, init, push=True)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1", wait_until="load"); pg.wait_for_timeout(600)
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(200)
        order = pg.evaluate("()=>[...document.querySelectorAll('#nl .nrow img')].map(i=>(i.className.match(/lg-(\\w+)/)||[])[1])")
        check(f"{lang} C: followed leagues first (mar, sau, kuw — in the site's league order), then the rest — {len(LEAGUES)} rows",
              set(order[:3]) == {"mar", "sau", "kuw"} and len(order) == len(LEAGUES) and len(set(order)) == len(LEAGUES), order)
        pg.screenshot(path=str(SHOTS / f"C_notifications_leagues_{lang}.png"))
        pg.click("#nl .nall"); pg.wait_for_timeout(300)
        sh = pg.evaluate("()=>{const s=document.getElementById('allsheet');return s?{on:s.classList.contains('on'),h:s.querySelector('h3').textContent,"
                         "ban:s.querySelector('.pban').textContent,n:s.querySelectorAll('.prow input').length,checked:[...s.querySelectorAll('.prow input')].filter(i=>i.checked).length,"
                         "save:s.querySelector('.pall').textContent}:null}")
        check(f"{lang} C: sheet open with title, banner «{S['all_l_ban']}», {len(push_ui.TYPE_ROWS)} type boxes, ✓ save",
              sh and sh["on"] and sh["h"] == S["all_l"] and sh["ban"] == S["all_l_ban"] and sh["n"] == len(push_ui.TYPE_ROWS) and sh["save"].startswith("\u2713"), sh)
        pg.screenshot(path=str(SHOTS / f"C_all_leagues_sheet_{lang}.png"))
        # choose: kickoff + goals + full time only
        want = 1 | 2 | 16
        pg.evaluate(f"()=>document.querySelectorAll('#allsheet .prow input').forEach(i=>{{i.checked=({want}&+i.dataset.bit)!==0;}})")
        pg.click("#allsheet .pall"); pg.wait_for_timeout(900)
        sb = [b for k, b in posts if k == "subscribe"]
        last = sb[-1] if sb else {}
        exp = sorted(IDS[c] for c in ("MAR", "SAU", "KUW"))
        check(f"{lang} C: ✓ -> ONE subscribe carrying all 3 followed leagues with mask {want}",
              len(sb) == 1 and sorted(last.get("leagues", [])) == exp and all(last["lt"][str(i)] == want for i in exp), [len(sb), last.get("leagues"), last.get("lt")])
        check(f"{lang} C: sheet closes, local state matches (fbPushLeagues = the 3, masks = {want})",
              not pg.evaluate("()=>document.getElementById('allsheet').classList.contains('on')")
              and sorted(stored(pg, "fbPushLeagues")) == exp and all(stored(pg, "fbPushTypes")[f"l:{i}"] == want for i in exp))
        check(f"{lang} C: rows show the leagues on (bells pressed)", pg.locator("#nl .nrow .bellbtn[aria-pressed=true]").count() == 3,
              pg.locator("#nl .nrow .bellbtn[aria-pressed=true]").count())
        # all types off -> the followed leagues' alerts are removed (other alerts untouched)
        pg.click("#nl .nall"); pg.wait_for_timeout(200)
        pg.evaluate("()=>document.querySelectorAll('#allsheet .prow input').forEach(i=>{i.checked=false;})")
        pg.click("#allsheet .pall"); pg.wait_for_timeout(800)
        check(f"{lang} C: nothing ticked + ✓ -> alerts off for the followed leagues", stored(pg, "fbPushLeagues") in (None, []), stored(pg, "fbPushLeagues"))
        check(f"{lang} C: no page errors", not errs, errs)
        ctx.close()

        # ---------------- D) All-leagues save leaves unfollowed-league / team / match alerts untouched
        # a kickoff 1 h from now (was fixed at 2026-10-29 14:35 UTC: the engine prunes a match a few hours after its kickoff, so the
        # test started failing that evening — the id 1603075 is only a label here, its real date does not matter)
        import time
        KO = int(time.time() * 1000) + 3600000
        init = ("localStorage.setItem('fbLeagues','[\"EGY\",\"MAR\"]');"
                f"localStorage.setItem('fbPushLeagues','[{IDS['SAU']}]');localStorage.setItem('fbPushTeams','[2951]');"
                f"localStorage.setItem('fbPushMatches','[[1603075,{KO}]]');"
                f"localStorage.setItem('fbPushTypes','{{\"l:{IDS['SAU']}\":2,\"t:2951\":115,\"m:1603075\":499}}');")
        ctx, pg, posts, errs = new_page(br, init, push=True)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1", wait_until="load"); pg.wait_for_timeout(600)
        before = pg.evaluate("()=>['fbPushTeams','fbPushMatches','fbPushLeagues','fbPushTypes'].map(k=>localStorage.getItem(k))")
        pg.click(".ntab[data-t=l]"); pg.click("#nl .nall"); pg.wait_for_timeout(300)
        want = 1 | 2 | 16
        pg.evaluate(f"()=>document.querySelectorAll('#allsheet .prow input').forEach(i=>{{i.checked=({want}&+i.dataset.bit)!==0;}})")
        pg.click("#allsheet .pall"); pg.wait_for_timeout(900)
        sb = [b for k, b in posts if k == "subscribe"]
        last = sb[-1] if sb else {}
        lt = last.get("lt", {})
        check(f"{lang} D: subscribe keeps SAU (unfollowed) at goals-only and adds EGY+MAR with the 3 types",
              sorted(last.get("leagues", [])) == sorted([IDS["SAU"], IDS["EGY"], IDS["MAR"]]) and lt.get(str(IDS["SAU"])) == 2
              and lt.get(str(IDS["EGY"])) == want and lt.get(str(IDS["MAR"])) == want, [last.get("leagues"), lt])
        check(f"{lang} D: team Abha and match 1603075 sent unchanged (lists + masks)",
              last.get("teams") == [2951] and last.get("tt") == {"2951": 115} and last.get("matches") == [1603075]
              and last.get("mt") == {"1603075": 499}, [last.get("teams"), last.get("tt"), last.get("matches"), last.get("mt")])
        after = pg.evaluate("()=>['fbPushTeams','fbPushMatches','fbPushLeagues','fbPushTypes'].map(k=>localStorage.getItem(k))")
        ty = json.loads(after[3] or "{}")
        check(f"{lang} D: local state: team/match lists identical, SAU mask still 2, EGY/MAR {want}",
              after[0] == before[0] and after[1] == before[1] and ty.get(f"l:{IDS['SAU']}") == 2 and ty.get("t:2951") == 115
              and ty.get("m:1603075") == 499 and ty.get(f"l:{IDS['EGY']}") == want and ty.get(f"l:{IDS['MAR']}") == want, [before, after])
        check(f"{lang} D: no page errors", not errs, errs)
        ctx.close()

        # ---------------- E) one-time migration of auto-added leagues
        ctx = br.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); mock_worker(pg, [])
        pg.goto(f"{BASE}/robots.txt")   # same origin, no FBPrefs: write the OLD storage (no fbLeaguesV2)
        pg.evaluate(f"""()=>{{localStorage.clear();localStorage.setItem('fbSetupDone','1');localStorage.setItem('fbClubs','[2951,962]');
                     localStorage.setItem('fbLeagues','["SAU","EGY"]');localStorage.setItem('fbPushLeagues','[{IDS['SAU']}]');
                     localStorage.setItem('fbPushTeams','[2951]');}}""")
        pg.goto(f"{BASE}{pre}/following.html", wait_until="load"); pg.wait_for_timeout(300)
        st = pg.evaluate("()=>['fbClubs','fbLeagues','fbLeaguesV2','fbPushLeagues','fbPushTeams'].map(k=>localStorage.getItem(k))")
        check(f"{lang} E: first load clears auto-added leagues, keeps clubs and alerts, sets the flag",
              st == ["[2951,962]", None, "1", f"[{IDS['SAU']}]", "[2951]"], st)
        pg.evaluate("()=>localStorage.setItem('fbLeagues','[\"MAR\"]')")   # a league followed after the migration
        pg.goto(f"{BASE}{pre}/leagues/mar.html", wait_until="load"); pg.wait_for_timeout(200)
        st2 = pg.evaluate("()=>['fbClubs','fbLeagues','fbLeaguesV2'].map(k=>localStorage.getItem(k))")
        check(f"{lang} E: second load does nothing — the league followed afterwards stays (pill shows Following)",
              st2 == ["[2951,962]", '["MAR"]', "1"] and pg.locator("#lfolbtn").inner_text() == U, [st2, pg.locator("#lfolbtn").inner_text()])
        ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
