// 30 s second live fetch (19 Oct 2026): inside the same cron run via ctx.waitUntil, only while the first fetch's result has a match the
// provider still reports live; it reuses the first result from memory (no KV read). Goal/status detection runs on both fetches with the
// existing sent/ev_sent dedupe; reminders, operator alerts, the lineup poll and dispatch stay on the first fetch. Feed + cron KV reads
// use cacheTtl 30. In-memory KV chained across ticks, in-memory D1 (node:sqlite, all migrations); the 30 s wait runs at once.
// Run: node --no-warnings test_second_pull.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_second_pull_test.mjs");
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
let seq, calls, store, gets, puts, kickoffs;
function reset() {
  seq = []; calls = []; store = {}; gets = []; puts = []; kickoffs = null; waits.length = 0;
  db.exec("DELETE FROM goal_log; DELETE FROM sent; DELETE FROM ev_sent");
}
const fx = (status, h, a, el) => ({ fixture: { id: FX, status: { short: status, elapsed: el } }, goals: { home: h, away: a }, events: [],
  teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: LG } });
globalThis.fetch = async (url) => {
  url = String(url);
  calls.push(url);
  const hd = { "x-ratelimit-requests-remaining": "5000" };
  if (url.includes("/fixtures?live=")) return new Response(JSON.stringify({ errors: [], response: seq.length ? seq.shift() : [] }), { status: 200, headers: hd });
  if (url.includes("/fixtures?ids=")) return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200, headers: hd });
  if (url === "https://saffara.app/assets/next_kickoffs.json") return kickoffs ? new Response(JSON.stringify(kickoffs), { status: 200 }) : new Response("{}", { status: 404 });
  return new Response("{}", { status: 404 });
};
const KV = {
  get: async (k, opts) => { gets.push({ k, opts }); return k in store ? store[k] : null; },
  put: async (k, v) => { store[k] = v; puts.push(k); },
  delete: async (k) => { delete store[k]; },
};
const env = { API_KEY: "k", LIVE_KV: KV, DB };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };
// one cron tick at minute `min`; returns how many waitUntil promises were registered
async function tick(w, min = 1) {
  calls = []; gets = []; puts = []; logs.length = 0; waits.length = 0;
  const pending = [];
  await w.scheduled({ scheduledTime: Date.UTC(2026, 9, 19, 14, min) }, env, { waitUntil: (p) => pending.push(p) });
  await Promise.all(pending);
  return pending.length;
}
const liveCalls = () => calls.filter((u) => u.includes("/fixtures?live=")).length;
const nowS = () => Math.floor(Date.now() / 1000);

// ═══ 1) live match -> second fetch 30 s later, from memory ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: { [FX]: { h: 0, a: 0, e: 20, s: "1H", th: H, ta: A, lg: LG } } });
  seq = [[fx("1H", 0, 0, 21)], [fx("1H", 0, 0, 21)]];
  await tick(w);
  check("live -> two live fetches in the run, the second after a 30 s wait", liveCalls() === 2 && waits.includes(30000), { n: liveCalls(), waits });
  check("  live KV read once (cron, cacheTtl 30); the second fetch used the first result from memory",
    gets.filter((g) => g.k === "live").length === 1 && gets.find((g) => g.k === "live").opts && gets.find((g) => g.k === "live").opts.cacheTtl === 30, gets);
  check("  KV live written twice (each fetch)", puts.filter((k) => k === "live").length === 2, puts);
  check("  live_pull_second logged ok", logs.some((l) => l.includes('"live_pull_second"') && l.includes('"ok":true')));
}

// ═══ 2) idle / nothing live -> no second fetch ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 400, m: {} });   // idle, last fetch > 5 min ago -> one fetch
  seq = [[]];
  await tick(w);
  check("idle (empty result) -> exactly one live fetch, no 30 s wait", liveCalls() === 1 && !waits.includes(30000), { n: liveCalls(), waits });
  store.live = JSON.stringify({ t: nowS() - 60, m: {} });
  await tick(w);
  check("idle inside the 5-minute window -> no fetch at all, no second fetch", liveCalls() === 0 && !waits.includes(30000), { n: liveCalls(), waits });
}
reset(); { const w = await loadWorker();
  // the match just dropped out of the live list and waits for its final status (carried in m with g): not live -> no second fetch
  store.live = JSON.stringify({ t: nowS() - 60, m: { [FX]: { h: 1, a: 0, e: 90, s: "2H", th: H, ta: A, lg: LG } } });
  seq = [[]];
  await tick(w);
  check("match pending its final status (carried, g) -> no second fetch", liveCalls() === 1 && !waits.includes(30000), { n: liveCalls(), waits });
}

// ═══ 3) no duplicate alerts ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: nowS() - 60, m: { [FX]: { h: 0, a: 0, e: 20, s: "1H", th: H, ta: A, lg: LG } } });
  seq = [[fx("1H", 0, 0, 21)], [fx("1H", 1, 0, 21)]];    // goal seen by the SECOND fetch
  await tick(w);
  const g1 = db.prepare("SELECT COUNT(*) c FROM goal_log WHERE fixture = ? AND kind = 'goal'").get(FX).c;
  check("goal seen by the second fetch -> logged once, KV live now 1-0", g1 === 1 && JSON.parse(store.live).m[FX].h === 1, { g1 });
  seq = [[fx("1H", 1, 0, 22)], [fx("1H", 1, 0, 22)]];    // next minute, same score on both fetches
  await tick(w, 2);
  const g2 = db.prepare("SELECT COUNT(*) c FROM goal_log WHERE fixture = ? AND kind = 'goal'").get(FX).c;
  check("  next minute (both fetches 1-0) -> still exactly one goal row (no re-detection)", g2 === 1, { g2 });
  seq = [[fx("1H", 2, 0, 23)], [fx("1H", 2, 0, 23)]];    // goal seen by the FIRST fetch, second sees the same
  await tick(w, 3);
  const g3 = db.prepare("SELECT COUNT(*) c FROM goal_log WHERE fixture = ? AND kind = 'goal'").get(FX).c;
  check("goal seen by the first fetch, same score on the second -> one more row only (2 total)", g3 === 2, { g3 });
}

// ═══ 4) first fetch only: lineup poll / reminders read the kick-offs file once ═══
reset(); { const w = await loadWorker();
  const S0 = Math.floor(Date.UTC(2026, 9, 19, 14, 5) / 1000);
  kickoffs = { t: 1, k: [S0 + 1800], f: [[S0 + 1800, 99, H, A, LG, "x", "y"]] };
  store.live = JSON.stringify({ t: nowS() - 60, m: { [FX]: { h: 0, a: 0, e: 20, s: "1H", th: H, ta: A, lg: LG } } });
  seq = [[fx("1H", 0, 0, 21)], [fx("1H", 0, 0, 21)]];
  await tick(w, 5);
  check("lineup poll (fixtures?ids) made once even with the second live fetch", calls.filter((u) => u.includes("/fixtures?ids=99")).length === 1 && liveCalls() === 2,
    { ids: calls.filter((u) => u.includes("fixtures?ids")), live: liveCalls() });
}

// ═══ 5) feed endpoint reads KV with cacheTtl 30, response no-store ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: 1, m: {} });
  const r = await w.fetch(new Request("https://x/"), env);
  const g = gets.find((x) => x.k === "live");
  check("GET / (live feed) -> KV get cacheTtl 30, Cache-Control no-store", g && g.opts && g.opts.cacheTtl === 30 && r.headers.get("Cache-Control") === "no-store", [g, r.headers.get("Cache-Control")]);
}

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
