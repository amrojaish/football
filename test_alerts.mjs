// Alert types (batch 3E): see the body below. Run: node --no-warnings test_alerts.mjs
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
for (const f of ["0001_push.sql", "0004_goal_log.sql", "0006_scorer_update.sql", "0007_scorer_update_correction.sql", "0008_sub_matches.sql", "0009_alert_types.sql"])
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
  for (const t of teams) db.prepare("INSERT OR REPLACE INTO sub_teams (endpoint, team_id, types) VALUES (?,?,127)").run(endpoint, t);   // all types on (the DB default for pre-3E rows is goals only)
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
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM sub_teams; DELETE FROM sub_matches; DELETE FROM sub_leagues; DELETE FROM subscriptions");
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
// in-memory Cloudflare Queue: the cron produces, drain() runs the consumer (worker.queue) until empty
let queued = [];
// live_scorers (هدّافو صفحة الموقع) ميزة مستقلة عن التنبيهات ومغطّاة بـtest_worker_goals.mjs: تُستبعد هنا
const QUEUE = { send: async (body, opts) => { if (body && body.kind === "live_scorers") return; queued.push({ body, opts }); } };
async function drain(worker, env) {
  let guard = 0;
  while (queued.length && guard++ < 200) {
    const { body } = queued.shift();
    await worker.queue({ messages: [{ body, ack() {}, retry() { queued.push({ body }); } }] }, env);
  }
}
// one cron tick: previous KV state (prevH-prevA) -> poll returns `live`, then the queue consumer runs
async function tick(worker, prevH, prevA, env = {}) {
  logs.length = 0;
  queued = [];
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: { [FX]: entry(prevH, prevA) } }), put: async () => { kvPuts++; } };
  const e = { API_KEY: "k", LIVE_KV: kv, DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, GOAL_QUEUE: QUEUE,
    VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on", ...env };
  await worker.scheduled({}, e, {});
  await drain(worker, e);
}
const cps = (s) => Array.from(s, (c) => c.codePointAt(0).toString(16)).join(" ");
// consumer/duplicate lines (the producer's {queued:true} line has no `sent`)
const pushLine = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push" && !l.queued);

// ───────── batch 3E: alert types (kickoff / goal / HT / 2H / FT / red card / reminder), masks per entity, league subscriptions, dedupe ─────────
// (prefix above = harness from test_goal_push.mjs: in-memory D1, encrypted web-push receivers, mocked provider)
const T = { KO: 1, GOAL: 2, HT: 4, SH: 8, FT: 16, RED: 32, REM: 64, ALL: 255 };
const LG = 387;
// full-event fixture helper: prev state = what the previous poll left in KV
const live1 = (s, h, a, el, events = []) => ({
  fixture: { id: FX, status: { short: s, elapsed: el } }, goals: { home: h, away: a }, events,
  teams: { home: { id: FAISALY, name: "Al Faisaly" }, away: { id: WEHDAT, name: "Al Wehdat" } }, league: { id: LG },
});
const prevEntry = (s, h, a, e) => ({ h, a, e, s, th: FAISALY, ta: WEHDAT, lg: LG, nh: "Al Faisaly", na: "Al Wehdat" });
async function tick2(worker, prevM, { v, ve, env = {}, finals } = {}) {
  logs.length = 0; queued = []; pushes = [];
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: prevM, ...(v ? { v } : {}), ...(ve ? { ve } : {}) }), put: async () => { kvPuts++; } };
  const e = { API_KEY: "k", LIVE_KV: kv, DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, GOAL_QUEUE: QUEUE, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on", ...env };
  const f0 = globalThis.fetch;
  if (finals) globalThis.fetch = async (url, init) => (String(url).includes("fixtures?ids=")
    ? new Response(JSON.stringify({ errors: [], response: finals }), { status: 200 }) : f0(url, init));
  await worker.scheduled({}, e, {});
  await drain(worker, e);
  globalThis.fetch = f0;
}
const to = (name) => pushes.filter((p) => p.url.endsWith("/" + name)).length;
const body = async (name) => { const p = pushes.filter((x) => x.url.endsWith("/" + name)).at(-1); return p ? decrypt(epOf(name), p.body) : null; };
const subTeam = (ep, team, mask) => db.prepare("UPDATE sub_teams SET types = ? WHERE endpoint = ? AND team_id = ?").run(mask, ep, team);
const alertLines = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "alert_push");

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) kickoff: new live match at minute 1 -> KO alert to subscribers with the KO bit only; same poll twice = ONE alert (ev_sent)
{
  reset(); const w = await loadWorker();
  const all = await addSub("all", [FAISALY], "en"), noko = await addSub("noko", [FAISALY], "ar");
  subTeam(noko, FAISALY, T.ALL & ~T.KO);
  live = [live1("1H", 0, 0, 1)];
  await tick2(w, {});
  check("kickoff: subscriber with the KO bit gets it, subscriber with KO off gets nothing", to("all") === 1 && to("noko") === 0, [to("all"), to("noko")]);
  const b = await body("all");
  check("  EN text: title 'Kick-off!', body 'Al-Faisaly - Al-Wehdat', tag ko-77, url, no renotify", b && b.title === "Kick-off!" && b.body === "Al-Faisaly - Al-Wehdat" && b.tag === "ko-77" && b.url === "/en/matches/77.html" && b.renotify === undefined, b);
  await tick2(w, {});
  check("  same poll again -> NO second kickoff alert (dedupe)", pushes.length === 0, pushes.length);
  live = [live1("1H", 0, 0, 20)];
  await tick2(w, {});
  check("  a match first seen at minute 20 (restart mid-game) is NOT announced as kick-off", pushes.length === 0, pushes.length);
}

