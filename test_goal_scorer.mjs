// Scorer name in the goal notification (two steps, 8 Oct 2026): the alert goes out at once WITHOUT a name; a queued update
// (delay 60 s, then 120 s, then 240 s) fetches fixtures/events and re-sends the SAME tag with the name (renotify:false).
// Lookup rules: n-th goal of the scoring side, lag guard, penalty / own goal tags, Arabic name only when confirmed.
// The harness runs queued messages immediately and records their delaySeconds. Mock api-sports + names + push services.
// Arabic is asserted by code points (\u escapes). Run: node --no-warnings test_goal_scorer.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_scorer_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0004_goal_log.sql", "0005_admin_devices.sql", "0006_scorer_update.sql"])
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
    .then((k) => crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: saltB, info }, k, len * 8)).then((x) => new Uint8Array(x));
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

const A = 4531, B = 4529, FX = 77;
const TEAMS = { [A]: { ar: "الفيصلي", en: "Al-Faisaly" }, [B]: { ar: "الوحدات", en: "Al-Wehdat" } };
const THALJI_AR = "يزن ثلجي";            // يزن ثلجي
const PLAYERS = { 900: { ar: THALJI_AR, en: "Yazan Thalji" }, 901: { en: "Only English" }, 902: { ar: "أحمد حمدي", en: "Ahmad Hamdi" },
  _n: { [`${A}|A. Ersan`]: { ar: "أحمد العرسان" }, [`${B}|W. Away`]: { ar: "وليد" } } };

let events, eventsReqs, hang, pushes, queue, sends, playersJson, delays, pushesAtEvents, liveScore, eventsPlan;
function reset() {
  events = { status: 200, body: { errors: [], response: [] }, throws: false };
  eventsReqs = 0; hang = false; pushes = []; queue = []; sends = 0; playersJson = PLAYERS; delays = []; pushesAtEvents = []; liveScore = undefined; eventsPlan = null;
  db.exec("DELETE FROM sent; DELETE FROM sub_teams; DELETE FROM subscriptions; DELETE FROM scorer_update; DELETE FROM admin_devices");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io/fixtures/events")) {
    eventsReqs++; pushesAtEvents.push(pushes.length);
    if (eventsPlan && eventsPlan[eventsReqs - 1]) events.body = eventsPlan[eventsReqs - 1];
    if (hang) await new Promise((_, rej) => init.signal && init.signal.addEventListener("abort", () => rej(new Error("aborted"))));
    if (events.throws) throw new Error("network");
    return new Response(JSON.stringify(events.body), { status: events.status });
  }
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  if (url === "https://saffara.app/assets/team_names.json") return new Response(JSON.stringify(TEAMS), { status: 200 });
  if (url === "https://saffara.app/assets/player_names.json") return playersJson ? new Response(JSON.stringify(playersJson), { status: 200 }) : new Response("x", { status: 404 });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: 201 }); }
  return new Response("{}", { status: 404 });
};
const QUEUE = { send: async (body, opts) => { sends++; queue.push({ body, opts }); if (opts && opts.delaySeconds) delays.push({ kind: body.kind, step: body.step, d: opts.delaySeconds, body }); } };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const mkEnv = (extra = {}) => ({ API_KEY: "k", DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on",
  GOAL_QUEUE: QUEUE, ADMIN_TOKEN: "t".repeat(32),
  LIVE_KV: { get: async () => (liveScore === null ? null : JSON.stringify({ t: 1, m: { [liveScore ? liveScore.fixture : FX]: liveScore ? { h: liveScore.h, a: liveScore.a } : { h: curMsg.h, a: curMsg.a } } })), put: async () => {} }, ...extra });
