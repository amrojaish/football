// «مين رح يفوز؟» voting (27 Oct 2026): POST /vote + GET /votes on the worker. No network: node:sqlite D1 shim with the real
// migrations (0003 rate_limit + 0010 votes), fake next_kickoffs.json (v = {fixture: kickoff}) and a fake live KV.
// Run: node --no-warnings test_votes.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_votes_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0003_rate_limit.sql", "0010_votes.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const NOW = Math.floor(Date.now() / 1000);
const FUT = 1001, PAST = 1002, LIVE = 1003, OTHER = 1004;
const kick = { t: NOW, k: [], f: [], v: { [FUT]: NOW + 3600, [PAST]: NOW - 60, [LIVE]: NOW + 600, [OTHER]: NOW + 7200 } };
let kickFetches = 0;
globalThis.fetch = async (url) => {
  if (String(url) === "https://saffara.app/assets/next_kickoffs.json") { kickFetches++; return new Response(JSON.stringify(kick), { status: 200 }); }
  return new Response("{}", { status: 404 });
};
const liveKV = { get: async () => JSON.stringify({ t: NOW, m: { [LIVE]: { h: 0, a: 0, s: "1H" } } }), put: async () => {} };
const env = { DB, LIVE_KV: liveKV };
const ORIGIN = "https://saffara.app";
const D = (n) => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
let ip = "10.0.0.1";
const call = async (method, p, body, origin = ORIGIN) => {
  const req = new Request("https://saffara-live.example" + p, { method,
    headers: { "Content-Type": "application/json", "CF-Connecting-IP": ip, ...(origin ? { Origin: origin } : {}) },
    ...(body !== undefined ? { body: typeof body === "string" ? body : JSON.stringify(body) } : {}) });
  const r = await worker.fetch(req, env, { waitUntil: () => {} });
  let j = null; try { j = await r.json(); } catch (e) {}
  return { s: r.status, j, h: r.headers };
};
const vote = (fixture, choice, device) => call("POST", "/vote", { fixture, choice, device });

let fail = 0, pass = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? pass++ : fail++; };

// vote ok + totals
let r = await vote(FUT, "h", D(1));
check("vote ok -> 200, totals h=1 total=1, choice echoed", r.s === 200 && r.j.ok && r.j.choice === "h" && r.j.h === 1 && r.j.total === 1, r);
check("  CORS for saffara.app on the reply", r.h.get("access-control-allow-origin") === ORIGIN, r.h.get("access-control-allow-origin"));
r = await vote(FUT, "a", D(2)); r = await vote(FUT, "a", D(3)); r = await vote(FUT, "d", D(4));
check("totals after 4 devices: h1 d1 a2 total4", r.s === 200 && r.j.h === 1 && r.j.d === 1 && r.j.a === 2 && r.j.total === 4, r.j);

// duplicate
r = await vote(FUT, "a", D(1));
check("same device again -> 409, keeps its first choice (h), totals unchanged", r.s === 409 && r.j.choice === "h" && r.j.h === 1 && r.j.a === 2 && r.j.total === 4, r);
check("  stored row unchanged", db.prepare(`SELECT choice FROM votes WHERE fixture_id=${FUT} AND device='${D(1)}'`).get().choice === "h");
r = await vote(FUT, "h", D(1).toUpperCase());
check("  same device in upper case is the same device -> 409", r.s === 409, r.s);

// after kickoff / live / unknown
r = await vote(PAST, "h", D(5));
check("kickoff passed -> 403 started (+ totals), nothing stored", r.s === 403 && r.j.error === "started" && r.j.total === 0
  && db.prepare(`SELECT COUNT(*) c FROM votes WHERE fixture_id=${PAST}`).get().c === 0, r);
r = await vote(LIVE, "h", D(5));
check("kickoff in the future but fixture already in live KV -> 403 started", r.s === 403 && r.j.error === "started", r);
r = await vote(9999, "h", D(5));
check("fixture not in our fixture data -> 404 unknown", r.s === 404, r);

