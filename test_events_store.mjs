// Live events after full time (19 Oct 2026): KV ev:<id> (36 h) written only when a live fixture's compact event list changes, plus a
// final copy (ft: 1) from the finals() fixtures?ids= reply the worker already makes; GET /events?id=. Zero extra provider requests.
// In-memory KV chained across polls (prev = what the last poll wrote), in-memory D1 shim (node:sqlite, all migrations).
// Run: node --no-warnings test_events_store.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_events_store_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
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
let live, finalsResp, remaining, apiCalls, store, puts;
function reset() { live = []; finalsResp = []; remaining = "5000"; apiCalls = []; store = {}; puts = []; }
const ev = (min, type, detail, team, pid, player, aid = null, assist = null) =>
  ({ time: { elapsed: min, extra: null }, team: { id: team }, player: { id: pid, name: player }, assist: { id: aid, name: assist }, type, detail, comments: null });
const fxObj = (status, h, a, el, events) => ({
  fixture: { id: FX, status: { short: status, elapsed: el } }, goals: { home: h, away: a }, events,
  teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: LG },
});
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) {
    apiCalls.push(url);
    const headers = { "x-ratelimit-requests-remaining": remaining };
    if (url.includes("fixtures?ids=")) return new Response(JSON.stringify({ errors: [], response: finalsResp }), { status: 200, headers });
    return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers });
  }
  return new Response("{}", { status: 404 });
};
const KV = {
  get: async (k) => (k in store ? store[k] : null),
  put: async (k, v, opts) => { store[k] = v; puts.push({ k, v, opts }); },
  delete: async (k) => { delete store[k]; },
};
const env = { API_KEY: "k", LIVE_KV: KV, DB };
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };
async function poll(w) { puts = []; apiCalls = []; logs.length = 0; await w.scheduled({ scheduledTime: Date.UTC(2026, 9, 19, 12, 1) }, env, {}); }
const evPuts = () => puts.filter((p) => p.k === "ev:" + FX);
const stored = () => JSON.parse(store["ev:" + FX]);

const G1 = ev(10, "Goal", "Normal Goal", H, 101, "Y. Thalji", 102, "A. Ersan");
const C1 = ev(30, "Card", "Yellow Card", A, 201, "M. Abu");
const S1 = ev(55, "subst", "Substitution 1", H, 103, "Out Guy", 104, "In Guy");
const V1 = ev(60, "Var", "Goal cancelled", A, null, null);

// ═══ 1) live: write only when the list changes ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: Math.floor(Date.now() / 1000) - 60, m: { [FX]: { h: 0, a: 0, e: 5, s: "1H", th: H, ta: A, lg: LG } } });
  live = [fxObj("1H", 0, 0, 8, [])];
  await poll(w);
  check("live, no events yet -> no ev: write", evPuts().length === 0, puts.map((p) => p.k));
  live = [fxObj("1H", 1, 0, 11, [G1])];
  await poll(w);
  let s = stored();
  check("first event -> ev:77 written, ft 0, TTL 129600", evPuts().length === 1 && evPuts()[0].opts.expirationTtl === 129600 && s.ft === 0 && s.fixture === FX, evPuts());
  check("  row carries player + assist ids: [10,0,'g','n','Y. Thalji','A. Ersan','h',101,102]",
    JSON.stringify(s.l[0]) === JSON.stringify([10, 0, "g", "n", "Y. Thalji", "A. Ersan", "h", 101, 102]), s.l[0]);
  check("  th/ta stored", s.th === H && s.ta === A);
  await poll(w);
  check("same list next minute -> no write", evPuts().length === 0);
  live = [fxObj("1H", 1, 0, 31, [G1, C1])];
  await poll(w);
  check("new card -> written again (2 rows)", evPuts().length === 1 && stored().l.length === 2);
  // provider fills a late name: same event count, different content
  const C1named = ev(30, "Card", "Yellow Card", A, 201, "M. Abu Late");
  live = [fxObj("1H", 1, 0, 32, [G1, C1named])];
  await poll(w);
  check("late name / correction (same count, new content) -> written", evPuts().length === 1 && stored().l[1][4] === "M. Abu Late");
  check("only the live fetch was requested (zero extra provider calls)", apiCalls.filter((u) => !u.includes("/fixtures/statistics")).length === 1 && apiCalls[0].includes("fixtures?live="), apiCalls);   // batch 6 #8: live stats call excluded

  // ═══ 2) quota guard ═══
  remaining = "799"; live = [fxObj("2H", 1, 0, 56, [G1, C1named, S1])];
  await poll(w);
  check("quota < 800 -> no ev: write", evPuts().length === 0, puts.map((p) => p.k));
  remaining = "5000";
  await poll(w);
  check("  quota back -> the missed change is written", evPuts().length === 1 && stored().l.length === 3);

  // ═══ 3) full time: final copy from finals() ═══
  live = [];
  finalsResp = [fxObj("FT", 1, 0, 90, [G1, C1named, S1, V1])];
  await poll(w);
  s = stored();
  check("match leaves the live list -> finals() reply gives the final copy: ft 1, includes the last-minute VAR row",
    evPuts().length === 1 && s.ft === 1 && s.l.length === 4 && s.l[3][2] === "v", s);
  check("  calls = live + the finals ids request it already made (no new call type)", apiCalls.length === 2 && apiCalls[1].includes("fixtures?ids=77"), apiCalls);
  check("  events_store log marks the final copy", logs.some((l) => l.includes('"events_store"') && l.includes("-77")));
  await poll(w);
  check("  next poll (f only) -> no more writes", evPuts().length === 0);
}

// ═══ 4) finished with no events at all -> nothing stored ═══
reset(); { const w = await loadWorker();
  store.live = JSON.stringify({ t: Math.floor(Date.now() / 1000) - 60, m: { [FX]: { h: 0, a: 0, e: 88, s: "2H", th: H, ta: A, lg: LG } } });
  live = []; finalsResp = [fxObj("FT", 0, 0, 90, [])];
  await poll(w);
  check("0-0 with no events -> no ev: key", !("ev:" + FX in store));
}

// ═══ 5) GET /events ═══
reset(); { const w = await loadWorker();
  store["ev:" + FX] = JSON.stringify({ fixture: FX, t: 1, th: H, ta: A, ft: 1, l: [] });
  let r = await w.fetch(new Request(`https://x/events?id=${FX}`), env);
  check("GET /events?id=77 -> 200 with the stored JSON, CORS *, cache 60 s", r.status === 200 && (await r.text()) === store["ev:" + FX]
    && r.headers.get("Access-Control-Allow-Origin") === "*" && r.headers.get("Cache-Control") === "public, max-age=60");
  r = await w.fetch(new Request("https://x/events?id=5"), env);
  check("  missing -> 404 {}", r.status === 404 && (await r.text()) === "{}");
  r = await w.fetch(new Request("https://x/events?id=1;2"), env);
  check("  bad id -> 400", r.status === 400);
  r = await w.fetch(new Request(`https://x/lineup?id=${FX}`), env);
  check("  /lineup reads lu: only (no ev: leak)", r.status === 404);
}

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
