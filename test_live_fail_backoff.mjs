// Live fetch failure pacing (21 Oct 2026). Idle (nothing live): a failed fetch stores KV live_fail and the next attempt waits the normal
// 5-minute idle cadence from the failure (it used to retry every minute, since a failure never rewrites t); the kickoff window still wins.
// Live (24 Oct 2026): a per-minute rate limit gets two in-request retries at ~8 s and ~20 s (+0-3 s jitter); the 30 s second fetch still
// runs (from the last good copy) unless the first fetch ended > 15 s into the run (its retries covered the half minute).
// The 3 s retry for other errors stays. In-memory KV + D1 (node:sqlite, all migrations); waits run at once.
// Run: node --no-warnings test_live_fail_backoff.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_live_fail_backoff_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const waits = [];
const realSetTimeout = globalThis.setTimeout;
// fake clock: every recorded wait advances Date.now by its length (so the 15 s second-fetch cut-off and the 50 s deadline are exercised)
let CLOCK_OFF = 0, BUMP = 0;   // BUMP: extra time added once at the next wait (a slow provider)
const realNow = Date.now;
Date.now = () => realNow() + CLOCK_OFF;
const jit = [];
globalThis.setTimeout = (fn, ms, ...a) => {
  let k = null;
  if (ms === 30000 || ms === 3000 || ms === 20000) k = ms;
  else if (ms >= 8000 && ms < 11000) k = 8000;
  else if (ms >= 12000 && ms < 15000) k = 12000;
  if (k == null) return realSetTimeout(fn, ms, ...a);
  waits.push(k); if (k !== ms) jit.push(ms - k); CLOCK_OFF += ms + BUMP; BUMP = 0;
  return realSetTimeout(fn, 0, ...a);
};
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

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

const H = 4531, A = 4529, FX = 77, LG = 307;
const RATE = { rateLimit: "Too many requests. You have exceeded the limit of requests per minute of your subscription." };
let seq, calls, store, puts, kickoffs;
function reset() {
  seq = []; calls = []; store = {}; puts = []; kickoffs = null; waits.length = 0; jit.length = 0; CLOCK_OFF = 0;
  db.exec("DELETE FROM goal_log; DELETE FROM sent; DELETE FROM ev_sent");
}
const fx = (status, h, a, el) => ({ fixture: { id: FX, status: { short: status, elapsed: el } }, goals: { home: h, away: a }, events: [],
  teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: LG } });
// seq items: an array = OK response; "rate" = errors.rateLimit (HTTP 200); "429" = HTTP 429; "500" = HTTP 500
globalThis.fetch = async (url) => {
  url = String(url);
  calls.push(url);
  const hd = { "x-ratelimit-requests-remaining": "5000" };
  if (url.includes("/fixtures?live=")) {
    const s = seq.length ? seq.shift() : [];
    if (s === "rate") return new Response(JSON.stringify({ errors: RATE, response: [] }), { status: 200, headers: hd });
    if (s === "429") return new Response("{}", { status: 429 });
    if (s === "500") return new Response("{}", { status: 500 });
    return new Response(JSON.stringify({ errors: [], response: s }), { status: 200, headers: hd });
  }
  if (url.includes("/fixtures?ids=")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200, headers: hd });
  if (url === "https://saffara.app/assets/next_kickoffs.json") return kickoffs ? new Response(JSON.stringify(kickoffs), { status: 200 }) : new Response("{}", { status: 404 });
  return new Response("{}", { status: 404 });
};
const KV = {
  get: async (k) => (k in store ? store[k] : null),
  put: async (k, v, o) => { store[k] = v; puts.push({ k, o }); },
  delete: async (k) => { delete store[k]; },
};
const env = { API_KEY: "k", LIVE_KV: KV, DB };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };
async function tick(w, min = 1) {
  calls = []; puts = []; logs.length = 0; waits.length = 0; jit.length = 0;
  const pending = [];
  await w.scheduled({ scheduledTime: Date.UTC(2026, 9, 21, 3, min) }, env, { waitUntil: (p) => pending.push(p) });
  await Promise.all(pending);
}
const liveCalls = () => calls.filter((u) => u.includes("/fixtures?live=")).length;
const nowS = () => Math.floor(Date.now() / 1000);
const liveRow = () => ({ [FX]: { h: 0, a: 0, e: 20, s: "1H", th: H, ta: A, lg: LG } });

