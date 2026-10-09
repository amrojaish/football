// goal_log (D1): every detected goal / goal_cancelled is stored with the previous score, independent of the
// sender switch; 30-day pruning on the dispatch cycle. No network: mock api-sports, node:sqlite D1 shim.
// Run: node --no-warnings test_goal_log.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_goallog_test.mjs");
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

let live, kvPuts;
globalThis.fetch = async (url) => {
  if (String(url).startsWith("https://v3.football.api-sports.io"))
    return new Response(JSON.stringify({ errors: [], response: live }), { status: 200 });
  return new Response("{}", { status: 404 });
};
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const NOW = Math.floor(Date.now() / 1000);
const fx = (id, h, a, el = 60, lg = 387) => ({ fixture: { id, status: { short: "2H", elapsed: el } }, goals: { home: h, away: a },
  teams: { home: { id: id * 10 + 1, name: "H" }, away: { id: id * 10 + 2, name: "A" } }, league: { id: lg } });
const entry = (id, h, a) => ({ h, a, e: 59, s: "2H", th: id * 10 + 1, ta: id * 10 + 2, lg: 387 });
async function poll(prevM, resp, env = {}, event = {}) {
  live = resp; kvPuts = 0; logs.length = 0;
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: prevM }), put: async () => { kvPuts++; } };
  await (await loadWorker()).scheduled(event, { API_KEY: "k", LIVE_KV: kv, DB, ...env }, {});
}
const rows = () => db.prepare("SELECT kind, fixture, th, ta, h, a, prev_h, prev_a, minute, league, ts FROM goal_log ORDER BY id").all();
const reset = () => db.exec("DELETE FROM goal_log");

let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) goal -> one row with every field, even with the sender switch OFF and no VAPID / queue configured
reset();
await poll({ 5: entry(5, 0, 0) }, [fx(5, 1, 0, 34, 307)]);
let r = rows();
check("goal 0-0 -> 1-0 stored: kind, fixture, th, ta, h, a, prev_h, prev_a, minute, league",
  r.length === 1 && r[0].kind === "goal" && r[0].fixture === 5 && r[0].th === 51 && r[0].ta === 52 && r[0].h === 1 && r[0].a === 0
  && r[0].prev_h === 0 && r[0].prev_a === 0 && r[0].minute === 34 && r[0].league === 307, r);
check("  ts = detection time (unix seconds, now)", Math.abs(r[0].ts - Math.floor(Date.now() / 1000)) <= 5, r[0].ts);
check("  GOAL_PUSH unset, no queue: still logged, KV still written", kvPuts === 1);

// 2) cancel, two goals in one poll, away goal
reset();
await poll({ 5: entry(5, 1, 0) }, [fx(5, 0, 0, 36)]);
r = rows();
check("cancel 1-0 -> 0-0 stored as goal_cancelled with prev 1-0", r.length === 1 && r[0].kind === "goal_cancelled" && r[0].h === 0 && r[0].prev_h === 1 && r[0].prev_a === 0, r);
reset();
await poll({ 5: entry(5, 1, 0) }, [fx(5, 2, 1, 70)]);
r = rows();
check("two goals in one poll (1-0 -> 2-1) = ONE row, prev 1-0 now 2-1", r.length === 1 && r[0].kind === "goal" && r[0].prev_h === 1 && r[0].h === 2 && r[0].a === 1, r);
reset();
await poll({ 5: entry(5, 1, 1) }, [fx(5, 1, 2, 80)]);
check("away goal 1-1 -> 1-2", rows().length === 1 && rows()[0].a === 2 && rows()[0].prev_a === 1);

// 3) nothing logged without an event; same poll twice (KV advanced) = no duplicate
reset();
await poll({ 5: entry(5, 1, 1), 6: { h: null, a: null, e: 1, s: "1H" } }, [fx(5, 1, 1), fx(6, 0, 0, 2)]);
check("unchanged score / null->0 start -> no rows", rows().length === 0, rows());
await poll({}, [fx(7, 2, 1)]);
check("fixture first seen mid-match -> no rows", rows().length === 0, rows());
// first sighting inside the first 20 min of the 1st half (idle-window gap, fixture 1627995 on 8 Oct): baseline 0-0
reset();
const fx1h = (id, h, a, el) => ({ ...fx(id, h, a, el), fixture: { id, status: { short: "1H", elapsed: el } } });
await poll({}, [fx1h(7, 1, 0, 5)]);
r = rows();
check("first seen 1-0 at 1H 5' -> ONE goal row, prev 0-0, minute 5", r.length === 1 && r[0].kind === "goal" && r[0].h === 1 && r[0].a === 0 && r[0].prev_h === 0 && r[0].prev_a === 0 && r[0].minute === 5, r);
reset();
await poll({}, [fx1h(7, 2, 1, 12)]);
r = rows();
check("first seen 2-1 at 12' -> one row PER goal: 0-0>1-0, 1-0>2-0, 2-0>2-1",
  r.map((x) => `${x.prev_h}-${x.prev_a}>${x.h}-${x.a}`).join() === "0-0>1-0,1-0>2-0,2-0>2-1", r);
