// Live match events in the live payload (13 Oct 2026, batch 3D): the existing `fixtures?live=` response already carries `events`,
// so the worker stores a compact copy under payload.v (NO extra provider requests). Quota guard: provider header
// x-ratelimit-requests-remaining < 800 -> `v` is omitted (scores / goal alerts / page scorers unaffected).
// Run: node --no-warnings test_live_events.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_live_events_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0004_goal_log.sql", "0006_scorer_update.sql", "0007_scorer_update_correction.sql", "0008_sub_matches.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const H = 4531, A = 4529, FX = 77;
let live, remaining, apiCalls, written;
const ev = (min, type, detail, team, player, assist = null, extra = null) =>
  ({ time: { elapsed: min, extra }, team: { id: team }, player: { id: 1, name: player }, assist: { id: null, name: assist }, type, detail });
const fx = (h, a, el, events) => ({
  fixture: { id: FX, status: { short: "2H", elapsed: el } }, goals: { home: h, away: a }, events,
  teams: { home: { id: H, name: "Al Faisaly" }, away: { id: A, name: "Al Wehdat" } }, league: { id: 387 },
});
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) {
    apiCalls.push(url);
    const headers = remaining === undefined ? {} : { "x-ratelimit-requests-remaining": String(remaining) };
    return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers });
  }
  return new Response("{}", { status: 404 });
};
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
const NOW = Math.floor(Date.now() / 1000);
async function tick(prev) {
  written = null; apiCalls = [];
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: prev }), put: async (k, v) => { if (k === "live") written = JSON.parse(v); } };
  const env = { API_KEY: "k", LIVE_KV: kv, DB, GOAL_QUEUE: { send: async () => {} }, GOAL_PUSH: "off" };
  await (await loadWorker()).scheduled({}, env, {});
}
let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };
const prev = { [FX]: { h: 1, a: 0, e: 40, s: "1H", th: H, ta: A, lg: 387, nh: "Al Faisaly", na: "Al Wehdat" } };
const EVENTS = [
  ev(10, "Goal", "Normal Goal", H, "Y. Thalji", "A. Ersan"),
  ev(25, "Card", "Yellow Card", A, "W. Away"),
  ev(38, "Goal", "Penalty", A, "S. Pen"),
  ev(50, "Card", "Red Card", H, "R. Red"),
  ev(55, "Card", "Second Yellow card", A, "T. Two"),
  ev(60, "subst", "Substitution 1", H, "Out Man", "In Man"),
  ev(70, "Goal", "Own Goal", H, "O. Gol"),
  ev(80, "Goal", "Missed Penalty", A, "M. Miss"),
  ev(90, "Var", "Goal cancelled", H, "V. Ar", null, 3),
  ev(12, "Foo", "unknown type", H, "Ignored"),
];

// 1) events ride on the existing poll: payload.v compact, ZERO extra provider requests
remaining = 5000; live = [fx(1, 0, 60, EVENTS)];
await tick(prev);
const v = written && written.v && written.v[FX];
check("payload carries v[fixture] with the known event types only (unknown type dropped)", Array.isArray(v) && v.length === 9, v && v.length);
check("  exactly ONE provider request (the normal live poll) — no events polling", apiCalls.length === 1 && apiCalls[0].includes("fixtures?live="), apiCalls);
check("  goal compact: [10,0,'g','n','Y. Thalji','A. Ersan','h']", JSON.stringify(v[0]) === JSON.stringify([10, 0, "g", "n", "Y. Thalji", "A. Ersan", "h"]), v[0]);
check("  yellow = y (away side a); penalty = p; own goal = o; missed penalty = m",
  v[1][2] === "c" && v[1][3] === "y" && v[1][6] === "a" && v[2][3] === "p" && v[6][3] === "o" && v[7][3] === "m", v);
check("  red = r, second yellow = yr; substitution keeps player + assist; VAR keeps detail + extra minute",
  v[3][3] === "r" && v[4][3] === "yr" && v[5][2] === "s" && v[5][4] === "Out Man" && v[5][5] === "In Man" && v[8][2] === "v" && v[8][3] === "Goal cancelled" && v[8][1] === 3, v);
check("  the score/live fields are unchanged (m[fixture] still {h,a,e,s,th,ta,lg})", written.m[FX].h === 1 && written.m[FX].a === 0 && written.m[FX].s === "2H" && written.m[FX].th === H, written.m);

// 2) quota guard: provider says < 800 requests left -> NO v; scores still polled and written
for (const [rem, want] of [[799, false], [800, true], [50, false], [7000, true], [undefined, true]]) {
  remaining = rem; live = [fx(1, 0, 61, EVENTS)];
  await tick(prev);
  check(`quota guard: remaining=${rem} -> v ${want ? "present" : "omitted"}; live payload still written with the score`,
    !!(written && written.v) === want && written && written.m[FX].h === 1, [rem, written]);
}

// 3) no events / finished match / no live matches -> no v key at all (payload unchanged shape)
remaining = 5000; live = [fx(1, 0, 61, [])];
await tick(prev);
check("live match with an empty events array -> no `v` key", written && !("v" in written), written);
live = []; await tick(prev);
check("nothing live -> no `v` key", !written || !("v" in written), written);

// 4) only still-live fixtures keep their events
const prev2 = { [FX]: prev[FX], 99: { h: 0, a: 0, e: 10, s: "1H", th: 1, ta: 2, lg: 387 } };
live = [fx(1, 0, 61, EVENTS)];
await tick(prev2);
check("a fixture that dropped out of the live list does not leak events (v has only the live one)", written && written.v && Object.keys(written.v).join() === String(FX), written && written.v && Object.keys(written.v));

console.log = origLog;
process.exit(fail ? 1 : 0);