// ═══ 1) idle: failure -> live_fail stored, no fetch the next minute, fetch again after 5 min ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 400, m: {} });   // idle, last good fetch > 5 min ago -> fetch due
  seq = ["rate", "rate"];
  await tick(w, 1);
  check("idle rate limit -> two attempts (20 s retry kept while nothing is live)", liveCalls() === 2 && waits.includes(20000), { n: liveCalls(), waits });
  check("  live_fail written (expirationTtl 600), live payload untouched", "live_fail" in store && Math.abs(Number(store.live_fail) - nowS()) <= 2
    && puts.some((p) => p.k === "live_fail" && p.o && p.o.expirationTtl === 600) && !puts.some((p) => p.k === "live"), { store, puts });
  check("  no second fetch while idle", !waits.includes(30000), waits);
  await tick(w, 2);
  check("idle, next minute after the failure -> no fetch (was: every minute)", liveCalls() === 0, { n: liveCalls() });
  store.live_fail = String(nowS() - 240);
  await tick(w, 5);
  check("idle, 4 min after the failure -> still no fetch", liveCalls() === 0, { n: liveCalls() });
  store.live_fail = String(nowS() - 301);
  seq = [[]];
  await tick(w, 6);
  check("idle, > 5 min after the failure -> one fetch, success writes live", liveCalls() === 1 && puts.some((p) => p.k === "live"), { n: liveCalls(), puts });
  await tick(w, 7);
  check("  after that success -> normal idle skip (no fetch)", liveCalls() === 0, { n: liveCalls() });
}
reset(); { const w = await loadWorker();
  // inside a kickoff window the failure backoff does not apply (every-minute polling before kickoff stays)
  const S0 = Math.floor(Date.now() / 1000);
  kickoffs = { t: 1, k: [S0 + 300], f: [] };
  store.live = JSON.stringify({ t: nowS() - 400, m: {} });
  store.live_fail = String(nowS() - 60);
  seq = [[]];
  await tick(w, 10);
  check("idle failure 1 min ago but kickoff in 5 min -> fetch anyway", liveCalls() === 1, { n: liveCalls() });
}
reset(); { const w = await loadWorker();
  // idle success with no prior failure: behaviour unchanged (no live_fail written)
  store.live = JSON.stringify({ t: nowS() - 400, m: {} });
  seq = [[]];
  await tick(w, 1);
  check("idle success -> one fetch, no live_fail key", liveCalls() === 1 && !("live_fail" in store), { n: liveCalls(), store: Object.keys(store) });
}

// ═══ 2) live: rate limit -> retries at ~8 s and ~20 s; the 30 s second fetch only if the first ended within 15 s ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["rate", [fx("1H", 0, 0, 22)], [fx("1H", 0, 0, 22)]];
  await tick(w, 1);
  check("live rate limit then OK -> one 8 s retry (+0-3 s jitter), no 20 s wait", waits[0] === 8000 && !waits.includes(20000)
    && jit.every((j) => j >= 0 && j < 3000), { waits, jit });
  check("  first fetch ended ~8-11 s in (< 15 s) -> second fetch still runs after 30 s (3 live calls)", liveCalls() === 3 && waits.includes(30000), { n: liveCalls(), waits });
  check("  success writes live, no live_pull_fail, no live_fail", puts.some((p) => p.k === "live") && !logs.some((l) => l.includes('"live_pull_fail"')) && !("live_fail" in store), { logs });
}
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["429", "429", [fx("1H", 0, 0, 23)]];
  await tick(w, 1);
  check("live HTTP 429 x2 then OK -> waits 8 s then 12 s (~+20 s), third attempt writes live", JSON.stringify(waits) === "[8000,12000]" && liveCalls() === 3
    && puts.some((p) => p.k === "live"), { n: liveCalls(), waits });
  check("  first fetch ended > 15 s into the run -> no second fetch", !waits.includes(30000) && !logs.some((l) => l.includes('"live_pull_second"')), { waits });
  check("  attempt logs carry the real jittered wait", logs.filter((l) => l.includes('"live_pull_attempt"') && l.includes('"wait_ms"')).length === 2, logs);
}
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["rate", "rate", "rate", "rate"];
  await tick(w, 1);
  check("live rate limit x3 -> exactly 3 calls (no 4th attempt), live_pull_fail logged, live payload kept", liveCalls() === 3
    && logs.some((l) => l.includes('"live_pull_fail"')) && !puts.some((p) => p.k === "live"), { n: liveCalls(), waits });
  check("  no live_fail while live; fresh last good copy (60 s) -> no rescue ids lookup", !("live_fail" in store) && !calls.some((u) => u.includes("ids=")), { calls });
  await tick(w, 2);
  check("  next minute (still live in KV) -> fetches again (live keeps every-minute cadence)", liveCalls() >= 1, { n: liveCalls() });
}
reset(); { const w = await loadWorker();
  // the 50 s run deadline: a retry that would start after it is skipped (logged), never spilling into the next minute
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["rate", "rate", "rate"];
  BUMP = 40000;   // the first 8 s retry lands ~48-51 s into the run: the 12 s retry would start after the 50 s deadline
  await tick(w, 1);
  check("retry past the 50 s run deadline -> skipped and logged (deadline), fetch fails", logs.some((l) => l.includes('"skipped":"deadline"')) && liveCalls() === 2
    && logs.some((l) => l.includes('"live_pull_fail"')) && !waits.includes(12000), { n: liveCalls(), waits, logs });
}
reset(); { const w = await loadWorker();
  // other errors while live keep the quick 3 s retry
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["500", [fx("1H", 0, 0, 22)], [fx("1H", 0, 0, 22)]];
  await tick(w, 1);
  check("live HTTP 500 -> one 3 s retry kept (then second fetch): 3 live calls", liveCalls() === 3 && waits.includes(3000) && waits.includes(30000), { n: liveCalls(), waits });
}
reset(); { const w = await loadWorker();
  // live match + first fetch OK: unchanged (two fetches, no retries)
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = [[fx("1H", 0, 0, 21)], [fx("1H", 0, 0, 21)]];
  await tick(w, 1);
  check("live, both fetches OK -> 2 calls, only the 30 s wait", liveCalls() === 2 && waits.length === 1 && waits[0] === 30000, { n: liveCalls(), waits });
}

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
