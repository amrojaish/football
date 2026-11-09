// Cups phase 2 (9 Nov 2026): per-cup push switch (PUSH_CUP_LEAGUE_IDS). OFF = zero alerts. ON = same payloads as a league match to the clubs' and
// the match's followers (goal, kick-off, HT, FT, red, missed penalty, 30-min reminder); shootout kicks never push; FT of a PEN match carries the pens score.
// Real encryption + decryption of the payloads, in-memory D1, mocked provider. The switch is flipped in a temp COPY of worker.js. No network.
// Run: node --no-warnings test_cups_push.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const SRC = fs.readFileSync(new URL("./worker.js", import.meta.url), "utf8");
const OFF_LINE = "const PUSH_CUP_LEAGUE_IDS = new Set([]);";
let nTmp = 0;
const loadWith = async (text) => {
  const f = path.join(tmpDir, `worker_cups_push_${nTmp++}.mjs`);
  fs.writeFileSync(f, text);
  return (await import(pathToFileURL(f).href + "?" + Math.random())).default;
};
const off = () => loadWith(SRC);
const on = (ids) => loadWith(SRC.replace(OFF_LINE, `const PUSH_CUP_LEAGUE_IDS = new Set([${ids.join(",")}]);`));

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
  return epOf(name);
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

const H = 4531, A = 4529, LG = 387, CUP = 302, FXL = 77, FXC = 78;
const NAMES = { [H]: { ar: "الفيصلي", en: "Al-Faisaly" }, [A]: { ar: "الوحدات", en: "Al-Wehdat" } };
const NOW = Math.floor(Date.now() / 1000);
let live, finals, kickoffs, pushes, queued, liveCalls, idsCalls;
function reset() {
  live = []; finals = []; kickoffs = null; pushes = []; queued = []; liveCalls = []; idsCalls = [];
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM sub_teams; DELETE FROM sub_matches; DELETE FROM sub_leagues; DELETE FROM subscriptions");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.includes("/fixtures?live=")) { liveCalls.push(url); return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers: { "x-ratelimit-requests-remaining": "5000" } }); }
  if (url.includes("/fixtures?ids=")) { idsCalls.push(url); return new Response(JSON.stringify({ errors: [], response: finals }), { status: 200 }); }
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  if (url === "https://saffara.app/assets/team_names.json") return new Response(JSON.stringify(NAMES), { status: 200 });
  if (url.includes("next_kickoffs.json")) return kickoffs ? new Response(JSON.stringify(kickoffs), { status: 200 }) : new Response("{}", { status: 404 });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: 201 }); }
  return new Response("{}", { status: 404 });
};
const origLog = console.log;
console.log = () => {};
let fail = 0, pass = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? pass++ : fail++; };
const QUEUE = { send: async (body) => { if (body && (body.kind === "live_scorers" || body.kind === "goal_scorer")) return; queued.push(body); } };
const fx = (id, lg, s, el, h, a, events = [], pen) => ({ fixture: { id, status: { short: s, elapsed: el } }, goals: { home: h, away: a }, events, score: { penalty: pen || { home: null, away: null } },
  teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: lg } });
