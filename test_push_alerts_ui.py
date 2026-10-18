"""Playwright test of the alert-type UI (13 Oct 2026, batch 3E): bell = all types on/off, «Edit» sheet with the 7 type checkboxes,
league bell, Settings -> Notifications page (tabs Teams / Leagues, per-row bell + edit). Run:
    python C:\\Users\\User\\Projects\\Football\\test_push_alerts_ui.py
Needs regenerated assets + pages (make_assets.py, make_clubs.py, make_matches.py EGY, make_leagues.py, make_following.py, make_notifications.py).
Same stubs as test_push_toggle.py (Notification / PushManager / serviceWorker; worker URL mocked)."""
import functools
import http.server
import json
import re
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
KEY = "B" + "A" * 86
import sys as _s
_s.path.insert(0, str(Path(__file__).resolve().parent))
import make_clubs  # noqa: E402
REPO_PUBLIC = bool(make_clubs.PUSH_PUBLIC)
MID = 1612257
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Quiet, directory=str(ROOT))
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8768), handler)
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8768"
STUB = re.search(r'STUB = """(.*?)"""', (ROOT / "test_push_toggle.py").read_text(encoding="utf-8"), re.S).group(1)


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


def subs(posts):
    return [b for k, b in posts if k == "subscribe"]


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script(STUB)
        pg = ctx.new_page()
        posts, errs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        mock_worker(pg, posts)

        # 1) club bell: one tap = all 7 types; Edit link appears only while on; the sheet lists 7 checked boxes
        pg.goto(f"{BASE}{pre}/clubs/962.html?push=1"); pg.wait_for_timeout(700)
        check(f"{lang}: club: Edit link hidden while the bell is off", pg.is_visible("#pushbtn") and not pg.is_visible("#pushedit"))
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sb = subs(posts)
        check(f"{lang}: club bell on -> subscribe teams=[962] tt={{962:243}} (the default: kickoff+goal+missed penalty+FT+red+reminder), no matches/leagues",
              len(sb) == 1 and sb[0]["teams"] == [962] and sb[0]["tt"] == {"962": 243} and sb[0]["matches"] == [] and sb[0]["leagues"] == [], posts)
        check(f"{lang}: Edit link now visible under the bell", pg.is_visible("#pushedit"))
        pg.click("#pushedit"); pg.wait_for_timeout(300)
        boxes = pg.locator("#psheet input[type=checkbox]")
        check(f"{lang}: sheet has exactly 8 type checkboxes: kick-off, goals, missed penalty, full-time, red cards, reminder ON; half-time and second half OFF; NO lineups type",
              boxes.count() == 8 and [boxes.nth(i).is_checked() for i in range(8)] == [True, True, True, False, False, True, True, True]
              and "تشكيل" not in pg.inner_text("#psheet") and "ineup" not in pg.inner_text("#psheet"), pg.inner_text("#psheet"))
        # tick half-time (bit 4, 4th row), untick goals (bit 2) and reminder (bit 64, last row): 243 + 4 - 2 - 64 = 181
        boxes.nth(3).check(); pg.wait_for_timeout(300); boxes.nth(1).uncheck(); pg.wait_for_timeout(300); boxes.nth(7).uncheck(); pg.wait_for_timeout(500)
        sb = subs(posts)
        check(f"{lang}: ticking half-time, unticking goals and reminder -> subscribe tt={{962:181}} (types stored per entity)", sb[-1]["tt"] == {"962": 181}, sb[-1])
        pg.click("#psheet .pdone"); pg.wait_for_timeout(200)
        check(f"{lang}: sheet closes; bell stays on", not pg.is_visible("#psheet") and pg.get_attribute("#pushbtn", "aria-pressed") == "true")
        pg.click("#pushbtn"); pg.wait_for_timeout(500); pg.click("#pushbtn"); pg.wait_for_timeout(600)
        check(f"{lang}: bell off then on again resets to the default (243)", subs(posts)[-1]["tt"] == {"962": 243}, subs(posts)[-1])
        # all unchecked = alerts off for the entity -> unsubscribe (nothing else subscribed)
        pg.click("#pushedit"); pg.wait_for_timeout(200)
        for i in range(8):
            pg.locator("#psheet input[type=checkbox]").nth(i).uncheck(); pg.wait_for_timeout(120)
        pg.wait_for_timeout(500)
        check(f"{lang}: unchecking every type turns the entity off -> /push/unsubscribe, bell off, Edit hidden",
              posts[-1][0] == "unsubscribe" and pg.get_attribute("#pushbtn", "aria-pressed") == "false" and not pg.is_visible("#pushedit"), posts[-1:])

        # 2) match bell: kind m, label stored; league bell: provider id (233 = EGY)
        posts.clear()
        pg.goto(f"{BASE}{pre}/matches/{MID}.html?push=1"); pg.wait_for_timeout(700)
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sb = subs(posts)
        check(f"{lang}: match bell -> matches=[{MID}] mt={{{MID}:243}}", len(sb) == 1 and sb[0]["matches"] == [MID] and sb[0]["mt"] == {str(MID): 243}, posts)
        check(f"{lang}: match label stored for the notifications page ('A × B')", "\u00d7" in (pg.evaluate("localStorage.getItem('fbPushLabels')") or ""), pg.evaluate("localStorage.getItem('fbPushLabels')"))
        pg.goto(f"{BASE}{pre}/leagues/egy.html?push=1"); pg.wait_for_timeout(700)
        check(f"{lang}: league page has a bell + Edit slot", pg.is_visible("#pushbtn"))
        pg.click("#pushbtn"); pg.wait_for_timeout(600)
        sb = subs(posts)
        # (the stub forgets its subscription on every navigation, so the earlier match entry was cleaned on load; the combined state is checked on the notifications page below)
        check(f"{lang}: league bell -> leagues=[233] lt={{233:243}}", sb[-1]["leagues"] == [233] and sb[-1]["lt"] == {"233": 243}, sb[-1])

        # 3) notifications page: gate, tabs, rows, bell + edit per row
        if REPO_PUBLIC:   # closed-gate behaviour checked on a patched copy of the page (PUB=true -> false)
            pg.route("**/notifications.html", lambda r: r.fulfill(response=r.fetch(), body=r.fetch().text().replace(",PUB=true,", ",PUB=false,")))
        pg.goto(f"{BASE}{pre}/notifications.html"); pg.wait_for_timeout(500)
        check(f"{lang}: notifications page with the gate closed (no ?push=1) shows only the beta note", pg.is_visible("#nbeta") and not pg.is_visible(".ntabs"))
        if REPO_PUBLIC:
            pg.unroute("**/notifications.html")
        # (the stub forgets its subscription on navigation: re-seed the local state the way a real session would have it)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(700)
        pg.evaluate("""() => { localStorage.setItem('fbClubs','[962,964]'); localStorage.setItem('fbPushTeams','[962]'); localStorage.setItem('fbPushLeagues','[233]');
                              localStorage.setItem('fbPushMatches','[[1612257,0]]'); localStorage.setItem('fbPushLabels','{"m:1612257":"A \\u00d7 B"}'); localStorage.setItem('fbPushOn','1'); localStorage.setItem('fbPushTypes','{"t:962":255}'); }""")
        pg.reload(); pg.wait_for_timeout(300)
        pg.evaluate("""() => { localStorage.setItem('fbClubs','[962,964]'); localStorage.setItem('fbPushTeams','[962]'); localStorage.setItem('fbPushLeagues','[233]');
                              localStorage.setItem('fbPushMatches','[[1612257,0]]'); localStorage.setItem('fbPushLabels','{"m:1612257":"A \\u00d7 B"}'); localStorage.setItem('fbPushOn','1'); localStorage.setItem('fbPushTypes','{"t:962":255}'); window.dispatchEvent(new Event('storage')); }""")
        # render again by flipping tabs (render runs on FBPush changes; trigger via a no-op sheet-less toggle of tab)
        pg.reload(); pg.wait_for_timeout(200)
        pg.evaluate("""() => { localStorage.setItem('fbClubs','[962,964]'); localStorage.setItem('fbPushTeams','[962]'); localStorage.setItem('fbPushLeagues','[233]');
                              localStorage.setItem('fbPushMatches','[[1612257,0]]'); localStorage.setItem('fbPushLabels','{"m:1612257":"A \\u00d7 B"}'); }""")
        pg.wait_for_timeout(100)
        # follow_data.js loads async and calls render(): wait for team rows then read them
        pg.wait_for_timeout(1200)
        rows = pg.locator("#nt .nrow")
        check(f"{lang}: Teams tab lists followed ∪ alert clubs (962 on first) + the per-match row", rows.count() >= 2, rows.count())
        txt = pg.inner_text("#nt")
        check(f"{lang}: summary line 'All types' / 'كل الأنواع' for the alerted club", ("كل الأنواع" if lang == "ar" else "All types") in txt, txt[:200])
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(300)
        check(f"{lang}: Leagues tab has 7 league rows", pg.locator("#nl .nrow").count() == 7, pg.locator("#nl .nrow").count())
        pg.locator("#nl .nrow .bellbtn").nth(0).click(); pg.wait_for_timeout(700)
        sb = subs(posts)
        check(f"{lang}: league row bell posts the full state (teams, matches and leagues kept; new league added)",
              sb and len(sb[-1]["leagues"]) >= 1 and sb[-1]["teams"] == [962] and sb[-1]["matches"] == [MID], sb[-1:] if sb else posts[-2:])
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()
    b.close()

