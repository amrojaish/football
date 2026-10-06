// Scorer name in the goal notification: fixtures/events lookup (1 request per goal), lag guard, penalty / own goal tags,
// Arabic name only when confirmed, never delays the send. Mock api-sports + names + push services; real encryption/decryption.
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
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0004_goal_log.sql"])
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

let events, eventsReqs, hang, pushes, queue, sends, playersJson;
function reset() {
  events = { status: 200, body: { errors: [], response: [] }, throws: false };
  eventsReqs = 0; hang = false; pushes = []; queue = []; sends = 0; playersJson = PLAYERS;
  db.exec("DELETE FROM sent; DELETE FROM sub_teams; DELETE FROM subscriptions");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io/fixtures/events")) {
    eventsReqs++;
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
const QUEUE = { send: async (body, opts) => { sends++; queue.push({ body, opts }); } };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const mkEnv = (extra = {}) => ({ API_KEY: "k", DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on",
  GOAL_QUEUE: QUEUE, ADMIN_TOKEN: "t".repeat(32), LIVE_KV: { get: async () => null, put: async () => {} }, ...extra });
async function consume(w, env) {
  let n = 0;
  while (queue.length && n++ < 200) { const { body } = queue.shift(); await w.queue({ messages: [{ body, ack() {}, retry() { queue.push({ body }); } }] }, env); }
}
const gmsg = (over = {}) => ({ fixture: FX, kind: "goal", th: A, ta: B, h: 1, a: 0, minute: 34, offset: 0, ts: Date.now(), side: "home", ...over });
async function run(msg, env = mkEnv()) { const w = await loadWorker(); logs.length = 0; queue = [{ body: msg }]; await consume(w, env); }
const ev = (id, name, team, elapsed, detail = "Normal Goal", type = "Goal") => ({ time: { elapsed, extra: null }, team: { id: team }, player: { id, name }, type, detail });
const bodyOf = async (ep) => { const p = pushes.find((x) => x.url.endsWith("/" + ep)); return p ? decrypt(`https://fcm.googleapis.com/fcm/send/${ep}`, p.body) : null; };
const cps = (x) => Array.from(x, (c) => c.codePointAt(0).toString(16)).join(" ");
const RLM = "‏";
const AR_SCORE_HOME = "الفيصلي " + RLM + "(1)" + RLM + " " + RLM + "-" + RLM + " " + RLM + "0" + RLM + " الوحدات";
const AR_MIN = " · الدقيقة 34";
const consumerLine = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push").at(-1);

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

async function subs() { await addSub("ar", [A], "ar"); await addSub("en", [A], "en"); }

// 1) name found by player id: ar + en text, one request
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34)];
await run(gmsg());
let ar = await bodyOf("ar"), en = await bodyOf("en");
check("scorer found (id): ar body = score · minute · Arabic name, exact code points", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN + " · " + THALJI_AR), ar && cps(ar.body));
check("  en body = \"Al-Faisaly (1) - 0 Al-Wehdat · 34' · Yazan Thalji\"", en && en.body === "Al-Faisaly (1) - 0 Al-Wehdat · 34' · Yazan Thalji", en && en.body);
check("  titles unchanged (ar: hadaf lil-Faisaly!, en: Goal! score)", cps(ar.title) === cps("⚽ هدف للفيصلي!") && en.title === "⚽ Goal! Al-Faisaly 1–0 Al-Wehdat", [ar.title, en.title]);
check("  exactly ONE events request; log says scorer:hit events_request:1", eventsReqs === 1 && consumerLine().scorer === "hit" && consumerLine().events_request === 1, [eventsReqs, consumerLine()]);

// 2) no matching event / provider lag -> sent immediately without a name
for (const [label, resp, over] of [
  ["no events yet", [], {}],
  ["provider lag: team already scored once, score is now 2 but only 1 goal listed", [ev(900, "Y. Thalji", A, 12)], { h: 2 }],
  ["only the OTHER team has goals", [ev(900, "Y. Thalji", B, 12)], {}],
  ["only a Missed Penalty listed", [ev(900, "Y. Thalji", A, 30, "Missed Penalty")], {}],
]) {
  reset(); await subs(); events.body.response = resp;
  await run(gmsg(over)); ar = await bodyOf("ar"); en = await bodyOf("en");
  check(`${label} -> sent without a name (ar and en), 1 request`, ar && en && cps(ar.body) === cps(AR_SCORE_HOME.replace("(1)", over.h ? "(2)" : "(1)") + AR_MIN) && en.body === `Al-Faisaly (${over.h || 1}) - 0 Al-Wehdat · 34'` && eventsReqs === 1, [ar && ar.body, en && en.body, eventsReqs]);
}

// 3) failed request: 500 / network error / provider "errors" body / hanging (timeout) — never blocks the send
for (const [label, setup] of [["HTTP 500", () => { events.status = 500; }], ["network error", () => { events.throws = true; }],
  ["errors body", () => { events.body = { errors: { token: "bad" }, response: [] }; }]]) {
  reset(); await subs(); setup();
  await run(gmsg()); ar = await bodyOf("ar");
  check(`events ${label} -> notification still sent, no name, logged scorer:error`, ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && consumerLine().scorer === "error" && consumerLine().sent === 2, [ar && ar.body, consumerLine()]);
}
reset(); await subs(); hang = true;
const keepAlive = setInterval(() => {}, 100);   // AbortSignal.timeout() timers are unref'd in Node: keep the loop alive for the test
const t0 = Date.now(); await run(gmsg()); const dt = Date.now() - t0; ar = await bodyOf("ar"); clearInterval(keepAlive);
check(`events request that never answers -> aborted after the 2.5 s cap (took ${dt} ms), notification still sent without a name`, dt < 4500 && ar && consumerLine().scorer === "error" && consumerLine().sent === 2, [dt, consumerLine()]);