const prev = (lg, s, h, a, e) => ({ h, a, e, s, th: H, ta: A, lg, nh: "Al Faisaly", na: "Al Wehdat" });
async function tick(w, prevM, extra = {}, ctl = {}) {
  queued = []; pushes = [];
  const kv = { get: async (k) => (k === "live" ? JSON.stringify({ t: NOW - 3600, m: prevM, ...extra }) : null), put: async () => {}, delete: async () => {} };
  const env = { API_KEY: "k", LIVE_KV: kv, DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, GOAL_QUEUE: QUEUE, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on" };
  await w.scheduled(ctl, env, {});
  let guard = 0;
  while (queued.length && guard++ < 100) { const body = queued.shift(); await w.queue({ messages: [{ body, ack() {}, retry() {} }] }, env); }
}
const got = async (name) => { const p = pushes.filter((x) => x.url.endsWith("/" + name)); return Promise.all(p.map((x) => decrypt(epOf(name), x.body))); };
const norm = (b, id) => JSON.parse(JSON.stringify(b).split(String(id)).join("ID"));
const redEv = { time: { elapsed: 34, extra: null }, team: { id: H }, player: { id: 5, name: "R. Red" }, assist: { id: null, name: null }, type: "Card", detail: "Red Card" };
const mpEv = { time: { elapsed: 40, extra: null }, team: { id: H }, player: { id: 6, name: "M. Miss" }, assist: { id: null, name: null }, type: "Goal", detail: "Missed Penalty" };

// one scenario per alert type, the same for a league fixture and a cup fixture
async function run(w, lg, id) {
  const out = {};
  const step = async (key, setup) => {
    reset();
    await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
    await setup();
    out[key] = { en: (await got("en")).map((b) => norm(b, id)), ar: (await got("ar")).map((b) => norm(b, id)), n: pushes.length };
  };
  await step("goal", async () => { live = [fx(id, lg, "1H", 21, 1, 0)]; await tick(w, { [id]: prev(lg, "1H", 0, 0, 20) }); });
  await step("ko", async () => { live = [fx(id, lg, "1H", 1, 0, 0)]; await tick(w, {}); });
  await step("ht", async () => { live = [fx(id, lg, "HT", 45, 1, 0)]; await tick(w, { [id]: prev(lg, "1H", 1, 0, 44) }); });
  await step("ft", async () => { finals = [fx(id, lg, "FT", 90, 2, 1)]; await tick(w, { [id]: prev(lg, "2H", 2, 1, 90) }); });
  await step("red", async () => { live = [fx(id, lg, "2H", 60, 0, 0, [redEv])]; await tick(w, { [id]: prev(lg, "2H", 0, 0, 59) }, { ve: 1, v: {} }); });
  await step("mp", async () => { live = [fx(id, lg, "2H", 60, 0, 0, [mpEv])]; await tick(w, { [id]: prev(lg, "2H", 0, 0, 59) }, { ve: 1, v: {} }); });
  await step("rem", async () => { kickoffs = { t: NOW, k: [NOW + 1800], f: [[NOW + 1800, id, H, A, lg, "Al Faisaly", "Al Wehdat"]], v: {} }; await tick(w, {}); });
  return out;
}

const wOn = await on([CUP]);
const leagueOut = await run(wOn, LG, FXL);
for (const k of ["goal", "ko", "ht", "ft", "red", "mp", "rem"]) {
  check(`baseline: league ${k} reaches both subscribers`, leagueOut[k].en.length === 1 && leagueOut[k].ar.length === 1, leagueOut[k]);
}
const cupOut = await run(await on([CUP]), CUP, FXC);
for (const k of ["goal", "ko", "ht", "ft", "red", "mp", "rem"]) {
  check(`ON: cup ${k} payload is identical to the league payload (EN+AR, fixture id aside)`,
    JSON.stringify(cupOut[k].en) === JSON.stringify(leagueOut[k].en) && JSON.stringify(cupOut[k].ar) === JSON.stringify(leagueOut[k].ar), [cupOut[k], leagueOut[k]]);
  check(`ON: cup ${k} has no competition name`, !/cup|League|كأس/i.test(JSON.stringify(cupOut[k].en[0] || {})) && !/كأس/.test(JSON.stringify(cupOut[k].ar[0] || {})), cupOut[k]);
}
const offOut = await run(await off(), CUP, FXC);
for (const k of ["goal", "ko", "ht", "ft", "red", "mp", "rem"]) check(`OFF: cup ${k} sends zero`, offOut[k].n === 0, offOut[k]);

// a cup that is not on the live-only list: the switch alone puts it on the single poll and sends
{
  reset(); await addSub("en", [H], "en");
  const w = await on([560]);
  live = [fx(FXC, 560, "1H", 1, 0, 0)];
  await tick(w, {});
  check("ON for a cup outside the live-only list: on the poll, kick-off sent", liveCalls.length === 1 && liveCalls[0].split("live=")[1].split("-").includes("560") && pushes.length === 1, [liveCalls, pushes.length]);
}
// switch ON for one cup leaves the other live-only cup silent
{
  reset(); await addSub("en", [H], "en");
  const w = await on([560]);
  live = [fx(FXC, CUP, "1H", 1, 0, 0)];
  await tick(w, {});
  check("per-competition: ON for 560 leaves 302 at zero", pushes.length === 0, pushes.length);
}

// shootout kick never pushes (ON)
{
  reset(); await addSub("en", [H], "en");
  const w = await on([CUP]);
  const SO = "Penalty Shootout";
  const kick = (d, n, name) => ({ time: { elapsed: 120, extra: n }, team: { id: H }, player: { id: 9, name }, assist: {}, type: "Goal", detail: d, comments: SO });
  live = [fx(FXC, CUP, "P", 120, 1, 1, [kick("Penalty", 1, "K. In"), kick("Missed Penalty", 2, "K. Out")], { home: 1, away: 0 })];
  await tick(w, { [FXC]: prev(CUP, "P", 1, 1, 120) }, { ve: 1, v: {} });
  check("ON: scored and missed shootout kicks push nothing", pushes.length === 0, pushes.length);
  live = [fx(FXC, CUP, "P", 120, 2, 1, [kick("Penalty", 1, "K. In"), kick("Missed Penalty", 2, "K. Out")], { home: 2, away: 1 })];
  await tick(w, { [FXC]: prev(CUP, "P", 1, 1, 120) }, { ve: 1, v: {} });
  check("ON: score moving during P pushes nothing", pushes.length === 0, pushes.length);
}

// FT of a PEN match, AR + EN
{
  reset(); await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
  const w = await on([CUP]);
  finals = [fx(FXC, CUP, "PEN", 120, 1, 1, [], { home: 4, away: 3 })];
  await tick(w, { [FXC]: prev(CUP, "P", 1, 1, 120) });
  const [en] = await got("en"), [ar] = await got("ar");
  check("PEN FT EN: one push, 'Full-time', final score + (4-3 pens)", pushes.length === 2 && en && en.title === "Full-time" && en.body === "Al-Faisaly 1 - 1 Al-Wehdat (4-3 pens)", en);
  const RLM = "‏";
  check("PEN FT AR: score + (4-3 ترجيح) with stable digit direction", ar && ar.body === `الفيصلي ${RLM}1${RLM} ${RLM}-${RLM} ${RLM}1${RLM} الوحدات (${RLM}4${RLM}-${RLM}3${RLM} ترجيح)`, ar);
  reset(); await addSub("en", [H], "en");
  finals = [fx(FXC, CUP, "PEN", 120, 1, 1, [])];
  await tick(await on([CUP]), { [FXC]: prev(CUP, "P", 1, 1, 120) });
  const [noPen] = await got("en");
  check("PEN FT with no score.penalty: score only", noPen && noPen.body === "Al-Faisaly 1 - 1 Al-Wehdat", noPen);
  reset(); await addSub("en", [H], "en");
  finals = [fx(FXC, CUP, "AET", 120, 2, 1, [], { home: 7, away: 7 })];
  await tick(await on([CUP]), { [FXC]: prev(CUP, "ET", 2, 1, 120) });
  const [aet] = await got("en");
  check("AET FT: no pens suffix", aet && aet.body === "Al-Faisaly 2 - 1 Al-Wehdat", aet);
}

// no duplicate: both clubs + the match on one device = one push; two devices = two
{
  reset();
  const ep = await addSub("dup", [H, A], "en");
  db.prepare("INSERT INTO sub_matches (endpoint, fixture, created_at, types) VALUES (?,?,?,1023)").run(ep, FXC, NOW);
  await addSub("other", [A], "en");
  const w = await on([CUP]);
  live = [fx(FXC, CUP, "1H", 21, 1, 0)];
  await tick(w, { [FXC]: prev(CUP, "1H", 0, 0, 20) });
  check("no duplicate: one device following both clubs and the match gets one goal push", pushes.filter((p) => p.url.endsWith("/dup")).length === 1, pushes.map((p) => p.url));
  check("a second device still gets its own", pushes.filter((p) => p.url.endsWith("/other")).length === 1 && pushes.length === 2, pushes.length);
  live = [fx(FXC, CUP, "1H", 21, 1, 0)];
  await tick(w, { [FXC]: prev(CUP, "1H", 0, 0, 20) });
  check("same goal on the next poll: no second push", pushes.length === 0, pushes.length);
}
// match follower only
{
  reset();
  const ep = await addSub("m", [], "en");
  db.prepare("INSERT INTO sub_matches (endpoint, fixture, created_at, types) VALUES (?,?,?,1023)").run(ep, FXC, NOW);
  live = [fx(FXC, CUP, "1H", 1, 0, 0)];
  await tick(await on([CUP]), {});
  check("ON: a match follower alone gets the alert", pushes.length === 1, pushes.length);
}

// not on the list for cups: second-half start and line-ups; the league keeps both
{
  reset(); await addSub("en", [H], "en");
  const w = await on([CUP]);
  live = [fx(FXC, CUP, "2H", 46, 1, 0)];
  await tick(w, { [FXC]: prev(CUP, "HT", 1, 0, 45) });
  check("ON: no second-half-start alert for a cup", pushes.length === 0, pushes.length);
  live = [fx(FXL, LG, "2H", 46, 1, 0)];
  await tick(w, { [FXL]: prev(LG, "HT", 1, 0, 45) });
  check("control: the league still sends it", pushes.length === 1, pushes.length);
}
{
  reset();
  const w = await on([CUP]);
  const boundary = Math.floor(Date.now() / 300000) * 300000;
  kickoffs = { t: NOW, k: [], f: [[Math.floor(boundary / 1000) + 1800, FXC, H, A, CUP, "H", "A"]], v: {} };
  await tick(w, {}, {}, { scheduledTime: boundary });
  check("ON: no line-up request for a cup", idsCalls.length === 0, idsCalls);
  reset();
  const w2 = await on([CUP]);
  kickoffs = { t: NOW, k: [], f: [[Math.floor(boundary / 1000) + 1800, FXL, H, A, 301, "H", "A"]], v: {} };
  await tick(w2, {}, {}, { scheduledTime: boundary });
  check("control: a league fixture still asks for line-ups", idsCalls.length === 1, idsCalls);
}

// subscribing: cup-only club and competition
{
  const cupOnly = Number(/const PUSH_CUP_TEAM_IDS = \{[\s\S]*?\b12: \[[^\n]*\r?\n\s*(\d+),/.exec(SRC)[1]);
  const sub = (w, teams, leagues) => w.fetch(new Request("https://w.example/push/subscribe", { method: "POST",
    headers: { Origin: "https://saffara.app", "Content-Type": "application/json", "CF-Connecting-IP": "3.3.3." + (nTmp % 250) },
    body: JSON.stringify({ subscription: { endpoint: epOf("s" + nTmp), keys: { p256dh: Buffer.alloc(65, 7).toString("base64url"), auth: Buffer.alloc(16, 7).toString("base64url") } }, teams, ...(leagues ? { leagues } : {}), lang: "ar" }) }), { DB, GOAL_PUSH: "on", VAPID_PUBLIC_KEY }, { waitUntil() {} });
  reset();
  check("OFF: following a cup-only club is refused", (await sub(await off(), [cupOnly])).status === 400);
  const r2 = await sub(await on([12]), [cupOnly]);
  check("ON for its cup: following a cup-only club is accepted", r2.status === 200, r2.status);
  check("ON for another cup: still refused", (await sub(await on([302]), [cupOnly])).status === 400);
  check("ON: subscribing to the competition itself stays refused", (await sub(await on([302]), [H], [302])).status === 400);
}

// the poll: OFF list unchanged; a single provider request however many cups are on it
{
  reset();
  await tick(await off(), {});
  check("OFF: the poll list is exactly today's", liveCalls.length === 1 && liveCalls[0].endsWith("?live=387-542-307-233-301-305-200-186-202-330-302"), liveCalls);
  reset();
  await tick(await on([302, 560]), {});
  check("302 on both lists appears once", liveCalls.length === 1 && liveCalls[0].split("live=")[1].split("-").filter((x) => x === "302").length === 1, liveCalls);
  const prepared = /\/\/ (const LIVE_ONLY_LEAGUE_IDS = new Set\(\[[0-9, ]+\]\);)/.exec(SRC)[1];
  const n = prepared.match(/\d+/g).length;
  check("prepared live-only line lists the 27 enabled cups", n === 27, n);
  const wAll = await loadWith(SRC.replace("const LIVE_ONLY_LEAGUE_IDS = new Set([302]);", prepared));
  reset();
  await addSub("en", [H], "en");
  live = [fx(FXC, 504, "1H", 1, 0, 0), fx(FXL, 12, "1H", 1, 0, 0)];
  await tick(wAll, {});
  const ids = liveCalls[0].split("live=")[1].split("-");
  check("prepared line: still ONE fixtures?live= request for all cups", liveCalls.length === 1, liveCalls.length);
  check("prepared line: 10 leagues + 27 cups on that request, no repeats", ids.length === 37 && new Set(ids).size === 37, ids.length);
  check("prepared line: those cups stay live-only (zero pushes)", pushes.length === 0 && queued.length === 0, pushes.length);
}

origLog(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