// 2) half-time / second-half start / full-time / red card, each once, each filtered by its own bit
{
  reset(); const w = await loadWorker();
  const a1 = await addSub("a1", [FAISALY], "ar");           // all on
  const a2 = await addSub("a2", [WEHDAT], "en"); subTeam(a2, WEHDAT, T.GOAL | T.FT);   // goals + full-time only
  live = [live1("HT", 1, 0, 45)];
  await tick2(w, { [FX]: prevEntry("1H", 1, 0, 44) });
  check("half-time: all-on gets it, goals+FT-only subscriber does not", to("a1") === 1 && to("a2") === 0, [to("a1"), to("a2")]);
  const ht = await body("a1");
  check("  AR half-time title (code points) and score line", ht && cps(ht.title) === cps("نهاية الشوط الأول") && ht.tag === "ht-77" && /1/.test(ht.body), ht);
  live = [live1("2H", 1, 0, 46)];
  await tick2(w, { [FX]: prevEntry("HT", 1, 0, 45) });
  check("second-half start: HT -> 2H transition alerts once", to("a1") === 1 && to("a2") === 0 && (await body("a1")).tag === "sh-77", [to("a1"), to("a2")]);
  await tick2(w, { [FX]: prevEntry("HT", 1, 0, 45) });
  check("  repeating the same transition -> no duplicate", pushes.length === 0, pushes.length);
  // full time: the match disappears from the live list; finals() supplies FT
  live = [];
  await tick2(w, { [FX]: prevEntry("2H", 2, 1, 90) }, { finals: [{ fixture: { id: FX, status: { short: "FT" } }, goals: { home: 2, away: 1 } }] });
  check("full-time: a1 and a2 (FT bit) both get it exactly once; final score in the text", to("a1") === 1 && to("a2") === 1, [to("a1"), to("a2"), alertLines()]);
  const ft = await body("a2");
  check("  EN full-time title + score 'Al-Faisaly 2 - 1 Al-Wehdat'", ft && ft.title === "Full-time" && ft.body === "Al-Faisaly 2 - 1 Al-Wehdat" && ft.tag === "ft-77", ft);
}
{
  reset(); const w = await loadWorker();
  const r1 = await addSub("r1", [FAISALY], "en"), r2 = await addSub("r2", [FAISALY], "en");
  subTeam(r2, FAISALY, T.ALL & ~T.RED);
  const RED = [34, 0, "c", "r", "R. Red", "", "h"];
  // baseline known (ve:1) and no card yet -> a new red card appears
  live = [live1("2H", 0, 0, 60, [{ time: { elapsed: 34, extra: null }, team: { id: FAISALY }, player: { id: 5, name: "R. Red" }, assist: { id: null, name: null }, type: "Card", detail: "Red Card" }])];
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 59) }, { ve: 1, v: {} });
  check("red card: new red in events -> alert to RED-bit subscriber only; minute + player in text, tag red-77-…", to("r1") === 1 && to("r2") === 0, [to("r1"), to("r2")]);
  const rb = await body("r1");
  check("  EN: title contains 'Red card' + team, body \"34' R. Red\" then score", rb && /Red card/.test(rb.title) && /Al-Faisaly/.test(rb.title) && rb.body.startsWith("34' R. Red\n") && rb.tag.startsWith("red-77-"), rb);
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 59) }, { ve: 1, v: {} });
  check("  same card seen again in the next poll (still absent from prev.v) -> deduped by ev_sent", pushes.length === 0, pushes.length);
  // a card already present in the previous poll is not re-announced; second yellow counts as red
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 59) }, { ve: 1, v: { [FX]: [RED] } });
  check("  card already in the previous poll's events -> nothing", pushes.length === 0, pushes.length);
  // no baseline (prev had no ve marker, e.g. quota guard was on) -> never announce old cards
  reset(); await addSub("r3", [FAISALY], "en");
  live = [live1("2H", 0, 0, 60, [{ time: { elapsed: 12, extra: null }, team: { id: FAISALY }, player: { id: 5, name: "Old Red" }, assist: { id: null, name: null }, type: "Card", detail: "Red Card" }])];
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 59) }, {});
  check("  no events baseline in the previous poll -> old red cards are not announced after a gap", pushes.length === 0, pushes.length);
}

