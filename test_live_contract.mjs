// Live data contract v1 (2 Nov 2026): docs/api_live_v1.md's ```contract block is parsed here and checked against payloads the REAL
// worker code produces — GET /, GET /events?id=, GET /lineup?id= — so a worker change that breaks a documented key/type fails this test.
// Scenario (one cron tick at a 5-minute boundary + queue + a second tick): one match live (2H, 45+2-style added time, goal/card/sub/VAR
// events, live stats), one match that left the live feed and comes back FT from fixtures?ids= (-> f), one match in its line-up window
// (-> lu:<id>). In-memory KV and D1 (all migrations), fake provider. No network.
// Run: node --no-warnings test_live_contract.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_live_contract_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

// ── the contract, from the doc ──
const doc = fs.readFileSync(new URL("./docs/api_live_v1.md", import.meta.url), "utf8");
const block = (doc.match(/```contract\r?\n([\s\S]*?)```/) || [])[1];
if (!block) { console.log("FAIL no ```contract block in docs/api_live_v1.md"); process.exit(1); }
const RULES = block.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
  const [ep, p, type, flag] = l.split(/\s+/);
  return { ep, path: p, types: type.split("|"), flag };
});

// ── in-memory D1 ──
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

// ── scenario ──
const LG = 307, H1 = 2932, A1 = 2939, H2 = 2934, A2 = 10511, H3 = 2933, A3 = 2929;
const FX_LIVE = 1603077, FX_DONE = 1603070, FX_LU = 1603080, FX_P = 1603081, FX_PEN = 1603082;   // P / PEN: covers m.*.p and f.*.p
const BASE = Math.floor(Date.now() / 300000) * 300000;   // 5-minute boundary (line-up poll gate), at or before now
const S0 = Math.floor(BASE / 1000);
const KO_LU = S0 + 20 * 60;                               // line-up window KO-60 … KO+5 min
const ev = (min, extra, type, detail, team, pid, player, aid = null, assist = null) =>
  ({ time: { elapsed: min, extra }, team: { id: team }, player: { id: pid, name: player }, assist: { id: aid, name: assist }, type, detail });
const LIVE_EVENTS = [
  ev(23, null, "Goal", "Normal Goal", H1, 1234, "S. Al-Dawsari", 5678, "M. Kanno"),
  ev(31, null, "Card", "Yellow Card", A1, 2001, "R. Mahrez"),
  ev(45, 2, "Card", "Red Card", A1, 2002, "F. Kessie"),
  ev(55, null, "subst", "Substitution 1", H1, 1235, "Out Guy", 1236, "In Guy"),
  ev(60, null, "Var", "Goal cancelled", A1, null, null),
];
const liveFx = () => ({
  fixture: { id: FX_LIVE, status: { short: "2H", elapsed: 67, extra: 2 } }, goals: { home: 1, away: 0 }, events: LIVE_EVENTS,
  teams: { home: { id: H1, name: "Al-Hilal Saudi FC" }, away: { id: A1, name: "Al-Ahli Jeddah" } }, league: { id: LG },
});
const doneFx = () => ({
  fixture: { id: FX_DONE, status: { short: "FT", elapsed: 90 } }, goals: { home: 2, away: 2 },
  events: [ev(89, null, "Goal", "Penalty", H2, 3001, "Late Scorer")],
  teams: { home: { id: H2, name: "Al-Ettifaq" }, away: { id: A2, name: "Al-Riyadh" } }, league: { id: LG },
});
const shootFx = (id, short, pen) => ({
  fixture: { id, status: { short, elapsed: 120 } }, goals: { home: 1, away: 1 }, score: { penalty: pen }, events: [],
  teams: { home: { id: H2, name: "Al-Ettifaq" }, away: { id: A2, name: "Al-Riyadh" } }, league: { id: LG },
});
const P = (id, name, number, pos, grid) => ({ player: { id, name, number, pos, grid } });
const luFx = () => ({
  fixture: { id: FX_LU, status: { short: "NS" } }, teams: { home: { id: H3 }, away: { id: A3 } },
  lineups: [{ team: { id: H3 }, formation: "4-3-3", coach: { name: "Coach H" }, startXI: [P(11, "Keeper H", 1, "G", "1:1")],
              substitutes: [P(12, "Sub H", 17, "M", null)] },
            { team: { id: A3 }, formation: "4-4-2", coach: { name: "Coach A" }, startXI: [P(21, "Keeper A", 1, "G", "1:1")],
              substitutes: [] }],
});
const stat = (t, poss, shots, on, corners) => ({ team: { id: t }, statistics: [
  { type: "Ball Possession", value: poss }, { type: "Total Shots", value: shots }, { type: "Shots on Goal", value: on },
  { type: "Corner Kicks", value: corners }] });

