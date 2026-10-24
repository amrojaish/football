// Missed-end recovery (24 Oct 2026): replay of 21 Oct 2026 18:52-19:10 UTC, when every live fetch hit the provider's per-minute rate
// limit while EGY 1612267 (2-3, 81') and 1612268 (1-0) finished 3-3 and 2-0 with 90' goals. Before the fix the fixtures?ids lookup
// (finals) was a single unlogged request; the matches stayed pending until GIVEUP_SECS and were then dropped silently -> the 90' goals
// and both FT alerts were never sent.
//   A) live + ids both rate-limited all window, then live recovers with ids still limited -> pending -> past GIVEUP kept in r ->
//      the idle poll's ids lookup finds FT -> late goals 3-3 / 2-0 + FT x2, each exactly once, nothing afterwards.
//   B) live rate-limited but ids OK -> rescue (no success for > 3 min while live) sends the late goals + FT during the outage;
//      the poll that finally succeeds re-reads FT and sends nothing again (sent / ev_sent / unsentGoals).
//   C) live rate limit -> retries at ~8 s and ~20 s with 0-3 s jitter; the first fetch that needed them skips the 30 s second fetch.
// Fake clock (Date.now) advanced by every wait; in-memory KV + D1 (node:sqlite, all migrations); queue messages captured.
// Run: node --no-warnings test_end_recovery.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_end_recovery_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);

let CLOCK = Date.UTC(2026, 9, 21, 18, 47);
Date.now = () => CLOCK;
const waits = [];
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...a) => {
  if (ms >= 1000 && ms <= 30000) { waits.push(ms); CLOCK += ms; return realSetTimeout(fn, 0, ...a); }
  return realSetTimeout(fn, ms, ...a);
};
const worker = (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

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

const F1 = 1612267, F2 = 1612268;
const M1 = { th: 1577, ta: 13822, lg: 233, nh: "Al Ahly", na: "El Qanah" };
const M2 = { th: 14651, ta: 1041, lg: 233, nh: "Haras El Hodood", na: "Ismaily" };
const RATE = { rateLimit: "Too many requests. You have exceeded the limit of requests per minute of your subscription." };
let store, calls, queue, logs, liveMode, idsMode;
const hd = { "x-ratelimit-requests-remaining": "6000" };
const fxRow = (id, M, s, h, a, el) => ({ fixture: { id, status: { short: s, elapsed: el } }, goals: { home: h, away: a }, events: [],
  teams: { home: { id: M.th, name: M.nh }, away: { id: M.ta, name: M.na } }, league: { id: M.lg } });
globalThis.fetch = async (url) => {
  url = String(url);
  calls.push({ url, t: CLOCK });
  if (url.includes("/fixtures?live=")) {
    if (liveMode === "rate") return new Response(JSON.stringify({ errors: RATE, response: [] }), { status: 200, headers: hd });
    return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200, headers: hd });   // both matches gone from the live list
  }
  if (url.includes("/fixtures?ids=")) {
    if (idsMode === "rate") return new Response("{}", { status: 429 });
    const fin = idsMode === "ft";
    return new Response(JSON.stringify({ errors: [], response: [
      fxRow(F1, M1, fin ? "FT" : "2H", fin ? 3 : 2, 3, 90), fxRow(F2, M2, fin ? "FT" : "2H", fin ? 2 : 1, 0, 90)] }), { status: 200, headers: hd });
  }
  return new Response("{}", { status: 404 });
};
const KV = {
  get: async (k) => (k in store ? store[k] : null),
  put: async (k, v) => { store[k] = v; },
  delete: async (k) => { delete store[k]; },
};
const GOAL_QUEUE = { send: async (body) => { queue.push(body); } };
const env = { API_KEY: "k", LIVE_KV: KV, DB, GOAL_QUEUE, GOAL_PUSH: "on", VAPID_PUBLIC_KEY: "p", VAPID_PRIVATE_KEY: "q" };
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };
const J = () => logs.map((l) => { try { return JSON.parse(l); } catch (e) { return {}; } });

