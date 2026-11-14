// Cups live, phase 1 (8 Nov 2026): a live-only competition (UAE-LC 302) rides the fixtures?live= poll and reaches the payload but sends
// no push of any type; "Penalty Shootout" events never reach the timeline, the scorers or a push (any competition); AWD/WO are final.
// Each scenario runs a league fixture next to the live-only one, so a filter that blocks everything fails too.
// In-memory KV + D1 (all migrations), fake provider, queue messages captured. No network.
// Run: node --no-warnings test_cups_live.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_cups_live_test.mjs");
// (15 Nov 2026) all cups are live + push in the shipped worker; this test exercises the live-only mechanism, so it runs on a variant
// with the 14 Nov pilot sets: LIVE_ONLY = [302] (UAE-LC), PUSH_CUP = [] (both lines rewritten by regex, whatever is shipped).
const PILOT = (s) => s
  .replace(/const LIVE_ONLY_LEAGUE_IDS = new Set\(\[[^\]]*\]\);/, "const LIVE_ONLY_LEAGUE_IDS = new Set([302]);")
  .replace(/const PUSH_CUP_LEAGUE_IDS = new Set\(\[[^\]]*\]\);/, "const PUSH_CUP_LEAGUE_IDS = new Set([]);");
fs.writeFileSync(tmp, PILOT(fs.readFileSync(new URL("./worker.js", import.meta.url), "utf8")));
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

const LO = 302, SAU = 307, CUP = 900001, LGE = 900002;
const CT = { h: 2879, a: 2882 }, LT = { h: 2939, a: 2932 };
const NOW = Math.floor(Date.now() / 1000);
let store, queue, calls, live, ids, eventsReply, kickoffs;
const fx = (id, lg, t, s, el, h, a, events = []) => ({ fixture: { id, status: { short: s, elapsed: el } }, goals: { home: h, away: a }, events,
  teams: { home: { id: t.h, name: "H" }, away: { id: t.a, name: "A" } }, league: { id: lg } });
const ev = (type, detail, el, extra, name, side, comments = null) => ({ time: { elapsed: el, extra }, type, detail, comments,
  team: { id: side }, player: { id: 77, name }, assist: {} });
const hd = { "x-ratelimit-requests-remaining": "5000" };
const J = (o) => new Response(JSON.stringify(o), { status: 200, headers: hd });
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.includes("next_kickoffs.json")) return kickoffs ? new Response(JSON.stringify(kickoffs), { status: 200 }) : new Response("{}", { status: 404 });
  if (!url.startsWith("https://v3.football.api-sports.io")) return new Response("{}", { status: 404 });
  calls.push(url);
  if (url.includes("/fixtures?live=")) return J({ errors: [], response: live });
  if (url.includes("/fixtures?ids=")) return J({ errors: [], response: ids });
  if (url.includes("/fixtures/events")) return J({ errors: [], response: eventsReply });
  return J({ errors: [], response: [] });
};
const KV = { get: async (k) => (k in store ? store[k] : null), put: async (k, v) => { store[k] = v; }, delete: async (k) => { delete store[k]; } };
const GOAL_QUEUE = { send: async (b) => { queue.push(b); } };
const env = { API_KEY: "k", LIVE_KV: KV, DB, GOAL_QUEUE, GOAL_PUSH: "on", VAPID_PUBLIC_KEY: "p", VAPID_PRIVATE_KEY: "q" };
const origLog = console.log;
console.log = () => {};
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };

const PUSH = new Set(["goal", "cancel", "alert", "goal_scorer"]);
const pushes = () => queue.filter((m) => PUSH.has(m.kind));
const pushesOf = (id) => pushes().filter((m) => m.fixture === id);
const kinds = (id) => pushesOf(id).map((m) => (m.kind === "alert" ? m.evt : m.kind)).sort();
const rows = (t, id) => db.prepare(`SELECT COUNT(*) n FROM ${t} WHERE fixture = ?`).get(id).n;
const payload = () => JSON.parse(store.live);
function reset(prevM = null) {
  store = {}; queue = []; calls = []; live = []; ids = []; eventsReply = []; kickoffs = null;
  db.exec("DELETE FROM sent; DELETE FROM ev_sent; DELETE FROM goal_log");
  store.live = JSON.stringify({ t: prevM ? NOW - 60 : NOW - 3600, ve: 1, m: prevM || {} });   // empty + recent = idle skip
}
let worker = await loadWorker();
const tick = () => worker.scheduled({}, env, {});
const entry = (lg, t, s, e, h, a) => ({ h, a, e, s, th: t.h, ta: t.a, lg, nh: "H", na: "A" });

