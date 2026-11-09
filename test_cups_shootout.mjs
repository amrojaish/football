// Cups phase 3 (9 Nov 2026): p:{h,a} from score.penalty on m and f entries (P / PEN only); shootout kicks never reach v, ev:<id>, the scorers
// or any push; raw ss:<id> snapshots while status is P (append, TTL 14 days, max 60, no push). Each scenario keeps a normal fixture alongside.
// In-memory KV + D1 (all migrations), fake provider, queue messages captured. No network.
// Run: node --no-warnings test_cups_shootout.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_cups_shootout_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
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

const LO = 302, SAU = 307, A = 900101, B = 900102, C = 900103;
const LT = { h: 2939, a: 2932 };
const NOW = Math.floor(Date.now() / 1000);
const DAY = 86400;
let store, opts, queue, calls, live, ids, eventsReply, ssPutFails;
const SO = "Penalty Shootout";
const fx = (id, lg, s, el, h, a, pen, events = []) => ({ fixture: { id, status: { short: s, elapsed: el, long: "x" } }, goals: { home: h, away: a }, events,
  score: { penalty: pen === undefined ? { home: null, away: null } : pen },
  teams: { home: { id: LT.h, name: "H" }, away: { id: LT.a, name: "A" } }, league: { id: lg } });
const ev = (type, detail, el, extra, name, side, comments = null) => ({ time: { elapsed: el, extra }, type, detail, comments, team: { id: side }, player: { id: 77, name }, assist: {} });
const reg = () => ev("Goal", "Normal Goal", 30, null, "R. Real", LT.h);
const kicks = () => [ev("Goal", "Penalty", 120, 1, "K. Scored", LT.h, SO), ev("Goal", "Missed Penalty", 120, 1, "K. Missed", LT.a, SO)];
const hd = { "x-ratelimit-requests-remaining": "5000" };
const J = (o) => new Response(JSON.stringify(o), { status: 200, headers: hd });
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.includes("next_kickoffs.json")) return new Response("{}", { status: 404 });
  if (!url.startsWith("https://v3.football.api-sports.io")) return new Response("{}", { status: 404 });
  calls.push(url);
  if (url.includes("/fixtures?live=")) return J({ errors: [], response: live });
  if (url.includes("/fixtures?ids=")) return J({ errors: [], response: ids });
  if (url.includes("/fixtures/events")) return J({ errors: [], response: eventsReply });
  return J({ errors: [], response: [] });
};
const KV = {
  get: async (k) => { if (ssPutFails && k.startsWith("ss:")) throw new Error("boom"); return k in store ? store[k] : null; },
  put: async (k, v, o) => { if (ssPutFails && k.startsWith("ss:")) throw new Error("boom"); store[k] = v; opts[k] = o; },
  delete: async (k) => { delete store[k]; },
};
const GOAL_QUEUE = { send: async (b) => { queue.push(b); } };
const env = { API_KEY: "k", LIVE_KV: KV, DB, GOAL_QUEUE, GOAL_PUSH: "on", VAPID_PUBLIC_KEY: "p", VAPID_PRIVATE_KEY: "q" };
const origLog = console.log;
console.log = () => {};
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };
const PUSH = new Set(["goal", "cancel", "alert", "goal_scorer"]);
const pushes = () => queue.filter((m) => PUSH.has(m.kind));
const pushesOf = (id) => pushes().filter((m) => m.fixture === id);
const payload = () => JSON.parse(store.live);
const entry = (lg, s, e, h, a, extra = {}) => ({ h, a, e, s, th: LT.h, ta: LT.a, lg, nh: "H", na: "A", ...extra });
function reset(prevM = null) {
  store = {}; opts = {}; queue = []; calls = []; live = []; ids = []; eventsReply = []; ssPutFails = false;
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM goal_log");
  store.live = JSON.stringify({ t: prevM ? NOW - 60 : NOW - 3600, ve: 1, m: prevM || {} });
}
const tick = () => worker.scheduled({}, env, {});
const livePolls = () => calls.filter((u) => u.includes("fixtures?live=")).length;
const ss = (id) => (store["ss:" + id] ? JSON.parse(store["ss:" + id]) : null);