# 4) master switch «كل التنبيهات / All alerts» (3E2)
with sync_playwright() as p2:
    b2 = p2.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = b2.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script(STUB)
        pg = ctx.new_page()
        posts, errs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        mock_worker(pg, posts)
        seed = """() => { localStorage.setItem('fbPushTeams','[962,964]'); localStorage.setItem('fbPushLeagues','[233]'); localStorage.setItem('fbPushTypes','{"t:962":243,"t:964":61,"l:233":243}'); localStorage.setItem('fbPushOn','1'); }"""
        # the stub forgets its browser subscription on every navigation, so the subscription is created ON the notifications page itself:
        # saved teams + masks are seeded, then the EGY league row bell is tapped (adds league 233 at the default and subscribes)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(500)
        pg.evaluate("""() => { localStorage.setItem('fbPushTeams','[962,964]'); localStorage.setItem('fbPushTypes','{"t:962":243,"t:964":61}'); localStorage.setItem('fbPushOn','1'); }""")
        pg.reload(); pg.wait_for_timeout(700)
        pg.evaluate("""() => { localStorage.setItem('fbPushTeams','[962,964]'); localStorage.setItem('fbPushTypes','{"t:962":243,"t:964":61}'); localStorage.setItem('fbPushOn','1'); }""")
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(300)
        pg.locator("#nl .nrow .bellbtn").nth(3).click(); pg.wait_for_timeout(800)    # EGY (233)
        check(f"{lang}: master switch visible at the top, ON by default, label «{'كل التنبيهات' if lang == 'ar' else 'All alerts'}»",
              pg.is_visible("#nmsw") and pg.is_checked("#nmsw") and ("كل التنبيهات" if lang == "ar" else "All alerts") in pg.inner_text("#nmaster"), pg.inner_text("#nmaster"))
        posts.clear()
        pg.locator("#nmaster .switch").click(); pg.wait_for_timeout(700)
        check(f"{lang}: switch OFF -> POST /push/unsubscribe (no alerts at all), rows dimmed, note shown", [k for k, _ in posts][-1:] == ["unsubscribe"] and not pg.is_checked("#nmsw")
              and "off" in (pg.get_attribute("#nviews", "class") or "") and pg.inner_text("#nmnote") != "", posts)
        saved = pg.evaluate("[localStorage.getItem('fbPushTeams'), localStorage.getItem('fbPushLeagues'), localStorage.getItem('fbPushTypes'), localStorage.getItem('fbPushMaster')]")
        check(f"{lang}: OFF keeps every saved choice (teams, leagues, per-entity masks) and records fbPushMaster=off",
              saved == ["[962,964]", "[233]", '{"t:962":243,"t:964":61,"l:233":243}', "off"], saved)
        # opening an entity page while off must NOT wipe the saved choices (the subscription is gone on purpose)
        pg.goto(f"{BASE}{pre}/clubs/962.html"); pg.wait_for_timeout(700)
        check(f"{lang}: club page while the master is off: bell shows OFF, saved lists intact",
              pg.get_attribute("#pushbtn", "aria-pressed") == "false" and pg.evaluate("localStorage.getItem('fbPushTeams')") == "[962,964]", pg.evaluate("localStorage.getItem('fbPushTeams')"))
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(800)
        posts.clear()
        pg.locator("#nmaster .switch").click(); pg.wait_for_timeout(900)
        sb = subs(posts)
        check(f"{lang}: switch ON -> ONE subscribe with the full saved state restored (teams, masks 243/61, league 233)",
              len(sb) == 1 and sb[0]["teams"] == [962, 964] and sb[0]["tt"] == {"962": 243, "964": 61} and sb[0]["leagues"] == [233] and sb[0]["lt"] == {"233": 243}, posts)
        check(f"{lang}: ON -> fbPushMaster cleared, rows not dimmed", pg.evaluate("localStorage.getItem('fbPushMaster')") is None and "off" not in (pg.get_attribute("#nviews", "class") or ""))
        # tapping a bell on an entity page while off: turns the master on AND the entity on
        pg.locator("#nmaster .switch").click(); pg.wait_for_timeout(700)
        pg.goto(f"{BASE}{pre}/clubs/965.html?push=1"); pg.wait_for_timeout(700)
        posts.clear()
        pg.click("#pushbtn"); pg.wait_for_timeout(800)
        sb = subs(posts)
        check(f"{lang}: bell tap while master is off -> master back ON, saved choices restored AND this club added (965 at the default)",
              sb and 965 in sb[-1]["teams"] and sb[-1]["tt"].get("965") == 243 and pg.evaluate("localStorage.getItem('fbPushMaster')") is None, sb[-1:] if sb else posts)
        check(f"{lang}: no page errors (master switch)", not errs, errs)
        ctx.close()
    b2.close()