// 4) latest Goal event of the scoring team (not the first), chronological; Missed Penalty ignored
reset(); await subs();
events.body.response = [ev(902, "A. Hamdi", A, 55), ev(900, "Y. Thalji", A, 12), ev(901, "X", B, 40), ev(900, "Y. Thalji", A, 70, "Missed Penalty")];
await run(gmsg({ h: 2, minute: 55, side: "home" })); en = await bodyOf("en");
check("two goals by the team (score 2): the LATEST real goal's scorer (55' Ahmad Hamdi), the 70' missed penalty ignored", en && en.body.endsWith("· Ahmad Hamdi") , en && en.body);

// 5) penalty and own goal tags
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34, "Penalty")];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("penalty: ar name followed by (ج) U+0020 U+0028 U+062C U+0029; en (pen)",
  ar && cps(ar.body).endsWith(cps(THALJI_AR + " (ج)")) && en && en.body.endsWith("· Yazan Thalji (pen)"), [ar && cps(ar.body).slice(-40), en && en.body]);
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", B, 34, "Own Goal")];   // B's player scored into his own net: credited to A (home)
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("own goal (event team = the scorer's own team): credited to the other side; ar (ع), en (og)",
  ar && en && en.body.endsWith("· Yazan Thalji (og)") && cps(ar.body).endsWith(cps("(ع)")), [ar && ar.body, en && en.body]);
reset(); await subs();
events.body.response = [ev(900, "Y. Thalji", A, 34, "Own Goal")];   // an own goal by A's player does NOT count for A
await run(gmsg()); en = await bodyOf("en");
check("an own goal by the scoring team's own player is not attributed to that team (no name)", en && !en.body.includes("Thalji"), en && en.body);

// 6) no confirmed Arabic name: the whole name is dropped from the Arabic text (no English inside), English keeps it
reset(); await subs();
events.body.response = [ev(901, "O. English", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("no confirmed Arabic name -> Arabic text has NO name and no Latin letters; English shows the name", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && !/[A-Za-z]/.test(ar.body) && en.body.endsWith("· Only English"), [ar && ar.body, en && en.body]);
reset(); await subs(); playersJson = null;   // player_names.json unavailable
events.body.response = [ev(900, "Y. Thalji", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("player_names.json unavailable -> ar: no name; en: the provider's name (Y. Thalji)", ar && cps(ar.body) === cps(AR_SCORE_HOME + AR_MIN) && en.body.endsWith("· Y. Thalji"), [ar && ar.body, en && en.body]);

// 7) fallback by name for leagues without player ids in the DB (Jordan / Iraq): key "<team>|<provider name>"
reset(); await subs();
events.body.response = [ev(777777, "A. Ersan", A, 34)];
await run(gmsg()); ar = await bodyOf("ar"); en = await bodyOf("en");
check("unknown player id, but 'team|A. Ersan' is confirmed -> Arabic name from the name map; en = provider name", ar && cps(ar.body).endsWith(cps(" · أحمد العرسان")) && en.body.endsWith("· A. Ersan"), [ar && ar.body, en && en.body]);
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
check("450 subscribers (3 pages): ONE events request in total; every page sent; the resolved scorer rides in the queue messages", eventsReqs === 1 && pushes.length === 450, [eventsReqs, pushes.length]);
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
check("a push retried after a transient failure does not re-query the provider (still 1 request): 2 attempts to that endpoint (503 then OK), delivered once", eventsReqs === 1 && flaky === 2 && pushes.filter((p) => p.url.endsWith("/rt3")).length === 1 && pushes.length === 10, [eventsReqs, flaky, pushes.length]);

// 9) /push/simulate with player_id (+ player_name, detail): same queue, no provider request
const sim = async (b, env = mkEnv()) => { const w = await loadWorker(); queue = []; sends = 0;
  return w.fetch(new Request("https://w.example/push/simulate", { method: "POST", headers: { Authorization: "Bearer " + "t".repeat(32), "Content-Type": "application/json" }, body: JSON.stringify(b) }), env); };
reset(); await subs();
const good = { fixture: 1643360, th: 4535, ta: A, h: 0, a: 1, minute: 34, kind: "goal", player_id: 900 };
let r = await sim(good); const w2 = await loadWorker();
check("simulate with player_id -> 200, message carries sc and scd", r.status === 200 && queue.length === 1 && queue[0].body.sc && queue[0].body.sc.pid === 900 && queue[0].body.scd === true, queue[0] && queue[0].body);
await consume(w2, mkEnv());
ar = await bodyOf("ar");
check("  the simulated notification shows the player's Arabic name and made NO provider request", ar && cps(ar.body).endsWith(cps(" · " + THALJI_AR)) && eventsReqs === 0, [ar && ar.body, eventsReqs]);
r = await sim({ ...good, player_id: 0 }); check("simulate: bad player_id -> 400", r.status === 400);
r = await sim({ ...good, detail: "Foul" }); check("simulate: bad detail -> 400", r.status === 400);
r = await sim({ ...good, player_id: undefined, player_name: "A. Ersan", detail: "Penalty" });
check("simulate with player_name + detail Penalty -> sc.pdet Penalty, ptid = the scoring (away) team", r.status === 200 && queue[0].body.sc.pdet === "Penalty" && queue[0].body.sc.ptid === A && queue[0].body.sc.pname === "A. Ersan", queue[0] && queue[0].body);
r = await sim({ ...good, player_id: undefined });
check("simulate without a player -> sc null, scd true (no lookup, old behaviour)", r.status === 200 && queue[0].body.sc === null && queue[0].body.scd === true);

console.log = origLog;
process.exit(fail ? 1 : 0);