const calls = [];
globalThis.fetch = async (url) => {
  url = String(url);
  calls.push(url);
  const hdr = { "x-ratelimit-requests-remaining": "5000" };
  const ok = (o) => new Response(JSON.stringify(o), { status: 200, headers: hdr });
  if (url.includes("/fixtures?live=")) return ok({ errors: [], response: [liveFx(), shootFx(FX_P, "P", { home: 2, away: 1 })] });
  if (url.includes("/fixtures?ids=")) {
    const ids = url.split("ids=")[1].split("-").map(Number);
    return ok({ errors: [], response: ids.map((id) => id === FX_DONE ? doneFx() : id === FX_LU ? luFx() : id === FX_PEN ? shootFx(FX_PEN, "PEN", { home: 5, away: 4 }) : null).filter(Boolean) });
  }
  if (url.includes("/fixtures/statistics?fixture=")) return ok({ errors: [], response: [stat(H1, "58%", 11, 5, 6), stat(A1, "42%", 7, 2, null)] });
  if (url.includes("/fixtures/events?fixture=")) return ok({ errors: [], response: LIVE_EVENTS });
  if (url === "https://saffara.app/assets/next_kickoffs.json")
    return new Response(JSON.stringify({ t: S0, k: [KO_LU], f: [[KO_LU, FX_LU, H3, A3, LG, "Al-Nassr", "Al-Ittihad"]] }), { status: 200 });
  if (url.startsWith("https://saffara.app/assets/")) return new Response("{}", { status: 200 });
  return new Response("{}", { status: 404 });
};
const store = {
  live: JSON.stringify({ t: S0 - 60, m: {
    [FX_LIVE]: { h: 0, a: 0, e: 66, s: "2H", th: H1, ta: A1, lg: LG },
    [FX_DONE]: { h: 2, a: 1, e: 88, s: "2H", th: H2, ta: A2, lg: LG },
    [FX_PEN]: { h: 1, a: 1, e: 120, s: "P", th: H2, ta: A2, lg: LG } } }),
};
const KV = {
  get: async (k) => (k in store ? store[k] : null),
  put: async (k, v) => { store[k] = v; },
  delete: async (k) => { delete store[k]; },
};
const queued = [];
const QUEUE = { send: async (body) => { queued.push(body); } };
const env = { API_KEY: "k", LIVE_KV: KV, DB, GOAL_QUEUE: QUEUE };
const origLog = console.log;
console.log = () => {};
async function tick(ms) {
  await worker.scheduled({ scheduledTime: ms }, env, {});
  let n = 0;
  while (queued.length && n++ < 50) { const body = queued.shift(); await worker.queue({ messages: [{ body, ack() {}, retry() {} }] }, env); }
}
await tick(BASE);                 // live + finals (f) + stats + line-up window + live-scorer queue
LIVE_EVENTS.push(ev(70, null, "Card", "Yellow Card", H1, 1237, "Late Card"));
await tick(BASE + 60000);         // second minute: v changes again, s read back from sc:<id>
const get = async (p) => {
  const r = await worker.fetch(new Request("https://saffara-live.example" + p), env, { waitUntil: () => {} });
  let j = null; try { j = await r.json(); } catch (e) {}
  return { status: r.status, j, h: r.headers };
};
const live = await get("/");
const events = await get("/events?id=" + FX_LIVE);
const eventsDone = await get("/events?id=" + FX_DONE);
const lineup = await get("/lineup?id=" + FX_LU);
const none = await get("/lineup?id=42");
const bad = await get("/events?id=abc");
console.log = origLog;

let fail = 0, pass = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? pass++ : fail++; };