# 5) finished matches hidden (18 Oct): FBPush.prune from the live payload (f: FT/AET/PEN = finished; m or a non-final f status = kept),
#    fallback kickoff + 4h when the id is not live/held; no kickoff = kept (14-day rule); live fetch failure = fallback only
H = 3600 * 1000
SEED_M = """(ko) => { const n = Date.now(); localStorage.setItem('fbPushMatches', JSON.stringify([
  [1001, n - 1*ko], [1002, n - 6*ko], [1003, n - 5*ko], [1004, 0], [1005, n - 5*ko], [1006, n - 1*ko], [1007, n - 2*ko]]));
  localStorage.setItem('fbPushLabels', JSON.stringify({'m:1001':'FT','m:1002':'PST','m:1003':'LIVE','m:1004':'NOKO','m:1005':'OLD','m:1006':'SOON','m:1007':'AET'})); }"""
LIVE_J = json.dumps({"t": 0, "m": {"1003": {"s": "2H"}}, "f": {"1001": {"s": "FT"}, "1002": {"s": "PST"}, "1007": {"s": "AET"}}})


def live_route(page, posts, body):
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
        if body is None:
            return route.abort()
        return route.fulfill(status=200, headers=h, body=body)
    page.route("https://saffara-live.abujaishamr.workers.dev/**", handle)