// 3) league subscription + match subscription + masks + dedupe across entities
{
  reset(); const w = await loadWorker();
  const lgOnly = await addSub("lgonly", [], "en"), matchOnly = await addSub("matchonly", [], "ar"), both = await addSub("both", [FAISALY], "en"), other = await addSub("otherlg", [], "en");
  db.prepare("INSERT INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(lgOnly, LG, T.ALL);
  db.prepare("INSERT INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(other, 233, T.ALL);        // another league
  db.prepare("INSERT INTO sub_matches (endpoint, fixture, created_at, types) VALUES (?,?,1,?)").run(matchOnly, FX, T.HT);
  db.prepare("INSERT INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(both, LG, T.ALL);        // team AND league -> still one push
  live = [live1("HT", 0, 0, 45)];
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 44) });
  check("league subscriber (all matches of league 387) + match subscriber (HT bit) + team&league subscriber each get exactly one; other league gets none",
    to("lgonly") === 1 && to("matchonly") === 1 && to("both") === 1 && to("otherlg") === 0, [to("lgonly"), to("matchonly"), to("both"), to("otherlg")]);
  // goal alerts honour the GOAL bit and the league route too
  reset(); await addSub("g1", [], "en"); db.prepare("INSERT INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(epOf("g1"), LG, T.ALL);
  await addSub("g2", [], "en"); db.prepare("INSERT INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(epOf("g2"), LG, T.ALL & ~T.GOAL);
  live = [live1("2H", 1, 0, 50)];
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 49) });
  check("goal alert: league subscriber with the GOAL bit gets it; one with GOAL off does not", to("g1") >= 1 && to("g2") === 0, [to("g1"), to("g2")]);
}