function reset() {
  store = {}; calls = []; queue = []; logs = []; waits.length = 0;
  db.exec("DELETE FROM goal_log; DELETE FROM sent; DELETE FROM ev_sent");
  // what D1 held on 21 Oct at 18:51: goals up to 2-3 / 1-0 sent, ko/ht/sh alerts sent
  for (const [f, h, a] of [[F1, 1, 0], [F1, 1, 1], [F1, 2, 1], [F1, 2, 2], [F1, 2, 3], [F2, 1, 0]]) db.prepare("INSERT INTO sent (fixture, h, a) VALUES (?, ?, ?)").run(f, h, a);
  for (const f of [F1, F2]) for (const k of ["ko", "ht", "sh"]) db.prepare("INSERT INTO ev_sent (fixture, kind, k, ts) VALUES (?, ?, '', 0)").run(f, k);
  // last good live copy: 18:51
  store.live = JSON.stringify({ t: Date.UTC(2026, 9, 21, 18, 51) / 1000, ve: 1, m: {
    [F1]: { h: 2, a: 3, e: 86, s: "2H", ...M1 }, [F2]: { h: 1, a: 0, e: 88, s: "2H", ...M2 } } });
}
// one cron run at hh:mm:22 UTC (the real runs fired ~22 s past the minute)
async function tick(hh, mm) {
  CLOCK = Date.UTC(2026, 9, 21, hh, mm, 22);
  const pending = [];
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 21, hh, mm) }, env, { waitUntil: (p) => pending.push(p) });
  await Promise.all(pending);
}
const minutes = (h1, m1, h2, m2) => { const out = []; for (let t = h1 * 60 + m1; t <= h2 * 60 + m2; t++) out.push([Math.floor(t / 60), t % 60]); return out; };
const goalMsgs = () => queue.filter((q) => q.kind === "goal");
const ftMsgs = () => queue.filter((q) => q.kind === "alert" && q.evt === "ft");
const rows = (sql, ...a) => db.prepare(sql).all(...a);

// ═══ A) the 10-21 shape: ids also rate-limited; live recovers at 19:11 ═══
reset();
liveMode = "rate"; idsMode = "rate";
for (const [h, m] of minutes(18, 52, 19, 10)) await tick(h, m);
check("A: 18:52-19:10 everything rate-limited -> nothing sent, live copy untouched", queue.length === 0 && JSON.parse(store.live).t === Date.UTC(2026, 9, 21, 18, 51) / 1000, queue);
check("A:   rescue lookups started once the last success (18:51:00) was > 3 min old (18:54:22 run), one per minute (17), failures logged (finals_fail)",
  J().filter((x) => x.type === "final_rescue").length === 17 && J().some((x) => x.type === "finals_fail")
  && calls.filter((c) => c.url.includes("ids=")).length > 0, J().filter((x) => x.type === "final_rescue").length);
liveMode = "ok";
for (const [h, m] of minutes(19, 11, 19, 21)) await tick(h, m);
const sA = JSON.parse(store.live);
check("A: live back but ids still limited until past GIVEUP (10 min) -> moved to r with the last known score, still nothing sent",
  queue.length === 0 && sA.r && sA.r[F1] && sA.r[F1].o.h === 2 && sA.r[F1].o.a === 3 && sA.r[F2].o.h === 1 && !Object.keys(sA.m).length, sA);
idsMode = "ft";
for (const [h, m] of minutes(19, 22, 19, 45)) await tick(h, m);
const g1 = goalMsgs();
check("A: the idle poll's ids lookup finds FT -> late goals 3-3 (home) and 2-0 (home), each exactly once",
  g1.length === 2 && g1.some((q) => q.fixture === F1 && q.h === 3 && q.a === 3 && q.ph === 2 && q.side === "home")
  && g1.some((q) => q.fixture === F2 && q.h === 2 && q.a === 0 && q.side === "home"), g1);
