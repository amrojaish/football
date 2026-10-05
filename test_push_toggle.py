"""Playwright test of the club-page "Goal alerts" toggle (beta, ?push=1). Run:
    python C:\\Users\\User\\Projects\\Football\\test_push_toggle.py
Needs regenerated assets + club pages (make_assets.py, make_clubs.py). No real push service:
Notification / PushManager / serviceWorker.ready are stubbed and the worker URL is mocked."""
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
KEY = "B" + "A" * 86          # fake 87-char VAPID key (valid base64url)
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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8766), handler)
srv.handle_error = lambda *a: None   # connection aborts when a context closes mid-transfer
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8766"

STUB = """
(function(){
  var perm='default', sub=null;
  window.__calls=[];
  window.Notification = function(){};
  Object.defineProperty(Notification,'permission',{get:function(){return perm;}});
  Notification.requestPermission=function(){window.__calls.push('requestPermission');perm='granted';return Promise.resolve('granted');};
  var reg={pushManager:{
    getSubscription:function(){return Promise.resolve(sub);},
    subscribe:function(o){window.__calls.push('subscribe:'+o.userVisibleOnly+':'+(o.applicationServerKey&&o.applicationServerKey.length));
      sub={endpoint:'https://fcm.googleapis.com/fcm/send/pw-test',
        toJSON:function(){return {endpoint:this.endpoint,expirationTime:null,keys:{p256dh:'P'.repeat(87),auth:'A'.repeat(22)}};},
        unsubscribe:function(){window.__calls.push('sub.unsubscribe');sub=null;return Promise.resolve(true);}};
      return Promise.resolve(sub);}}};
  Object.defineProperty(navigator,'serviceWorker',{value:{ready:Promise.resolve(reg),register:function(){return Promise.resolve(reg);},addEventListener:function(){}},configurable:true});
  window.PushManager=function(){};
})();
"""


def mock_worker(page, posts):
    def handle(route):
        req = route.request
        headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
                   "Content-Type": "application/json"}
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=headers)
        if req.url.endswith("/push/key"):
            return route.fulfill(status=200, headers=headers, body=json.dumps({"key": KEY}))
        if "/push/" in req.url:
            posts.append((req.url.rsplit("/", 1)[1], json.loads(req.post_data)))
            return route.fulfill(status=200, headers=headers, body='{"ok":true}')
        return route.fulfill(status=200, headers=headers, body='{"t":0,"m":{}}')
    page.route("https://saffara-live.abujaishamr.workers.dev/**", handle)