def stored_ids(pg):
    return sorted(x[0] for x in json.loads(pg.evaluate("localStorage.getItem('fbPushMatches')") or "[]"))


with sync_playwright() as p3:
    b3 = p3.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        # a) live payload available, no browser subscription (the stub forgets it on navigation): local list pruned, nothing posted
        ctx = b3.new_context(viewport={"width": 390, "height": 844}); ctx.add_init_script(STUB)
        pg = ctx.new_page(); posts, errs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        live_route(pg, posts, LIVE_J)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(300)
        pg.evaluate(SEED_M, H); pg.reload(); pg.wait_for_timeout(1500)
        ids = stored_ids(pg)
        check(f"{lang}: prune: FT (status rule) dropped", 1001 not in ids, ids)
        check(f"{lang}: prune: AET (status rule) dropped", 1007 not in ids, ids)
        check(f"{lang}: prune: PST kept although kickoff + 6h passed", 1002 in ids, ids)
        check(f"{lang}: prune: live match kept although kickoff + 5h passed", 1003 in ids, ids)
        check(f"{lang}: prune: no-kickoff entry kept (14-day rule)", 1004 in ids, ids)
        check(f"{lang}: prune: kickoff + 5h, not in the live payload -> dropped (fallback)", 1005 not in ids, ids)
        check(f"{lang}: prune: kickoff + 1h, not in the live payload -> kept", 1006 in ids, ids)
        lab = pg.evaluate("localStorage.getItem('fbPushLabels')") or ""
        check(f"{lang}: prune: labels of dropped matches removed, kept ones intact", "FT" not in lab and "OLD" not in lab and "PST" in lab and "NOKO" in lab, lab)
        hrefs = sorted(int(re.search(r"(\d+)\.html", h).group(1)) for h in pg.eval_on_selector_all("#nt a[href*='matches/']", "els => els.map(e => e.getAttribute('href'))"))
        check(f"{lang}: Matches section lists only the kept matches", hrefs == [1002, 1003, 1004, 1006], hrefs)
        check(f"{lang}: prune with no subscription posts nothing", not posts, posts)
        check(f"{lang}: no page errors (prune)", not errs, errs)
        ctx.close()

        # b) live fetch fails: status rule skipped, fallback only (FT within 4h kept; PST/live older than 4h dropped: no status known)
        ctx = b3.new_context(viewport={"width": 390, "height": 844}); ctx.add_init_script(STUB)
        pg = ctx.new_page(); posts, errs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        live_route(pg, posts, None)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(300)
        pg.evaluate(SEED_M, H); pg.reload(); pg.wait_for_timeout(1500)
        ids = stored_ids(pg)
        check(f"{lang}: fetch fail: fallback only -> [1001, 1004, 1006, 1007] kept", ids == [1001, 1004, 1006, 1007], ids)
        check(f"{lang}: fetch fail: Matches section still rendered", pg.locator("#nt a[href*='matches/']").count() == 4)
        check(f"{lang}: no page errors (fetch fail)", not errs, errs)
        ctx.close()

        # c) a browser subscription exists: prune -> ONE /push/subscribe with the pruned match set (server set replaced)
        ctx = b3.new_context(viewport={"width": 390, "height": 844}); ctx.add_init_script(STUB)
        pg = ctx.new_page(); posts, errs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        live_route(pg, posts, '{"t":0,"m":{}}')
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(800)
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(200)
        pg.locator("#nl .nrow .bellbtn").nth(3).click(); pg.wait_for_timeout(800)   # creates the subscription (EGY league)
        pg.evaluate(SEED_M, H)
        posts.clear()
        r = pg.evaluate("FBPush.prune([1001,1007],[1002,1003])"); pg.wait_for_timeout(600)
        sb = subs(posts)
        check(f"{lang}: prune with a subscription -> one subscribe, matches = kept set, league kept",
              r is True and len(sb) == 1 and sorted(sb[0]["matches"]) == [1002, 1003, 1004, 1006] and sb[0]["leagues"] == [233], posts)
        posts.clear()
        r = pg.evaluate("FBPush.prune([],[1002,1003])"); pg.wait_for_timeout(400)
        check(f"{lang}: prune with nothing to drop -> no post", r is False and not posts, posts)
        # failed live fetch (finishedIds === null) with a subscription: hidden locally only, server set NOT replaced
        pg.evaluate(SEED_M, H)
        posts.clear()
        r = pg.evaluate("FBPush.prune(null,[])"); pg.wait_for_timeout(600)
        ids = stored_ids(pg)
        check(f"{lang}: prune after a failed fetch with a subscription -> local fallback applied, NO /push/ post",
              r is True and ids == [1001, 1004, 1006, 1007] and not posts, (ids, posts))
        check(f"{lang}: no page errors (prune + subscription)", not errs, errs)
        ctx.close()

        # 6) league rows: logo badges (lgbadge lg-<code>, 36px), no trophy emoji
        ctx = b3.new_context(viewport={"width": 390, "height": 844}); ctx.add_init_script(STUB)
        pg = ctx.new_page(); posts = []
        mock_worker(pg, posts)
        pg.goto(f"{BASE}{pre}/notifications.html?push=1"); pg.wait_for_timeout(500)
        pg.click(".ntab[data-t=l]"); pg.wait_for_timeout(300)
        imgs = pg.locator("#nl .nrow img.lgbadge")
        info = pg.eval_on_selector_all("#nl .nrow img.lgbadge", "els => els.map(e => [e.className, e.naturalWidth > 0, Math.round(e.getBoundingClientRect().width)])")
        check(f"{lang}: 7 league rows with lgbadge logos (loaded, 36px), classes lg-<code>",
              imgs.count() == 7 and all(ok and w == 36 for _, ok, w in info) and info[0][0] == "lgbadge lg-jor", info)
        check(f"{lang}: no trophy emoji on league rows", "\U0001F3C6" not in pg.inner_text("#nl"))
        ctx.close()
    b3.close()

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
