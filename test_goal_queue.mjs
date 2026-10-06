// Goal fan-out through Cloudflare Queues: 1000 fake subscribers, retries without duplicates, pagination,
// TTL, GOAL_PUSH=off, /push/test cap. In-memory queue + D1 shim (node:sqlite) + mock push services. No network.
// Run: node --no-warnings test_goal_queue.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_goalqueue_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0004_goal_log.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => { hook(sql); return { results: db.prepare(sql).all(...args) }; },
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
let hook = () => {};
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const b64u = (u) => Buffer.from(u).toString("base64url");
const vkp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const VAPID_PUBLIC_KEY = b64u(await crypto.subtle.exportKey("raw", vkp.publicKey));
const VAPID_PRIVATE_KEY = (await crypto.subtle.exportKey("jwk", vkp.privateKey)).d;
const ekp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
const P256DH = b64u(await crypto.subtle.exportKey("raw", ekp.publicKey));
const AUTH = b64u(crypto.getRandomValues(new Uint8Array(16)));

const A = 4531, B = 4529, FX = 77;
const ep = (i) => `https://fcm.googleapis.com/fcm/send/s${String(i).padStart(5, "0")}`;
function seed(n, teamsOf) {
  db.exec("DELETE FROM subscriptions; DELETE FROM sub_teams; DELETE FROM sent");
  db.exec("BEGIN");
  const si = db.prepare("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)"), ti = db.prepare("INSERT INTO sub_teams VALUES (?,?)");
  for (let i = 0; i < n; i++) {
    si.run(ep(i), P256DH, AUTH, i % 2 ? "en" : "ar", 1, 1);
    for (const t of teamsOf(i)) ti.run(ep(i), t);
  }
  db.exec("COMMIT");
}

