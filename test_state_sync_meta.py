#!/usr/bin/env python3
"""state_sync.GitHubStore.put_meta / put_blob: يتعافيان من أصل متبقٍّ ومن 422 already_exists
بعد إعادة محاولة _req (حادثة 4 نوفمبر). GitHub مزيَّف على مستوى HTTP — بلا شبكة.
التشغيل: python test_state_sync_meta.py"""
import hashlib
import json
import sys

import state_sync as ss

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


class Resp:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)


class FakeGitHub:
    """أصول إصدار db-state بالذاكرة؛ upload_5xx_after_create يحاكي 502 بعد إنشاء الأصل."""
    API = ss.GitHubStore.API
    UP = "https://uploads.example/assets"

    def __init__(self, digests=False):
        self.assets = {}  # id -> {"id","name","state","data"}
        self.next_id = 100
        self.upload_5xx_after_create = 0
        self.digests = digests
        self.calls = []

    def add(self, name, data, state="uploaded"):
        self.next_id += 1
        self.assets[self.next_id] = {"id": self.next_id, "name": name, "state": state,
                                     "data": data}
        return self.next_id

    def by_name(self, name):
        return [a for a in self.assets.values() if a["name"] == name]

    def count(self, method, kind=None):
        return sum(1 for m, u, _ in self.calls
                   if m == method and (kind is None or kind in u))

    def _pub(self, a):
        p = {"id": a["id"], "name": a["name"], "state": a["state"], "size": len(a["data"]),
             "url": f"{self.API}/repos/x/releases/assets/{a['id']}"}
        if self.digests:
            p["digest"] = "sha256:" + hashlib.sha256(a["data"]).hexdigest()
        return p

    def request(self, method, url, timeout=None, headers=None, params=None, data=None,
                json=None):
        self.calls.append((method, url, (params or {}).get("name")))
        if method == "GET" and url.endswith(f"/releases/tags/{ss.TAG}"):
            return Resp(200, {"upload_url": self.UP + "{?name,label}",
                              "assets": [self._pub(a) for a in self.assets.values()]})
        if method == "POST" and url == self.UP:
            name = params["name"]
            if self.by_name(name):
                return Resp(422, {"message": "Validation Failed",
                                  "errors": [{"resource": "ReleaseAsset",
                                              "code": "already_exists", "field": "name"}]})
            aid = self.add(name, data)
            if self.upload_5xx_after_create:
                self.upload_5xx_after_create -= 1
                return Resp(502, b"Bad Gateway")
            return Resp(201, self._pub(self.assets[aid]))
        if "/releases/assets/" in url:
            aid = int(url.rsplit("/", 1)[1])
            a = self.assets.get(aid)
            if method == "GET":
                return Resp(200, a["data"]) if a else Resp(404)
            if method == "DELETE":
                return Resp(204) if self.assets.pop(aid, None) else Resp(404)
            if method == "PATCH":
                if not a:
                    return Resp(404)
                if self.by_name(json["name"]):
                    return Resp(422, {"errors": [{"code": "already_exists"}]})
                a["name"] = json["name"]
                return Resp(200, self._pub(a))
        raise AssertionError(f"unexpected {method} {url}")


def store(fake):
    s = ss.GitHubStore.__new__(ss.GitHubStore)
    s.r, s.repo, s.h, s._rel = fake, "x", {}, None
    return s


def scenario(label, fn):
    """كل سيناريو معزول: SystemExit/استثناء = FAIL بدل إيقاف الملف (لفحص الكود القديم)."""
    try:
        fn()
    except BaseException as e:  # noqa: BLE001  (SystemExit مقصود)
        check(f"{label}: no crash", False, f"{type(e).__name__}: {str(e)[:120]}")


ss.time.sleep = lambda *_: None  # إعادة محاولات _req بلا انتظار

OLD = {"seq": 1529, "lock": None}
NEW = {"seq": 1529, "lock": {"holder": "ci"}}
BLOB = "state-001530-20261104.enc"
PAYLOAD = b"SFR1" + bytes(range(256)) * 40


def enc(m):
    return json.dumps(m, indent=1, ensure_ascii=False).encode("utf-8")


def base():
    f = FakeGitHub()
    f.add("meta.json", enc(OLD))
    f.add("state-001529-20261104.enc", b"blob")
    return f


def meta_ok(fake, want, label):
    metas = fake.by_name("meta.json")
    check(f"{label}: one meta.json", len(metas) == 1, [a["name"] for a in fake.assets.values()])
    check(f"{label}: meta.json content = new", metas and metas[0]["data"] == enc(want))
    check(f"{label}: no meta.new left", not fake.by_name("meta.new"))
    check(f"{label}: blobs untouched", len(fake.by_name("state-001529-20261104.enc")) == 1)


def blob_ok(fake, label):
    b = fake.by_name(BLOB)
    check(f"{label}: exactly one blob", len(b) == 1, [a["name"] for a in fake.assets.values()])
    check(f"{label}: blob content = payload", b and b[0]["data"] == PAYLOAD)
    check(f"{label}: blob fully uploaded", b and b[0]["state"] == "uploaded")
    check(f"{label}: other assets untouched",
          len(fake.by_name("meta.json")) == 1
          and len(fake.by_name("state-001529-20261104.enc")) == 1)


