#!/usr/bin/env python3
"""
Playwright (390px): per-club goal-alert button on club pages.
PushManager / Notification / the worker are mocked (headless Chromium has no real push), so this tests the
page's own logic: fbPushTeams list (separate from fbClubs), replace-list semantics, last club = unsubscribe,
429/503 messages, 50-club cap, legacy migration, PUSH_PUBLIC + iOS hint, hidden-by-default.

Needs the site served locally (python -m http.server 8765 from the repo root, after make_assets.py +
make_clubs.py). Run: python test_push_button.py [screenshot_dir]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8765"
W = "https://saffara-live.abujaishamr.workers.dev"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
FAISALY, WEHDAT, SALT = 4531, 4529, 4535

MOCK_JS = """
(() => {
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} };
  const fakeSub = () => ({
    toJSON() { return { endpoint: 'https://fcm.googleapis.com/fcm/send/pw1', keys: { p256dh: 'P'.repeat(87), auth: 'A'.repeat(22) } }; },
    unsubscribe() { ls('mocksub', null); window.__unsubscribed = (window.__unsubscribed || 0) + 1; return Promise.resolve(true); },
  });
  const reg = { pushManager: {
    getSubscription: () => Promise.resolve(ls('mocksub') === '1' ? fakeSub() : null),
    subscribe: () => { ls('mocksub', '1'); window.__subscribed = (window.__subscribed || 0) + 1; return Promise.resolve(fakeSub()); },
  } };
  const sw = { ready: Promise.resolve(reg), register: () => Promise.resolve(reg), addEventListener() {}, getRegistrations: () => Promise.resolve([]) };
  Object.defineProperty(navigator, 'serviceWorker', { get() { return sw; }, configurable: true });
  if (!window.PushManager) window.PushManager = function () {};
  Notification.requestPermission = () => { ls('mockperm', 'granted'); return Promise.resolve('granted'); };
  Object.defineProperty(Notification, 'permission', { get() { return ls('mockperm') || 'default'; }, configurable: true });
})();
"""

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " " + json.dumps(extra, ensure_ascii=False, default=str)))
    if not cond:
        fails += 1


class Server:
    """mock saffara-live: records calls; `force` = status to answer /push/subscribe with; `teams_reply` for /push/teams"""
    def __init__(self):
        self.calls, self.force, self.teams_reply = [], None, ("ok", [])

    def handle(self, route, request):
        h = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Content-Type": "application/json"}
        if request.method == "OPTIONS":
            return route.fulfill(status=204, headers=h)
        path = request.url[len(W):]
        body = json.loads(request.post_data) if request.post_data else None
        self.calls.append((path, body))
        if path == "/push/key":
            return route.fulfill(status=200, headers=h, body=json.dumps({"key": "A" * 87}))
        if path == "/push/subscribe" and self.force:
            return route.fulfill(status=self.force, headers=h, body=json.dumps({"error": "x"}))
        if path == "/push/teams":
            kind, teams = self.teams_reply
            return route.fulfill(status=200 if kind == "ok" else 500, headers=h, body=json.dumps({"teams": teams}))
        return route.fulfill(status=200, headers=h, body=json.dumps({"ok": True}))

    def last(self, path):
        xs = [b for p, b in self.calls if p == path]
        return xs[-1] if xs else None

    def n(self, path):
        return sum(1 for p, _ in self.calls if p == path)


def new_page(browser, srv, ui_lang="ar", ua=None, storage=None, replace_pub=False, errors=None):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="en-US", **({"user_agent": ua} if ua else {}))
    ctx.add_init_script(MOCK_JS)
    if storage:
        ctx.add_init_script("(()=>{ if (sessionStorage.getItem('seeded')) return; sessionStorage.setItem('seeded','1'); const s=%s; for (const k in s) localStorage.setItem(k, s[k]); })();" % json.dumps(storage))
    ctx.route(W + "/**", srv.handle)
    if replace_pub:
        ctx.route("**/assets/club.*.js*", lambda r: r.fulfill(response=r.fetch(), body=r.fetch().text().replace("var PUB=false", "var PUB=true")))
    pg = ctx.new_page()
    if errors is not None:
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, pg


def club(lang, tid, push=True):
    return f"{B}{'' if lang == 'ar' else '/en'}/clubs/{tid}.html" + ("?push=1" if push else "")


def state(pg):
    return pg.evaluate("""() => ({ pressed: document.getElementById('pushbtn').getAttribute('aria-pressed'),
      msg: document.getElementById('pushmsg').textContent, hidden: document.getElementById('pushrow').hidden,
      disabled: document.getElementById('pushbtn').disabled,
      teams: JSON.parse(localStorage.getItem('fbPushTeams') || 'null'), on: localStorage.getItem('fbPushOn'),
      clubs: JSON.parse(localStorage.getItem('fbClubs') || 'null'), unsub: window.__unsubscribed || 0, subd: window.__subscribed || 0,
      hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth })""")


def click(pg):
    pg.click("#pushbtn")
    pg.wait_for_timeout(500)


with sync_playwright() as p:
    br = p.chromium.launch()
    errors = []

    # ---- 1) add club, follow stays separate, add second club (list replaced), remove one, remove last ----
    srv = Server()
    ctx, pg = new_page(br, srv, storage={"fbClubs": json.dumps([SALT])}, errors=errors)
    pg.goto(club("ar", FAISALY)); pg.wait_for_timeout(600)
    s = state(pg)
    check("button visible with ?push=1 and starts off", (not s["hidden"]) and s["pressed"] == "false" and s["teams"] is None, s)
    click(pg); s = state(pg)
    sub = srv.last("/push/subscribe")
    check("on: POST /push/subscribe with ONLY this club (followed club excluded), page lang ar",
          sub and sub["teams"] == [FAISALY] and sub["lang"] == "ar", sub)
    check("  pressed, fbPushTeams=[club], fbClubs untouched", s["pressed"] == "true" and s["teams"] == [FAISALY] and s["clubs"] == [SALT] and s["on"] == "1", s)
    pg.screenshot(path=str(SHOTS / "pushbtn_ar_on.png"))
    pg.goto(club("en", WEHDAT)); pg.wait_for_timeout(600)
    check("other club's page starts off (state is per club)", state(pg)["pressed"] == "false")
    click(pg); sub = srv.last("/push/subscribe"); s = state(pg)
    check("second club (en page): full list [A,B] sent, lang switches to en", sub["teams"] == [FAISALY, WEHDAT] and sub["lang"] == "en", sub)
    check("  fbPushTeams=[A,B]", s["teams"] == [FAISALY, WEHDAT], s)
    pg.screenshot(path=str(SHOTS / "pushbtn_en_on.png"))
    click(pg); sub = srv.last("/push/subscribe"); s = state(pg)
    check("turn one off: list [A] re-sent via subscribe (no unsubscribe)", sub["teams"] == [FAISALY] and srv.n("/push/unsubscribe") == 0 and s["teams"] == [FAISALY] and s["pressed"] == "false", [sub, s])
    pg.goto(club("ar", FAISALY)); pg.wait_for_timeout(600)
    check("page of the remaining club shows on after reload", state(pg)["pressed"] == "true")
    click(pg); s = state(pg)
    check("turn off the LAST club -> /push/unsubscribe, browser sub removed, local state cleared",
          srv.n("/push/unsubscribe") == 1 and s["unsub"] == 1 and s["teams"] is None and s["on"] is None and s["pressed"] == "false", [srv.last("/push/unsubscribe"), s])
    ctx.close()

    # ---- 2) limits shown to the user ----
    for code, key_ar, key_en in ((429, "محاولات كثيرة", "Too many attempts"), (503, "ممتلئة", "full right now")):
        for lang, needle in (("ar", key_ar), ("en", key_en)):
            srv = Server(); srv.force = code
            ctx, pg = new_page(br, srv)
            pg.goto(club(lang, FAISALY)); pg.wait_for_timeout(500)
            click(pg); s = state(pg)
            check(f"{code} on subscribe ({lang}): friendly message, button stays off, nothing saved, new browser sub rolled back",
                  needle in s["msg"] and s["pressed"] == "false" and s["teams"] is None and s["unsub"] == 1, s)
            if lang == "ar" and code == 503:
                pg.screenshot(path=str(SHOTS / "pushbtn_ar_full.png"))
            ctx.close()

    # ---- 3) 50-club cap on the client ----
    srv = Server()
    fifty = [962, 964, 965, 968, 969, 971, 973, 974, 975, 976, 977, 1030, 1031, 1032, 1036, 1037, 1039, 1040, 1041, 1044, 1046, 1048, 1074, 1075, 1572,
             1574, 1575, 1576, 1577, 2865, 2867, 2868, 2869, 2870, 2871, 2872, 2873, 2874, 2875, 2876, 2877, 2879, 2893, 2894, 2895, 2896, 2897, 2898, 2899, 2900]
    ctx, pg = new_page(br, srv, storage={"fbPushTeams": json.dumps(fifty), "fbPushOn": "1", "mocksub": "1", "mockperm": "granted"})
    pg.goto(club("en", FAISALY)); pg.wait_for_timeout(500)
    click(pg); s = state(pg)
    check("already 50 alert clubs: adding another -> 'up to 50' message, no POST", "50" in s["msg"] and srv.n("/push/subscribe") == 0 and s["pressed"] == "false", s)
    ctx.close()

    # ---- 4) legacy subscribers (fbPushOn=1, no fbPushTeams) ----
    srv = Server(); srv.teams_reply = ("ok", [FAISALY, SALT])
    ctx, pg = new_page(br, srv, storage={"fbPushOn": "1", "mocksub": "1", "mockperm": "granted", "fbClubs": json.dumps([777])})
    pg.goto(club("ar", SALT)); pg.wait_for_timeout(700); s = state(pg)
    check("migration: list = what the server has for this subscription ([A, SALT]); this club shows on",
          s["teams"] == [FAISALY, SALT] and s["pressed"] == "true" and srv.n("/push/teams") == 1, s)
    ctx.close()
    srv = Server(); srv.teams_reply = ("fail", [])
    ctx, pg = new_page(br, srv, storage={"fbPushOn": "1", "mocksub": "1", "mockperm": "granted"})
    pg.goto(club("ar", WEHDAT)); pg.wait_for_timeout(700); s = state(pg)
    check("migration fallback (server unreachable): list = this club only", s["teams"] == [WEHDAT] and s["pressed"] == "true", s)
    ctx.close()
    srv = Server()
    ctx, pg = new_page(br, srv, storage={"fbPushTeams": json.dumps([FAISALY]), "fbPushOn": "1"})   # permission/sub gone
    pg.goto(club("ar", FAISALY)); pg.wait_for_timeout(600); s = state(pg)
    check("browser lost the subscription/permission: local list cleared, button off", s["teams"] is None and s["pressed"] == "false" and s["on"] is None, s)
    ctx.close()

    # ---- 5) hidden by default; PUSH_PUBLIC; iOS hint ----
    srv = Server()
    ctx, pg = new_page(br, srv)
    pg.goto(club("ar", FAISALY, push=False)); pg.wait_for_timeout(500)
    check("no ?push=1 and PUSH_PUBLIC=False -> row stays hidden", state(pg)["hidden"] is True)
    ctx.close()
    ctx, pg = new_page(br, srv, replace_pub=True)
    pg.goto(club("ar", FAISALY, push=False)); pg.wait_for_timeout(500)
    check("PUSH_PUBLIC=True (patched asset) -> visible to everyone without ?push=1", state(pg)["hidden"] is False)
    ctx.close()
    IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
    for lang, needle in (("ar", "أضف الموقع للشاشة الرئيسية لتفعيل التنبيهات"), ("en", "Add the site to your Home Screen to turn on alerts")):
        ctx, pg = new_page(br, srv, ua=IOS, replace_pub=True)
        pg.goto(club(lang, FAISALY, push=False)); pg.wait_for_timeout(500); s = state(pg)
        check(f"PUSH_PUBLIC + iPhone not installed ({lang}): hint shown, button disabled", s["msg"] == needle and s["disabled"] and not s["hidden"], s)
        pg.screenshot(path=str(SHOTS / f"pushbtn_{lang}_ios_hint.png"))
        ctx.close()
    ctx, pg = new_page(br, srv, ua=IOS)
    pg.goto(club("ar", FAISALY, push=False)); pg.wait_for_timeout(500)
    check("iPhone, PUSH_PUBLIC=False, no ?push=1 -> still hidden", state(pg)["hidden"] is True)
    ctx.close()

    # ---- 6) layout + console ----
    srv = Server()
    for lang in ("ar", "en"):
        ctx, pg = new_page(br, srv, errors=errors)
        pg.goto(club(lang, FAISALY)); pg.wait_for_timeout(500); click(pg)
        check(f"390px {lang}: no horizontal scroll with the button and message", state(pg)["hscroll"] is False)
        ctx.close()
    check("no console errors / page errors", not errors, errors[:3])
    br.close()

print("FAILS:", fails)
sys.exit(1 if fails else 0)