// 4) reminder 30 min before kickoff (from assets/next_kickoffs.json `f`), once, per-entity bit, even if the poll is idle
{
  reset(); const w = await loadWorker();
  const rem = await addSub("rem", [FAISALY], "ar"), norem = await addSub("norem", [FAISALY], "en"); subTeam(norem, FAISALY, T.ALL & ~T.REM);
  const ko = Math.floor(Date.now() / 1000) + 30 * 60;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => String(url).includes("next_kickoffs.json")
    ? new Response(JSON.stringify({ t: 1, k: [ko], f: [[ko, FX, FAISALY, WEHDAT, LG, "Al Faisaly", "Al Wehdat"], [ko + 7200, 88, 1, 2, LG, "X", "Y"]] }), { status: 200 })
    : realFetch(url, init);
  live = [];
  const kv = { get: async () => JSON.stringify({ t: NOW, m: {} }), put: async () => {} };
  const env = { API_KEY: "k", LIVE_KV: kv, DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, GOAL_QUEUE: QUEUE, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on" };
  queued = []; pushes = [];
  await w.scheduled({}, env, {}); await drain(w, env);
  check("reminder: kickoff in 30 min -> subscriber with REM gets it (AR), REM-off gets nothing, far-future match ignored", to("rem") === 1 && to("norem") === 0 && pushes.length === 1, [to("rem"), to("norem"), pushes.length]);
  const rb = await body("rem");
  check("  AR title 'تنطلق بعد 30 دقيقة', tag rem-77", rb && cps(rb.title) === cps("تنطلق بعد 30 دقيقة") && rb.tag === "rem-77", rb);
  pushes = []; queued = [];
  await w.scheduled({}, env, {}); await drain(w, env);
  check("  next minute's cron -> still one reminder in total (ev_sent)", pushes.length === 0, pushes.length);
  globalThis.fetch = realFetch;
}

// 4b) defaults (13 Oct): new subscription = 115 (no half-time / second-half); a pre-3E row (DB default 2) = goals ONLY; half-time/second-half only once ticked
{
  reset(); const w = await loadWorker();
  const fresh = await addSub("fresh", [FAISALY], "en"); subTeam(fresh, FAISALY, 115);               // what a 3E client sends for a new club
  const ticked = await addSub("ticked", [FAISALY], "en"); subTeam(ticked, FAISALY, 115 | T.HT | T.SH);   // user ticked both extra types
  const legacy = await addSub("legacy", [], "en"); db.prepare("INSERT OR REPLACE INTO sub_teams (endpoint, team_id) VALUES (?,?)").run(legacy, FAISALY);   // pre-3E row: DB default
  check("DB default for a row without a mask = 2 (goals only): nobody who subscribed before 3E starts getting new alert types",
    db.prepare("SELECT types FROM sub_teams WHERE endpoint = ?").get(legacy).types === T.GOAL, db.prepare("SELECT types FROM sub_teams WHERE endpoint = ?").get(legacy));
  live = [live1("HT", 0, 0, 45)];
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 44) });
  check("half-time: only the subscriber who ticked it (115 + HT) gets it; the 115 default and the legacy row do not", to("ticked") === 1 && to("fresh") === 0 && to("legacy") === 0, [to("ticked"), to("fresh"), to("legacy")]);
  live = [live1("2H", 0, 0, 46)];
  await tick2(w, { [FX]: prevEntry("HT", 0, 0, 45) });
  check("second-half start: same rule (only SH ticked)", to("ticked") === 1 && to("fresh") === 0 && to("legacy") === 0, [to("ticked"), to("fresh"), to("legacy")]);
  live = [live1("2H", 1, 0, 60)];
  await tick2(w, { [FX]: prevEntry("2H", 0, 0, 59) });
  check("goal: all three get it (goal is in the default and in the legacy mask)", to("ticked") >= 1 && to("fresh") >= 1 && to("legacy") >= 1, [to("ticked"), to("fresh"), to("legacy")]);
  live = [];
  await tick2(w, { [FX]: prevEntry("2H", 1, 0, 90) }, { finals: [{ fixture: { id: FX, status: { short: "FT" } }, goals: { home: 1, away: 0 } }] });
  check("full-time: in the default (115) and ticked sets, not in the legacy goals-only row", to("fresh") === 1 && to("ticked") === 1 && to("legacy") === 0, [to("fresh"), to("ticked"), to("legacy")]);
}

