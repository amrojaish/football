// Operator (admin_devices-only) health alerts: API quota (2 levels), deploy failed twice, GitHub token rejected, live scores stale.
// Mocked API-Football + GitHub + push services, in-memory D1 shim (node:sqlite, ALL migrations), real encryption + decryption of the
// payload. A controllable clock replaces Date.now so "next day" / "2 hours later" are exact. Arabic asserted by code points.
// Run: node --no-warnings test_admin_alerts.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_adminalerts_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);

// controllable clock (set before importing so module-level code sees it)
const realNow = Date.now.bind(Date);
let CLOCK = null;
Date.now = () => (CLOCK == null ? realNow() : CLOCK);
const worker = (await import(pathToFileURL(tmp).href + "?" + realNow())).default;
// the live-fetch retry waits 3 s: recorded and run at once here
const waitsMs = [];
const realSetTimeout = globalThis.setTimeout;
// 3 s (errors) and 20 s (per-minute rate limit) retry waits: recorded and run at once
globalThis.setTimeout = (fn, ms, ...a) => { if (ms === 3000 || ms === 20000) { waitsMs.push(ms); return realSetTimeout(fn, 0, ...a); }
  if (ms === 30000) return realSetTimeout(fn, 0, ...a);   // the second live fetch: run at once, not counted as a retry wait
  return realSetTimeout(fn, ms, ...a); };

const db = new DatabaseSync(":memory:");
for (const f of fs.readdirSync(new URL("./migrations/", import.meta.url)).filter((x) => x.endsWith(".sql")).sort())
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const b64u = (u) => Buffer.from(u).toString("base64url");
const vkp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const VAPID_PUBLIC_KEY = b64u(await crypto.subtle.exportKey("raw", vkp.publicKey));
const VAPID_PRIVATE_KEY = (await crypto.subtle.exportKey("jwk", vkp.privateKey)).d;

const clients = {};
const epOf = (name) => `https://fcm.googleapis.com/fcm/send/${name}`;
async function addSub(name, admin) {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const auth = crypto.getRandomValues(new Uint8Array(16));
  const endpoint = epOf(name);
  clients[endpoint] = { priv: kp.privateKey, pubBytes: Buffer.from(pub, "base64url"), auth };
  db.prepare("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?,?)").run(endpoint, pub, b64u(auth), "ar", 1, 1);
  db.prepare("INSERT OR REPLACE INTO sub_teams (endpoint, team_id) VALUES (?,?)").run(endpoint, 4531);
  if (admin) db.prepare("INSERT INTO admin_devices VALUES (?,?)").run(endpoint, 1);
}
async function decrypt(endpoint, body) {
  const c = clients[endpoint];
  const buf = Buffer.from(body);
  const salt = buf.subarray(0, 16), idlen = buf[20];
  const serverPub = buf.subarray(21, 21 + idlen), ct = buf.subarray(21 + idlen);
  const spk = await crypto.subtle.importKey("raw", serverPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const secret = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: spk }, c.priv, 256));
  const hk = (saltB, ikm, info, len) => crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"])
    .then((k) => crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: saltB, info }, k, len * 8))
    .then((x) => new Uint8Array(x));
  const enc = new TextEncoder();
  const info = Buffer.concat([enc.encode("WebPush: info\0"), c.pubBytes, serverPub]);
  const prk = await hk(c.auth, secret, info, 32);
  const cek = await hk(salt, prk, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hk(salt, prk, enc.encode("Content-Encoding: nonce\0"), 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["decrypt"]);
  const plain = Buffer.from(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ct));
  let end = plain.length;
  while (end > 0 && plain[end - 1] === 0) end--;
  return JSON.parse(plain.subarray(0, end - 1).toString("utf8"));
}

