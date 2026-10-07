// Cron-triggered deploy-site dispatch: mocked GitHub + api-sports, in-memory D1 shim, KV mock.
// Run: node --no-warnings test_dispatch.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_dispatch_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Date.now())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { db.prepare(sql).run(...args); return {}; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const NOW = Math.floor(Date.now() / 1000);
// scheduled time at a given UTC minute
const at = (min) => Date.UTC(2026, 9, 6, 12, min, 0);

let gh;            // per-test GitHub behaviour
let calls;         // every fetch
let kvPuts;
function reset(over = {}) {
  gh = { queued: 0, in_progress: 0, waiting: 0, pending: 0, requested: 0, ageMin: 5, runsStatus: 200, dispatchStatus: 204, throwOnGh: false, ...over };
  calls = [];
  kvPuts = 0;
  db.exec("DELETE FROM dispatch_log");
}
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  calls.push({ url, init });
  if (url.startsWith("https://v3.football.api-sports.io")) {
    return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 });
  }
  if (gh.throwOnGh) throw new Error("network down");
  if (url.includes("/runs?")) {
    const st = /status=(\w+)/.exec(url)[1];
    if (gh.runsStatus !== 200) return new Response("{}", { status: gh.runsStatus });
    const runs = gh[st] ? [{ id: gh.runId ?? 4242, created_at: new Date(at(gh.minute ?? 5) - gh.ageMin * 60000).toISOString() }] : [];
    return new Response(JSON.stringify({ total_count: gh[st], workflow_runs: runs }), { status: 200 });
  }
  if (url.endsWith("/dispatches")) return new Response(null, { status: gh.dispatchStatus });
  return new Response("{}", { status: 404 });
};

