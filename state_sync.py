#!/usr/bin/env python3
"""
الحالة الدائمة للموقع (football.db + sitemap_state.json) كأصول Release مشفّرة
===============================================================================
المرحلة B: البوت لم يعد يلتزم بالصفحات المولَّدة ولا بـfootball.db بالفرع.
الحالة الدائمة (تتراكم بين التشغيلات ولا تُشتق من الكود) تُحفظ بإصدار GitHub
واحد اسمه `db-state`، مشفّرةً (المستودع عام).

  state-<seq>-<YYYYMMDD>.enc   tar.gz للملفات ثم AES-256-GCM (مفتاح DB_KEY)
  meta.json                    المؤشر + البصمة + الأعداد + القفل (غير مشفَّر، بلا أسرار)

⚠️ **DB_KEY ضياعه = ضياع الحالة كلها.** نسخة بسرّ المستودع + مدير كلمات المرور
   + نسخ محلية غير مشفَّرة دورية (db_pull.py --backup-dir). راجع README.

⚠️ **القفل (6 ساعات محلياً، 90 دقيقة للـCI) يحل محل تعطيل الجدولة بكوميتات:**
   البوت يتخطى تشغيله إن كان القفل لغيره ساري المفعول.

⚠️ **ثلاثة فحوص قبل أي رفع** (راجع push()): (1) seq البعيد = seq الذي سُحب منه
   (لم تُدفع حالة أحدث)، (2) القفل لك أو غير موجود، (3) القاعدة سليمة
   (integrity_check) وأعداد جداولها وأحدث مباراة لا تقل عن البعيدة (إلا
   --force-shrink).

⚠️ **الاحتفاظ:** آخر 7 تواريخ (أحدث نسخة من كل يوم) + آخر 3 نسخ + الحالية.

للتجربة بلا شبكة: STATE_STORE_DIR=<مجلد> يستبدل GitHub بمجلد محلي.
"""
import base64
import gzip  # noqa: F401  (tarfile يستعمله داخلياً)
import hashlib
import io
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = os.environ.get("STATE_REPO", "amrojaish/football")
TAG = "db-state"
STATE_FILES = ("football.db", "sitemap_state.json")
MAGIC = b"SFR1"
KEEP_DATES = 7
COUNT_TABLES = ("matches", "goals", "events", "lineup_players", "player_stats")
LOCAL_BASE = BASE / ".db_base.json"


# ───────────────────────── البيئة والمفتاح ─────────────────────────
def load_env():
    """يقرأ .env (KEY=VALUE) دون الكتابة فوق متغيرات البيئة الموجودة."""
    p = BASE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_key():
    load_env()
    raw = os.environ.get("DB_KEY", "").strip()
    if not raw:
        raise SystemExit("❌ DB_KEY غير مضبوط (.env محلياً، أو سرّ المستودع بالـCI)")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception:
        raise SystemExit("❌ DB_KEY ليس base64 صالحاً")
    if len(key) != 32:
        raise SystemExit("❌ DB_KEY يجب أن يكون 32 بايت (db_keygen.py يولّده)")
    return key


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ───────────────────────── التشفير والتعبئة ─────────────────────────
def encrypt(data, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def decrypt(blob, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:4] != MAGIC:
        raise SystemExit("❌ ملف الحالة ليس بصيغة SFR1")
    try:
        return AESGCM(key).decrypt(blob[4:16], blob[16:], MAGIC)
    except Exception:
        raise SystemExit("❌ فشل فك التشفير — DB_KEY خاطئ أو الملف تالف")


def pack(src_dir):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tf:
        for name in STATE_FILES:
            p = Path(src_dir) / name
            if p.exists():
                tf.add(p, arcname=name)
    return buf.getvalue()


def unpack(data, dest_dir):
    """يفكّ إلى مجلد مؤقت ثم ينقل بالاستبدال الذري. يعيد قائمة الملفات."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.name not in STATE_FILES or not m.isfile():
                raise SystemExit(f"❌ عضو غير متوقع بالأرشيف: {m.name}")
            tmp = dest / (m.name + ".part")
            with open(tmp, "wb") as f:
                f.write(tf.extractfile(m).read())
            os.replace(tmp, dest / m.name)
            out.append(m.name)
    return out


def content_sha(src_dir):
    h = hashlib.sha256()
    for name in STATE_FILES:
        p = Path(src_dir) / name
        if p.exists():
            h.update(name.encode() + b"\0" + str(p.stat().st_size).encode() + b"\0")
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def db_facts(db_path):
    """أعداد الجداول وأحدث مباراة منتهية + سلامة القاعدة."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        counts = {}
        for t in COUNT_TABLES:
            try:
                counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                counts[t] = 0
        mx = con.execute(
            "SELECT MAX(date) FROM matches WHERE home_goals IS NOT NULL").fetchone()[0]
    finally:
        con.close()
    return ok, counts, mx or ""


# ───────────────────────── المخازن ─────────────────────────
class FileStore:
    """مخزن مجلد محلي — للتجربة بلا شبكة (STATE_STORE_DIR)."""

    def __init__(self, d):
        self.d = Path(d)
        self.d.mkdir(parents=True, exist_ok=True)

    def get_meta(self):
        p = self.d / "meta.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put_meta(self, meta):
        tmp = self.d / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.d / "meta.json")

    def get_blob(self, name):
        return (self.d / name).read_bytes()

    def put_blob(self, name, data):
        (self.d / name).write_bytes(data)

    def del_blob(self, name):
        p = self.d / name
        if p.exists():
            p.unlink()