reset();
await poll({}, [fx1h(7, 0, 0, 5)]);
check("first seen 0-0 at 5' -> nothing", rows().length === 0, rows());
await poll({}, [fx1h(7, 1, 0, 21)]);
check("first seen 1-0 at 21' (restart mid-match) -> nothing", rows().length === 0, rows());
await poll({}, [fx(7, 1, 0, 8)]);
check("first seen 1-0 but status 2H -> nothing", rows().length === 0, rows());
await poll({ 7: entry(7, 1, 0) }, [fx1h(7, 1, 0, 6)]);
check("already known fixture unchanged at 6' -> nothing", rows().length === 0, rows());
reset();
await poll({ 8: entry(8, 2, 1) }, []);
check("fixture leaving the feed -> no rows", rows().length === 0, rows());
await poll({ 5: entry(5, 0, 0) }, [fx(5, 1, 0, 10)]);
await poll({ 5: entry(5, 1, 0) }, [fx(5, 1, 0, 11)]);   // next minute: KV now has 1-0
check("the goal is logged once; the following unchanged poll adds nothing", rows().length === 1, rows());

// 4) several fixtures in one poll
reset();
await poll({ 1: entry(1, 0, 0), 2: entry(2, 1, 1), 3: entry(3, 0, 0) }, [fx(1, 1, 0), fx(2, 1, 2), fx(3, 0, 0)]);
check("3 live fixtures, 2 changed -> 2 rows", rows().length === 2 && rows().map((x) => x.fixture).sort().join() === "1,2", rows());

// 5) D1 failure must not stop the poll / KV write
reset();
const broken = { prepare: () => { throw new Error("d1 down"); }, batch: async () => { throw new Error("d1 down"); } };
await poll({ 5: entry(5, 0, 0) }, [fx(5, 1, 0)], { DB: broken });
check("D1 down -> logged as goal_log_error, KV still written", kvPuts === 1 && logs.some((l) => l.includes("goal_log_error")), [kvPuts, logs]);
await poll({ 5: entry(5, 0, 0) }, [fx(5, 1, 0)], { DB: undefined });
check("no DB binding -> nothing breaks, KV written", kvPuts === 1);

// 6) 30-day retention, pruned on the :05/:35 cycle only
reset();
const day = 86400;
db.prepare("INSERT INTO goal_log (ts, kind, fixture, h, a, prev_h, prev_a) VALUES (?, 'goal', 1, 1, 0, 0, 0)").run(NOW - 31 * day);
db.prepare("INSERT INTO goal_log (ts, kind, fixture, h, a, prev_h, prev_a) VALUES (?, 'goal', 2, 1, 0, 0, 0)").run(NOW - 29 * day);
db.prepare("INSERT INTO goal_log (ts, kind, fixture, h, a, prev_h, prev_a) VALUES (?, 'goal', 3, 1, 0, 0, 0)").run(NOW - 60);
await poll({}, [], {}, { scheduledTime: Date.UTC(2026, 9, 6, 12, 20, 0) });
check("minute :20 -> no pruning", rows().length === 3);
const nearNow = new Date(); nearNow.setUTCMinutes(5, 0, 0);
await poll({}, [], {}, { scheduledTime: nearNow.getTime() });
check("minute :05 -> rows older than 30 days deleted, newer kept", JSON.stringify(rows().map((x) => x.fixture)) === "[2,3]", rows().map((x) => x.fixture));

// 7) comparing against the provider's final score: replay of a match gives a consistent goal chain
reset();
let prev = { 9: entry(9, 0, 0) };
const chain = [[1, 0], [1, 1], [2, 1], [2, 1], [3, 1]];
for (const [h, a] of chain) { await poll(prev, [fx(9, h, a)]); prev = { 9: entry(9, h, a) }; }
const rr = rows();
check("replay 0-0 -> 1-0 -> 1-1 -> 2-1 -> 2-1 -> 3-1: 4 goal rows chained (prev of each = score of the one before), final 3-1",
  rr.length === 4 && rr.every((x, i) => i === 0 || (x.prev_h === rr[i - 1].h && x.prev_a === rr[i - 1].a)) && rr.at(-1).h === 3 && rr.at(-1).a === 1
  && rr.reduce((n, x) => n + (x.h - x.prev_h) + (x.a - x.prev_a), 0) === 4, rr);

console.log = origLog;
process.exit(fail ? 1 : 0);