// ── 6) p on m ──
reset();
live = [fx(A, SAU, "P", 120, 1, 1, { home: 2, away: 3 }), fx(B, SAU, "P", 120, 0, 0, { home: null, away: null }), fx(C, SAU, "2H", 70, 1, 0, { home: 9, away: 9 })];
await tick();
let m = payload().m;
check("6 P with score.penalty: m.p = {h,a}", JSON.stringify(m[A].p) === '{"h":2,"a":3}', m[A]);
check("6 P with null score.penalty: no p key", !("p" in m[B]), m[B]);
check("6 a non-shootout status never gets p, even if the provider sent numbers", !("p" in m[C]), m[C]);
reset();
live = [{ ...fx(A, SAU, "P", 120, 1, 1), score: undefined }, fx(C, SAU, "ET", 100, 1, 1, { home: 1, away: 0 })];
await tick();
check("6 P with no score object at all: no crash, no p", !("p" in payload().m[A]), payload().m[A]);
check("6 ET: no p", !("p" in payload().m[C]), payload().m[C]);
reset();
live = [fx(A, LO, "P", 120, 1, 1, { home: 1, away: 1 })];
await tick();
check("6 live-only cup also gets p", JSON.stringify(payload().m[A].p) === '{"h":1,"a":1}', payload().m[A]);

// ── 6) p on f ──
reset({ [A]: entry(SAU, "P", 120, 1, 1, { p: { h: 2, a: 3 } }), [B]: entry(SAU, "2H", 90, 2, 0), [C]: entry(SAU, "ET", 120, 1, 1) });
ids = [fx(A, SAU, "PEN", 120, 1, 1, { home: 4, away: 5 }), fx(B, SAU, "FT", 90, 2, 0, { home: 7, away: 7 }), fx(C, SAU, "AET", 120, 1, 1, { home: null, away: null })];
await tick();
let f = payload().f;
check("6 PEN: f.p = {h,a}", JSON.stringify(f[A].p) === '{"h":4,"a":5}' && f[A].s === "PEN" && f[A].h === 1, f[A]);
check("6 FT and AET: no p on f", !("p" in f[B]) && !("p" in f[C]), [f[B], f[C]]);
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
ids = [fx(A, SAU, "PEN", 120, 1, 1, { home: null, away: null })];
await tick();
check("6 PEN with no score.penalty: f has no p", payload().f[A] && !("p" in payload().f[A]), payload().f[A]);

// ── 7) a kick event never reaches ev, the scorers or a push (with p present) ──
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
store.live = JSON.stringify({ t: NOW - 60, ve: 1, v: { [A]: [[30, 0, "g", "n", "R. Real", "", "h", 77, null]] }, m: { [A]: entry(SAU, "P", 120, 1, 1) } });
live = [fx(A, SAU, "P", 120, 1, 1, { home: 1, away: 0 }, [reg(), ...kicks()])];
await tick();
const vr = (payload().v || {})[A] || [];
check("7 live timeline v: the real goal only", vr.length === 1 && vr[0][4] === "R. Real", vr);
check("7 p is carried while the kicks are not", JSON.stringify(payload().m[A].p) === '{"h":1,"a":0}', payload().m[A]);
check("7 no push for a scored or missed kick", pushes().length === 0, pushes());
const ev0 = store["ev:" + A] ? JSON.parse(store["ev:" + A]) : null;
check("7 ev:<id> holds no kick", !ev0 || ev0.l.every((x) => x[4] === "R. Real"), ev0);
check("7 the payload has no kick name anywhere", !store.live.includes("K. Scored") && !store.live.includes("K. Missed"), store.live.length);
live = []; ids = [fx(A, SAU, "PEN", 120, 1, 1, { home: 5, away: 4 }, [reg(), ...kicks()])];
await tick();
const fin = store["ev:" + A] ? JSON.parse(store["ev:" + A]) : null;
check("7 final ev:<id> holds no kick", fin && fin.ft === 1 && fin.l.length === 1 && fin.l[0][4] === "R. Real", fin);
check("7 final: only the full-time alert is queued, nothing from the kicks", pushesOf(A).map((x) => x.kind === "alert" ? x.evt : x.kind).join() === "ft", pushes());
const src = fs.readFileSync(new URL("./worker.js", import.meta.url), "utf8");
check("7 worker :124 filter is untouched", src.includes('if (!e || !e.time || e.comments === SHOOTOUT) continue;'));
check("7 worker :539 filter is untouched", src.includes('e.type === "Goal" && e.detail !== "Missed Penalty" && e.comments !== SHOOTOUT && e.team && e.player)'));