// ── mocks ──
let apiSeq, providerErrors, apiStatus, remainingHdr, completed, ghStatus, dispatchStatus, kickoffs, pushes, calls, kvState, active, ghFailFor;
function reset() {
  apiSeq = []; providerErrors = null; waitsMs.length = 0;
  apiStatus = 200; remainingHdr = "5000"; completed = []; active = { queued: [], in_progress: [] }; ghFailFor = []; ghStatus = 200; dispatchStatus = 204; kickoffs = null;
  pushes = []; calls = [];
  db.exec("DELETE FROM dispatch_log; DELETE FROM admin_devices; DELETE FROM sub_teams; DELETE FROM subscriptions; DELETE FROM ev_sent");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  calls.push({ url, init });
  if (url.startsWith("https://v3.football.api-sports.io")) {
    const h = new Headers();
    if (remainingHdr != null) h.set("x-ratelimit-requests-remaining", remainingHdr);
    // apiSeq: per-call outcomes for the live fetch (number = HTTP status, "timeout", "network", "errors"); empty = apiStatus
    const step = apiSeq.length ? apiSeq.shift() : apiStatus;
    if (step === "timeout") throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
    if (step === "network") throw new TypeError("fetch failed");
    if (step === "errors") return new Response(JSON.stringify({ errors: providerErrors, response: [] }), { status: 200, headers: h });
    if (step !== 200) return new Response("{}", { status: step, headers: h });
    return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200, headers: h });
  }
  if (url === "https://saffara.app/assets/next_kickoffs.json") {
    return kickoffs ? new Response(JSON.stringify({ t: 1, k: kickoffs }), { status: 200 }) : new Response("{}", { status: 404 });
  }
  if (url.includes("api.github.com") && url.includes("/runs?")) {
    if (ghStatus !== 200) return new Response("{}", { status: ghStatus });
    const st = /status=(\w+)/.exec(url)[1];
    if (ghFailFor.includes(st)) return new Response("{}", { status: 500 });
    const list = st === "completed" ? completed : (active[st] || []);
    return new Response(JSON.stringify({ total_count: list.length, workflow_runs: list }), { status: 200 });
  }
  if (url.endsWith("/dispatches")) return new Response(null, { status: dispatchStatus });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: 201 }); }
  return new Response("{}", { status: 404 });
};
const makeEnv = (extra = {}) => ({ API_KEY: "k", LIVE_KV: { get: async () => kvState, put: async () => {} }, DB,
  GH_DISPATCH_TOKEN: "ghp_test", ADMIN_TOKEN: "adm", VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", ...extra });
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };

const D0 = Date.UTC(2026, 9, 14, 12, 0, 0);   // 14 Oct 2026 12:00:00Z
const kv = (tSecAgo, live) => JSON.stringify({ t: Math.floor(CLOCK / 1000) - tSecAgo, m: live ? { "1": { h: 0, a: 0, e: 30, s: "1H" } } : {} });
async function tick(minute, e = makeEnv()) {
  logs.length = 0; pushes.length = 0; calls.length = 0;
  const base = Math.floor(CLOCK / 3600000) * 3600000;   // scheduledTime only decides the dispatch minute
  const waits = [];
  await worker.scheduled({ scheduledTime: base + minute * 60000 }, e, { waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
}
const msgs = async () => { const o = []; for (const p of pushes) o.push({ to: p.url, ...(await decrypt(p.url, p.body)) }); return o; };
const adm = async () => { reset(); await addSub("admin", true); await addSub("visitor", false); };
const onlyAdmin = () => pushes.every((p) => p.url === epOf("admin"));

// code-point titles/bodies
const T_WARN = "⚠️ رصيد الـAPI نازل", T_LOW = "🚨 رصيد الـAPI قليل جداً";
const T_DEPLOY = "❌ النشر فشل مرتين", T_AUTH = "🔑 توكن GitHub مرفوض", T_STALE = "⏸️ النتائج الحية واقفة";

// ═══ 1) quota ═══
CLOCK = D0; await adm(); kvState = kv(3600, false);
remainingHdr = "3000"; await tick(1);
check("quota 3000 -> no alert (not < 3000)", pushes.length === 0, pushes.length);
remainingHdr = "2999"; await tick(1);
let m = await msgs();
check("quota 2999 -> one warn push, admin only", m.length === 1 && onlyAdmin() && m[0].title === T_WARN && m[0].body === "المتبقي 2999 طلب اليوم", m);
remainingHdr = "2500"; await tick(1);
check("  same UTC day again -> deduped (no second push)", pushes.length === 0, pushes.length);
check("  dedupe row quota_warn:2026-10-14 in ev_sent", !!db.prepare("SELECT 1 x FROM ev_sent WHERE kind='adm' AND k='quota_warn:2026-10-14'").get());
CLOCK = D0 + 24 * 3600000; kvState = kv(3600, false); remainingHdr = "2500"; await tick(1);
check("  next UTC day -> warns again", pushes.length === 1 && (await msgs())[0].title === T_WARN);
// low
await adm(); CLOCK = D0; kvState = kv(3600, false);
remainingHdr = "1500"; await tick(1);
m = await msgs();
check("quota 1500 -> warn level only (not < 1500)", m.length === 1 && m[0].title === T_WARN, m.map((x) => x.title));
await adm(); remainingHdr = "1499"; await tick(1);
m = await msgs();
check("quota 1499 -> low push only (one, not warn+low), admin only", m.length === 1 && onlyAdmin() && m[0].title === T_LOW && m[0].body === "المتبقي 1499 — الأحداث بتوقف تحت 800", m);
remainingHdr = "100"; await tick(1);
check("  low deduped same day", pushes.length === 0);
// missing / NaN
await adm(); remainingHdr = null; await tick(1);
check("quota header missing -> no alert", pushes.length === 0);
remainingHdr = "abc"; await tick(1);
check("quota header NaN -> no alert", pushes.length === 0);
remainingHdr = ""; await tick(1);
check("quota header empty -> no alert", pushes.length === 0);
await adm(); remainingHdr = "100"; apiStatus = 500; await tick(1);
check("provider failed (no header read) -> no alert, no throw", pushes.length === 0);
// no admin devices / no DB
reset(); await addSub("visitor", false); remainingHdr = "100"; kvState = kv(3600, false); await tick(1);
check("no admin devices -> no push to visitors", pushes.length === 0);
await adm(); remainingHdr = "100"; await tick(1, makeEnv({ DB: undefined }));
check("no DB binding -> no push, no throw", pushes.length === 0);

// ═══ 2) deploy failed twice (minute 5 = dispatch minute) ═══
const R = (id, conclusion) => ({ id, conclusion, status: "completed", created_at: new Date(D0 - id * 60000).toISOString() });
CLOCK = D0; await adm(); kvState = kv(60, false);
completed = [R(20, "failure"), R(19, "failure")]; await tick(5);
m = await msgs();
check("2 failures -> one push (admin only) with run id", m.length === 1 && onlyAdmin() && m[0].title === T_DEPLOY && m[0].body === "التشغيل 20", m);
const di = calls.findIndex((c) => c.url.endsWith("/dispatches")), ci = calls.findIndex((c) => c.url.includes("status=completed"));
check("  dispatch happened BEFORE the extra completed-runs call; exactly one such call, per_page=5", di >= 0 && ci > di
  && calls.filter((c) => c.url.includes("status=completed")).length === 1 && calls[ci].url.includes("per_page=5"), { di, ci });
completed = [R(20, "failure"), R(19, "failure")]; await tick(5);
check("  same newest failed run id -> no second push", pushes.length === 0);
completed = [R(21, "timed_out"), R(20, "failure")]; await tick(5);
m = await msgs();
check("  new newest failed id (timed_out+failure) -> alerts again for 21", m.length === 1 && m[0].body === "التشغيل 21", m);
await adm(); completed = [R(30, "startup_failure"), R(29, "failure")]; await tick(5);
check("startup_failure + failure -> alert", pushes.length === 1);
await adm(); completed = [R(31, "failure"), R(30, "success")]; await tick(5);
check("failure + success -> none", pushes.length === 0);
completed = [R(32, "success"), R(31, "failure")]; await tick(5);
check("success + failure -> none", pushes.length === 0);
completed = [R(33, "failure"), R(32, "cancelled")]; await tick(5);
check("failure + cancelled -> none (cancelled ignored, not a failure)", pushes.length === 0);
completed = [R(34, "skipped"), R(33, "cancelled")]; await tick(5);
check("skipped + cancelled -> none", pushes.length === 0);
completed = [R(35, "failure")]; await tick(5);
check("only one completed run -> none", pushes.length === 0);
completed = [R(36, "failure"), R(35, "failure")]; await tick(5, makeEnv({ DB: undefined }));
check("no DB -> no push, dispatch still attempted", pushes.length === 0 && calls.some((c) => c.url.endsWith("/dispatches")));
// the check must not break/delay dispatch: even when the completed call blows up
await adm(); completed = null;   // JSON of null -> workflow_runs access throws inside the isolated block
let threw = false;
try { await tick(5); } catch (e) { threw = true; }
check("completed-runs call blowing up -> no throw, dispatch already done", !threw && calls.some((c) => c.url.endsWith("/dispatches")) && pushes.length === 0);
completed = [];
await adm(); completed = [R(40, "failure"), R(39, "failure")]; await tick(1);
check("non-dispatch minute (:01) -> no GitHub call at all, no alert", pushes.length === 0 && !calls.some((c) => c.url.includes("api.github.com")));

// A) cancelled/skipped are dropped first; then the first 2 REMAINING must both be failures
await adm(); completed = [R(50, "failure"), R(49, "cancelled"), R(48, "failure"), R(47, "success"), R(46, "success")]; await tick(5);
m = await msgs();
check("failure, cancelled, failure -> alert (cancelled dropped, the two failures count)", m.length === 1 && m[0].title === T_DEPLOY && m[0].body === "التشغيل 50", m);
await adm(); completed = [R(52, "failure"), R(51, "success"), R(50, "failure"), R(49, "failure"), R(48, "failure")]; await tick(5);
check("failure, success, failure, failure -> none (only the first 2 remaining count)", pushes.length === 0, pushes.length);
await adm(); completed = [R(54, "cancelled"), R(53, "skipped"), R(52, "failure"), R(51, "timed_out"), R(50, "success")]; await tick(5);
m = await msgs();
check("cancelled, skipped, failure, timed_out -> alert for the first failure id (52)", m.length === 1 && m[0].body === "التشغيل 52", m);
await adm(); completed = [R(56, "failure"), R(55, "cancelled"), R(54, "cancelled"), R(53, "skipped"), R(52, "cancelled")]; await tick(5);
check("failure then only cancelled/skipped (one run remains) -> none", pushes.length === 0, pushes.length);
await adm(); completed = [R(58, "failure"), R(57, "cancelled")]; await tick(5);
check("failure, cancelled (one remains) -> none", pushes.length === 0);

// B) the check runs after the dispatch logic on EVERY path
const T_PATHS = [
  ["dispatched", () => {}, "dispatched"],
  ["skipped_queued", () => { active.queued = [{ id: 900, created_at: new Date(CLOCK - 60000).toISOString() }]; }, "skipped_queued"],
  ["skipped_in_progress", () => { active.in_progress = [{ id: 901, created_at: new Date(CLOCK - 60000).toISOString() }]; }, "skipped_in_progress"],
  ["stale_ignored", () => { active.queued = [{ id: 902, created_at: new Date(CLOCK - 2 * 3600000).toISOString() }]; active.in_progress = [{ id: 903, created_at: new Date(CLOCK - 2 * 3600000).toISOString() }]; }, "stale_ignored"],
  ["check_failed", () => { ghFailFor = ["queued"]; }, "check_failed"],
];
let pid = 100;
for (const [name, setup, expectRow] of T_PATHS) {
  await adm(); CLOCK = D0; kvState = kv(60, false);
  setup(); pid += 10;
  completed = [R(pid + 1, "failure"), R(pid, "failure")];
  await tick(5);
  const rowsNow = db.prepare("SELECT result FROM dispatch_log ORDER BY id").all().map((r) => r.result);
  const ci2 = calls.findIndex((c) => c.url.includes("status=completed"));
  const lastDispatchLogic = Math.max(calls.findIndex((c) => c.url.endsWith("/dispatches")), calls.findLastIndex((c) => /status=(queued|in_progress)/.test(c.url)));
  m = await msgs();
  check(`path ${name}: dispatch_log row '${expectRow}' + the deploy-fail check still ran (alert for ${pid + 1}), after the dispatch logic`,
    rowsNow.includes(expectRow) && ci2 > lastDispatchLogic && m.length === 1 && m[0].body === `التشغيل ${pid + 1}`, { rowsNow, ci2, lastDispatchLogic, n: m.length });
  if (name === "skipped_in_progress") check("  skipped_in_progress: no dispatch POST was made, yet the check ran", !calls.some((c) => c.url.endsWith("/dispatches")) && ci2 >= 0);
}

// ═══ 3) GitHub token rejected ═══
CLOCK = D0; await adm(); kvState = kv(60, false); ghStatus = 401;
await tick(5);
m = await msgs();
check("401 on runs check -> one push, admin only", m.length === 1 && onlyAdmin() && m[0].title === T_AUTH, m);
check("  body names the HTTP status", m[0] && m[0].body.includes("401"), m[0]);
await tick(35);
check("  second 401 the same UTC day -> no second push (deduped), dispatch_log still records auth_failed",
  pushes.length === 0 && db.prepare("SELECT COUNT(*) c FROM dispatch_log WHERE result='auth_failed'").get().c === 2);
CLOCK = D0 + 24 * 3600000; kvState = kv(60, false); await tick(5);
check("  next UTC day -> alerts again", pushes.length === 1 && (await msgs())[0].title === T_AUTH);
await adm(); ghStatus = 200; dispatchStatus = 403; CLOCK = D0; await tick(5);
check("403 on the dispatch POST -> alert too", pushes.length === 1 && (await msgs())[0].title === T_AUTH);
await adm(); dispatchStatus = 204; await tick(5);
check("healthy token -> no auth alert", pushes.length === 0);

// ═══ 4) live scores stale ═══
const NOWS = () => Math.floor(CLOCK / 1000);
CLOCK = D0; await adm(); apiStatus = 500; remainingHdr = "5000";
kvState = kv(9 * 60, true); await tick(1);
check("live match in KV, last ok 9 min -> none", pushes.length === 0, pushes.length);
kvState = kv(11 * 60, true); await tick(1);
m = await msgs();
check("last ok 11 min -> one push (admin only), body has minutes", m.length === 1 && onlyAdmin() && m[0].title === T_STALE && m[0].body.startsWith("آخر تحديث ناجح قبل 11 دقيقة"), m);
kvState = kv(13 * 60, true); CLOCK = D0 + 3 * 60000; await tick(1);
check("  second check inside the same 2h bucket -> none", pushes.length === 0, pushes.length);
CLOCK = D0 + 2 * 3600000; kvState = kv(15 * 60, true); await tick(1);
check("  next 2h bucket, still stale -> alerts again", pushes.length === 1);
await adm(); CLOCK = D0; kvState = kv(11 * 60, false); kickoffs = null; await tick(1);
check("no live match and no kickoff window (idle, old t) -> none", pushes.length === 0, pushes.length);
// no KV state at all
kvState = null; await tick(1);
check("empty KV (no t known) -> none", pushes.length === 0);
// successful fetch refreshes t -> never stale
await adm(); apiStatus = 200; kvState = kv(30 * 60, true); await tick(1);
check("live match in KV but the fetch succeeds this minute -> none", pushes.length === 0, pushes.length);
// kickoff window with m empty
await adm(); apiStatus = 500; kvState = kv(11 * 60, false); kickoffs = [NOWS() + 300];
CLOCK = D0 + 20 * 60000;   // past the 10-minute kickoff-file cache from earlier ticks
kickoffs = [Math.floor(CLOCK / 1000) + 300]; kvState = kv(11 * 60, false); await tick(1);
check("m empty but inside the kickoff window, last ok 11 min -> alert", pushes.length === 1 && (await msgs())[0].title === T_STALE, pushes.length);
// no extra API-Football request: only the one live fetch per tick
check("no extra API-Football requests (the live fetch + its one retry on HTTP 500)", calls.filter((c) => c.url.startsWith("https://v3.football.api-sports.io")).length === 2,
  calls.map((c) => c.url));

// ═══ 4b) failure reason, retry, attempted (19 Oct 2026) ═══
// live fetches only (a live match vanishing from the empty mock reply adds one finals() fixtures?ids= call)
const apiCalls = () => calls.filter((c) => c.url.includes("/fixtures?live=")).length;
const failLog = () => logs.map((l) => { try { return JSON.parse(l); } catch (e) { return {}; } });
// the in-request retry (3 s / 20 s) is the nothing-live path since 21 Oct 2026 (live = the 30 s second fetch is the retry):
// idle, last ok 11 min ago, kickoff in 5 min -> a fetch is due and the stale alert is expected
const idleKO = () => { kickoffs = [Math.floor(CLOCK / 1000) + 300]; return kv(11 * 60, false); };
CLOCK = D0 + 6 * 3600000; await adm(); kvState = idleKO(); apiSeq = [503, 502]; await tick(1);
m = await msgs();
check("reason propagates: alert body = minutes + both attempts' HTTP reasons",
  m.length === 1 && m[0].body === "آخر تحديث ناجح قبل 11 دقيقة — المزوّد رفض الطلب: HTTP 503 / المزوّد رفض الطلب: HTTP 502", m.map((x) => x.body));
check("  two API calls, one 3 s wait", apiCalls() === 2 && waitsMs.length === 1, { n: apiCalls(), waitsMs });
const L = failLog();
check("  both attempts logged + live_pull_fail with the same reason",
  L.filter((x) => x.type === "live_pull_attempt").map((x) => x.attempt).join() === "1,2"
  && L.some((x) => x.type === "live_pull_fail" && x.why.includes("HTTP 503") && x.why.includes("HTTP 502")), L);
for (const first of [500, "timeout", "network"]) {
  CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); apiSeq = [first, 200]; await tick(1);
  const LL = failLog();
  check(`retry on ${first} then success -> no alert, 2 calls, both attempts logged (2nd ok)`,
    pushes.length === 0 && apiCalls() === 2 && waitsMs.length === 1
    && LL.some((x) => x.type === "live_pull_attempt" && x.attempt === 1 && !x.ok)
    && LL.some((x) => x.type === "live_pull_attempt" && x.attempt === 2 && x.ok) && !LL.some((x) => x.type === "live_pull_fail"), { p: pushes.length, n: apiCalls(), LL });
}
CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); apiSeq = ["timeout", "timeout"]; await tick(1);
m = await msgs();
check("timeout twice -> alert names the timeout", m.length === 1 && m[0].body.includes("مهلة 10 ثوانٍ انتهت"), m.map((x) => x.body));
// daily quota: never retried
CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); apiSeq = ["errors"]; providerErrors = { requests: "You have reached the request limit for the day" }; await tick(1);
m = await msgs();
check("no retry on errors.requests (daily quota): one call, no wait, alert still sent with the reason",
  apiCalls() === 1 && waitsMs.length === 0 && m.length === 1 && m[0].body.includes("خطأ من المزوّد"), { n: apiCalls(), w: waitsMs, m: m.map((x) => x.body) });