// bad input
for (const [n, b] of [["choice x", { fixture: FUT, choice: "x", device: D(6) }], ["no device", { fixture: FUT, choice: "h" }],
                      ["device not a UUID", { fixture: FUT, choice: "h", device: "abc" }], ["fixture as string", { fixture: String(FUT), choice: "h", device: D(6) }],
                      ["fixture 0", { fixture: 0, choice: "h", device: D(6) }]]) {
  r = await vote(b.fixture, b.choice, b.device);
  check(`bad input (${n}) -> 400`, r.s === 400, r);
}
r = await call("POST", "/vote", "{not json");
check("bad json -> 400", r.s === 400, r.s);
r = await call("POST", "/vote", { fixture: FUT, choice: "h", device: D(7) }, "https://evil.example");
check("foreign Origin -> 400, nothing stored", r.s === 400 && db.prepare(`SELECT COUNT(*) c FROM votes WHERE device='${D(7)}'`).get().c === 0, r.s);

// GET totals
r = await call("GET", `/votes?id=${FUT}`);
check("GET /votes?id -> {h,d,a,total}", r.s === 200 && r.j.h === 1 && r.j.d === 1 && r.j.a === 2 && r.j.total === 4, r.j);
check("  cacheable 30 s (public, max-age=30)", /public, max-age=30/.test(r.h.get("cache-control") || ""), r.h.get("cache-control"));
r = await call("GET", `/votes?id=${OTHER}`);
check("GET a fixture with no votes -> zeros", r.s === 200 && r.j.total === 0 && r.j.h === 0, r.j);
r = await call("GET", `/votes?ids=${FUT},${OTHER}`);
check("GET /votes?ids=a,b -> map per fixture", r.s === 200 && r.j[FUT].total === 4 && r.j[OTHER].total === 0, r.j);
r = await call("GET", "/votes?id=abc");
check("GET bad id -> 400", r.s === 400, r.s);
r = await call("GET", "/votes?ids=" + Array.from({ length: 51 }, (_, i) => i + 1).join(","));
check("GET more than 50 ids -> 400", r.s === 400, r.s);

// rate limit (per IP, per hour): 30 POSTs accepted, the 31st -> 429 with Retry-After; another IP is not affected
ip = "10.9.9.9";
let last;
for (let i = 0; i < 30; i++) last = await vote(OTHER, "d", D(100 + i));
check("30 votes from one IP in the hour -> all accepted", last.s === 200 && last.j.total === 30, last);
r = await vote(OTHER, "d", D(200));
check("31st vote from that IP -> 429 + Retry-After, not stored", r.s === 429 && Number(r.h.get("retry-after")) > 0
  && db.prepare(`SELECT COUNT(*) c FROM votes WHERE device='${D(200)}'`).get().c === 0, r);
ip = "10.9.9.10";
r = await vote(OTHER, "h", D(201));
check("  another IP still votes", r.s === 200 && r.j.total === 31, r);
check("  the subscribe counter key is separate (v: prefix)", db.prepare("SELECT COUNT(*) c FROM rate_limit WHERE k LIKE 'v:%'").get().c >= 2
  && db.prepare("SELECT COUNT(*) c FROM rate_limit WHERE k NOT LIKE 'v:%'").get().c === 0);
check("raw IP never stored", db.prepare("SELECT COUNT(*) c FROM rate_limit WHERE k LIKE '%10.9%'").get().c === 0);

// D1 down -> 5xx-ish, never a crash of the whole worker route table
const envBroken = { DB: { prepare: () => { throw new Error("d1 down"); } }, LIVE_KV: liveKV };
let threw = false;
try { await worker.fetch(new Request("https://x/votes?id=1", { headers: { Origin: ORIGIN } }), envBroken, {}); } catch (e) { threw = true; }
check("D1 down on GET -> throws inside the route (Workers returns 500; the page hides the card)", threw);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
