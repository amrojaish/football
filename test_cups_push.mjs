// Cups phase 2 (9 Nov 2026): per-cup push switch (PUSH_CUP_LEAGUE_IDS). OFF = zero alerts. ON = same payloads as a league match to the clubs' and
// the match's followers (the whole league alert set); shootout kicks never push; FT of a PEN match carries the pens score.
// Real encryption + decryption of the payloads, in-memory D1, mocked provider. The switch is flipped in a temp COPY of worker.js. No network.
// Run: node --no-warnings test_cups_push.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const SRC = fs.readFileSync(new URL("./worker.js", import.meta.url), "utf8");
// (15 Nov 2026) the shipped worker has every cup ON; OFF and ON are both built here by rewriting the line (regex), whatever is shipped
const PUSH_RE = /const PUSH_CUP_LEAGUE_IDS = new Set\(\[[^\]]*\]\);/;
// ids of a `const NAME = new Set([...]);` line in the shipped source, in source order (null if absent)
const idsOf = (name) => {
  const m = SRC.match(new RegExp(`const ${name} = new Set\\(\\[([^\\]]*)\\]\\);`));
  return m ? m[1].split(",").map((x) => x.trim()).filter(Boolean) : null;
};
let nTmp = 0;
const loadWith = async (text) => {
  const f = path.join(tmpDir, `worker_cups_push_${nTmp++}.mjs`);
  fs.writeFileSync(f, text);
  return (await import(pathToFileURL(f).href + "?" + Math.random())).default;
};
const off = () => loadWith(SRC.replace(PUSH_RE, "const PUSH_CUP_LEAGUE_IDS = new Set([]);"));
const on = (ids) => loadWith(SRC.replace(PUSH_RE, `const PUSH_CUP_LEAGUE_IDS = new Set([${ids.join(",")}]);`));

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

