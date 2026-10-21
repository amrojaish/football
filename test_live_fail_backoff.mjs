// Live fetch failure pacing (21 Oct 2026). Idle (nothing live): a failed fetch stores KV live_fail and the next attempt waits the normal
// 5-minute idle cadence from the failure (it used to retry every minute, since a failure never rewrites t); the kickoff window still wins.
// Live: a per-minute rate limit gets no 20 s in-request retry; the 30 s second fetch still runs (from the last good copy) and is the retry.
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
globalThis.setTimeout = (fn, ms, ...a) => { if (ms === 30000 || ms === 3000 || ms === 20000) { waits.push(ms); return realSetTimeout(fn, 0, ...a); } return realSetTimeout(fn, ms, ...a); };
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
  seq = []; calls = []; store = {}; puts = []; kickoffs = null; waits.length = 0;
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
  calls = []; puts = []; logs.length = 0; waits.length = 0;
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

// ═══ 2) live: rate limit -> no 20 s retry; the 30 s second fetch still runs ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["rate", [fx("1H", 0, 0, 22)]];
  await tick(w, 1);
  check("live rate limit -> no 20 s wait", !waits.includes(20000), waits);
  check("  second fetch still runs after 30 s (2 live calls: failed first + second)", liveCalls() === 2 && waits.includes(30000), { n: liveCalls(), waits });
  check("  second fetch success writes live and logs ok", puts.some((p) => p.k === "live") && logs.some((l) => l.includes('"live_pull_second"') && l.includes('"ok":true')), { puts, logs });
  check("  no live_fail while live", !("live_fail" in store), Object.keys(store));
}
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["429", "429"];
  await tick(w, 1);
  check("live HTTP 429 twice -> exactly 2 calls (first + second fetch), no 20 s retry in either", liveCalls() === 2 && !waits.includes(20000) && waits.includes(30000), { n: liveCalls(), waits });
  check("  second fetch logged not ok; live payload kept", logs.some((l) => l.includes('"live_pull_second"') && l.includes('"ok":false')) && !puts.some((p) => p.k === "live"), { logs });
  await tick(w, 2);
  check("  next minute (still live in KV) -> fetches again (live keeps every-minute cadence)", liveCalls() >= 1, { n: liveCalls() });
}
reset(); { const w = await loadWorker();
  // other errors while live keep the quick 3 s retry
  store.live = JSON.stringify({ t: nowS() - 60, m: liveRow() });
  seq = ["500", [fx("1H", 0, 0, 22)], [fx("1H", 0, 0, 22)]];
  await tick(w, 1);
  check("live HTTP 500 -> 3 s retry kept (then second fetch): 3 live calls", liveCalls() === 3 && waits.includes(3000) && waits.includes(30000), { n: liveCalls(), waits });
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