check("A:   FT alerts for both, exactly once, final scores", ftMsgs().length === 2 && ftMsgs().some((q) => q.fixture === F1 && q.h === 3 && q.a === 3)
  && ftMsgs().some((q) => q.fixture === F2 && q.h === 2 && q.a === 0), ftMsgs());
check("A:   D1: sent has 3-3 / 2-0 once, ev_sent ft once each, goal_log one late row each",
  rows("SELECT * FROM sent WHERE (fixture=? AND h=3 AND a=3) OR (fixture=? AND h=2 AND a=0)", F1, F2).length === 2
  && rows("SELECT * FROM ev_sent WHERE kind='ft'").length === 2 && rows("SELECT * FROM goal_log").length === 2, rows("SELECT * FROM goal_log"));
const sA2 = JSON.parse(store.live);
check("A:   r cleared, f holds both finals", !sA2.r && sA2.f && sA2.f[F1].h === 3 && sA2.f[F2].h === 2, sA2);

// ═══ B) ids OK during the outage: rescue sends while the live feed is still rate-limited ═══
reset();
liveMode = "rate"; idsMode = "2h";
for (const [h, m] of minutes(18, 52, 18, 57)) await tick(h, m);
check("B: rescue lookups while the matches are still 2H -> nothing sent", queue.length === 0, queue);
idsMode = "ft";
for (const [h, m] of minutes(18, 58, 19, 10)) await tick(h, m);
check("B: FT seen by the 18:58 rescue -> late goals 3-3 and 2-0 + FT x2, sent during the outage, once",
  goalMsgs().length === 2 && ftMsgs().length === 2 && queue.every((q) => q.ts <= Date.UTC(2026, 9, 21, 18, 59)), queue.map((q) => [q.kind, q.evt, q.fixture, q.h, q.a, new Date(q.ts).toISOString()]));
liveMode = "ok";
for (const [h, m] of minutes(19, 11, 19, 30)) await tick(h, m);
check("B: the live poll that finally succeeds re-reads FT -> no duplicate goal or FT message", goalMsgs().length === 2 && ftMsgs().length === 2, queue.length);
check("B:   D1 rows once (sent 3-3/2-0, ft x2, goal_log 2)", rows("SELECT * FROM ev_sent WHERE kind='ft'").length === 2 && rows("SELECT * FROM goal_log").length === 2
  && rows("SELECT * FROM sent WHERE fixture=? AND h=3 AND a=3", F1).length === 1, rows("SELECT * FROM goal_log"));
check("B:   final payload: matches out of m, f set, no r/g", (() => { const s = JSON.parse(store.live); return !Object.keys(s.m).length && s.f && s.f[F1] && !s.r && !s.g; })(), store.live);

// ═══ C) retry timing inside one run ═══
reset();
liveMode = "rate"; idsMode = "2h";
store.live = JSON.stringify({ t: Date.UTC(2026, 9, 21, 18, 51) / 1000, ve: 1, m: { [F1]: { h: 2, a: 3, e: 86, s: "2H", ...M1 } } });
waits.length = 0; calls = [];
await tick(18, 52);
const liveCalls = calls.filter((c) => c.url.includes("live="));
const t1 = Date.UTC(2026, 9, 21, 18, 52, 22);
check("C: live rate limit -> 3 attempts at +0, +8..11 s, +20..26 s (jitter 0-3 s each)",
  liveCalls.length === 3 && liveCalls[1].t - t1 >= 8000 && liveCalls[1].t - t1 < 11000 && liveCalls[2].t - liveCalls[1].t >= 12000 && liveCalls[2].t - liveCalls[1].t < 15000,
  liveCalls.map((c) => c.t - t1));
check("C:   first fetch needed its retries (> 15 s) -> no 30 s second fetch", !waits.includes(30000) && !J().some((x) => x.type === "live_pull_second"), waits);

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