class GitHubStore:
    """أصول إصدار GitHub (REST مباشرة — لا gh محلياً)."""

    API = "https://api.github.com"

    def __init__(self, repo, token):
        import requests
        self.r = requests
        self.repo = repo
        self.h = {"Authorization": f"Bearer {token}",
                  "Accept": "application/vnd.github+json",
                  "X-GitHub-Api-Version": "2022-11-28"}
        self._rel = None

    def _req(self, method, url, **kw):
        for attempt in range(4):
            r = self.r.request(method, url, timeout=300, **kw)
            if r.status_code >= 500 or r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            return r
        return r

    def release(self, create=False, fresh=False):
        if self._rel is not None and not fresh:
            return self._rel
        r = self._req("GET", f"{self.API}/repos/{self.repo}/releases/tags/{TAG}",
                      headers=self.h)
        if r.status_code == 404:
            if not create:
                return None
            r = self._req("POST", f"{self.API}/repos/{self.repo}/releases",
                          headers=self.h,
                          json={"tag_name": TAG, "name": "db-state (مشفَّر — لا تحذف)",
                                "body": "حالة الموقع الدائمة مشفّرة AES-256-GCM. راجع state_sync.py.",
                                "prerelease": True})
        if r.status_code >= 300:
            raise SystemExit(f"❌ GitHub release: {r.status_code} {r.text[:200]}")
        self._rel = r.json()
        return self._rel

    def _asset(self, name):
        rel = self.release(fresh=True)
        if not rel:
            return None
        for a in rel["assets"]:
            if a["name"] == name:
                return a
        return None

    def _download(self, asset):
        h = dict(self.h)
        h["Accept"] = "application/octet-stream"
        r = self._req("GET", asset["url"], headers=h)
        if r.status_code >= 300:
            raise SystemExit(f"❌ تنزيل {asset['name']}: {r.status_code}")
        return r.content

    def _upload(self, name, data):
        rel = self.release()
        url = rel["upload_url"].split("{")[0]
        h = dict(self.h)
        h["Content-Type"] = "application/octet-stream"
        r = self._req("POST", url, headers=h, params={"name": name}, data=data)
        if r.status_code >= 300:
            raise SystemExit(f"❌ رفع {name}: {r.status_code} {r.text[:200]}")
        return r.json()

    def _delete(self, asset):
        r = self._req("DELETE", f"{self.API}/repos/{self.repo}/releases/assets/{asset['id']}",
                      headers=self.h)
        if r.status_code not in (204, 404):
            raise SystemExit(f"❌ حذف {asset['name']}: {r.status_code}")

    def get_meta(self):
        a = self._asset("meta.json")
        return json.loads(self._download(a).decode("utf-8")) if a else None

    def put_meta(self, meta):
        self.release(create=True)
        data = json.dumps(meta, indent=1, ensure_ascii=False).encode("utf-8")
        new = self._upload("meta.new", data)
        old = self._asset("meta.json")
        if old:
            self._delete(old)
        r = self._req("PATCH", f"{self.API}/repos/{self.repo}/releases/assets/{new['id']}",
                      headers=self.h, json={"name": "meta.json"})
        if r.status_code >= 300:
            raise SystemExit(f"❌ إعادة تسمية meta: {r.status_code} {r.text[:200]}")

    def get_blob(self, name):
        a = self._asset(name)
        if not a:
            raise SystemExit(f"❌ الأصل {name} غير موجود بالإصدار")
        return self._download(a)

    def put_blob(self, name, data):
        self.release(create=True)
        self._upload(name, data)

    def del_blob(self, name):
        a = self._asset(name)
        if a:
            self._delete(a)