// ── mocks ──
let live, hits, behave, queue, sends, sendFail, namesBody = null;
function reset() { live = []; hits = new Map(); behave = () => 201; queue = []; sends = 0; sendFail = null; hook = () => {}; }
const fx = (h, a, el) => ({
  fixture: { id: FX, status: { short: "2H", elapsed: el } }, goals: { home: h, away: a },
  teams: { home: { id: A, name: "Al Faisaly" }, away: { id: B, name: "Al Wehdat" } }, league: { id: 387 },
});
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) return new Response(JSON.stringify({ errors: [], response: live }), { status: 200 });
  if (url === "https://saffara.app/assets/team_names.json")
    return namesBody ? new Response(JSON.stringify(namesBody), { status: 200 }) : new Response("{}", { status: 404 });
  if (url.startsWith("https://fcm.googleapis.com/")) {
    const n = (hits.get(url) || 0) + 1; hits.set(url, n);
    const st = behave(url, n);
    if (st === "throw") throw new Error("network");
    return new Response(null, { status: st });
  }
  return new Response("{}", { status: 404 });
};
const QUEUE = { send: async (body, opts) => { if (sendFail && sendFail()) throw new Error("queue down"); sends++; queue.push({ body, opts }); } };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const NOW = Math.floor(Date.now() / 1000);
const entry = (h, a) => ({ h, a, e: 33, s: "2H", th: A, ta: B, lg: 387, nh: "Al Faisaly", na: "Al Wehdat" });
const mkEnv = (extra = {}) => ({ API_KEY: "k", LIVE_KV: { get: async () => JSON.stringify({ t: NOW - 3600, m: { [FX]: entry(0, 0) } }), put: async () => {} },
  DB, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on", GOAL_QUEUE: QUEUE, ...extra });
async function produce(env, h = 1, a = 0) {
  live = [fx(h, a, 34)];
  logs.length = 0;
  await (await loadWorker()).scheduled({}, env, {});
}
// run the consumer like the queue does: ack on return, retry (re-deliver same body) on throw
async function consume(worker, env, { maxRetries = 5, stopAfter = 500 } = {}) {
  let n = 0, retried = 0;
  while (queue.length && n++ < stopAfter) {
    const { body } = queue.shift();
    let tries = 0;
    for (;;) {
      let threw = false;
      await worker.queue({ messages: [{ body, ack() {}, retry() { threw = true; } }] }, env);
      if (!threw || ++tries > maxRetries) break;
      retried++;
    }
  }
  return { processed: n, retried };
}
const consumerLines = () => logs.map((l) => JSON.parse(l)).filter((l) => l.type === "goal_push" && !l.queued);
const succeeded = () => [...hits.keys()].filter((k) => k.includes("/s"));

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) 1000 subscribers: ONE queued message, every subscriber gets exactly one push (no 40 cap), 5 pages of 200
{
  reset();
  seed(1000, (i) => (i % 10 < 6 ? [A] : i % 10 < 9 ? [B] : [A, B]));   // 60% A, 30% B, 10% both
  const env = mkEnv(); const w = await loadWorker();
  await produce(env);
  check("goal -> exactly ONE message on the queue", sends === 1 && queue.length === 1, sends);
  const m = queue[0].body;
  check("  message fields {fixture,kind,th,ta,h,a,minute,offset} (+ts,nh,na)",
    m.fixture === FX && m.kind === "goal" && m.th === A && m.ta === B && m.h === 1 && m.a === 0 && m.minute === 34 && m.offset === 0 && typeof m.ts === "number" && m.nh === "Al Faisaly", m);
  const t0 = Date.now();
  const r = await consume(w, env);
  const perEp = [...hits.values()];
  check("every one of the 1000 subscribers got exactly one push (incl. both-teams followers)", hits.size === 1000 && perEp.every((x) => x === 1), [hits.size, Math.max(...perEp)]);
  check("  5 pages (offsets 0,200,..,800), 200 sent each", JSON.stringify(consumerLines().map((l) => [l.offset, l.sent])) === JSON.stringify([[0, 200], [200, 200], [400, 200], [600, 200], [800, 200]]), consumerLines().map((l) => [l.offset, l.sent]));
  check("  log lines carry {fixture,offset,sent,gone,failed}", consumerLines().every((l) => l.fixture === FX && "offset" in l && "sent" in l && "gone" in l && "failed" in l && l.failed === 0 && l.gone === 0), consumerLines()[0]);
  origLog(`   (1000 pushes encrypted+sent in ${Date.now() - t0} ms)`);
  // the same goal again (duplicate poll): nothing new queued
  queue = []; sends = 0; hits.clear();
  await produce(env);
  check("  same score seen again -> no new queue message (sent table dedupe)", sends === 0 && hits.size === 0, sends);
}

// 2) transient failures retry ONLY the failed subscribers; delivered ones are never re-sent
{
  reset();
  seed(150, () => [A]);
  const bad = new Set([5, 77, 100, 120, 149].map(ep));
  behave = (url, n) => (bad.has(url) && n === 1 ? 503 : 201);   // fails once, then fine
  const env = mkEnv(); const w = await loadWorker();
  await produce(env); await consume(w, env);
  const counts = [...hits.entries()];
  check("failed ones retried once; the other 145 got exactly one request", counts.every(([u, n]) => (bad.has(u) ? n === 2 : n === 1)) && hits.size === 150, counts.filter(([u, n]) => n !== (bad.has(u) ? 2 : 1)).slice(0, 3));
  const ls = consumerLines();
  check("  log shows retrying:5 on the first page then a retry line sent:5", ls[0].failed === 5 && ls[0].retrying === 5 && ls[0].sent === 145 && ls[1].attempt === 1 && ls[1].sent === 5, ls);
  const retryMsgs = sends;   // 1 original + 1 only-retry
  check("  retry went through the queue (with a delay)", retryMsgs === 2, retryMsgs);
}
{
  reset();
  seed(50, () => [A]);
  const bad = ep(3);
  behave = (url) => (url === bad ? 500 : 201);   // never recovers
  const env = mkEnv(); const w = await loadWorker();
  await produce(env); await consume(w, env);
  check("a subscriber that never recovers: tried 1 + 3 retries then stopped; others once", hits.get(bad) === 4 && [...hits].filter(([u]) => u !== bad).every(([, n]) => n === 1), [...hits].filter(([u, n]) => n > 1));
  const last = consumerLines().at(-1);
  check("  final attempt logged (attempt 3, failed 1, retrying 0)", last.attempt === 3 && last.failed === 1 && last.retrying === 0, last);
}
{
  reset();
  seed(40, () => [A]);
  behave = (url) => (url === ep(7) ? 400 : url === ep(8) ? "throw" : 201);
  const env = mkEnv(); const w = await loadWorker();
  await produce(env); await consume(w, env);
  check("permanent 4xx (400) is NOT retried; a network error IS", hits.get(ep(7)) === 1 && hits.get(ep(8)) === 4, [hits.get(ep(7)), hits.get(ep(8))]);
}

// 3) consumer crashes BEFORE sending (D1 hiccup / next-page enqueue fails) -> queue retries -> still exactly once
{
  reset();
  seed(450, () => [A]);
  const env = mkEnv(); const w = await loadWorker();
  await produce(env);
  let throws = 1;
  hook = (sql) => { if (sql.includes("FROM subscriptions") && throws-- > 0) throw new Error("D1 hiccup"); };
  const r = await consume(w, env);
  check("D1 error on the first page -> message retried by the queue, nothing duplicated", r.retried === 1 && hits.size === 450 && [...hits.values()].every((n) => n === 1), [r, hits.size]);
  reset(); seed(450, () => [A]);
  await produce(env);
  let q = 1; sendFail = () => q-- > 0;   // the NEXT-page enqueue fails once
  const r2 = await consume(w, env);
  check("enqueue of the next page fails -> retried BEFORE any send; no duplicate, no skipped page", r2.retried === 1 && hits.size === 450 && [...hits.values()].every((n) => n === 1), [r2, hits.size]);
}

// 4) gone subscriptions (410) are deleted and do NOT shift pagination (keyset cursor, not numeric offset)
{
  reset();
  seed(450, () => [A]);
  const gone = new Set(Array.from({ length: 60 }, (_, i) => ep(10 + i)));   // all inside page 1
  behave = (url) => (gone.has(url) ? 410 : 201);
  const env = mkEnv(); const w = await loadWorker();
  await produce(env); await consume(w, env);
  const left = db.prepare("SELECT COUNT(*) c FROM subscriptions").get().c;
  check("60 x 410 -> deleted; the other 390 each got one push, none skipped", hits.size === 450 && left === 390 && [...hits].filter(([u]) => !gone.has(u)).every(([, n]) => n === 1), [hits.size, left]);
  check("  page 1 log shows gone:60", consumerLines()[0].gone === 60 && consumerLines()[0].sent === 140, consumerLines()[0]);
}

// 5) GOAL_PUSH != on -> nothing queued; consumer is a no-op even if a message exists
for (const val of ["off", undefined, ""]) {
  reset();
  seed(100, () => [A]);
  const env = mkEnv({ GOAL_PUSH: val });
  await produce(env);
  check(`GOAL_PUSH=${JSON.stringify(val)} -> zero messages on the queue, zero pushes`, sends === 0 && hits.size === 0 && db.prepare("SELECT COUNT(*) c FROM sent").get().c === 0, [sends, hits.size]);
}
{
  reset(); seed(10, () => [A]);
  const env = mkEnv({ GOAL_PUSH: "off" }); const w = await loadWorker();
  await w.queue({ messages: [{ body: { fixture: FX, kind: "goal", th: A, ta: B, h: 1, a: 0, minute: 3, offset: 0, ts: Date.now() }, ack() {}, retry() {} }] }, env);
  check("a leftover message is not sent once the switch is off", hits.size === 0);
}

// 6) TTL: a message older than 10 minutes is never sent
{
  reset(); seed(100, () => [A]);
  const env = mkEnv(); const w = await loadWorker();
  logs.length = 0;
  await w.queue({ messages: [{ body: { fixture: FX, kind: "goal", th: A, ta: B, h: 1, a: 0, minute: 3, offset: 0, ts: Date.now() - 11 * 60 * 1000 }, ack() {}, retry() {} }] }, env);
  check("11-minute-old goal message -> expired, nothing sent", hits.size === 0 && consumerLines()[0].expired === true, consumerLines());
  logs.length = 0;
  await w.queue({ messages: [{ body: { fixture: FX, kind: "goal", th: A, ta: B, h: 1, a: 0, minute: 3, offset: 0, ts: Date.now() - 9 * 60 * 1000 }, ack() {}, retry() {} }] }, env);
  check("  9-minute-old message still goes out", hits.size === 100, hits.size);
}

// 7) VAR cancel goes through the same queue with kind=cancel
{
  reset(); seed(30, () => [B]);
  const env = mkEnv({ LIVE_KV: { get: async () => JSON.stringify({ t: NOW - 3600, m: { [FX]: entry(1, 0) } }), put: async () => {} } });
  live = [fx(0, 0, 36)]; logs.length = 0;
  await (await loadWorker()).scheduled({}, env, {});
  check("cancel -> one queue message kind=cancel", sends === 1 && queue[0].body.kind === "cancel" && queue[0].body.h === 0, queue[0] && queue[0].body);
  await consume(await loadWorker(), env);
  check("  all 30 followers of the other club notified once", hits.size === 30, hits.size);
}

// 8) /push/test stays capped at SEND_CAP (40)
{
  reset(); seed(60, () => [A]);
  const ADMIN = "t".repeat(32);
  const w = await loadWorker();
  const res = await w.fetch(new Request("https://w.example/push/test", { method: "POST",
    headers: { Authorization: "Bearer " + ADMIN, "Content-Type": "application/json" },
    body: JSON.stringify({ team_id: A, title: "x", body: "y" }) }), mkEnv({ ADMIN_TOKEN: ADMIN }));
  const j = await res.json();
  check("/push/test is still limited: 40 sent, capped:true", j.sent === 40 && j.capped === true && hits.size === 40, j);
}

// 9) no queue binding: the failure is visible, nothing crashes
{
  reset(); seed(10, () => [A]);
  const env = mkEnv(); delete env.GOAL_QUEUE;
  await produce(env);
  const l = logs.map((x) => JSON.parse(x)).find((x) => x.type === "goal_push");
  check("missing GOAL_QUEUE binding -> logged (error:no_queue), no throw", l && l.error === "no_queue", l);
}


// 10) POST /push/simulate: admin-only, same real queue, never touches `sent` or KV
{
  const ADMIN = "t".repeat(32);
  const cpsOf = (x) => Array.from(x, (c) => c.codePointAt(0).toString(16)).join(" ");
  let kvPuts = 0;
  const envS = () => mkEnv({ ADMIN_TOKEN: ADMIN, LIVE_KV: { get: async () => null, put: async () => { kvPuts++; } } });
  const sim = async (body, env, auth = "Bearer " + ADMIN, method = "POST") => (await loadWorker()).fetch(new Request("https://w.example/push/simulate",
    { method, headers: { Authorization: auth, "Content-Type": "application/json" }, ...(method === "POST" ? { body: JSON.stringify(body) } : {}) }), env);
  const good = { fixture: 1643360, th: 4535, ta: A, h: 0, a: 1, minute: 34, kind: "goal" };
  reset();
  seed(5, () => [A]);
  db.prepare("INSERT INTO sent VALUES (1643360, 0, 1), (1643360, 3, 3), (99, 1, 0)").run();
  const envx = envS();
  check("no / wrong Bearer -> 401, nothing queued", (await sim(good, envx, "")).status === 401 && (await sim(good, envx, "Bearer nope")).status === 401 && sends === 0);
  check("GET -> 405", (await sim(null, envx, "Bearer " + ADMIN, "GET")).status === 405);
  const bad = [{ ...good, th: 1 }, { ...good, kind: "x" }, { ...good, minute: 500 }, { ...good, h: -1 }, { ...good, fixture: 0 }, { ...good, a: "1" }, {}];
  const codes2 = []; for (const b of bad) codes2.push((await sim(b, envx)).status);
  check("bad input (unknown team / kind / minute / score / fixture / type) -> 400, nothing queued", codes2.every((c) => c === 400) && sends === 0, codes2);
  check("GOAL_PUSH off -> 409, nothing queued", (await sim(good, mkEnv({ ADMIN_TOKEN: ADMIN, GOAL_PUSH: "off" }))).status === 409 && sends === 0);
  const sentBefore = JSON.stringify(db.prepare("SELECT * FROM sent ORDER BY fixture,h,a").all());
  namesBody = { 4535: { ar: "السلط", en: "Al-Salt" }, [A]: { ar: "الفيصلي", en: "Al-Faisaly" } };
  const r = await sim(good, envx);
  const j = await r.json();
  check("valid goal -> 200 queued, ONE message with sim:true + ts", r.status === 200 && j.queued === true && sends === 1 && queue[0].body.sim === true && typeof queue[0].body.ts === "number" && queue[0].body.kind === "goal", [r.status, queue[0] && queue[0].body]);
  logs.length = 0;
  await consume(await loadWorker(), envx);
  const line = consumerLines()[0];
  check("  consumer sends to the club's subscribers; log line carries sim:true {fixture,offset,sent,gone,failed}", line && line.sim === true && line.fixture === 1643360 && line.sent === 5 && line.failed === 0 && line.gone === 0 && line.offset === 0, line);
  const rc = await sim({ ...good, h: 0, a: 0, kind: "cancel" }, envx);
  await consume(await loadWorker(), envx);
  check("cancel simulate -> queued kind=cancel and delivered", rc.status === 200 && consumerLines().some((l) => l.sim && l.kind === "cancel" && l.sent === 5), consumerLines());
  check("`sent` table untouched (even by a simulated cancel) and no KV write", JSON.stringify(db.prepare("SELECT * FROM sent ORDER BY fixture,h,a").all()) === sentBefore && kvPuts === 0, [sentBefore, kvPuts]);
  check("a real goal for the same fixture is unaffected by simulations (dedupe row still there)", db.prepare("SELECT COUNT(*) c FROM sent WHERE fixture = 1643360 AND h = 0 AND a = 1").get().c === 1);
  namesBody = null;
}

console.log = origLog;
process.exit(fail ? 1 : 0);
