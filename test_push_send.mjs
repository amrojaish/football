// Sender + /push/test tests with a mock push service and an in-memory D1 shim (node:sqlite).
// Run: node --no-warnings test_push_send.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_push_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Date.now())).default;

// ── D1 shim ──
const db = new DatabaseSync(":memory:");
db.exec(fs.readFileSync(new URL("./migrations/0001_push.sql", import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { db.prepare(sql).run(...args); return {}; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (list) => { list.forEach((x) => x._run()); return []; } };

// ── keys ──
const b64u = (u) => Buffer.from(u).toString("base64url");
const vkp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const VAPID_PUBLIC_KEY = b64u(await crypto.subtle.exportKey("raw", vkp.publicKey));
const VAPID_PRIVATE_KEY = (await crypto.subtle.exportKey("jwk", vkp.privateKey)).d;
const ADMIN_TOKEN = "test-admin-token-" + "x".repeat(20);
const env = { DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", ADMIN_TOKEN };

const clients = {};   // endpoint -> {priv, pubBytes, auth}
async function addSub(name, team, lang = "ar") {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const auth = crypto.getRandomValues(new Uint8Array(16));
  const endpoint = `https://fcm.googleapis.com/fcm/send/${name}`;
  clients[endpoint] = { priv: kp.privateKey, pubBytes: Buffer.from(pub, "base64url"), auth };
  db.prepare("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?,?)").run(endpoint, pub, b64u(auth), lang, 1, 1);
  db.prepare("INSERT OR REPLACE INTO sub_teams VALUES (?,?)").run(endpoint, team);
  return endpoint;
}

// RFC 8291 decrypt (aes128gcm) to check the real payload
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
  while (end > 0 && plain[end - 1] === 0) end--;   // strip zero padding, then the 0x02 delimiter
  return JSON.parse(plain.subarray(0, end - 1).toString("utf8"));
}

// ── mock push service ──
const calls = [];
const statusFor = (url) => (url.endsWith("/gone") ? 410 : url.endsWith("/missing") ? 404 : url.endsWith("/boom") ? 500 : 201);
globalThis.fetch = async (url, init) => {
  calls.push({ url: String(url), init });
  return new Response(null, { status: statusFor(String(url)) });
};

const call = (hdrs, body, method = "POST") => worker.fetch(new Request("https://w.example/push/test", {
  method, headers: { "Content-Type": "application/json", ...hdrs },
  body: body === undefined ? undefined : JSON.stringify(body) }), env);
const auth = { Authorization: "Bearer " + ADMIN_TOKEN };
const T = { team_id: 962, title: "هدف!", body: "نهضة بركان 1-0" };

let fail = 0;
const check = (n, c, x) => {
  console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x)));
  if (!c) fail++;
};
const count = (t) => db.prepare(`SELECT COUNT(*) c FROM ${t}`).get().c;

// 401s
let r = await call({}, T);
check("no Authorization -> 401", r.status === 401 && calls.length === 0, r.status);
r = await call({ Authorization: "Bearer wrong" }, T);
check("wrong token -> 401", r.status === 401 && calls.length === 0);
r = await call({ Authorization: "Basic " + ADMIN_TOKEN }, T);
check("wrong scheme -> 401", r.status === 401);
const savedTok = env.ADMIN_TOKEN;
env.ADMIN_TOKEN = undefined;
r = await call(auth, T);
check("ADMIN_TOKEN not configured -> 401", r.status === 401);
env.ADMIN_TOKEN = savedTok;
r = await call({}, undefined, "GET");
check("GET without token -> 401", r.status === 401);

// 400s with a valid token
for (const [n, b] of [
  ["unknown team", { ...T, team_id: 1 }], ["string team", { ...T, team_id: "962" }],
  ["no title", { ...T, title: "" }], ["long title", { ...T, title: "x".repeat(101) }],
  ["no body", { team_id: 962, title: "t" }]]) {
  r = await call(auth, b);
  check("400: " + n, r.status === 400 && calls.length === 0, r.status);
}

// send: 2 ok (ar + en), 410, 404, 500, plus one subscriber of another team
const ok1 = await addSub("ok1", 962, "ar"), ok2 = await addSub("ok2", 962, "en");
const gone = await addSub("gone", 962), missing = await addSub("missing", 962), boom = await addSub("boom", 962);
await addSub("other", 964);
r = await call(auth, T);
const j = await r.json();
check("send -> sent 2, gone 2, failed 1, not capped",
  r.status === 200 && j.sent === 2 && j.gone === 2 && j.failed === 1 && j.capped === false, j);
check("  only team 962 subscribers contacted (5 requests)",
  calls.length === 5 && !calls.some((c) => c.url.endsWith("/other")), calls.map((c) => c.url));
const sent1 = calls.find((c) => c.url === ok1);
const h = Object.fromEntries(Object.entries(sent1.init.headers).map(([k, v]) => [k.toLowerCase(), v]));
check("  headers: vapid auth, aes128gcm, ttl 600, urgency high",
  /^vapid t=.+, k=.+/.test(h.authorization) && h["content-encoding"] === "aes128gcm"
  && String(h.ttl) === "600" && h.urgency === "high", h);
const p1 = await decrypt(ok1, sent1.init.body);
const p2 = await decrypt(ok2, calls.find((c) => c.url === ok2).init.body);
check("  payload decrypts: ar subscriber gets /clubs url",
  p1.title === "هدف!" && p1.body === "نهضة بركان 1-0" && p1.tag === "test-962" && p1.url === "/clubs/962.html", p1);
check("  payload decrypts: en subscriber gets /en/clubs url", p2.url === "/en/clubs/962.html", p2);
check("  410 + 404 rows deleted from both tables; 500 kept",
  !db.prepare("SELECT 1 FROM subscriptions WHERE endpoint IN (?,?)").get(gone, missing)
  && !db.prepare("SELECT 1 FROM sub_teams WHERE endpoint IN (?,?)").get(gone, missing)
  && !!db.prepare("SELECT 1 FROM subscriptions WHERE endpoint = ?").get(boom), count("subscriptions"));
check("  remaining: ok1, ok2, boom, other = 4 subs / 4 team rows", count("subscriptions") === 4 && count("sub_teams") === 4);

// cap
db.exec("DELETE FROM subscriptions; DELETE FROM sub_teams;");
calls.length = 0;
for (let i = 0; i < 45; i++) await addSub("bulk" + i, 965);
r = await call(auth, { ...T, team_id: 965 });
const jc = await r.json();
check("45 subscribers -> only 40 sent, capped=true", jc.sent === 40 && jc.capped === true && calls.length === 40, jc);

process.exit(fail ? 1 : 0);
