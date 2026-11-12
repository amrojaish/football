// Batch 10 (9 Nov 2026), worker: first goal alert carries the minute in the title and only the score in the body; scorer update unchanged;
// EN status wording; notification icon (club logo first, player photo on the update only with p:1); sc rows with and without the player id.
// Real encryption + decryption of payloads, in-memory D1, mocked provider. No network. Run: node --no-warnings test_batch10_push.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_batch10_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const load = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

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
const epOf = (n) => `https://fcm.googleapis.com/fcm/send/${n}`;
async function addSub(name, teams, lang) {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const auth = crypto.getRandomValues(new Uint8Array(16));
  clients[epOf(name)] = { priv: kp.privateKey, pubBytes: Buffer.from(pub, "base64url"), auth };
  db.prepare("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?,?)").run(epOf(name), pub, b64u(auth), lang, 1, 1);
  for (const t of teams) db.prepare("INSERT OR REPLACE INTO sub_teams (endpoint, team_id, types) VALUES (?,?,1023)").run(epOf(name), t);
}
async function decrypt(endpoint, body) {
  const c = clients[endpoint];
  const buf = Buffer.from(body);
  const salt = buf.subarray(0, 16), idlen = buf[20];
  const serverPub = buf.subarray(21, 21 + idlen), ct = buf.subarray(21 + idlen);
  const spk = await crypto.subtle.importKey("raw", serverPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const secret = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: spk }, c.priv, 256));
  const hk = (saltB, ikm, info, len) => crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"])
    .then((k) => crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: saltB, info }, k, len * 8)).then((x) => new Uint8Array(x));
  const enc = new TextEncoder();
  const prk = await hk(c.auth, secret, Buffer.concat([enc.encode("WebPush: info\0"), c.pubBytes, serverPub]), 32);
  const cek = await hk(salt, prk, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hk(salt, prk, enc.encode("Content-Encoding: nonce\0"), 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["decrypt"]);
  const plain = Buffer.from(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ct));
  let end = plain.length;
  while (end > 0 && plain[end - 1] === 0) end--;
  return JSON.parse(plain.subarray(0, end - 1).toString("utf8"));
}