with sync_playwright() as p:
    b = p.chromium.launch()

    # 1) hidden without ?push=1, visible with it (ar + en)
    for lang, path in (("ar", "/clubs/962.html"), ("en", "/en/clubs/962.html")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + path, wait_until="load")
        check(f"{lang}: toggle hidden without ?push=1", not pg.is_visible("#pushrow"))
        pg.goto(BASE + path + "?push=1", wait_until="load")
        check(f"{lang}: toggle visible with ?push=1", pg.is_visible("#pushrow") and pg.is_visible("#pushbtn"))
        txt = pg.inner_text("#pushbtn")
        check(f"{lang}: label", ("تنبيهات الأهداف" in txt) if lang == "ar" else ("Goal alerts" in txt), txt)
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()

    # 1b) installed app (standalone): visible without ?push=1 (matchMedia + iOS navigator.standalone)
    MM = r"""
    (function(){var o=window.matchMedia.bind(window);
      window.matchMedia=function(q){ if(/display-mode:\s*standalone/.test(q)){
        return {matches:true,media:q,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}}; }
        return o(q); };})();
    """
    for label, init in (("display-mode standalone", MM),
                        ("iOS navigator.standalone", "Object.defineProperty(navigator,'standalone',{value:true});")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script(init)
        pg = ctx.new_page()
        pg.goto(BASE + "/clubs/962.html", wait_until="load")
        check(f"standalone ({label}): visible without ?push=1", pg.is_visible("#pushrow") and pg.is_visible("#pushbtn"))
        pg.goto(BASE + "/en/clubs/962.html", wait_until="load")
        check(f"standalone ({label}): visible on en page", pg.is_visible("#pushrow"))
        ctx.close()

    # 1c) normal browser, no param: hidden (display-mode browser, navigator.standalone false/undefined)
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.goto(BASE + "/clubs/962.html", wait_until="load")
    check("normal browser without ?push=1: hidden (standalone not matched)",
          not pg.is_visible("#pushrow") and not pg.evaluate("window.matchMedia('(display-mode: standalone)').matches"))
    ctx.close()

    # 2) ?push=0 / other values stay hidden
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto(BASE + "/clubs/962.html?push=0", wait_until="load")
    check("?push=0 -> hidden", not pg.is_visible("#pushrow"))
    ctx.close()

    # 3) full flow with stubs: subscribe (club + followed), then unsubscribe
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(STUB)
    ctx.add_init_script("try{localStorage.setItem('fbClubs','[964,962,965]');}catch(e){}")
    pg = ctx.new_page()
    posts = []
    mock_worker(pg, posts)
    pg.goto(BASE + "/clubs/962.html?push=1", wait_until="load")
    check("flow: starts off", pg.get_attribute("#pushbtn", "aria-pressed") == "false")
    pg.click("#pushbtn")
    pg.wait_for_function("document.getElementById('pushbtn').getAttribute('aria-pressed')==='true'", timeout=5000)
    calls = pg.evaluate("window.__calls")
    check("flow: requestPermission then subscribe(userVisibleOnly, key bytes=65)",
          calls[:2] == ["requestPermission", "subscribe:true:65"], calls)
    sub = [x for x in posts if x[0] == "subscribe"]
    check("flow: POST /push/subscribe once", len(sub) == 1, posts)
    if sub:
        body = sub[0][1]
        check("  teams = followed clubs + this club (deduped)", sorted(body["teams"]) == [962, 964, 965], body["teams"])
        check("  lang ar + subscription keys", body["lang"] == "ar" and body["subscription"]["keys"]["auth"] == "A" * 22, body)
    check("flow: 'on' message shown", "مفعّلة" in pg.inner_text("#pushmsg"), pg.inner_text("#pushmsg"))
    pg.click("#pushbtn")
    pg.wait_for_function("document.getElementById('pushbtn').getAttribute('aria-pressed')==='false'", timeout=5000)
    un = [x for x in posts if x[0] == "unsubscribe"]
    check("flow: POST /push/unsubscribe with endpoint + auth",
          len(un) == 1 and un[0][1] == {"endpoint": "https://fcm.googleapis.com/fcm/send/pw-test", "auth": "A" * 22}, posts)
    check("flow: browser subscription removed", "sub.unsubscribe" in pg.evaluate("window.__calls"))
    ctx.close()

    # 4) english page posts lang=en and the club id of that page
    ctx = b.new_context()
    ctx.add_init_script(STUB)
    pg = ctx.new_page()
    posts = []
    mock_worker(pg, posts)
    pg.goto(BASE + "/en/clubs/964.html?push=1", wait_until="load")
    pg.click("#pushbtn")
    pg.wait_for_function("document.getElementById('pushbtn').getAttribute('aria-pressed')==='true'", timeout=5000)
    sub = [x for x in posts if x[0] == "subscribe"]
    check("en: lang=en, teams=[964] (nothing followed)", sub and sub[0][1]["lang"] == "en" and sub[0][1]["teams"] == [964], posts)
    ctx.close()

    # 5) permission denied -> message, no subscribe
    ctx = b.new_context()
    ctx.add_init_script(STUB + "Notification.requestPermission=function(){window.__calls.push('requestPermission');return Promise.resolve('denied');};")
    pg = ctx.new_page()
    posts = []
    mock_worker(pg, posts)
    pg.goto(BASE + "/clubs/962.html?push=1", wait_until="load")
    pg.click("#pushbtn")
    pg.wait_for_function("document.getElementById('pushmsg').textContent.length>0", timeout=5000)
    check("denied: message shown, nothing posted, not pressed",
          "محظور" in pg.inner_text("#pushmsg") and not posts and pg.get_attribute("#pushbtn", "aria-pressed") == "false",
          (pg.inner_text("#pushmsg"), posts))
    ctx.close()

    # 6) unsupported (no PushManager) -> disabled button + explanation (iPhone not installed)
    ctx = b.new_context()
    ctx.add_init_script("try{delete window.PushManager;}catch(e){window.PushManager=undefined;}")
    pg = ctx.new_page()
    pg.goto(BASE + "/clubs/962.html?push=1", wait_until="load")
    check("unsupported: visible, button disabled, message mentions Home Screen/الشاشة الرئيسية",
          pg.is_visible("#pushrow") and pg.is_disabled("#pushbtn") and "الشاشة الرئيسية" in pg.inner_text("#pushmsg"),
          pg.inner_text("#pushmsg"))
    ctx.close()
    b.close()

srv.shutdown()
raise SystemExit(1 if fails else 0)