// per-minute rate limit (19 Oct 2026): one retry after 20 s
const RL = { rateLimit: "Too many requests. You have exceeded the limit of requests per minute of your subscription." };
for (const [label, first] of [["errors.rateLimit", "errors"], ["HTTP 429", 429]]) {
  CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); providerErrors = RL; apiSeq = [first, 200]; await tick(1);
  const LL = failLog();
  const a1 = LL.find((x) => x.type === "live_pull_attempt" && x.attempt === 1);
  check(`${label} then success -> one retry after 20 s, no alert, no live_pull_fail`,
    apiCalls() === 2 && JSON.stringify(waitsMs) === "[20000]" && pushes.length === 0 && !LL.some((x) => x.type === "live_pull_fail"), { n: apiCalls(), waitsMs, p: pushes.length });
  check(`  ${label}: attempt 1 logged with retry true + wait_ms 20000, attempt 2 ok`,
    a1 && a1.retry === true && a1.wait_ms === 20000 && LL.some((x) => x.type === "live_pull_attempt" && x.attempt === 2 && x.ok), LL);
}
CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); providerErrors = RL; apiSeq = ["errors", "errors"]; await tick(1);
m = await msgs();
const LR = failLog();
check("rateLimit twice -> 2 calls, one 20 s wait, live_pull_fail logged with the rate-limit reason, no third call",
  apiCalls() === 2 && JSON.stringify(waitsMs) === "[20000]" && LR.some((x) => x.type === "live_pull_fail" && x.why.includes("rateLimit")), { n: apiCalls(), waitsMs, LR });