async function consume(w, env) {
  let n = 0;
  while (queue.length && n++ < 200) { const { body } = queue.shift(); await w.queue({ messages: [{ body, ack() {}, retry() { queue.push({ body }); } }] }, env); }
}
let curMsg = { h: 1, a: 0 };
const gmsg = (over = {}) => ({ fixture: FX, kind: "goal", th: A, ta: B, h: 1, a: 0, minute: 34, offset: 0, ts: Date.now(), side: "home", ...over });
async function run(msg, env = mkEnv()) { const w = await loadWorker(); logs.length = 0; curMsg = msg; queue = [{ body: msg }]; await consume(w, env); }
const ev = (id, name, team, elapsed, detail = "Normal Goal", type = "Goal") => ({ time: { elapsed, extra: null }, team: { id: team }, player: { id, name }, type, detail });
const bodyOf = async (ep) => { const p = pushes.filter((x) => x.url.endsWith("/" + ep)).at(-1); return p ? decrypt(`https://fcm.googleapis.com/fcm/send/${ep}`, p.body) : null; };
const firstBodyOf = async (ep) => { const p = pushes.find((x) => x.url.endsWith("/" + ep)); return p ? decrypt(`https://fcm.googleapis.com/fcm/send/${ep}`, p.body) : null; };
const nPush = (ep) => pushes.filter((x) => x.url.endsWith("/" + ep)).length;
const cps = (x) => Array.from(x, (c) => c.codePointAt(0).toString(16)).join(" ");
const RLM = "‏";
const AR_SCORE_HOME = "الفيصلي " + RLM + "(1)" + RLM + " " + RLM + "-" + RLM + " " + RLM + "0" + RLM + " الوحدات";
const AR_MIN = "\nالدقيقة 34";   // line 2 = minute
const consumerLine = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push" && !l.upd).at(-1);   // the first (immediate) send
const updateLine = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push" && l.upd).at(-1);
const scorerLines = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_scorer");

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

async function subs() { await addSub("ar", [A], "ar"); await addSub("en", [A], "en"); }

// 1) name found by player id: ar + en text, one request
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34)];
await run(gmsg());
let ar = await bodyOf("ar"), en = await bodyOf("en");
check("scorer found (id): ar body = score · minute · Arabic name, exact code points", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN + " · " + THALJI_AR), ar && cps(ar.body));
check("  en body = 2 lines: score / \"34' Yazan Thalji\" (full name from the file)", en && en.body === "Al-Faisaly (1) - 0 Al-Wehdat\n34' Yazan Thalji", en && en.body);
check("  titles: ar hadaf lil-Faisaly!, en Goal for Al-Faisaly! (no score)", cps(ar.title) === cps("⚽ هدف للفيصلي!") && en.title === "⚽ Goal for Al-Faisaly!", [ar.title, en.title]);
check("  exactly ONE events request; the update log says scorer:hit events_request:1", eventsReqs === 1 && scorerLines().at(-1).scorer === "hit" && scorerLines().at(-1).events_request === 1, [eventsReqs, scorerLines()]);
{
  const f1 = await firstBodyOf("ar"), f2 = await firstBodyOf("en");
  check("  TWO pushes per subscriber: the first has NO name (score + minute only), the second adds the name",
    nPush("ar") === 2 && nPush("en") === 2 && cps(f1.body) === cps(AR_SCORE_HOME + AR_MIN) && f2.body === "Al-Faisaly (1) - 0 Al-Wehdat\n34'", [nPush("ar"), nPush("en"), f1.body, f2.body]);
  check("  same tag and title and url on both; ONLY the update carries renotify:false", f1.tag === ar.tag && f1.title === ar.title && f1.url === ar.url && f2.tag === en.tag && f1.renotify === undefined && ar.renotify === false && en.renotify === false, [f1, ar]);
  check("  the first push was sent BEFORE any events request (the lookup never delays the alert)", pushesAtEvents[0] === 2, pushesAtEvents);
}

// 2) no matching event / provider lag -> sent immediately without a name
for (const [label, resp, over] of [
  ["no events yet", [], {}],
  ["provider lag: team already scored once, score is now 2 but only 1 goal listed", [ev(900, "Y. Thalji", A, 12)], { h: 2 }],
  ["only the OTHER team has goals", [ev(900, "Y. Thalji", B, 12)], {}],
  ["only a Missed Penalty listed", [ev(900, "Y. Thalji", A, 30, "Missed Penalty")], {}],
]) {
  reset(); await subs(); events.body.response = resp;
  await run(gmsg(over)); ar = await bodyOf("ar"); en = await bodyOf("en");
  check(`${label} -> only the nameless alert (ar and en, ONE push each); 3 attempts then given up`, ar && en && nPush("ar") === 1 && nPush("en") === 1 && cps(ar.body) === cps(AR_SCORE_HOME.replace("(1)", over.h ? "(2)" : "(1)") + AR_MIN) && en.body === `Al-Faisaly (${over.h || 1}) - 0 Al-Wehdat\n34'` && eventsReqs === 3 && scorerLines().at(-1).gave_up === true, [ar && ar.body, en && en.body, eventsReqs, scorerLines()]);
}