// ── 10) ss:<id> snapshots ──
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
const pen1 = { home: 1, away: 0 };
live = [fx(A, SAU, "P", 120, 1, 1, pen1, [reg(), ...kicks()]), fx(C, SAU, "2H", 70, 0, 0)];
await tick();
let l = ss(A);
check("10 P writes one snapshot per poll", l && l.length === livePolls() && livePolls() >= 1, [l && l.length, livePolls()]);
const s0 = l[0];
check("10 snapshot: fixture status", s0.status.short === "P" && s0.status.elapsed === 120 && s0.status.long === "x", s0.status);
check("10 snapshot: goals {home, away} as sent", JSON.stringify(s0.goals) === '{"home":1,"away":1}', s0.goals);
check("10 snapshot: score.penalty as sent", JSON.stringify(s0.penalty) === JSON.stringify(pen1), s0.penalty);
check("10 snapshot: only shootout events, raw", s0.events.length === 2 && s0.events.every((e) => e.comments === SO) && s0.events[0].player.name === "K. Scored", s0.events);
check("10 snapshot: fetch time", Math.abs(s0.at - Math.floor(Date.now() / 1000)) < 30, s0.at);
check("10 TTL is 14 days", opts["ss:" + A].expirationTtl === 14 * DAY, opts["ss:" + A]);
check("10 zero pushes of any kind from P", pushes().length === 0, pushes());
check("10 no queue message at all for the P fixture", !queue.some((q) => q.fixture === A), queue);
check("10 a non-P fixture writes no snapshot", !(("ss:" + C) in store));
check("10 snapshots stay out of the live payload", !("ss" in payload()) && !store.live.includes('"penalty"'));
check("10 no extra provider request", calls.every((u) => !u.includes("score") && !u.includes("/fixtures/events")), calls);
const before = l.length;
const polls0 = livePolls();
await tick();
l = ss(A);
check("10 next poll appends, oldest first", l.length === before + (livePolls() - polls0) && l[0].at <= l[l.length - 1].at, l.length);
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
store["ss:" + A] = JSON.stringify(Array.from({ length: 60 }, (_, i) => ({ at: i, status: {}, penalty: null, events: [] })));
live = [fx(A, SAU, "P", 120, 1, 1, { home: 3, away: 3 })];
await tick();
l = ss(A);
check("10 capped at 60 entries, newest kept", l.length === 60 && l[59].penalty.home === 3 && l[0].at >= 1, [l.length, l[0], l[59]]);
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
store["ss:" + A] = "not json";
live = [fx(A, SAU, "P", 120, 1, 1)];
await tick();
check("10 corrupt old value is replaced, null penalty kept as sent", ss(A).length >= 1 && ss(A)[0].penalty.home === null, ss(A));
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
live = [{ ...fx(A, SAU, "P", 120, 1, 1), goals: undefined }];
await tick();
check("10 snapshot with no goals object: nulls, no crash", JSON.stringify(ss(A)[0].goals) === '{"home":null,"away":null}', ss(A));
reset({ [A]: entry(SAU, "P", 120, 1, 1) });
ssPutFails = true;
live = [fx(A, SAU, "P", 120, 1, 1, { home: 1, away: 1 }), fx(C, SAU, "2H", 70, 0, 0)];
await tick();
check("10 a snapshot KV failure does not stop the feed", payload().m[A] && JSON.stringify(payload().m[A].p) === '{"h":1,"a":1}' && payload().m[C], payload());
reset({ [A]: entry(SAU, "2H", 90, 1, 1) });
live = [fx(A, SAU, "ET", 100, 1, 1)];
await tick();
check("10 no snapshot outside status P", !(("ss:" + A) in store));

origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
