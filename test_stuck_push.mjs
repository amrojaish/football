// Stuck deploy-run alert: mocked GitHub + mocked push services, in-memory D1 shim (node:sqlite), real encryption +
// decryption of the payload. Fake runs only: nothing here (or in the worker) ever cancels a run.
// Arabic is asserted by code points, never typed through a Windows command line.
// Run: node --no-warnings test_stuck_push.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_stuckpush_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Date.now())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0005_admin_devices.sql"])
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
async function addSub(name, teams, lang) {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const auth = crypto.getRandomValues(new Uint8Array(16));
  const endpoint = `https://fcm.googleapis.com/fcm/send/${name}`;
  clients[endpoint] = { priv: kp.privateKey, pubBytes: Buffer.from(pub, "base64url"), auth };
  db.prepare("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?,?)").run(endpoint, pub, b64u(auth), lang, 1, 1);
  for (const t of teams) db.prepare("INSERT OR REPLACE INTO sub_teams VALUES (?,?)").run(endpoint, t);
  return endpoint;
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
const epOf = (name) => `https://fcm.googleapis.com/fcm/send/${name}`;

const NOW = Math.floor(Date.now() / 1000);
const at = (min) => Date.UTC(2026, 9, 7, 12, min, 0);
let runs, pushes, calls, pushStatus;
function reset() {
  runs = { waiting: [], pending: [], requested: [], queued: [], in_progress: [] };
  pushes = []; calls = []; pushStatus = 201;
  db.exec("DELETE FROM dispatch_log; DELETE FROM admin_devices; DELETE FROM sub_teams; DELETE FROM subscriptions");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  calls.push({ url, init });
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  if (url.includes("api.github.com") && url.includes("/runs?")) {
    const st = /status=(\w+)/.exec(url)[1];
    const list = runs[st] || [];
    return new Response(JSON.stringify({ total_count: list.length, workflow_runs: list }), { status: 200 });
  }
  if (url.endsWith("/dispatches")) return new Response(null, { status: 204 });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: pushStatus }); }
  return new Response("{}", { status: 404 });
};
const KV = { get: async () => JSON.stringify({ t: NOW - 3600, m: {} }), put: async () => {} };
const env = (extra = {}) => ({ API_KEY: "k", LIVE_KV: KV, DB, GH_DISPATCH_TOKEN: "ghp_test", ADMIN_TOKEN: "adm",
  VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", ...extra });
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
async function tick(minute, e = env()) {
  logs.length = 0; pushes.length = 0; calls.length = 0;
  const waits = [];
  await worker.scheduled({ scheduledTime: at(minute) }, e, { waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
}
const run = (id, ageMin, minute = 5) => ({ id, created_at: new Date(at(minute) - ageMin * 60000).toISOString() });
const rows = () => db.prepare("SELECT result FROM dispatch_log ORDER BY id").all().map((r) => r.result);
const adminReq = (method, body, token = "adm") => worker.fetch(new Request("https://saffara-live.example/push/admin-device", {
  method, headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", Origin: "https://saffara.app" }, body: JSON.stringify(body) }), env());
let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// title and body asserted by code points
const TITLE = "⚠️ النشر عالق";
const bodyOf = (id, n) => `التشغيل ${id} — صار له ${n} دقيقة`;
const subRow = (name) => db.prepare("SELECT p256dh, auth FROM subscriptions WHERE endpoint=?").get(epOf(name));
const adminCount = () => db.prepare("SELECT COUNT(*) c FROM admin_devices").get().c;

// 1) registering an admin device: auth, validation, must be subscribed
reset();
await addSub("admin", [], "ar"); await addSub("visitor", [4531], "ar");
let r = await adminReq("POST", { endpoint: epOf("admin") }, "wrong");
check("admin-device wrong token -> 401, nothing written", r.status === 401 && adminCount() === 0);
r = await worker.fetch(new Request("https://saffara-live.example/push/admin-device", { method: "POST", body: "{}" }), env());
check("admin-device no token -> 401", r.status === 401);
r = await adminReq("POST", { endpoint: epOf("nobody") });
check("endpoint not subscribed -> 404, nothing written", r.status === 404 && adminCount() === 0, r.status);
r = await adminReq("POST", { endpoint: "http://evil.example/x" });
check("bad endpoint -> 400", r.status === 400);
r = await adminReq("POST", { endpoint: epOf("admin") });
check("valid -> 200 admin:true, one row", r.status === 200 && (await r.json()).admin === true && adminCount() === 1);
r = await adminReq("POST", { endpoint: epOf("admin") });
check("registering twice is idempotent", r.status === 200 && adminCount() === 1);

// 2) the public subscribe path cannot set the flag
const v = subRow("visitor");
r = await worker.fetch(new Request("https://saffara-live.example/push/subscribe", { method: "POST",
  headers: { Origin: "https://saffara.app", "Content-Type": "application/json" },
  body: JSON.stringify({ endpoint: epOf("visitor"), keys: { p256dh: v.p256dh, auth: v.auth }, lang: "ar", teams: [4531], admin: true, admin_device: true }) }), env());
check("visitor subscribe with admin fields -> no admin row for the visitor", db.prepare("SELECT COUNT(*) c FROM admin_devices WHERE endpoint=?").get(epOf("visitor")).c === 0, r.status);
await addSub("visitor-en", [4529], "en");

// 3) first time a stuck run is seen -> only the admin device gets one push, with the right text
runs.waiting = [run(37520113840, 60)];
await tick(5);
check("first sighting -> stuck_run row + exactly one push, to the admin device only", rows().includes("stuck_run:37520113840")
  && pushes.length === 1 && pushes[0].url === epOf("admin"), { rows: rows(), pushes: pushes.map((p) => p.url) });
const msg = pushes[0] ? await decrypt(pushes[0].url, pushes[0].body) : {};
check("  title is the stuck-deploy title, body has run id + minutes", msg.title === TITLE && msg.body === bodyOf(37520113840, 60) && msg.tag === "stuck-run-37520113840", msg);
check("  visitors (even with team subscriptions) got nothing", !pushes.some((p) => p.url === epOf("visitor") || p.url === epOf("visitor-en")));
check("  the dispatch still happened; no GitHub cancel call; only the dispatch POST", calls.some((c) => c.url.endsWith("/dispatches"))
  && !calls.some((c) => /cancel/.test(c.url)) && calls.filter((c) => c.init && c.init.method === "POST" && c.url.includes("api.github.com")).length === 1);

// 4) next cycle, same run id -> logged again but NO new push
runs.waiting = [run(37520113840, 90, 35)];
await tick(35);
check("same run next cycle -> row logged, no push", pushes.length === 0 && rows().filter((x) => x === "stuck_run:37520113840").length === 2, { pushes: pushes.length, rows: rows() });
// 5) a different run id -> notifies again, for the new id only
runs.waiting = [run(37520113840, 120, 5), run(37999999999, 50, 5)];
await tick(5);
const bodies = [];
for (const p of pushes) bodies.push((await decrypt(p.url, p.body)).body);
check("second stuck run id (old one already seen) -> one push, for the new id only", pushes.length === 1 && bodies[0] === bodyOf(37999999999, 50), bodies);

// 6) not stuck yet (44 min) -> no row, no push; pending / requested behave like waiting
for (const st of ["pending", "requested"]) {
  reset(); await addSub("admin", [], "ar"); db.prepare("INSERT INTO admin_devices VALUES (?,?)").run(epOf("admin"), 1);
  runs[st] = [run(555, 44)];
  await tick(5);
  check(`${st} 44 min -> no push, no row`, pushes.length === 0 && !rows().some((x) => x.startsWith("stuck_run")), rows());
  runs[st] = [run(555, 61)];
  await tick(5);
  check(`${st} 61 min -> one push`, pushes.length === 1 && rows().includes("stuck_run:555"), { n: pushes.length, rows: rows() });
}

// 7) no admin device registered -> no push, run still logged and dispatch still happens
reset(); await addSub("visitor", [4531], "ar");
runs.waiting = [run(7, 70)];
await tick(5);
check("no admin devices -> no push, stuck_run logged, dispatch happens", pushes.length === 0 && rows().includes("stuck_run:7")
  && calls.some((c) => c.url.endsWith("/dispatches")) && logs.some((l) => l.includes('"stuck_run_push"') && l.includes('"devices":0')));
// 8) orphan admin row (subscription gone) is ignored; a push-service failure never throws
reset(); await addSub("admin", [], "ar");
db.prepare("INSERT INTO admin_devices VALUES (?,?)").run(epOf("ghost"), 1);
db.prepare("INSERT INTO admin_devices VALUES (?,?)").run(epOf("admin"), 1);
runs.waiting = [run(8, 70)];
pushStatus = 500;
let threw = false;
try { await tick(5); } catch (e) { threw = true; }
check("push service 500 -> no throw, dispatch still happens", !threw && calls.some((c) => c.url.endsWith("/dispatches")));
check("  orphan admin row (no subscription) is not messaged", !pushes.some((p) => p.url === epOf("ghost")) && pushes.length === 1);
// 9) no DB -> cannot dedupe -> never notifies; DELETE unregisters
reset(); await addSub("admin", [], "ar"); db.prepare("INSERT INTO admin_devices VALUES (?,?)").run(epOf("admin"), 1);
runs.waiting = [run(9, 70)];
await tick(5, env({ DB: undefined }));
check("no DB binding -> no push (cannot dedupe), dispatch still happens", pushes.length === 0 && calls.some((c) => c.url.endsWith("/dispatches")));
r = await adminReq("DELETE", { endpoint: epOf("admin") });
check("DELETE admin-device removes the flag", r.status === 200 && adminCount() === 0);
runs.waiting = [run(10, 70)];
await tick(5);
check("after removal, a new stuck run pushes to nobody", pushes.length === 0);

console.log = origLog;
process.exit(fail ? 1 : 0);