// 3) failed request: 500 / network error / provider "errors" body / hanging (timeout) — never blocks the send
for (const [label, setup] of [["HTTP 500", () => { events.status = 500; }], ["network error", () => { events.throws = true; }],
  ["errors body", () => { events.body = { errors: { token: "bad" }, response: [] }; }]]) {
  reset(); await subs(); setup();
  await run(gmsg()); ar = await bodyOf("ar");
  check(`events ${label} -> notification still sent, no name, update attempts logged scorer:error then given up`, ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && scorerLines().every((l) => l.scorer === "error") && scorerLines().at(-1).gave_up === true && consumerLine().sent === 2 && nPush("ar") === 1, [ar && ar.body, scorerLines(), consumerLine()]);
}
reset(); await subs(); hang = true;
const keepAlive = setInterval(() => {}, 100);   // AbortSignal.timeout() timers are unref'd in Node: keep the loop alive for the test
const t0 = Date.now(); await run(gmsg()); const dt = Date.now() - t0; ar = await bodyOf("ar"); clearInterval(keepAlive);
check(`events request that never answers -> each attempt aborted at the 2.5 s cap (3 attempts, ${dt} ms total); the alert itself went out BEFORE the first events request`, dt < 11000 && ar && scorerLines().every((l) => l.scorer === "error") && consumerLine().sent === 2 && pushesAtEvents[0] === 2 && nPush("ar") === 1, [dt, scorerLines(), pushesAtEvents]);

// 4) latest Goal event of the scoring team (not the first), chronological; Missed Penalty ignored
reset(); await subs();
events.body.response = [ev(902, "A. Hamdi", A, 55), ev(900, "Y. Thalji", A, 12), ev(901, "X", B, 40), ev(900, "Y. Thalji", A, 70, "Missed Penalty")];
await run(gmsg({ h: 2, minute: 55, side: "home" })); en = await bodyOf("en");
check("two goals by the team (score 2): the 2nd goal's scorer (55' Ahmad Hamdi), the 70' missed penalty ignored", en && en.body.endsWith("\n55' Ahmad Hamdi") , en && en.body);
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 12), ev(902, "A. Hamdi", A, 55), ev(901, "O. English", A, 77)];   // a 3rd goal already listed, the alert is for 2-0
await run(gmsg({ h: 2, minute: 55, side: "home" })); en = await bodyOf("en");
check("a later goal already in the events (score 2, three listed): the name is the SECOND goal's (55' Ahmad Hamdi), not the latest", en && en.body.endsWith("\n55' Ahmad Hamdi"), en && en.body);

// 5) penalty and own goal tags
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34, "Penalty")];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("penalty: ar name followed by (ج) U+0020 U+0028 U+062C U+0029; en (pen)",
  ar && cps(ar.body).endsWith(cps(THALJI_AR + " (ج)")) && en && en.body.endsWith("\n34' Yazan Thalji (pen)"), [ar && cps(ar.body).slice(-40), en && en.body]);
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", B, 34, "Own Goal")];   // B's player scored into his own net: credited to A (home)
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("own goal (event team = the scorer's own team): credited to the other side; ar (ع), en (og)",
  ar && en && en.body.endsWith("\n34' Yazan Thalji (og)") && cps(ar.body).endsWith(cps("(ع)")), [ar && ar.body, en && en.body]);
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34, "Own Goal")];   // an own goal by A's player does NOT count for A
await run(gmsg()); en = await bodyOf("en");
check("an own goal by the scoring team's own player is not attributed to that team (no name)", en && !en.body.includes("Thalji"), en && en.body);