check("  stale alert names the rate limit", m.length === 1 && m[0].body.includes("rateLimit"), m.map((x) => x.body));
// live match (21 Oct 2026): rate limit -> no 20 s retry; the 30 s second fetch runs instead, the stale alert still fires once
CLOCK += 2 * 3600000; await adm(); kvState = kv(11 * 60, true); providerErrors = RL; apiSeq = ["errors", "errors"]; await tick(1);
m = await msgs();
const LV = failLog();
check("live + rateLimit -> no 20 s wait, 2 calls (first fetch + 30 s second fetch), stale alert once with the reason",
  apiCalls() === 2 && !waitsMs.includes(20000) && m.length === 1 && m[0].body.includes("rateLimit")
  && LV.some((x) => x.type === "live_pull_second" && x.ok === false), { n: apiCalls(), waitsMs, m: m.map((x) => x.body) });
CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); apiSeq = [503, 200]; await tick(1);
check("other errors keep the 3 s wait (HTTP 503 -> [3000])", JSON.stringify(waitsMs) === "[3000]" && apiCalls() === 2, waitsMs);
CLOCK += 2 * 3600000; await adm(); kvState = idleKO(); apiSeq = ["errors", "errors"]; providerErrors = { token: "bad" }; await tick(1);
check("other provider error (not quota) -> retried once", apiCalls() === 2 && waitsMs.length === 1, apiCalls());
// not attempted: idle skip path (t 4 min old, m empty, no kickoff) -> no fetch, so no stale check at all
CLOCK += 2 * 3600000; await adm(); kickoffs = null; apiSeq = [500, 500];
kvState = kv(4 * 60, false); await tick(1);
check("idle skip (no fetch attempted) -> no alert, no API call", pushes.length === 0 && apiCalls() === 0, { p: pushes.length, n: apiCalls() });
await adm(); kvState = kv(30 * 60, true); apiSeq = [200]; await tick(1);
check("attempted and succeeded -> no alert, one call, no retry", pushes.length === 0 && apiCalls() === 1 && waitsMs.length === 0);

// ═══ 5) all alerts go through admin_devices only ═══
await adm(); await addSub("visitor2", false); CLOCK = D0; apiStatus = 200; remainingHdr = "10"; kvState = kv(3600, false); await tick(1);
check("every alert type reaches admin devices only, never subscribers", pushes.length === 1 && onlyAdmin());

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