// ── path resolution: "m.*.h", "v.*[][0]", "home.xi[].id" ──
function resolve(root, p) {
  let cur = [root];
  for (const part of p.split(".")) {
    const m = part.match(/^([^\[]+)?((?:\[\d*\])*)$/);
    let next = [];
    for (const v of cur) {
      if (m[1] === "*") { if (v && typeof v === "object" && !Array.isArray(v)) next.push(...Object.values(v)); }
      else if (m[1] !== undefined) { if (v && typeof v === "object" && m[1] in v) next.push(v[m[1]]); }
      else next.push(v);
    }
    for (const br of (m[2].match(/\[\d*\]/g) || [])) {
      const nx = [];
      for (const v of next) {
        if (!Array.isArray(v)) continue;
        if (br === "[]") nx.push(...v);
        else { const i = Number(br.slice(1, -1)); if (i < v.length) nx.push(v[i]); }
      }
      next = nx;
    }
    cur = next;
  }
  return cur;
}
const typeOf = (v) => v === null ? "null" : Array.isArray(v) ? "array" : Number.isInteger(v) ? "int" : typeof v === "string" ? "string"
  : typeof v === "object" ? "object" : typeof v;
const roots = { live: live.j, events: events.j, lineup: lineup.j };

check("GET / -> 200 JSON, ACAO *, no-store", live.status === 200 && live.h.get("Access-Control-Allow-Origin") === "*"
  && live.h.get("Cache-Control") === "no-store", live.status);
check("GET /events?id=<live> -> 200", events.status === 200, events.status);
check("GET /events?id=<finished> -> 200, ft 1", eventsDone.status === 200 && eventsDone.j.ft === 1, eventsDone.j);
check("GET /lineup?id=<in window> -> 200, public max-age=60", lineup.status === 200 && lineup.h.get("Cache-Control") === "public, max-age=60", lineup.status);
check("missing line-up -> 404 {}", none.status === 404 && JSON.stringify(none.j) === "{}", none);
check("bad id -> 400 {error:'bad id'}", bad.status === 400 && bad.j.error === "bad id", bad);
check("scenario: live match in m, finished match in f (FT 2-2), not in m",
  live.j.m[FX_LIVE] && live.j.f && live.j.f[FX_DONE] && live.j.f[FX_DONE].s === "FT" && live.j.f[FX_DONE].h === 2 && !live.j.m[FX_DONE], live.j);

let checked = 0;
for (const r of RULES) {
  const root = roots[r.ep];
  if (!root) { check(`${r.ep} ${r.path}: endpoint payload missing`, false); continue; }
  const vals = resolve(root, r.path);
  if (r.flag === "internal") {
    const badT = vals.filter((v) => !r.types.includes(typeOf(v)));
    check(`${r.ep} ${r.path} (internal) type ${r.types.join("|")} if present`, badT.length === 0, badT.slice(0, 2).map(typeOf));
    continue;
  }
  // stable and optional keys must all be produced by this scenario (it is built to cover every documented key)
  const badT = vals.filter((v) => !r.types.includes(typeOf(v)));
  check(`${r.ep} ${r.path} : ${r.types.join("|")} (${r.flag})`, vals.length > 0 && badT.length === 0,
    vals.length ? { got: badT.slice(0, 2).map(typeOf) } : "absent");
  checked++;
}
check(`contract block parsed (${RULES.length} rules, ${checked} stable/optional)`, RULES.length > 50 && checked > 40);
// statuses documented for m
const ST_M = ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"];
check("m statuses within the documented set", Object.values(live.j.m).every((e) => ST_M.includes(e.s)), Object.values(live.j.m).map((e) => e.s));
check("f statuses within the documented set", Object.values(live.j.f).every((e) => ["FT", "AET", "PEN", "SUSP", "ABD", "PST", "INT"].includes(e.s)));
// event row semantics spot checks
const row = live.j.v[FX_LIVE].find((x) => x[2] === "c" && x[3] === "r");
check("event row: red card 45+2 -> [45, 2, 'c', 'r', name, '', 'a', 2002, null]",
  row && row[0] === 45 && row[1] === 2 && row[6] === "a" && row[7] === 2002 && row[8] === null, row);
const sub = live.j.v[FX_LIVE].find((x) => x[2] === "s");
check("event row: substitution [4] = out, [5] = in", sub && sub[4] === "Out Guy" && sub[5] === "In Guy" && sub[7] === 1235 && sub[8] === 1236, sub);
check("m.<id>.x = provider added time", live.j.m[FX_LIVE].x === 2 && live.j.m[FX_LIVE].e === 67, live.j.m[FX_LIVE]);
check("st.<id>: [possession, shots, on target, corners], null when missing",
  JSON.stringify(live.j.st[FX_LIVE].h) === "[58,11,5,6]" && live.j.st[FX_LIVE].a[3] === null, live.j.st && live.j.st[FX_LIVE]);
check("doc: every top-level key of GET / is documented", Object.keys(live.j).every((k) => RULES.some((r) => r.ep === "live" && r.path === k)),
  Object.keys(live.j));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
