// Goal detection -> push wiring (batch 5): mock api-sports, mock team_names.json, mock push services,
// in-memory D1 shim (node:sqlite), real encryption + decryption of the payloads.
// Arabic is asserted by code points (\u escapes), never typed through a Windows command line.
// Run: node --no-warnings test_goal_push.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_goalpush_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
// fresh module (fresh names cache) per scenario
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
db.exec(fs.readFileSync(new URL("./migrations/0001_push.sql", import.meta.url), "utf8"));
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

// ── mocks ──
const FAISALY = 4531, WEHDAT = 4529, FX = 77;
const NAMES = { [FAISALY]: { ar: "الفيصلي", en: "Al-Faisaly" },
                [WEHDAT]: { ar: "الوحدات", en: "Al-Wehdat" } };
let live, namesStatus, pushStatus, pushes, namesFetches, kvPuts;
function reset() {
  live = []; namesStatus = 200; pushStatus = 201; pushes = []; namesFetches = 0; kvPuts = 0;
  db.exec("DELETE FROM sent; DELETE FROM sub_teams; DELETE FROM subscriptions");
}
const fx = (h, a, el) => ({
  fixture: { id: FX, status: { short: "2H", elapsed: el } }, goals: { home: h, away: a },
  teams: { home: { id: FAISALY, name: "Al Faisaly" }, away: { id: WEHDAT, name: "Al Wehdat" } }, league: { id: 387 },
});
const baseFetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: live }), { status: 200 });
  if (url === "https://saffara.app/assets/team_names.json") {
    namesFetches++;
    return namesStatus === 200 ? new Response(JSON.stringify(NAMES), { status: 200 }) : new Response("x", { status: namesStatus });
  }
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: pushStatus }); }
  return new Response("{}", { status: 404 });
};
globalThis.fetch = baseFetch;

const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const NOW = Math.floor(Date.now() / 1000);
const entry = (h, a) => ({ h, a, e: 33, s: "2H", th: FAISALY, ta: WEHDAT, lg: 387, nh: "Al Faisaly", na: "Al Wehdat" });
// one cron tick: previous KV state (prevH-prevA) -> poll returns `live`
async function tick(worker, prevH, prevA, env = {}) {
  logs.length = 0;
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: { [FX]: entry(prevH, prevA) } }), put: async () => { kvPuts++; } };
  await worker.scheduled({}, { API_KEY: "k", LIVE_KV: kv, DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY,
    VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on", ...env }, {});
}
const cps = (s) => Array.from(s, (c) => c.codePointAt(0).toString(16)).join(" ");
const pushLine = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push");

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) one push per goal, even if the same poll repeats; log line shape
{
  reset();
  const w = await loadWorker();
  await addSub("ar1", [FAISALY], "ar");
  live = [fx(1, 0, 34)];
  await tick(w, 0, 0);
  check("goal -> exactly one push", pushes.length === 1 && pushes[0].url.endsWith("/ar1"), pushes.length);
  const l = pushLine()[0];
  check("  goal_push log {fixture,sent,gone,failed,capped}", l && l.fixture === FX && l.sent === 1 && l.gone === 0 && l.failed === 0 && l.capped === false, l);
  check("  KV still written", kvPuts === 1, kvPuts);
  await tick(w, 0, 0);   // same transition seen again (retry / KV write lost)
  check("  repeated poll of the same goal -> still one push total", pushes.length === 1, pushes.length);
  check("  duplicate is logged, not silent", pushLine()[0] && pushLine()[0].duplicate === true && pushLine()[0].sent === 0, pushLine());
}

// 2) follower of both teams gets one notification; others one each
{
  reset();
  const w = await loadWorker();
  await addSub("both", [FAISALY, WEHDAT], "ar");
  await addSub("home", [FAISALY], "en");
  await addSub("away", [WEHDAT], "ar");
  await addSub("other", [999999], "ar");
  live = [fx(0, 1, 50)];
  await tick(w, 0, 0);
  const eps = pushes.map((p) => p.url.split("/").pop()).sort();
  check("both-teams follower: one push; home/away one each; unrelated none", JSON.stringify(eps) === '["away","both","home"]', eps);
}