def get_store():
    load_env()
    d = os.environ.get("STATE_STORE_DIR")
    if d:
        return FileStore(d)
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise SystemExit("❌ GH_TOKEN غير مضبوط (.env محلياً؛ GITHUB_TOKEN تلقائي بالـCI)")
    return GitHubStore(REPO, tok)


# ───────────────────────── المنطق ─────────────────────────
def lock_info(meta):
    """القفل الساري فقط (منتهي الصلاحية = لا قفل)."""
    lk = (meta or {}).get("lock")
    if lk and parse(lk["expires_at"]) > now():
        return lk
    return None


def _set_lock(store, meta, holder, hours):
    meta["lock"] = {"holder": holder, "acquired_at": iso(now()),
                    "expires_at": iso(now() + timedelta(hours=hours))}
    store.put_meta(meta)
    again = store.get_meta()
    lk = lock_info(again)
    if not lk or lk["holder"] != holder:
        raise SystemExit("❌ سباق على القفل — حاول مجدداً")
    return again


class Locked(Exception):
    pass


def pull(store, key, holder, lock_hours=0, version=None):
    """ينزّل الحالة ويفكّها بمجلد مؤقت. يعيد (meta، المجلد) بعد وضع القفل إن طُلب."""
    meta = store.get_meta()
    if not meta:
        raise SystemExit("❌ لا حالة بالإصدار بعد — شغّل db_push.py --init أولاً")
    lk = lock_info(meta)
    if lk and lk["holder"] != holder and lock_hours:
        raise Locked(f"القفل لـ{lk['holder']} حتى {lk['expires_at']}")
    asset = meta["asset"]
    if version is not None:
        hit = [h for h in meta.get("history", []) if h["seq"] == int(version)]
        if not hit:
            raise SystemExit(f"❌ النسخة {version} غير موجودة؛ المتاح: "
                             f"{[h['seq'] for h in meta.get('history', [])]}")
        asset = hit[0]["asset"]
    if lock_hours:
        meta = _set_lock(store, meta, holder, lock_hours)
    data = decrypt(store.get_blob(asset), key)
    tmp = Path(tempfile.mkdtemp(prefix="state_pull_"))
    unpack(data, tmp)
    if version is None and content_sha(tmp) != meta["content_sha"]:
        raise SystemExit("❌ بصمة المحتوى لا تطابق meta.json — الحالة تالفة")
    return meta, tmp


def release_lock(store, holder):
    meta = store.get_meta()
    lk = (meta or {}).get("lock")
    if meta and lk and lk["holder"] == holder:
        meta["lock"] = None
        store.put_meta(meta)
        return True
    return False