# ═══════════════ put_meta ═══════════════
def m1():  # الحادثة: meta.new متبقٍّ من تشغيل سابق
    f = base()
    f.add("meta.new", enc(NEW))
    store(f).put_meta(NEW)
    meta_ok(f, NEW, "meta leftover")
    check("meta leftover: get_meta reads it back", store(f).get_meta() == NEW)


def m2():  # بقايا بمحتوى مختلف (قديم) لا تتسرب إلى meta.json
    f = base()
    f.add("meta.new", enc({"seq": 1, "stale": True}))
    store(f).put_meta(NEW)
    meta_ok(f, NEW, "meta stale leftover")


def m3():  # السبب الجذري: 502 بعد إنشاء الأصل ← إعادة محاولة _req تتلقى 422
    f = base()
    f.upload_5xx_after_create = 1
    store(f).put_meta(NEW)
    meta_ok(f, NEW, "meta 5xx-then-422")
    check("meta 5xx-then-422: reused, no third POST", f.count("POST") == 2, f.count("POST"))


def m4():  # 422 والأصل ظهر بين الحذف والرفع ناقصاً (state != uploaded) ← يُحذف ويُعاد
    f = base()
    s = store(f)
    orig = s._post_asset
    done = []

    def post(name, data):
        if not done:
            done.append(1)
            f.add(name, data[:5], state="starter")
        return orig(name, data)

    s._post_asset = post
    s.put_meta(NEW)
    meta_ok(f, NEW, "meta partial on 422")


def m5():  # المسار العادي + أول رفع (لا meta.json بعد)
    f = FakeGitHub()
    f.add("state-001529-20261104.enc", b"blob")
    store(f).put_meta(OLD)
    meta_ok(f, OLD, "meta first")
    store(f).put_meta(NEW)
    meta_ok(f, NEW, "meta normal replace")


def m6():  # خطأ غير 422 ما زال يوقف التشغيل
    f = FakeGitHub()
    s = store(f)
    s._post_asset = lambda name, data: Resp(403, {"message": "forbidden"})
    try:
        s.put_meta(NEW)
        check("meta 403 still aborts", False, "no SystemExit")
    except SystemExit as e:
        check("meta 403 still aborts", "403" in str(e), str(e))
    check("meta 403: meta.json not created", not f.by_name("meta.json"))


# ═══════════════ put_blob ═══════════════
def b1():  # بقايا مطابقة (حجم + sha) ← تُستعمل بلا حذف ولا إعادة رفع
    f = base()
    f.add(BLOB, PAYLOAD)
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob identical leftover")
    check("blob identical leftover: no delete", f.count("DELETE") == 0, f.count("DELETE"))
    check("blob identical leftover: single POST", f.count("POST") == 1, f.count("POST"))


def b2():  # بقايا بنفس الحجم ومحتوى مختلف ← تُحذف ويُعاد الرفع
    f = base()
    f.add(BLOB, bytes(len(PAYLOAD)))
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob same-size different-sha")
    check("blob same-size different-sha: one delete", f.count("DELETE") == 1)


def b3():  # بقايا بحجم مختلف ← تُحذف بلا تنزيل (الحجم يكفي)
    f = base()
    f.add(BLOB, PAYLOAD[:100])
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob size mismatch")
    check("blob size mismatch: no download needed",
          f.count("GET", "/releases/assets/") == 0, f.count("GET", "/releases/assets/"))


def b4():  # السبب الجذري للـblob: 502 بعد الإنشاء ← 422 ← يُستعمل الموجود
    f = base()
    f.upload_5xx_after_create = 1
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob 5xx-then-422")
    check("blob 5xx-then-422: reused, no third POST", f.count("POST") == 2, f.count("POST"))


def b5():  # بقايا ناقصة (starter) ← تُحذف ويُعاد الرفع
    f = base()
    f.add(BLOB, PAYLOAD[:10], state="starter")
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob partial leftover")


def b6():  # digest من GitHub ← مقارنة بلا تنزيل 23MB
    f = base()
    f.digests = True
    f.add(BLOB, PAYLOAD)
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob digest match")
    check("blob digest match: no download",
          f.count("GET", "/releases/assets/") == 0, f.count("GET", "/releases/assets/"))


def b7():  # 422 مستمر (أصل غريب يعود كل مرة) ← يتوقف بعد محاولتين، لا حلقة
    f = base()
    s = store(f)
    orig = s._post_asset

    def post(name, data):
        if not f.by_name(name):
            f.add(name, b"x" * len(data))  # منافس يرفع محتوى آخر قبلنا
        return orig(name, data)

    s._post_asset = post
    try:
        s.put_blob(BLOB, PAYLOAD)
        check("blob persistent 422 aborts", False, "no SystemExit")
    except SystemExit as e:
        check("blob persistent 422 aborts", "422" in str(e), str(e))
    check("blob persistent 422: exactly 2 POSTs", f.count("POST") == 2, f.count("POST"))


def b8():  # المسار العادي
    f = base()
    store(f).put_blob(BLOB, PAYLOAD)
    blob_ok(f, "blob normal")
    check("blob normal: single POST, no delete",
          f.count("POST") == 1 and f.count("DELETE") == 0)


for fn in (m1, m2, m3, m4, m5, m6, b1, b2, b3, b4, b5, b6, b7, b8):
    scenario(fn.__name__, fn)

print("ALL PASS" if not fail else f"{fail} FAILED")
sys.exit(1 if fail else 0)