const KV = { get: async () => JSON.stringify({ t: NOW - 3600, m: {} }), put: async () => { kvPuts++; } };
const env = (extra = {}) => ({ API_KEY: "k", LIVE_KV: KV, DB, GH_DISPATCH_TOKEN: "ghp_test_token", ...extra });
const logs = [];
const origLog = console.log;
console.log = (s) => { logs.push(String(s)); };
async function tick(minute, e = env()) {
  logs.length = 0;
  const waits = [];
  await worker.scheduled({ scheduledTime: at(minute) }, e, { waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
  return waits.length;
}
const rows = () => db.prepare("SELECT ts, result, http_status FROM dispatch_log ORDER BY id").all();
const gh_calls = () => calls.filter((c) => c.url.startsWith("https://api.github.com"));

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) :05 dispatches, with the right request
reset();
let waits = await tick(5);
let post = calls.find((c) => c.url.endsWith("/dispatches"));
check(":05 -> stuck-run checks (3) + queued + in_progress checked, then one POST dispatches", gh_calls().length === 6 && !!post && post.init.method === "POST", gh_calls().map((c) => c.url));
check("  POST url/body/headers", post.url === "https://api.github.com/repos/amrojaish/football/actions/workflows/deploy-site.yml/dispatches"
  && post.init.body === '{"ref":"main"}' && post.init.headers.Authorization === "Bearer ghp_test_token"
  && post.init.headers.Accept === "application/vnd.github+json" && post.init.headers["X-GitHub-Api-Version"] === "2022-11-28"
  && post.init.headers["User-Agent"] === "saffara-live", post);
check("  run checks used status=queued and status=in_progress", calls.some((c) => c.url.includes("status=queued")) && calls.some((c) => c.url.includes("status=in_progress")));
check("  dispatch ran in ctx.waitUntil, after the live poll (api-sports call first)", waits === 1 && calls[0].url.startsWith("https://v3.football.api-sports.io"), calls[0].url);
check("  D1 row: dispatched / 204", JSON.stringify(rows().map((r) => [r.result, r.http_status])) === '[["dispatched",204]]', rows());
const line = JSON.parse(logs.find((l) => l.includes('"dispatch"')));
check("  one JSON log line type=dispatch result=dispatched", line.type === "dispatch" && line.result === "dispatched" && line.http_status === 204, line);

// 2) :35 dispatches; every other minute does not
reset();
await tick(35);
check(":35 -> dispatched", rows().length === 1 && rows()[0].result === "dispatched");
for (const m of [0, 4, 6, 20, 34, 36, 59]) {
  reset();
  await tick(m);
  check(`:${String(m).padStart(2, "0")} -> no GitHub call, no log row`, gh_calls().length === 0 && rows().length === 0, gh_calls().length);
}

// 3) skip while a run is queued / in progress
for (const st of ["queued", "in_progress"]) {
  reset({ [st]: 1 });
  await tick(5);
  check(`run ${st} -> skipped, no POST`, !calls.some((c) => c.url.endsWith("/dispatches")) && rows()[0].result === "skipped_" + st, rows());
}

// 3b) stale runs (stuck on GitHub) must not block dispatch
for (const st of ["queued", "in_progress"]) {
  reset({ [st]: 1, ageMin: 10 });
  await tick(5);
  check(`${st} run aged 10 min -> skip, no POST`, !calls.some((c) => c.url.endsWith("/dispatches")) && rows()[0].result === "skipped_" + st, rows());
  reset({ [st]: 1, ageMin: 44 });
  await tick(5);
  check(`${st} run aged 44 min -> still skip`, rows()[0].result === "skipped_" + st && !calls.some((c) => c.url.endsWith("/dispatches")), rows());
  reset({ [st]: 1, ageMin: 60 });
  await tick(5);
  const sl = logs.map((l) => JSON.parse(l)).find((l) => l.result === "stale_ignored");
  check(`${st} run aged 60 min -> stale_ignored then dispatched`, JSON.stringify(rows().map((r) => r.result)) === '["stale_ignored","dispatched"]'
    && calls.some((c) => c.url.endsWith("/dispatches")), rows());
  check("  stale_ignored JSON line carries run id", sl && sl.run_id === 4242 && sl.run_status === st && sl.age_min === 60, sl);
}
reset({ queued: 1, ageMin: 60 });
gh.in_progress = 0;
await tick(5);
reset({ queued: 1, in_progress: 1, ageMin: 5 });
await tick(5);
check("fresh run still blocks even when checked after a stale one", rows()[0].result === "skipped_queued", rows());

// 3c) stuck runs (waiting / pending / requested older than 45 min): logged as stuck_run:<id>, never blocks, never cancels
for (const st of ["waiting", "pending", "requested"]) {
  reset({ [st]: 1, ageMin: 60, runId: 37520113840 });
  await tick(5);
  const sr = logs.map((l) => JSON.parse(l)).find((l) => String(l.result).startsWith("stuck_run"));
  check(`${st} run aged 60 min -> row stuck_run:<id>, then dispatched`, JSON.stringify(rows().map((r) => r.result)) === '["stuck_run:37520113840","dispatched"]'
    && calls.some((c) => c.url.endsWith("/dispatches")), rows());
  check("  stuck_run JSON line carries run id/status/age", sr && sr.run_id === 37520113840 && sr.run_status === st && sr.age_min === 60, sr);
  check("  no cancel / write call to GitHub other than the dispatch POST", calls.filter((c) => c.init && c.init.method === "POST").length === 1
    && !calls.some((c) => /cancel|force-cancel/.test(c.url)));
  reset({ [st]: 1, ageMin: 44 });
  await tick(5);
  check(`${st} run aged 44 min -> no stuck_run row`, JSON.stringify(rows().map((r) => r.result)) === '["dispatched"]', rows());
}
reset({ waiting: 1, queued: 1, ageMin: 60 });
gh.queued = 1;
await tick(5);
check("waiting 60 min + queued 60 min -> stuck_run, stale_ignored, dispatched", JSON.stringify(rows().map((r) => r.result)) === '["stuck_run:4242","stale_ignored","dispatched"]', rows());
reset({ waiting: 1, ageMin: 60 });
const f0 = globalThis.fetch;
globalThis.fetch = async (url, init) => (String(url).includes("status=waiting") ? new Response("{}", { status: 500 }) : f0(url, init));
await tick(5);
check("stuck-run check failing (500) -> ignored, dispatch still happens", JSON.stringify(rows().map((r) => r.result)) === '["dispatched"]', rows());
globalThis.fetch = f0;

// 4) auth failures are visible
for (const [label, over] of [["dispatch 401", { dispatchStatus: 401 }], ["dispatch 403", { dispatchStatus: 403 }], ["runs check 401", { runsStatus: 401 }], ["runs check 403", { runsStatus: 403 }]]) {
  reset(over);
  await tick(5);
  const l = JSON.parse(logs.find((x) => x.includes("dispatch")) || "{}");
  check(`${label} -> type dispatch_auth_failed + row auth_failed`, l.type === "dispatch_auth_failed" && rows()[0]?.result === "auth_failed" && [401, 403].includes(rows()[0].http_status), [l, rows()]);
}
reset({ runsStatus: 500 });
await tick(5);
check("runs check 500 -> check_failed, never dispatches", rows()[0].result === "check_failed" && !calls.some((c) => c.url.endsWith("/dispatches")));
reset({ dispatchStatus: 422 });
await tick(5);
check("dispatch 422 -> failed (not auth)", rows()[0].result === "failed" && rows()[0].http_status === 422);

// 5) live poll unaffected by GitHub trouble
reset({ throwOnGh: true });
let threw = false;
try { await tick(5); } catch (e) { threw = true; }
check("GitHub unreachable -> scheduled() does not throw", !threw);
check("  live poll still ran (api-sports called)", calls.some((c) => c.url.startsWith("https://v3.football.api-sports.io")));
check("  the error attempt is still recorded (row result=error)", rows().length === 1 && rows()[0].result === "error", rows());
reset();
await tick(5, env({ GH_DISPATCH_TOKEN: undefined }));
check("no token configured -> no GitHub call, poll still runs", gh_calls().length === 0 && calls.length === 1);
reset();
await tick(5, env({ DB: undefined }));
check("no DB binding -> still dispatches, no crash", calls.some((c) => c.url.endsWith("/dispatches")));
// idle-skip path: poll returns early, dispatch must still happen at :05
reset();
const idleKv = { get: async () => JSON.stringify({ t: NOW - 10, m: {} }), put: async () => { kvPuts++; } };
await tick(35, env({ LIVE_KV: idleKv }));
check("idle poll (skipped) -> dispatch still happens at :35, no api-sports call", calls.every((c) => !c.url.startsWith("https://v3.football.api-sports.io"))
  && rows().length === 1 && rows()[0].result === "dispatched", rows());
// poll failing (api-sports 500 handled inside pull) must not block dispatch
reset();

// 6) log pruning: keep the last 500
reset();
for (let i = 0; i < 520; i++) db.prepare("INSERT INTO dispatch_log (ts, result, http_status) VALUES (?, 'skipped_queued', 200)").run(i);
await tick(5);
const n = db.prepare("SELECT COUNT(*) c FROM dispatch_log").get().c;
const last = db.prepare("SELECT result FROM dispatch_log ORDER BY id DESC LIMIT 1").get().result;
check("pruned to the last 500 rows, newest kept", n === 500 && last === "dispatched", { n, last });

// 7) no scheduledTime (older callers/tests) -> never dispatches
reset();
logs.length = 0;
await worker.scheduled({}, env(), {});
check("scheduled({}) without scheduledTime -> no dispatch", gh_calls().length === 0 && rows().length === 0);

console.log = origLog;
process.exit(fail ? 1 : 0);