// ── 2a/2b: live-only cup: on the poll and in the payload, zero pushes through a whole match; the league next to it is unchanged ──
reset();
live = [fx(CUP, LO, CT, "1H", 2, 0, 0), fx(LGE, SAU, LT, "1H", 2, 0, 0)];
await tick();
const q = calls.find((u) => u.includes("fixtures?live=")) || "";
const liveIds = (q.match(/live=([\d-]+)/) || [, ""])[1].split("-");
check("2b one poll, 11 ids, UAE-LC 302 included", liveIds.length === 11 && liveIds.includes("302"), liveIds);
check("2a live-only fixture is in m with its league id", payload().m[CUP] && payload().m[CUP].lg === LO, payload().m);
check("2a kick-off: league pushes, live-only does not", kinds(LGE).join() === "ko" && kinds(CUP).length === 0, pushes());

const incidents = (side) => [ev("Goal", "Normal Goal", 10, null, "A. Scorer", side), ev("Card", "Red Card", 11, null, "B. Red", side),
  ev("Goal", "Missed Penalty", 12, null, "C. Miss", side)];
live = [fx(CUP, LO, CT, "1H", 13, 1, 0, incidents(CT.h)), fx(LGE, SAU, LT, "1H", 13, 1, 0, incidents(LT.h))];
await tick();
check("2a goal + red + missed pen: league gets all three (plus the earlier ko)", kinds(LGE).join() === "goal,ko,mp,red", kinds(LGE));
check("2a goal + red + missed pen: live-only gets none", kinds(CUP).length === 0, pushesOf(CUP));
check("2a live-only events still reach the timeline (v)", (payload().v || {})[CUP] && payload().v[CUP].length === 3, payload().v);
check("2a live-only goal still queues the page scorers", queue.some((m) => m.kind === "live_scorers" && m.fixture === CUP), queue);
check("2a live-only leaves no sent / ev_sent rows", rows("sent", CUP) === 0 && rows("ev_sent", CUP) === 0, [rows("sent", CUP), rows("ev_sent", CUP)]);

live = [fx(CUP, LO, CT, "HT", 45, 1, 0), fx(LGE, SAU, LT, "HT", 45, 1, 0)];
await tick();
live = [fx(CUP, LO, CT, "2H", 46, 1, 0), fx(LGE, SAU, LT, "2H", 46, 1, 0)];
await tick();
live = [fx(CUP, LO, CT, "2H", 60, 0, 0), fx(LGE, SAU, LT, "2H", 60, 0, 0)];
await tick();
check("2a HT / 2H / goal cancelled: league pushes, live-only does not",
  ["ht", "sh", "cancel"].every((k) => kinds(LGE).includes(k)) && kinds(CUP).length === 0, [kinds(LGE), kinds(CUP)]);
live = [];
ids = [fx(CUP, LO, CT, "FT", 90, 2, 1), fx(LGE, SAU, LT, "FT", 90, 2, 1)];
await tick();
check("2a full-time: result in f for both", payload().f[CUP].s === "FT" && payload().f[LGE].s === "FT" && !payload().m[CUP], payload());
check("2a full-time + late goals: league pushes, live-only does not", kinds(LGE).includes("ft") && kinds(LGE).includes("goal") && kinds(CUP).length === 0, [kinds(LGE), kinds(CUP)]);

// reminder path is closed too, even if a live-only row ever reached the kickoffs file
reset();
worker = await loadWorker();
kickoffs = { t: NOW, k: [], v: {}, f: [[NOW + 1800, CUP, CT.h, CT.a, LO, "H", "A"], [NOW + 1800, LGE, LT.h, LT.a, SAU, "H", "A"]] };
await tick();
check("2a reminder: league yes, live-only no", kinds(LGE).join() === "rem" && kinds(CUP).length === 0, pushes());
worker = await loadWorker();
kickoffs = null;

// subscribing to the live-only competition is refused; the league cap is unchanged
const b64u = (n) => Buffer.alloc(n, 7).toString("base64url");
const r = await worker.fetch(new Request("https://w.example/push/subscribe", { method: "POST",
  headers: { Origin: "https://saffara.app", "Content-Type": "application/json", "CF-Connecting-IP": "3.3.3.3" },
  body: JSON.stringify({ subscription: { endpoint: "https://fcm.googleapis.com/fcm/send/x1", keys: { p256dh: b64u(65), auth: b64u(16) } }, teams: [LT.h], leagues: [302], lang: "ar" }) }), { DB });
check("2a league subscription to 302 is rejected", r.status === 400, r.status);