// 4c) missed penalty (13 Oct, 3E2): Goal event with detail "Missed Penalty" in the live events -> its own type (bit 128); default for NEW subs (243), never added to old masks
{
  reset(); const w = await loadWorker();
  const MP = 128;
  const withMp = await addSub("withmp", [FAISALY], "en"); subTeam(withMp, FAISALY, 243);               // 3E2 default for a new subscription
  const arMp = await addSub("armp", [WEHDAT], "ar"); subTeam(arMp, WEHDAT, MP);                       // follows the OTHER team: gets it too (either team's penalty)
  const noMp = await addSub("nomp", [FAISALY], "en"); subTeam(noMp, FAISALY, 115);                    // an existing 115 mask is unchanged: no missed-penalty bit
  const old = await addSub("oldmask", [FAISALY], "en"); subTeam(old, FAISALY, 2);                     // legacy goals-only
  check("the bit and the default: 243 = 115 + 128; a 115 or goals-only mask does not carry it", (243 & MP) !== 0 && (243 & 115) === 115 && (115 & MP) === 0 && (2 & MP) === 0);
  const miss = { time: { elapsed: 34, extra: null }, team: { id: WEHDAT }, player: { id: 7, name: "P. Miss" }, assist: { id: null, name: null }, type: "Goal", detail: "Missed Penalty" };
  live = [live1("1H", 0, 0, 36, [miss])];
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 35) }, { ve: 1, v: {} });
  check("missed penalty: subscribers with the bit get it (either team), 115 and goals-only masks do not; NO goal alert (score unchanged)", to("withmp") === 1 && to("armp") === 1 && to("nomp") === 0 && to("oldmask") === 0, [to("withmp"), to("armp"), to("nomp"), to("oldmask")]);
  const eb = await body("withmp"), ab = await body("armp");
  const NL = String.fromCharCode(10);
  check("  EN text: title 'Missed penalty - Al-Wehdat', body 34' P. Miss + score, tag mp-77-...", eb && eb.title === "Missed penalty – Al-Wehdat" && eb.body === "34' P. Miss" + NL + "Al-Faisaly 0 - 0 Al-Wehdat" && eb.tag.startsWith("mp-77-"), eb);
  check("  AR title = missed penalty - Al-Wehdat in Arabic (code points)", ab && cps(ab.title) === cps("ضربة جزاء ضائعة – الوحدات"), ab && cps(ab.title));
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 35) }, { ve: 1, v: {} });
  check("  the same miss in the next poll (still absent from prev.v) -> deduped by ev_sent", pushes.length === 0, pushes.length);
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 35) }, { ve: 1, v: { [FX]: [[34, 0, "g", "m", "P. Miss", "", "a"]] } });
  check("  a miss already in the previous poll's events -> nothing", pushes.length === 0, pushes.length);
  reset(); await addSub("late", [FAISALY], "en"); subTeam(epOf("late"), FAISALY, 243);
  live = [live1("1H", 0, 0, 36, [miss])];
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 35) }, {});
  check("  no events baseline in the previous poll (quota guard gap) -> an old miss is not announced", pushes.length === 0, pushes.length);
}

// 5) GOAL_PUSH off -> nothing for any alert type
{
  reset(); const w = await loadWorker();
  await addSub("off1", [FAISALY], "en");
  live = [live1("HT", 0, 0, 45)];
  await tick2(w, { [FX]: prevEntry("1H", 0, 0, 44) }, { env: { GOAL_PUSH: "off" } });
  check("GOAL_PUSH=off: no status alert queued or sent, no ev_sent row", pushes.length === 0 && db.prepare("SELECT COUNT(*) c FROM ev_sent").get().c === 0, pushes.length);
}

console.log = origLog;
process.exit(fail ? 1 : 0);