// 3) ar / en text by code points; score is home-away; tag + url
{
  reset();
  const w = await loadWorker();
  const a = await addSub("a", [FAISALY], "ar");
  const e = await addSub("e", [WEHDAT], "en");
  live = [fx(1, 0, 34)];
  await tick(w, 0, 0);
  const pa = await decrypt(a, pushes.find((p) => p.url.endsWith("/a")).body);
  const pe = await decrypt(e, pushes.find((p) => p.url.endsWith("/e")).body);
  const titleAr = "⚽ هدف! الفيصلي 1–0 الوحدات";
  check("ar title code points", cps(pa.title) === cps(titleAr), cps(pa.title));
  check("ar body = minute 34 (code points)", cps(pa.body) === cps("الدقيقة 34"), cps(pa.body));
  check("en title / body", pe.title === "⚽ Goal! Al-Faisaly 1–0 Al-Wehdat" && pe.body === "34'", pe);
  check("title never contains the app name (ar or en)", !/صافرة|saffara/i.test(pa.title + pe.title), [pa.title, pe.title]);
  check("tag goal-<fixture>; url per language", pa.tag === "goal-77" && pe.tag === "goal-77" && pa.url === "/matches/77.html" && pe.url === "/en/matches/77.html", [pa, pe]);
  reset();
  const a2 = await addSub("a2", [FAISALY], "en");
  live = [fx(1, 1, 60)];
  await tick(await loadWorker(), 1, 0);
  const p2 = await decrypt(a2, pushes[0].body);
  check("away goal keeps home-away order", p2.title === "⚽ Goal! Al-Faisaly 1–1 Al-Wehdat", p2.title);
}

// 4) VAR: goal, disallowed, same goal again => 2 goal pushes + 1 cancel, same tag
{
  reset();
  const w = await loadWorker();
  const a = await addSub("v", [FAISALY], "ar");
  const en = await addSub("ve", [WEHDAT], "en");
  live = [fx(1, 0, 34)]; await tick(w, 0, 0);
  live = [fx(0, 0, 36)]; await tick(w, 1, 0);
  check("cancel removes the sent row", db.prepare("SELECT COUNT(*) c FROM sent").get().c === 0);
  live = [fx(1, 0, 40)]; await tick(w, 0, 0);
  const texts = [];
  for (const p of pushes.filter((p) => p.url.endsWith("/v"))) texts.push(await decrypt(a, p.body));
  check("goal / cancel / goal again = 3 pushes (2 goal alerts)", texts.length === 3 && texts.filter((t) => t.title.startsWith("⚽")).length === 2, texts.map((t) => t.title));
  const cancelAr = "❌ أُلغي الهدف — الفيصلي 0–0 الوحدات";
  check("  ar cancel text by code points", cps(texts[1].title) === cps(cancelAr), cps(texts[1].title));
  check("  same tag on all three (cancel replaces the goal notification)", new Set(texts.map((t) => t.tag)).size === 1 && texts[0].tag === "goal-77", texts.map((t) => t.tag));
  const enCancel = await decrypt(en, pushes.filter((p) => p.url.endsWith("/ve"))[1].body);
  check("  en cancel = Goal disallowed", enCancel.title === "❌ Goal disallowed — Al-Faisaly 0–0 Al-Wehdat", enCancel.title);
  // partial cancel: only rows above the current score go
  reset();
  db.prepare("INSERT INTO sent VALUES (77,1,0),(77,2,0),(77,2,1),(88,5,5)").run();
  await addSub("p", [FAISALY], "en");
  live = [fx(2, 0, 70)]; await tick(await loadWorker(), 2, 1);
  const rows = db.prepare("SELECT fixture,h,a FROM sent ORDER BY fixture,h,a").all().map((r) => `${r.fixture}:${r.h}-${r.a}`);
  check("cancel 2-1 -> 2-0 deletes only rows above 2-0 (other fixtures untouched)", JSON.stringify(rows) === '["77:1-0","77:2-0","88:5-5"]', rows);
}