def push(store, key, src, holder, base_seq=None, force_shrink=False, init=False):
    """يشفّر ويرفع حالة جديدة. يعيد (meta, رُفع؟)."""
    ok, counts, mx = db_facts(Path(src) / "football.db")
    if not ok:
        raise SystemExit("❌ PRAGMA integrity_check فشل — لا رفع")
    sha = content_sha(src)
    meta = store.get_meta()
    if init:
        if meta:
            raise SystemExit("❌ الحالة موجودة أصلاً — --init للتهيئة الأولى فقط")
        seq = 0
        history = []
    else:
        if not meta:
            raise SystemExit("❌ لا حالة بالإصدار — --init أولاً")
        if base_seq is not None and meta["seq"] != base_seq:
            raise SystemExit(f"❌ حالة أحدث موجودة (seq {meta['seq']} ≠ {base_seq} الذي سُحب) — "
                             "اسحب من جديد ودمج شغلك؛ لا رفع")
        lk = lock_info(meta)
        if lk and lk["holder"] != holder:
            raise SystemExit(f"❌ القفل لـ{lk['holder']} حتى {lk['expires_at']} — لا رفع")
        if not force_shrink:
            # الـCI يسمح بانكماش حتى 2% (apply_exclusions/دمج قد يحذف صفوفاً مشروعة)؛
            # المحلي صارم: أي نقص = رفض (--force-shrink لو مقصود)
            tol = 0.02 if holder == "ci" else 0.0
            for t in COUNT_TABLES:
                if counts[t] < meta["counts"].get(t, 0) * (1 - tol):
                    raise SystemExit(f"❌ {t}: {counts[t]} < {meta['counts'].get(t)} بالبعيدة — "
                                     "قاعدة أقدم/أصغر؛ لا رفع (--force-shrink لو مقصود)")
            if mx < (meta.get("max_match_date") or ""):
                raise SystemExit(f"❌ أحدث مباراة {mx} أقدم من البعيدة "
                                 f"{meta.get('max_match_date')} — لا رفع")
        if sha == meta["content_sha"]:
            meta["lock"] = None if (lk and lk["holder"] == holder) else meta.get("lock")
            store.put_meta(meta)
            return meta, False
        seq = meta["seq"]
        history = list(meta.get("history", []))
    seq += 1
    name = f"state-{seq:06d}-{now().strftime('%Y%m%d')}.enc"
    store.put_blob(name, encrypt(pack(src), key))
    # إعادة قراءة قبل الإحلال لتضييق نافذة السباق
    cur = store.get_meta()
    if not init and cur and cur["seq"] != meta["seq"]:
        store.del_blob(name)
        raise SystemExit("❌ سباق: دُفعت حالة أخرى أثناء الرفع — أُلغي")
    history.append({"seq": seq, "asset": name, "date": now().strftime("%Y%m%d"),
                    "content_sha": sha})
    keep, drop = _retention(history, seq)
    new = {"seq": seq, "asset": name, "content_sha": sha, "counts": counts,
           "max_match_date": mx, "created_at": iso(now()), "created_by": holder,
           "lock": None, "history": keep}
    store.put_meta(new)
    for h in drop:
        store.del_blob(h["asset"])
    return new, True


def _retention(history, current_seq):
    """آخر KEEP_DATES تواريخ (أحدث نسخة بكل يوم) + آخر 3 نسخ (تغطية يوم التلف) + الحالية."""
    best = {}
    for h in history:
        if h["date"] not in best or h["seq"] > best[h["date"]]["seq"]:
            best[h["date"]] = h
    dates = sorted(best, reverse=True)[:KEEP_DATES]
    recent = {h["seq"] for h in sorted(history, key=lambda h: h["seq"])[-3:]}
    keep_seqs = {best[d]["seq"] for d in dates} | recent | {current_seq}
    keep = [h for h in history if h["seq"] in keep_seqs]
    drop = [h for h in history if h["seq"] not in keep_seqs]
    return keep, drop


# ───────────────────────── القاعدة المحلية ─────────────────────────
def read_local_base():
    if LOCAL_BASE.exists():
        return json.loads(LOCAL_BASE.read_text(encoding="utf-8"))
    return None


def write_local_base(meta):
    LOCAL_BASE.write_text(json.dumps(
        {"seq": meta["seq"], "content_sha": meta["content_sha"],
         "pulled_at": iso(now())}, indent=1), encoding="utf-8")


def gh_output(**kv):
    """يكتب مخارج خطوة GitHub Actions إن كنا داخلها."""
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