// 6) no confirmed Arabic name: the whole name is dropped from the Arabic text (no English inside), English keeps it
reset(); await subs();
events.body.response = [ev(901, "O. English", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("no confirmed Arabic name -> Arabic subscriber gets ONLY the nameless alert (no update, no Latin letters); English gets the name", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && !/[A-Za-z]/.test(ar.body) && nPush("ar") === 1 && nPush("en") === 2 && en.body.endsWith("\n34' Only English") && updateLine().skipped_no_name === 1, [ar && ar.body, en && en.body, nPush("ar"), nPush("en"), updateLine()]);
reset(); await subs(); playersJson = null;   // player_names.json unavailable
events.body.response = [ev(900, "Y. Thalji", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("player_names.json unavailable -> ar: no name; en: the provider's abbreviated name reduced to the surname (Thalji)", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && en.body.endsWith("\n34' Thalji"), [ar && ar.body, en && en.body]);

// 7) fallback by name for leagues without player ids in the DB (Jordan / Iraq): key "<team>|<provider name>"
reset(); await subs();
events.body.response = [ev(777777, "A. Ersan", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("unknown player id, but 'team|A. Ersan' is confirmed -> Arabic name from the name map; en = provider name", ar && cps(ar.body).endsWith(cps(" · أحمد العرسان")) && en.body.endsWith("\n34' Ersan"), [ar && ar.body, en && en.body]);
reset(); await addSub("awayar", [B], "ar");
events.body.response = [ev(555, "W. Away", B, 34)];
await run(gmsg({ h: 0, a: 1, side: "away" })); ar = await bodyOf("awayar");
check("away goal: name looked up with the AWAY team's key; parentheses on the away number", ar && cps(ar.body).endsWith(cps(" · وليد")) && ar.body.includes(RLM + "(1)" + RLM) && ar.body.indexOf("(1)") > ar.body.indexOf("-"), ar && ar.body);

// 8) cost: one request per goal across many pages; none without subscribers; none for cancels / simulate
reset();
db.exec("BEGIN");
for (let i = 0; i < 450; i++) { const e = `https://fcm.googleapis.com/fcm/send/bulk${String(i).padStart(4, "0")}`;
  const k = Object.values(clients)[0] || null; }
db.exec("COMMIT");
const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
const P256 = b64u(await crypto.subtle.exportKey("raw", kp.publicKey)), AUTH = b64u(crypto.getRandomValues(new Uint8Array(16)));
db.exec("BEGIN");
for (let i = 0; i < 450; i++) { const e = `https://fcm.googleapis.com/fcm/send/bulk${String(i).padStart(4, "0")}`;
  db.prepare("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)").run(e, P256, AUTH, i % 2 ? "en" : "ar", 1, 1);
  db.prepare("INSERT INTO sub_teams VALUES (?,?)").run(e, A); }
db.exec("COMMIT");
events.body.response = [ev(900, "Y. Thalji", A, 34)];
await run(gmsg());
check("450 subscribers (3 pages): ONE events request in total; 450 alerts + 450 updates (each of the 3 pages sent twice); ONE finder message", eventsReqs === 1 && pushes.length === 900 && delays.filter((x) => x.kind === "goal_scorer").length === 1, [eventsReqs, pushes.length, delays]);
reset();
await run(gmsg());
check("goal with NO subscribers -> zero provider requests", eventsReqs === 0 && pushes.length === 0, eventsReqs);
reset(); await subs();
await run(gmsg({ kind: "cancel", h: 0, a: 0 }));
check("cancel -> no events request, no name", eventsReqs === 0 && (await bodyOf("ar")).body.indexOf("·") < 0, eventsReqs);
// failed pushes retried later must not call the provider again
reset();
db.exec("BEGIN");
for (let i = 0; i < 10; i++) { const e = `https://fcm.googleapis.com/fcm/send/rt${i}`; db.prepare("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)").run(e, P256, AUTH, "en", 1, 1); db.prepare("INSERT INTO sub_teams VALUES (?,?)").run(e, A); }
db.exec("COMMIT");
events.body.response = [ev(900, "Y. Thalji", A, 34)];
const realFetch = globalThis.fetch; let flaky = 0;
globalThis.fetch = async (u, i) => { if (String(u).includes("/rt3") && flaky++ === 0) return new Response(null, { status: 503 }); return realFetch(u, i); };
await run(gmsg());
globalThis.fetch = realFetch;
check("a push retried after a transient failure does not re-query the provider (still 1 request): 503 then OK for the alert, then the update; 2 deliveries to that endpoint", eventsReqs === 1 && flaky === 3 && pushes.filter((p) => p.url.endsWith("/rt3")).length === 2 && pushes.length === 20, [eventsReqs, flaky, pushes.length]);

// 9) /push/simulate with player_id (+ player_name, detail): same queue, no provider request
const sim = async (b, env = mkEnv()) => { const w = await loadWorker(); queue = []; sends = 0; delays = [];
  return w.fetch(new Request("https://w.example/push/simulate", { method: "POST", headers: { Authorization: "Bearer " + "t".repeat(32), "Content-Type": "application/json" }, body: JSON.stringify(b) }), env); };
reset(); await subs();
const good = { fixture: 1643360, th: 4535, ta: A, h: 0, a: 1, minute: 34, kind: "goal", player_id: 900 };
let r = await sim(good); const w2 = await loadWorker();
check("simulate with player_id -> 200, message carries simsc (the scorer to 'find') but NO sc: the first alert has no name", r.status === 200 && queue.length === 1 && queue[0].body.simsc && queue[0].body.simsc.pid === 900 && queue[0].body.sc === undefined, queue[0] && queue[0].body);
curMsg = queue[0].body;
await consume(w2, mkEnv());
ar = await bodyOf("ar");
check("  the simulated flow: first alert nameless, 60 s update with the Arabic name, NO provider request", ar && nPush("ar") === 2 && cps((await firstBodyOf("ar")).body).endsWith(cps("الدقيقة 34")) && cps(ar.body).endsWith(cps(" · " + THALJI_AR)) && ar.renotify === false && eventsReqs === 0 && delays[0].d === 60, [ar && ar.body, eventsReqs, delays]);
r = await sim({ ...good, player_id: 0 }); check("simulate: bad player_id -> 400", r.status === 400);
r = await sim({ ...good, detail: "Foul" }); check("simulate: bad detail -> 400", r.status === 400);
r = await sim({ ...good, player_id: undefined, player_name: "A. Ersan", detail: "Penalty" });
check("simulate with player_name + detail Penalty -> simsc.pdet Penalty, ptid = the scoring (away) team", r.status === 200 && queue[0].body.simsc.pdet === "Penalty" && queue[0].body.simsc.ptid === A && queue[0].body.simsc.pname === "A. Ersan", queue[0] && queue[0].body);
r = await sim({ ...good, player_id: undefined });
check("simulate without a player -> no simsc, no sc: nameless alert only and no update is scheduled", r.status === 200 && queue[0].body.simsc === undefined && queue[0].body.sc === undefined);
await consume(w2, mkEnv());
check("  ...and nothing else gets queued (no finder for a simulation with nobody to find)", delays.length === 0, delays);
r = await sim({ ...good, admin_only: "yes" }); check("simulate: admin_only must be a boolean -> 400", r.status === 400);

// 10) simulated goals/cancels use the same per-score tags
reset(); await subs();
{
  const wsim = await loadWorker();
  const post = (b) => wsim.fetch(new Request("https://w.example/push/simulate", { method: "POST", headers: { Authorization: "Bearer " + "t".repeat(32), "Content-Type": "application/json" }, body: JSON.stringify(b) }), mkEnv());
  const base = { fixture: 1643360, th: 4535, ta: A, minute: 34 };
  queue = []; pushes = [];
  await post({ ...base, kind: "goal", h: 0, a: 1 }); await post({ ...base, kind: "goal", h: 0, a: 2, minute: 60 });
  await post({ ...base, kind: "cancel", h: 0, a: 1, minute: 62, side: "away" });          // inferred prev = 0-2
  await post({ ...base, kind: "cancel", h: 0, a: 1, minute: 62, side: "away", prev_h: 0, prev_a: 2 });   // explicit prev
  const bodies = queue.map((q) => q.body);
  check("simulate cancel without prev infers it (0-1 + away goal = 0-2); explicit prev_h/prev_a also accepted", bodies[2].ph === 0 && bodies[2].pa === 2 && bodies[3].ph === 0 && bodies[3].pa === 2, bodies.map((x) => [x.ph, x.pa]));
  await consume(wsim, mkEnv());
  const tg = [];
  for (const pu of pushes.filter((p) => p.url.endsWith("/en"))) tg.push((await decrypt("https://fcm.googleapis.com/fcm/send/en", pu.body)).tag);
  check("simulated tags: goal 0-1, goal 0-2 differ; both cancels (prev 0-2) carry goal-1643360-0-2", JSON.stringify(tg) === JSON.stringify(["goal-1643360-0-1", "goal-1643360-0-2", "goal-1643360-0-2", "goal-1643360-0-2"]), tg);
  const bad = await post({ ...base, kind: "cancel", h: 0, a: 1, prev_h: -1 });
  check("simulate: bad prev score -> 400", bad.status === 400);
}

// 11) the 2-line format: surname rule for abbreviated English names, exact lines, cancel format
{
  const surnameCases = [["N. Al Rawabdeh", "Al Rawabdeh"], ["A. Rabbo", "Rabbo"], ["A. B. Smith", "Smith"], ["A.Ersan", "Ersan"], ["Mohamed Salah", "Mohamed Salah"], ["Yazan Thalji", "Yazan Thalji"]];
  for (const [prov, want] of surnameCases) {
    reset(); await subs();
    events.body.response = [ev(424242, prov, A, 34)];   // id not in the names file -> English = the provider's name
    await run(gmsg()); en = await bodyOf("en");
    check(`English provider name "${prov}" -> line 2 shows "${want}"` + (want === prov ? " (full name kept)" : " (surname only)"), en && en.body.split("\n")[1] === `34' ${want}`, en && en.body);
  }
  reset(); await subs();
  events.body.response = [ev(900, "Y. Thalji", A, 34)];
  await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
  check("goal with a scorer: body has exactly ONE line break; ar line 2 = 'minute \u00b7 name', en line 2 = \"34' Yazan Thalji\"",
    ar.body.split("\n").length === 2 && en.body.split("\n").length === 2
    && cps(ar.body.split("\n")[1]) === cps("\u0627\u0644\u062f\u0642\u064a\u0642\u0629 34 \u00b7 " + THALJI_AR) && en.body.split("\n")[1] === "34' Yazan Thalji", [ar.body, en.body]);
  check("  line 1 (score) unchanged: ar RLM-wrapped with (1) on the scorer, en \"Al-Faisaly (1) - 0 Al-Wehdat\"",
    cps(ar.body.split("\n")[0]) === cps(AR_SCORE_HOME) && en.body.split("\n")[0] === "Al-Faisaly (1) - 0 Al-Wehdat", [ar.body, en.body]);
  check("  titles name the scoring team and carry no score: en \"Goal for Al-Faisaly!\", ar hadaf lil-Faisaly!",
    en.title === "\u26bd Goal for Al-Faisaly!" && cps(ar.title) === cps("\u26bd \u0647\u062f\u0641 \u0644\u0644\u0641\u064a\u0635\u0644\u064a!") && !/\d/.test(en.title + ar.title), [en.title, ar.title]);
  // no scorer: line 2 = minute only
  reset(); await subs();
  await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
  check("no scorer -> line 2 is the minute only (en \"34'\", ar \"\u0627\u0644\u062f\u0642\u064a\u0642\u0629 34\")", en.body.split("\n")[1] === "34'" && cps(ar.body.split("\n")[1]) === cps("\u0627\u0644\u062f\u0642\u064a\u0642\u0629 34"), [ar.body, en.body]);
  // cancel format (the cancelled team = the one whose goal was disallowed; en dash U+2013, not an em dash)
  reset(); await subs();
  await run(gmsg({ kind: "cancel", h: 0, a: 0, side: "home", ph: 1, pa: 0 })); ar = await bodyOf("ar"); en = await bodyOf("en");
  check("cancel: en title \"\u274c Goal disallowed \u2013 Al-Faisaly\" with an EN dash (U+2013); ar \u274c ulghiya hadaf al-Faisaly",
    en.title === "\u274c Goal disallowed \u2013 Al-Faisaly" && cps(en.title).includes("2013") && !cps(en.title).includes("2014")
    && cps(ar.title) === cps("\u274c \u0623\u064f\u0644\u063a\u064a \u0647\u062f\u0641 \u0627\u0644\u0641\u064a\u0635\u0644\u064a"), [en.title, cps(ar.title)]);
  check("  cancel body = the score only (one line, no parentheses, no minute); tag = the cancelled goal's score (1-0)",
    en.body === "Al-Faisaly 0 - 0 Al-Wehdat" && !ar.body.includes("\n") && !ar.body.includes("(") && en.tag === "goal-77-1-0", [en.body, ar.body, en.tag]);
}

// 12) two-step goal alert: the update step (delays, retries, guards, once per goal, admin-only simulation)
const dl = () => delays.map((x) => x.d);
{
  // a) found at once: one finder, delay 60, scheduled by the first page only
  reset(); await subs();
  events.body.response = [ev(900, "Y. Thalji", A, 34)];
  await run(gmsg());
  check("finder scheduled ONCE with delaySeconds=60; the update was queued as a normal goal message with sc + upd (no second finder)", JSON.stringify(dl()) === "[60]" && delays[0].kind === "goal_scorer" && eventsReqs === 1 && nPush("en") === 2, [dl(), eventsReqs, nPush("en")]);
  ar = await bodyOf("ar"); en = await bodyOf("en");
  check("  update: SAME tag as the alert (goal-77-1-0), name line added, renotify:false", ar.tag === "goal-77-1-0" && en.tag === "goal-77-1-0" && ar.renotify === false && en.body.endsWith("\n34' Yazan Thalji"), [ar, en]);

  // b) found on the 2nd attempt (120 s), c) on the 3rd (240 s), d) never
  for (const [label, plan, want, reqs] of [
    ["found on the 2nd attempt", [{ errors: [], response: [] }, { errors: [], response: [ev(900, "Y. Thalji", A, 34)] }], [60, 120], 2],
    ["found on the 3rd attempt", [{ errors: [], response: [] }, { errors: [], response: [] }, { errors: [], response: [ev(900, "Y. Thalji", A, 34)] }], [60, 120, 240], 3],
    ["never found", [{ errors: [], response: [] }, { errors: [], response: [] }, { errors: [], response: [] }, { errors: [], response: [ev(900, "Y. Thalji", A, 34)] }], [60, 120, 240], 3],
  ]) {
    reset(); await subs(); eventsPlan = plan;
    await run(gmsg());
    const found = label !== "never found";
    check(`${label}: delays ${JSON.stringify(want)} (each from the previous attempt), ${reqs} events requests, ${found ? "exactly one update" : "no update, given up (a 4th attempt never happens)"}`,
      JSON.stringify(dl()) === JSON.stringify(want) && eventsReqs === reqs && nPush("en") === (found ? 2 : 1) && (found || scorerLines().at(-1).gave_up === true), [dl(), eventsReqs, nPush("en"), scorerLines()]);
  }

  // e) the score changed before the update (a later goal, or a cancel): no update, no events request
  for (const [label, live] of [["a later goal (KV now 2-0)", { fixture: FX, h: 2, a: 0 }], ["a VAR cancel (KV now 0-0)", { fixture: FX, h: 0, a: 0 }], ["the other team scored (KV now 1-1)", { fixture: FX, h: 1, a: 1 }]]) {
    reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)];
    const w = await loadWorker(); logs.length = 0; liveScore = live; curMsg = gmsg();
    queue = [{ body: curMsg }]; await consume(w, mkEnv());
    check(`${label} -> update NOT sent, no events request; log skipped:score_changed`, nPush("en") === 1 && eventsReqs === 0 && scorerLines().at(-1).skipped === "score_changed", [nPush("en"), eventsReqs, scorerLines()]);
  }
  // f) no state in KV: skip (never guess)
  reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)]; liveScore = null;
  await run(gmsg());
  check("no live state for the fixture -> update skipped (no_state), no events request", nPush("en") === 1 && eventsReqs === 0 && scorerLines().at(-1).skipped === "no_state", scorerLines());
  // the finished match is found in `f` (final score) too
  reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)];
  {
    const w = await loadWorker(); logs.length = 0; curMsg = gmsg();
    const env = mkEnv({ LIVE_KV: { get: async () => JSON.stringify({ t: 1, m: {}, f: { [FX]: { h: 1, a: 0, s: "FT", ft: 1 } } }), put: async () => {} } });
    queue = [{ body: curMsg }]; await consume(w, env);
    check("match already finished (score read from `f`) -> the update still goes out", nPush("en") === 2 && eventsReqs === 1, [nPush("en"), eventsReqs]);
  }

  // g) once per goal: the same finder redelivered (queue at-least-once) sends nothing more
  reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)];
  await run(gmsg());
  const finder = delays.find((x) => x.kind === "goal_scorer").body;
  const before = pushes.length, reqsBefore = eventsReqs;
  { const w = await loadWorker(); logs.length = 0; queue = [{ body: finder }, { body: finder }]; await consume(w, mkEnv()); }
  check("finder redelivered twice after the update was sent -> nothing sent, no events request (already_updated)", pushes.length === before && eventsReqs === reqsBefore && scorerLines().every((l) => l.skipped === "already_updated"), [pushes.length - before, eventsReqs - reqsBefore, scorerLines()]);
  check("  one claim row per (fixture, score) in scorer_update", db.prepare("SELECT count(*) AS n FROM scorer_update WHERE fixture = 77 AND h = 1 AND a = 0").get().n === 1);
  // two finders racing before any claim: only one update
  reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)];
  await run(gmsg());
  db.exec("DELETE FROM scorer_update"); pushes = [];
  { const w = await loadWorker(); const f2 = delays.find((x) => x.kind === "goal_scorer").body; queue = [{ body: f2 }, { body: f2 }]; await consume(w, mkEnv()); }
  check("two identical finders processed one after the other (claim row absent at start) -> exactly ONE update push per subscriber", nPush("en") === 1 && nPush("ar") === 1, [nPush("en"), nPush("ar")]);

  // h) too old (TTL 10 min) / GOAL_PUSH off
  reset(); await subs(); events.body.response = [ev(900, "Y. Thalji", A, 34)];
  await run(gmsg());
  const old = { ...delays.find((x) => x.kind === "goal_scorer").body, ts: Date.now() - 11 * 60 * 1000 };
  db.exec("DELETE FROM scorer_update"); pushes = []; eventsReqs = 0;
  { const w = await loadWorker(); logs.length = 0; queue = [{ body: old }]; await consume(w, mkEnv()); }
  check("a finder older than the 10-minute TTL does nothing (expired), no events request", pushes.length === 0 && eventsReqs === 0 && scorerLines().at(-1).expired === true, scorerLines());
  { const w = await loadWorker(); logs.length = 0; queue = [{ body: delays.find((x) => x.kind === "goal_scorer").body }]; await consume(w, mkEnv({ GOAL_PUSH: "off" })); }
  check("GOAL_PUSH off -> the finder does nothing (skipped:off)", pushes.length === 0 && eventsReqs === 0 && scorerLines().at(-1).skipped === "off", scorerLines());

  // i) a cancelled goal never gets a finder; the cancel message itself is unchanged
  reset(); await subs();
  await run(gmsg({ kind: "cancel", h: 0, a: 0, side: "home", ph: 1, pa: 0 }));
  check("cancel -> no finder scheduled, no events request", delays.length === 0 && eventsReqs === 0, [delays, eventsReqs]);

  // j) /push/simulate admin_only: ONLY admin_devices get the alert and the update; other subscribers get nothing
  reset(); await subs();
  db.prepare("INSERT INTO admin_devices VALUES (?, ?)").run("https://fcm.googleapis.com/fcm/send/en", 1);
  {
    const w = await loadWorker(); queue = []; delays = [];
    const rr = await w.fetch(new Request("https://w.example/push/simulate", { method: "POST", headers: { Authorization: "Bearer " + "t".repeat(32), "Content-Type": "application/json" },
      body: JSON.stringify({ fixture: 1643360, th: 4535, ta: A, h: 0, a: 1, minute: 34, kind: "goal", player_id: 900, admin_only: true }) }), mkEnv());
    curMsg = queue[0].body; const adminFlag = queue[0].body.admin === true;
    await consume(w, mkEnv());
    check("simulate admin_only: alert + update reach ONLY the admin device (en); the other subscriber (ar) gets nothing", rr.status === 200 && adminFlag && nPush("en") === 2 && nPush("ar") === 0, [rr.status, nPush("en"), nPush("ar")]);
    const f1 = await firstBodyOf("en"), f2 = await bodyOf("en");
    check("  and the simulated pair is nameless first, then named with renotify:false and the same tag", f1.tag === f2.tag && f1.renotify === undefined && f2.renotify === false && !f1.body.includes("Yazan") && f2.body.endsWith("Yazan Thalji"), [f1, f2]);
  }
}

console.log = origLog;
process.exit(fail ? 1 : 0);