const H = 4531, A = 4529, LG = 307, CUP = 302, FXL = 77, FXC = 78;
const KEYS = ["goal", "ko", "ht", "sh", "ft", "red", "mp", "rem", "lineup"];
const NAMES = { [H]: { ar: "الفيصلي", en: "Al-Faisaly" }, [A]: { ar: "الوحدات", en: "Al-Wehdat" }, 5242: { ar: "الشرطة", en: "Al-Shorta" }, 3463: { en: "East Bengal" } };
const NOW = Math.floor(Date.now() / 1000);
let live, finals, kickoffs, pushes, queued, liveCalls, idsCalls, statsReply, eventsReply, cupTeams, cupTeamFetches = 0, lastLive, lastLu;
const lu = (t) => ({ team: { id: t }, formation: "4-4-2", coach: { name: "C" }, startXI: [{ player: { id: t, name: "P", number: 1, pos: "G", grid: "1:1" } }], substitutes: [] });
function reset() {
  live = []; finals = []; kickoffs = null; pushes = []; queued = []; liveCalls = []; idsCalls = []; statsReply = []; eventsReply = []; cupTeams = { 12: [5468] }; lastLive = null;
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM sub_teams; DELETE FROM sub_matches; DELETE FROM sub_leagues; DELETE FROM subscriptions");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.includes("/fixtures?live=")) { liveCalls.push(url); return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers: { "x-ratelimit-requests-remaining": "5000" } }); }
  if (url.includes("/fixtures?ids=")) { idsCalls.push(url); return new Response(JSON.stringify({ errors: [], response: finals }), { status: 200 }); }
  if (url.includes("/fixtures/statistics")) return new Response(JSON.stringify({ errors: [], response: statsReply }), { status: 200 });
  if (url.includes("/fixtures/events")) return new Response(JSON.stringify({ errors: [], response: eventsReply }), { status: 200 });
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  if (url.includes("cup_teams.json")) { cupTeamFetches++; return cupTeams ? new Response(JSON.stringify(cupTeams), { status: 200 }) : new Response("x", { status: 500 }); }
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
  const kv = { get: async (k) => (k === "live" ? JSON.stringify({ t: NOW - 3600, m: prevM, ...extra }) : null), put: async (k, v) => { if (k === "live") lastLive = JSON.parse(v); if (k.startsWith("lu:")) lastLu = JSON.parse(v); }, delete: async () => {} };
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
async function run(mk, lg, id) {
  const out = {};
  let w;   // a fresh worker per step: next_kickoffs.json is cached per isolate
  const step = async (key, setup) => {
    reset();
    w = await mk();
    await addSub("en", [H], "en"); await addSub("ar", [H], "ar");
    await setup();
    out[key] = { en: (await got("en")).map((b) => norm(b, id)), ar: (await got("ar")).map((b) => norm(b, id)), n: pushes.length };
  };
  await step("goal", async () => { live = [fx(id, lg, "1H", 21, 1, 0)]; await tick(w, { [id]: prev(lg, "1H", 0, 0, 20) }); });
  await step("ko", async () => { live = [fx(id, lg, "1H", 1, 0, 0)]; await tick(w, {}); });
  await step("ht", async () => { live = [fx(id, lg, "HT", 45, 1, 0)]; await tick(w, { [id]: prev(lg, "1H", 1, 0, 44) }); });
  await step("sh", async () => { live = [fx(id, lg, "2H", 46, 1, 0)]; await tick(w, { [id]: prev(lg, "HT", 1, 0, 45) }); });
  await step("lineup", async () => { const b = Math.floor(Date.now() / 300000) * 300000; kickoffs = { t: NOW, k: [], f: [[Math.floor(b / 1000) + 900, id, H, A, lg, "Al Faisaly", "Al Wehdat"]], v: {} };   // 15 min: inside the line-up window, outside the 30-min reminder
    finals = [{ ...fx(id, lg, "NS", 0, null, null), lineups: [lu(H), lu(A)] }]; await tick(w, {}, {}, { scheduledTime: b }); });
  await step("ft", async () => { finals = [fx(id, lg, "FT", 90, 2, 1)]; await tick(w, { [id]: prev(lg, "2H", 2, 1, 90) }); });
  await step("red", async () => { live = [fx(id, lg, "2H", 60, 0, 0, [redEv])]; await tick(w, { [id]: prev(lg, "2H", 0, 0, 59) }, { ve: 1, v: {} }); });
  await step("mp", async () => { live = [fx(id, lg, "2H", 60, 0, 0, [mpEv])]; await tick(w, { [id]: prev(lg, "2H", 0, 0, 59) }, { ve: 1, v: {} }); });
  await step("rem", async () => { kickoffs = { t: NOW, k: [NOW + 1800], f: [[NOW + 1800, id, H, A, lg, "Al Faisaly", "Al Wehdat"]], v: {} }; await tick(w, {}); });
  return out;
}

const leagueOut = await run(() => on([CUP]), LG, FXL);
for (const k of KEYS) {
  check(`baseline: league ${k} reaches both subscribers`, leagueOut[k].en.length === 1 && leagueOut[k].ar.length === 1, leagueOut[k]);
}
const cupOut = await run(() => on([CUP]), CUP, FXC);
for (const k of KEYS) {
  check(`ON: cup ${k} payload is identical to the league payload (EN+AR, fixture id aside)`,
    JSON.stringify(cupOut[k].en) === JSON.stringify(leagueOut[k].en) && JSON.stringify(cupOut[k].ar) === JSON.stringify(leagueOut[k].ar), [cupOut[k], leagueOut[k]]);
  check(`ON: cup ${k} has no competition name`, !/cup|League|كأس/i.test(JSON.stringify(cupOut[k].en[0] || {})) && !/كأس/.test(JSON.stringify(cupOut[k].ar[0] || {})), cupOut[k]);
}
const offOut = await run(off, CUP, FXC);
for (const k of KEYS) check(`OFF: cup ${k} sends zero`, offOut[k].n === 0, offOut[k]);

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

// TEAM_ID_ALIASES: the provider's duplicate ids become ours before the feed, the recipients and the text
{
  const AL = 28571, OURS = 5242, CUP2 = 18;
  const afx = (s, el, h, a, ev = []) => ({ ...fx(FXC, CUP2, s, el, h, a, ev), teams: { home: { id: AL, name: "Al Shorta" }, away: { id: A, name: "Al Wehdat" } } });
  reset(); await addSub("al", [OURS], "en");
  live = [afx("1H", 1, 0, 0)];
  await tick(await on([CUP2]), {});
  const [ko] = await got("al");
  check("alias: a live fixture with 28571 reaches followers of 5242", pushes.length === 1 && ko && ko.body === "Al-Shorta - Al-Wehdat", [pushes.length, ko]);
  check("alias: the feed carries 5242, never 28571", lastLive.m[FXC].th === OURS && !JSON.stringify(lastLive).includes(String(AL)), lastLive.m[FXC]);
  reset(); await addSub("al", [OURS], "en");
  const pa = { ...prev(CUP2, "2H", 0, 0, 59), th: OURS };
  live = [afx("2H", 60, 0, 0, [{ ...redEv, team: { id: AL } }])];
  await tick(await on([CUP2]), { [FXC]: pa }, { ve: 1, v: {} });
  const [red] = await got("al");
  check("alias: a red card on the duplicate id is the home side's", red && red.title.includes("Al-Shorta"), red);
  reset(); await addSub("al", [OURS], "en");
  finals = [afx("FT", 90, 2, 1)];
  await tick(await on([CUP2]), { [FXC]: { ...prev(CUP2, "2H", 2, 1, 90), th: OURS } });
  check("alias: full-time entry in f carries 5242", lastLive.f[FXC].th === OURS && pushes.length === 1, [lastLive.f, pushes.length]);
  reset(); await addSub("aw", [3463], "en");
  live = [{ ...fx(FXC, CUP2, "1H", 1, 0, 0), teams: { home: { id: H, name: "x" }, away: { id: 21137, name: "East Bengal II" } } }];
  await tick(await on([CUP2]), {});
  check("alias: 21137 on the away side reaches followers of 3463", pushes.length === 1 && lastLive.m[FXC].ta === 3463, [pushes.length, lastLive.m]);
  reset();
  live = [afx("1H", 1, 0, 0)];
  await tick(await off(), {});
  check("alias: applied to the feed with the switch off, zero pushes", lastLive.m[FXC].th === OURS && pushes.length === 0, lastLive.m);
  reset(); await addSub("al", [OURS], "en");
  statsReply = [{ team: { id: A }, statistics: [{ type: "Ball Possession", value: "40%" }] }, { team: { id: AL }, statistics: [{ type: "Ball Possession", value: "60%" }] }];
  live = [afx("1H", 30, 0, 0)];
  await tick(await on([CUP2]), { [FXC]: { ...prev(CUP2, "1H", 0, 0, 29), th: OURS } });
  check("alias: statistics of the duplicate id land on the home side", lastLive.st && lastLive.st[FXC].h[0] === 60, lastLive.st);
  reset();
  const w = await on([CUP2]), store = {};
  eventsReply = [{ time: { elapsed: 10, extra: null }, team: { id: AL }, player: { id: 9, name: "A. Scorer" }, type: "Goal", detail: "Normal Goal", comments: null }];
  const env = { API_KEY: "k", DB, LIVE_KV: { get: async (k) => store[k] ?? null, put: async (k, v) => { store[k] = v; }, delete: async () => {} }, GOAL_QUEUE: QUEUE };
  await w.queue({ messages: [{ body: { kind: "live_scorers", fixture: FXC, th: OURS, ta: A, h: 1, a: 0, step: 0 }, ack() {}, retry() {} }] }, env);
  check("alias: a scorer on the duplicate id is listed for the home side", store["sc:" + FXC] && JSON.parse(store["sc:" + FXC]).l[0][0] === "h", store);
  reset(); await addSub("al", [OURS], "en");
  const b0 = Math.floor(Date.now() / 300000) * 300000;
  kickoffs = { t: NOW, k: [], f: [[Math.floor(b0 / 1000) + 900, FXC, OURS, A, CUP2, "H", "A"]], v: {} };
  finals = [{ ...afx("NS", 0, null, null), lineups: [lu(AL), lu(A)] }];
  await tick(await on([CUP2]), {}, {}, { scheduledTime: b0 });
  check("alias: a line-up under the duplicate id still counts and is stored under ours", pushes.length === 1 && lastLu && lastLu.home.id === OURS, [pushes.length, lastLu]);
}
// shootout kicks stay the only exception: nothing is filtered by type for an ON cup
check("no cup-specific alert filter is left in the worker", !SRC.includes("CUP_SKIP_ALERTS") && !/LINEUP_SKIP_LEAGUES\.has\(r\[4\]\) \|\|/.test(SRC));

// subscribing: cup-only club and competition
{
  const cupOnly = 5468;   // in the mocked assets/cup_teams.json under CAF-CL (12)
  const sub = (w, teams, leagues) => w.fetch(new Request("https://w.example/push/subscribe", { method: "POST",
    headers: { Origin: "https://saffara.app", "Content-Type": "application/json", "CF-Connecting-IP": "3.3.3." + (nTmp % 250) },
    body: JSON.stringify({ subscription: { endpoint: epOf("s" + nTmp), keys: { p256dh: Buffer.alloc(65, 7).toString("base64url"), auth: Buffer.alloc(16, 7).toString("base64url") } }, teams, ...(leagues ? { leagues } : {}), lang: "ar" }) }), { DB, GOAL_PUSH: "on", VAPID_PUBLIC_KEY }, { waitUntil() {} });
  reset();
  cupTeamFetches = 0;
  check("OFF: following a cup-only club is refused", (await sub(await off(), [cupOnly])).status === 400);
  check("OFF: the build-generated list is not even fetched", cupTeamFetches === 0, cupTeamFetches);
  const r2 = await sub(await on([12]), [cupOnly]);
  check("ON for its cup: following a cup-only club is accepted", r2.status === 200, r2.status);
  check("ON for another cup: still refused", (await sub(await on([302]), [cupOnly])).status === 400);
  check("ON: subscribing to the competition itself stays refused", (await sub(await on([302]), [H], [302])).status === 400);
  cupTeams = null;
  check("ON, list unavailable: the cup-only club is refused, no crash", (await sub(await on([12]), [cupOnly])).status === 400);
  check("ON, list unavailable: a league club still subscribes", (await sub(await on([12]), [H])).status === 200);
}

// the poll: OFF list unchanged; a single provider request however many cups are on it
{
  reset();
  await tick(await off(), {});
  // OFF only clears PUSH_CUP; the live list stays the shipped one: the 10 leagues + every live cup (source order), one request
  check("OFF: the poll list is the 10 leagues + the shipped live cups",
    liveCalls.length === 1 && liveCalls[0].endsWith("?live=387-542-307-233-301-305-200-186-202-330-" + idsOf("LIVE_ONLY_LEAGUE_IDS").join("-")), liveCalls);
  reset();
  await tick(await on([302, 560]), {});
  check("302 on both lists appears once", liveCalls.length === 1 && liveCalls[0].split("live=")[1].split("-").filter((x) => x === "302").length === 1, liveCalls);
  // (15 Nov 2026) the all-cups live line is now the active one (was a prepared comment); scenario = all cups live, push off
  const prepared = /^(const LIVE_ONLY_LEAGUE_IDS = new Set\(\[[0-9, ]+\]\);)/m.exec(SRC)[1];
  const n = prepared.match(/\d+/g).length;
  check("shipped live-only line lists the 27 enabled cups", n === 27, n);
  const wAll = await loadWith(SRC.replace(PUSH_RE, "const PUSH_CUP_LEAGUE_IDS = new Set([]);"));
  reset();
  await addSub("en", [H], "en");
  live = [fx(FXC, 504, "1H", 1, 0, 0), fx(FXL, 12, "1H", 1, 0, 0)];
  await tick(wAll, {});
  const ids = liveCalls[0].split("live=")[1].split("-");
  check("prepared line: still ONE fixtures?live= request for all cups", liveCalls.length === 1, liveCalls.length);
  check("prepared line: 10 leagues + 27 cups on that request, no repeats", ids.length === 37 && new Set(ids).size === 37, ids.length);
  check("prepared line: those cups stay live-only (zero pushes)", pushes.length === 0 && queued.length === 0, pushes.length);
}

// (15 Nov 2026) shipped worker: every enabled cup is live AND push (the two sets are identical, 27 provider ids)
{
  const push = idsOf("PUSH_CUP_LEAGUE_IDS"), live = idsOf("LIVE_ONLY_LEAGUE_IDS");
  check("shipped: PUSH_CUP_LEAGUE_IDS == LIVE_ONLY_LEAGUE_IDS, 27 cups",
    push !== null && live !== null && push.length === 27 && [...push].sort().join() === [...live].sort().join(), [push, live]);
}
origLog(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