// ── 2c: Penalty Shootout ──
const SO = "Penalty Shootout";
const reg = (side) => ev("Goal", "Normal Goal", 30, null, "R. Real", side);
const kicks = (side) => [ev("Goal", "Penalty", 120, 1, "K. Scored", side, SO), ev("Goal", "Missed Penalty", 120, 2, "K. Missed", side, SO)];
reset({ [LGE]: entry(SAU, LT, "P", 120, 1, 1) });
store.live = JSON.stringify({ t: NOW - 60, ve: 1, v: { [LGE]: [[30, 0, "g", "n", "R. Real", "", "h", 77, null]] }, m: { [LGE]: entry(SAU, LT, "P", 120, 1, 1) } });
live = [fx(LGE, SAU, LT, "P", 120, 1, 1, [reg(LT.h), ...kicks(LT.h)])];
await tick();
const vRows = (payload().v || {})[LGE] || [];
check("2c shootout kicks are dropped from the live timeline, the real goal stays", vRows.length === 1 && vRows[0][4] === "R. Real", vRows);
check("2c no 'missed penalty' push for a missed kick", kinds(LGE).length === 0, pushes());
const evStore = store["ev:" + LGE] ? JSON.parse(store["ev:" + LGE]) : null;
check("2c ev:<id> holds no kicks", !evStore || evStore.l.every((x) => x[4] === "R. Real"), evStore);

live = [fx(LGE, SAU, LT, "P", 120, 2, 1, [reg(LT.h), ...kicks(LT.h)])];
await tick();
check("2c score moving during P is no goal push", kinds(LGE).length === 0, pushes());
live = [];
ids = [fx(LGE, SAU, LT, "PEN", 120, 1, 1, [reg(LT.h), ...kicks(LT.h)])];
await tick();
check("2c final below an inflated P score: no 'goal cancelled', FT sent", kinds(LGE).join() === "ft", kinds(LGE));
check("2c final PEN lands in f", payload().f[LGE].s === "PEN" && payload().f[LGE].h === 1, payload().f);
const fin = store["ev:" + LGE] ? JSON.parse(store["ev:" + LGE]) : null;
check("2c final ev:<id> holds no kicks", fin && fin.ft === 1 && fin.l.length === 1 && fin.l[0][4] === "R. Real", fin);

// a real goal missed just before the shootout is still announced
reset({ [LGE]: entry(SAU, LT, "P", 120, 1, 1) });
ids = [fx(LGE, SAU, LT, "PEN", 120, 2, 1)];
await tick();
check("2c real goal found only at the final is still pushed", kinds(LGE).join() === "ft,goal", kinds(LGE));

// control: a missed penalty in normal time still alerts
reset({ [LGE]: entry(SAU, LT, "2H", 70, 1, 0) });
live = [fx(LGE, SAU, LT, "2H", 71, 1, 0, [ev("Goal", "Missed Penalty", 70, null, "N. Miss", LT.h)])];
await tick();
check("2c normal-time missed penalty still alerts", kinds(LGE).join() === "mp", kinds(LGE));

// scorers list ignores kicks
reset();
eventsReply = [reg(LT.h), ...kicks(LT.h)];
await worker.queue({ messages: [{ body: { kind: "live_scorers", fixture: LGE, th: LT.h, ta: LT.a, h: 1, a: 0, step: 0, ts: Date.now() }, ack() {}, retry() {} }] }, env);
const sc = store["sc:" + LGE] ? JSON.parse(store["sc:" + LGE]).l : [];
check("2c page scorers exclude kicks", sc.length === 1 && sc[0][3].includes("Real"), sc);

// ── 2d: AWD / WO ──
const P2 = 900003;
reset({ [CUP]: entry(LO, CT, "2H", 60, 1, 1), [LGE]: entry(SAU, LT, "2H", 60, 1, 1), [P2]: entry(LO, { h: 1, a: 2 }, "1H", 20, 0, 0) });
ids = [fx(CUP, LO, CT, "AWD", 60, 3, 0), fx(LGE, SAU, LT, "AWD", 60, 3, 0), fx(P2, LO, { h: 1, a: 2 }, "WO", 20, null, null)];
await tick();
let p = payload();
check("2d AWD and WO are final: all three in f, none left in m / g / r",
  [CUP, LGE, P2].every((i) => p.f[i]) && !Object.keys(p.m).length && !p.g && !p.r, p);
check("2d statuses and scores kept (AWD 3-0, WO null)", p.f[CUP].s === "AWD" && p.f[CUP].h === 3 && p.f[P2].s === "WO" && p.f[P2].h === null, p.f);
check("2d live-only: no push at all", kinds(CUP).length === 0 && kinds(P2).length === 0, [kinds(CUP), kinds(P2)]);
check("2d league: full-time push, and no goal or cancel push from the awarded score", kinds(LGE).join() === "ft", kinds(LGE));
calls = [];
store.live = JSON.stringify({ ...payload(), t: NOW - 3600 });   // past the idle window, so this tick really polls
await tick();
check("2d live poll ran", calls.some((u) => u.includes("fixtures?live=")), calls);
check("2d polling stopped: no further fixtures?ids lookup", !calls.some((u) => u.includes("fixtures?ids=")), calls);

// source check: the shared constants the scenarios rely on
const src = fs.readFileSync(new URL("./worker.js", import.meta.url), "utf8");
check("LEAGUE_IDS (subscribable) still comes from ACTIVE_LEAGUE_IDS only", src.includes("const LEAGUE_IDS = new Set(ACTIVE_LEAGUE_IDS)"));

origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