const H = 4531, A = 4529, LG = 387, FX = 77, PHOTO = 1234, NOPHOTO = 5678;
const NAMES = { [H]: { ar: "الفيصلي", en: "Al-Faisaly" }, [A]: { ar: "الوحدات", en: "Al-Wehdat" } };
const RLM = "‏";
const PLAYERS = { [PHOTO]: { en: "Ali Star", ar: "علي", p: 1 }, [NOPHOTO]: { en: "No Pic", ar: "بلا" } };
let live, pushes, eventsReply, store, queued;
function reset() {
  live = []; pushes = []; eventsReply = []; store = {}; queued = [];
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM scorer_update; DELETE FROM sub_teams; DELETE FROM sub_matches; DELETE FROM sub_leagues; DELETE FROM subscriptions");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.includes("/fixtures?live=")) return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers: { "x-ratelimit-requests-remaining": "5000" } });
  if (url.includes("/fixtures/events")) return new Response(JSON.stringify({ errors: [], response: eventsReply }), { status: 200 });
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  if (url.endsWith("team_names.json")) return new Response(JSON.stringify(NAMES), { status: 200 });
  if (url.endsWith("player_names.json")) return new Response(JSON.stringify(PLAYERS), { status: 200 });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: 201 }); }
  return new Response("{}", { status: 404 });
};
const origLog = console.log;
console.log = () => {};
let fail = 0, pass = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? pass++ : fail++; };
const QUEUE = { send: async (b) => { if (b.kind === "live_scorers" || b.kind === "goal_scorer") return; queued.push(b); } };
const kv = () => ({ get: async (k) => store[k] ?? null, put: async (k, v) => { store[k] = v; }, delete: async (k) => { delete store[k]; } });
const envOf = () => ({ API_KEY: "k", LIVE_KV: kv(), DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, GOAL_QUEUE: QUEUE, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on" });
const fx = (s, el, h, a) => ({ fixture: { id: FX, status: { short: s, elapsed: el } }, goals: { home: h, away: a }, events: [], teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: LG } });
const prev = (s, h, a, e) => ({ h, a, e, s, th: H, ta: A, lg: LG, nh: "Al Faisaly", na: "Al Wehdat" });
async function drain(w, env) { let g = 0; while (queued.length && g++ < 50) { const body = queued.shift(); await w.queue({ messages: [{ body, ack() {}, retry() {} }] }, env); } }
const NOW = Math.floor(Date.now() / 1000);
async function tick(w, m) { store.live = JSON.stringify({ t: NOW - 3600, m }); const env = envOf(); await w.scheduled({}, env, {}); await drain(w, env); return env; }
const got = async (name) => Promise.all(pushes.filter((p) => p.url.endsWith("/" + name)).map((p) => decrypt(epOf(name), p.body)));
const AR_SCORES = "يسجّل!";

// ── first goal alert ──
reset(); await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
let w = await load();
live = [fx("1H", 23, 1, 0)];
await tick(w, { [FX]: prev("1H", 0, 0, 22) });
let [en] = await got("en"), [ar] = await got("ar");
check("first goal EN title: minute + team", en && en.title === "23' Al-Faisaly scores!", en);
check("first goal EN body: score line only", en && en.body === "Al-Faisaly [1] - 0 Al-Wehdat", en);
check("first goal AR title: RLM minute RLM + team", ar && ar.title === `${RLM}23'${RLM} الفيصلي ${AR_SCORES}`, ar);
check("first goal AR body: score line only, no second line", ar && !ar.body.includes("\n") && ar.body.startsWith("الفيصلي"), ar);
check("first goal icon: scoring club logo (home side)", en && en.icon === `https://saffara.app/thumbs/${H}-128.webp`, en);
reset(); await addSub("en", [A], "en");
live = [fx("2H", 70, 0, 1)];
await tick(await load(), { [FX]: prev("2H", 0, 0, 69) });
[en] = await got("en");
check("away goal: logo of the away club, marks the away score", en && en.icon === `https://saffara.app/thumbs/${A}-128.webp` && en.title === "70' Al-Wehdat scores!" && en.body === "Al-Faisaly 0 - [1] Al-Wehdat", en);

// direct queue message: minute null, cancel, update
const goalMsg = (o) => ({ kind: "goal", fixture: FX, th: H, ta: A, lg: LG, h: 1, a: 0, minute: 23, offset: 0, ts: Date.now(), nh: "x", na: "y", side: "home", ph: 0, pa: 0, ...o });
async function send(body) { pushes = []; const w2 = await load(); const env = envOf(); await w2.queue({ messages: [{ body, ack() {}, retry() {} }] }, env); await drain(w2, env); }
reset(); await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
await send(goalMsg({ minute: null }));
[en] = await got("en"); [ar] = await got("ar");
check("minute null EN: title without a minute", en && en.title === "Al-Faisaly scores!" && !en.body.includes("\n"), en);
check("minute null AR: title without a minute", ar && ar.title === `الفيصلي ${AR_SCORES}`, ar);
await send(goalMsg({ kind: "cancel", h: 0, a: 0, ph: 1, pa: 0 }));
[en] = await got("en");
check("goal cancelled: no icon, title unchanged in kind", en && en.icon === undefined && en.title.includes("Goal disallowed"), en);
await send(goalMsg({ upd: true, sc: { n: "Star", ar: "علي", tag: "", pid: PHOTO } }));
[en] = await got("en"); [ar] = await got("ar");
check("update EN: title without minute, line 1 minute + name, line 2 score", en && en.title === "Al-Faisaly scores!" && en.body === "23' Star\nAl-Faisaly [1] - 0 Al-Wehdat" && en.renotify === false, en);
check("update AR: same shape", ar && ar.title === `الفيصلي ${AR_SCORES}` && ar.body.split("\n").length === 2 && ar.body.includes("علي"), ar);
check("update with a known photo: player photo icon", en && en.icon === `https://media.api-sports.io/football/players/${PHOTO}.png`, en);
await send(goalMsg({ upd: true, sc: { n: "No Pic", ar: "بلا", tag: "", pid: NOPHOTO } }));
[en] = await got("en");
check("update, player without a photo: club logo", en && en.icon === `https://saffara.app/thumbs/${H}-128.webp`, en);
await send(goalMsg({ upd: true, sc: { n: "Old", ar: "قديم", tag: "" } }));
[en] = await got("en");
check("update from an old sc row (no pid): club logo, text intact", en && en.icon === `https://saffara.app/thumbs/${H}-128.webp` && en.body.startsWith("23' Old"), en);
await send(goalMsg({ upd: true, sc: { n: "Own", ar: "ذاتي", tag: "og", pid: 999 } }));
[en] = await got("en");
check("update, player not in the list: club logo", en && en.icon === `https://saffara.app/thumbs/${H}-128.webp` && en.body.includes("(OG)"), en);

// ── sc:<fixture> rows ──
reset();
eventsReply = [
  { time: { elapsed: 10, extra: null }, team: { id: H }, player: { id: PHOTO, name: "A. Star" }, type: "Goal", detail: "Normal Goal", comments: null },
  { time: { elapsed: 40, extra: null }, team: { id: A }, player: { id: null, name: "B. Noid" }, type: "Goal", detail: "Penalty", comments: null },
];
{
  const w2 = await load(), env = envOf();
  await w2.queue({ messages: [{ body: { kind: "live_scorers", fixture: FX, th: H, ta: A, h: 1, a: 1, step: 0 }, ack() {}, retry() {} }] }, env);
  const row = JSON.parse(store["sc:" + FX]).l;
  check("sc row: player id appended as the last element", row[0].length === 7 && row[0][6] === PHOTO, row);
  check("sc row: the first six fields are unchanged", row[0][0] === "h" && row[0][1] === 10 && row[0][3] === "Star" && row[0][5] === "", row[0]);
  check("sc row: a kick with no player id stores null", row[1][6] === null && row[1][5] === "p", row[1]);
}
// scorer step end to end: old row (6 fields) and new row (7 fields)
async function scorerStep(rowCells) {
  reset(); await addSub("en", [H], "en");
  const w2 = await load(), env = envOf();
  store["sc:" + FX] = JSON.stringify({ l: [rowCells] });
  store.live = JSON.stringify({ t: NOW, m: { [FX]: prev("1H", 1, 0, 30) } });
  await w2.queue({ messages: [{ body: { kind: "goal_scorer", fixture: FX, th: H, ta: A, lg: LG, h: 1, a: 0, minute: 23, step: 0, ts: Date.now(), side: "home", nh: "x", na: "y", ph: 0, pa: 0 }, ack() {}, retry() {} }] }, env);
  await drain(w2, env);
  return (await got("en"))[0];
}
let u = await scorerStep(["h", 23, 0, "Star", "علي", "", PHOTO]);
check("scorer step, new row: photo on the update", u && u.icon === `https://media.api-sports.io/football/players/${PHOTO}.png` && u.title === "Al-Faisaly scores!", u);
u = await scorerStep(["h", 23, 0, "Old", "قديم", ""]);
check("scorer step, old row without pid: club logo, still sent", u && u.icon === `https://saffara.app/thumbs/${H}-128.webp` && u.body.startsWith("23' Old"), u);

// ── status wording ──
reset(); await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
live = [fx("1H", 1, 0, 0)];
await tick(await load(), {});
[en] = await got("en"); [ar] = await got("ar");
check("EN kick-off title is 'Started'", en && en.title === "Started", en);
check("AR kick-off title unchanged", ar && ar.title === "انطلقت المباراة", ar);
check("status alerts carry no icon", en && en.icon === undefined, en);
reset(); await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
live = [fx("2H", 46, 1, 0)];
await tick(await load(), { [FX]: prev("HT", 1, 0, 45) });
[en] = await got("en"); [ar] = await got("ar");
check("EN second half title is 'Second half begins'", en && en.title === "Second half begins", en);
check("AR second half title unchanged", ar && ar.title === "بداية الشوط الثاني", ar);

// ── service worker ──
{
  const sw = fs.readFileSync(new URL("./sw.js", import.meta.url), "utf8");
  check("sw.js uses d.icon, falls back to the app icon; badge unchanged",
    sw.includes("icon: d.icon || NOTIF_ICON") && sw.includes("badge: NOTIF_ICON")
    && /const NOTIF_ICON = '\/icons\/icon-192\.png\?v=[0-9a-f]{8}';/.test(sw));
}

origLog(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