// 5) GOAL_PUSH != on => log only, zero sends, D1 untouched
for (const val of ["off", undefined, "ON", ""]) {
  reset();
  await addSub("o", [FAISALY], "ar");
  live = [fx(1, 0, 34)];
  await tick(await loadWorker(), 0, 0, { GOAL_PUSH: val });
  const events = logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal");
  check(`GOAL_PUSH=${JSON.stringify(val)} -> 0 pushes, 0 names fetches, sent empty, goal logged, KV written`,
    pushes.length === 0 && namesFetches === 0 && db.prepare("SELECT COUNT(*) c FROM sent").get().c === 0 && events.length === 1 && kvPuts === 1,
    { p: pushes.length, n: namesFetches, ev: events.length, kv: kvPuts });
}

// 6) team_names.json fetch fails => provider English names, push still sent
for (const bad of [500, "throw"]) {
  reset();
  const a = await addSub("n", [FAISALY], "ar");
  if (bad === "throw") globalThis.fetch = async (u, i) => { if (String(u).includes("team_names")) throw new Error("down"); return baseFetch(u, i); };
  else namesStatus = 500;
  live = [fx(1, 0, 34)];
  await tick(await loadWorker(), 0, 0);
  globalThis.fetch = baseFetch;
  const p = await decrypt(a, pushes[0].body);
  check(`names fetch ${bad} -> English provider names in the ar title`, p.title === "⚽ هدف! Al Faisaly 1–0 Al Wehdat", p.title);
}

// 7) names cached within the hour (one fetch for two goals)
{
  reset();
  const w = await loadWorker();
  await addSub("c", [FAISALY], "en");
  live = [fx(1, 0, 10)]; await tick(w, 0, 0);
  live = [fx(2, 0, 20)]; await tick(w, 1, 0);
  check("team_names.json fetched once for two goals", namesFetches === 1 && pushes.length === 2, { namesFetches, p: pushes.length });
}

// 8) push service failing / expired subs / D1 down: poll continues, KV written, failures logged
{
  reset();
  await addSub("f", [FAISALY], "en");
  pushStatus = 500;
  live = [fx(1, 0, 34)];
  await tick(await loadWorker(), 0, 0);
  check("push service 500 -> failed:1, KV still written", pushLine()[0].failed === 1 && pushLine()[0].sent === 0 && kvPuts === 1, [pushLine(), kvPuts]);
  reset();
  await addSub("g", [FAISALY], "en");
  pushStatus = 410;
  live = [fx(1, 0, 34)];
  await tick(await loadWorker(), 0, 0);
  check("push 410 -> gone:1 and the subscription is deleted", pushLine()[0].gone === 1 && db.prepare("SELECT COUNT(*) c FROM subscriptions").get().c === 0, pushLine());
  reset();
  const broken = { prepare: () => { throw new Error("d1 down"); }, batch: async () => { throw new Error("d1 down"); } };
  live = [fx(1, 0, 34)];
  let threw = false;
  try { await tick(await loadWorker(), 0, 0, { DB: broken }); } catch (e) { threw = true; }
  check("D1 failure while sending -> scheduled() does not throw, KV written", !threw && kvPuts === 1, { threw, kvPuts });
}

// 9) no event, no work
{
  reset();
  await addSub("z", [FAISALY], "en");
  live = [fx(1, 0, 34)];
  await tick(await loadWorker(), 1, 0);
  check("unchanged score -> no push, no goal_push log, no names fetch", pushes.length === 0 && pushLine().length === 0 && namesFetches === 0, pushes.length);
}

console.log = origLog;
process.exit(fail ? 1 : 0);
