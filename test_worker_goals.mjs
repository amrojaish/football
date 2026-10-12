// Scenarios for goal detection logging in worker.js (batch 1). Run: node test_worker_goals.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
const url_to_path = (u) => fileURLToPath(u);

// ⚠️ داخل المستودع (.wrangler/ مُتجاهَل) كي يجد node مجلد node_modules (استيراد مكتبة الدفع)
const tmpDir = new URL("./.wrangler/tmp/", import.meta.url);
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(url_to_path(tmpDir), "worker_under_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Date.now())).default;

const NOW = Math.floor(Date.now() / 1000);
const fx = (id, h, a, status = "2H", el = 60) => ({
  fixture: { id, status: { short: status, elapsed: el } },
  goals: { home: h, away: a },
  teams: { home: { id: id * 10 + 1 }, away: { id: id * 10 + 2 } },
  league: { id: 387 },
});
const mEntry = (id, h, a) => ({ h, a, e: 60, s: "2H", th: id * 10 + 1, ta: id * 10 + 2, lg: 387 });

async function run(prevM, live, finalsResp, prevExtra = {}) {
  const logs = [];
  let puts = 0, apiCalls = 0, stored = null;
  const origLog = console.log, origFetch = globalThis.fetch;
  console.log = (s) => logs.push(s);
  globalThis.fetch = async (url) => {
    apiCalls++;
    const body = String(url).includes("ids=") ? (finalsResp || []) : live;
    return { ok: true, json: async () => ({ errors: [], response: body }) };
  };
  const kv = {
    get: async () => JSON.stringify({ t: Object.keys(prevM).length ? NOW - 60 : NOW - 3600, m: prevM, ...prevExtra }),
    put: async (k, v) => { puts++; stored = JSON.parse(v); },
  };
  try { await worker.scheduled({}, { API_KEY: "x", LIVE_KV: kv }, {}); }
  finally { console.log = origLog; globalThis.fetch = origFetch; }
  return { logs: logs.map((l) => JSON.parse(l)), puts, apiCalls, stored };
}

let fail = 0;
const check = (name, cond, extra) => { console.log((cond ? "PASS " : "FAIL ") + name + (cond ? "" : " " + JSON.stringify(extra))); if (!cond) fail++; };

// 1) 0-0 -> 1-0
let r = await run({ 1: mEntry(1, 0, 0) }, [fx(1, 1, 0)]);
check("goal 0-0 -> 1-0", r.logs.length === 1 && r.logs[0].type === "goal" && r.logs[0].h === 1 && r.logs[0].prev_h === 0 && r.logs[0].th === 11 && r.logs[0].ta === 12 && r.logs[0].league === 387 && r.logs[0].minute === 60, r.logs);
check("  one KV write, one API call", r.puts === 1 && r.apiCalls === 1, r);
console.log("  line:", JSON.stringify(r.logs[0]));

// 2) 1-0 -> 2-1 in one poll
r = await run({ 1: mEntry(1, 1, 0) }, [fx(1, 2, 1)]);
check("two goals in one poll -> one goal line, prev 1-0 now 2-1", r.logs.length === 1 && r.logs[0].type === "goal" && r.logs[0].prev_h === 1 && r.logs[0].prev_a === 0 && r.logs[0].h === 2 && r.logs[0].a === 1, r.logs);

// 3) 1-0 -> 0-0 cancelled
r = await run({ 1: mEntry(1, 1, 0) }, [fx(1, 0, 0)]);
check("cancelled 1-0 -> 0-0", r.logs.length === 1 && r.logs[0].type === "goal_cancelled" && r.logs[0].prev_h === 1 && r.logs[0].h === 0, r.logs);

// 4) new fixture at 2-1 (not in prev)
r = await run({}, [fx(2, 2, 1)]);
check("new fixture mid-match -> no event, stored with ids", r.logs.length === 0 && r.stored.m[2].th === 21 && r.stored.m[2].lg === 387, r);

// 5) fixture leaves the feed 2-1 -> final 3-1: f has the final score AND the missed goal is emitted (late)
const ft = (id, h, a, s = "FT") => ({ fixture: { id, status: { short: s } }, goals: { home: h, away: a } });
r = await run({ 3: mEntry(3, 2, 1) }, [], [ft(3, 3, 1)]);
check("match leaves feed 2-1 -> FT 3-1: f set, one late goal 2-1>3-1", r.stored.f && r.stored.f[3].h === 3 && r.stored.f[3].a === 1 && r.stored.f[3].s === "FT" && Object.keys(r.stored.m).length === 0
  && r.logs.length === 1 && r.logs[0].type === "goal" && r.logs[0].late === true && r.logs[0].prev_h === 2 && r.logs[0].h === 3 && r.logs[0].a === 1 && r.logs[0].minute === null, r);

// 5a2) f entries carry team ids + league id when the provider returns them (live table, 12 Oct); absent otherwise (above: ft() has none)
const ftFull = (id, h, a, th, ta, lg, s = "FT") => ({ ...ft(id, h, a, s), teams: { home: { id: th }, away: { id: ta } }, league: { id: lg } });
r = await run({ 3: mEntry(3, 2, 1) }, [], [ftFull(3, 3, 1, 31, 32, 387)]);
check("f entry gets th/ta/lg from the ids response; h/a/s unchanged", r.stored.f[3].th === 31 && r.stored.f[3].ta === 32 && r.stored.f[3].lg === 387
  && r.stored.f[3].h === 3 && r.stored.f[3].a === 1 && r.stored.f[3].s === "FT", r.stored.f);
r = await run({ 3: mEntry(3, 2, 1) }, [], [ft(3, 3, 1)]);
check("f entry without teams/league in the response: no th/ta/lg keys (backward compatible)", !("th" in r.stored.f[3]) && !("ta" in r.stored.f[3]) && !("lg" in r.stored.f[3]), r.stored.f);
r = await run({ 3: mEntry(3, 2, 1) }, [], [ftFull(3, 1, 1, 31, 32, 387, "SUSP")]);
check("suspended match: f entry also gets ids (the site ignores non-final statuses)", r.stored.f[3].s === "SUSP" && r.stored.f[3].lg === 387, r.stored.f);

// 5b) 0-0 then FT 2-0 (1627993): one event per missing goal
r = await run({ 5: mEntry(5, 0, 0) }, [], [ft(5, 2, 0)]);
check("0-0 -> FT 2-0 -> two late goals 0-0>1-0, 1-0>2-0", r.logs.length === 2 && r.logs.every((l) => l.type === "goal" && l.late) && r.logs[0].h === 1 && r.logs[0].prev_h === 0 && r.logs[1].h === 2 && r.logs[1].prev_h === 1, r.logs);

// 5c) 0-4 at 74' then FT 0-5 (1603041)
r = await run({ 6: { ...mEntry(6, 0, 4), e: 74 } }, [], [ft(6, 0, 5)]);
check("0-4 -> FT 0-5 -> one late goal 0-4>0-5", r.logs.length === 1 && r.logs[0].a === 5 && r.logs[0].prev_a === 4 && r.logs[0].h === 0 && r.logs[0].late === true, r.logs);

// 5d) goal already seen: stored score equals final -> no event
r = await run({ 7: mEntry(7, 0, 5) }, [], [ft(7, 0, 5)]);
check("already seen (0-5 -> FT 0-5) -> no event", r.logs.length === 0 && r.stored.f[7].a === 5, r.logs);

// 5e) AET/PEN counts too; final lower than stored -> cancelled; abandoned lower -> nothing
r = await run({ 8: mEntry(8, 1, 1) }, [], [ft(8, 2, 1, "AET")]);
check("AET 1-1 -> 2-1 -> late goal", r.logs.length === 1 && r.logs[0].type === "goal" && r.logs[0].h === 2, r.logs);
r = await run({ 9: mEntry(9, 2, 0) }, [], [ft(9, 1, 0)]);
check("FT lower than stored -> goal_cancelled late", r.logs.length === 1 && r.logs[0].type === "goal_cancelled" && r.logs[0].prev_h === 2 && r.logs[0].h === 1, r.logs);
r = await run({ 10: mEntry(10, 2, 0) }, [], [ft(10, 1, 0, "ABD")]);
check("ABD lower than stored -> no event", r.logs.length === 0, r.logs);

// 5f) final not resolved yet (ids lookup still says 2H): fixture stays pending in m (stale score) with g, no event, poll still writes
r = await run({ 11: mEntry(11, 0, 0) }, [], [ft(11, 1, 0, "2H")]);
check("final not ready -> pending: kept in m, g set, no event, written", r.logs.length === 0 && r.puts === 1 && r.stored.m[11] && r.stored.g && r.stored.g[11] > 0 && !r.stored.f, r);

// 5g) pending past GIVEUP -> dropped without f
r = await run({ 11: mEntry(11, 0, 0) }, [], [ft(11, 1, 0, "2H")], { g: { 11: NOW - 11 * 60 } });
check("pending older than GIVEUP -> dropped, no f, no g", r.logs.length === 0 && !r.stored.m[11] && !r.stored.f && !r.stored.g, r);

// 5h) pending keeps its original g and resolves later with a late goal
r = await run({ 11: mEntry(11, 0, 0) }, [], [ft(11, 1, 0)], { g: { 11: NOW - 120 } });
check("pending resolves to FT 1-0 -> late goal, f set, no g", r.logs.length === 1 && r.logs[0].late && r.stored.f[11].h === 1 && !r.stored.m[11] && !r.stored.g, r);

// 5i) DECOUPLED: fixture 12 pending (not FT yet) while fixture 1 scores in the same poll -> goal still detected and written
r = await run({ 12: mEntry(12, 0, 0), 1: mEntry(1, 0, 0) }, [fx(1, 1, 0)], [ft(12, 0, 0, "2H")]);
check("pending fixture does not block another live match's goal", r.logs.length === 1 && r.logs[0].fixture === 1 && r.logs[0].type === "goal" && r.logs[0].h === 1
  && r.puts === 1 && r.stored.m[1].h === 1 && r.stored.m[12] && r.stored.g[12] > 0, r);

// 6) unchanged score and null->0 start
r = await run({ 1: mEntry(1, 1, 1), 4: { h: null, a: null, e: 1, s: "1H" } }, [fx(1, 1, 1), fx(4, 0, 0, "1H", 2)]);
check("no change / null->0 -> no event", r.logs.length === 0, r.logs);

// 7) public payload keeps old fields
r = await run({ 1: mEntry(1, 0, 0) }, [fx(1, 0, 0)]);
const e = r.stored.m[1];
check("payload keeps t, m.{h,a,e,s}", typeof r.stored.t === "number" && ["h", "a", "e", "s"].every((k) => k in e), r.stored);

// ── 8) هدّافو المباريات الجارية: جدولة + قراءة sc: + مستهلك live_scorers ──
async function run2(prevM, live, { kvSc = {}, queue = [] } = {}) {
  const origLog = console.log, origFetch = globalThis.fetch; console.log = () => {};
  let stored = null;
  globalThis.fetch = async (url) => ({ ok: true, json: async () => ({ errors: [], response: String(url).includes("ids=") ? [] : live }) });
  const kv = { get: async (k) => (k.startsWith("sc:") ? (kvSc[k] ?? null) : JSON.stringify({ t: NOW - 60, m: prevM })),
               put: async (k, v) => { if (!k.startsWith("sc:")) stored = JSON.parse(v); } };
  try { await worker.scheduled({}, { API_KEY: "x", LIVE_KV: kv, GOAL_QUEUE: { send: async (b, o) => queue.push({ b, o }) } }, {}); }
  finally { console.log = origLog; globalThis.fetch = origFetch; }
  return { stored, queue };
}
let r2 = await run2({ 1: mEntry(1, 0, 0) }, [fx(1, 1, 0)]);
check("goal -> one live_scorers message, delay 45s, no s yet", r2.queue.length === 1 && r2.queue[0].b.kind === "live_scorers" && r2.queue[0].b.fixture === 1 && r2.queue[0].b.h === 1
  && r2.queue[0].o.delaySeconds === 45 && !r2.stored.s, r2);
r2 = await run2({ 1: mEntry(1, 1, 0) }, [fx(1, 1, 0)], { kvSc: { "sc:1": JSON.stringify({ l: [["h", 62, 0, "Calafiori", "", ""]] }) } });
check("no new goal -> no message; stored sc:1 is merged into payload.s", r2.queue.length === 0 && r2.stored.s && r2.stored.s[1][0][3] === "Calafiori", r2);
r2 = await run2({ 1: mEntry(1, 1, 0) }, [fx(1, 1, 0)], { kvSc: { "sc:1": "garbage", "sc:2": JSON.stringify({ l: [["h", 1, 0, "X", "", ""]] }) } });
check("unparsable / unrelated sc keys ignored -> no s", !r2.stored.s, r2.stored);
r2 = await run2({ 1: mEntry(1, 0, 0), 2: mEntry(2, 0, 0) }, [fx(1, 1, 0), fx(2, 0, 1)]);
check("two fixtures score in one poll -> two messages", r2.queue.length === 2, r2.queue);

async function consume(body, evResp, { fail = false } = {}) {
  const puts = {}, dels = [], sent = [], origFetch = globalThis.fetch, origLog = console.log; console.log = () => {};
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("player_names")) return { ok: true, json: async () => ({ 777: { ar: "كالافيوري" }, _n: { "101|Z. Ali": { ar: "زيد علي" } } }) };
    if (fail) return { ok: false, json: async () => ({}) };
    return { ok: true, json: async () => ({ errors: [], response: evResp }) };
  };
  let acked = false;
  try {
    await worker.queue({ messages: [{ body, ack: () => { acked = true; }, retry: () => {} }] },
      { API_KEY: "x", LIVE_KV: { put: async (k, v, o) => { puts[k] = { v: JSON.parse(v), o }; }, delete: async (k) => dels.push(k), get: async () => null },
        GOAL_QUEUE: { send: async (b, o) => sent.push({ b, o }) } });
  } finally { console.log = origLog; globalThis.fetch = origFetch; }
  return { puts, dels, sent, acked };
}
const ev = (min, team, pid, name, detail = "Normal Goal", extra = null) => ({ time: { elapsed: min, extra }, team: { id: team }, player: { id: pid, name }, type: "Goal", detail });
let c = await consume({ kind: "live_scorers", fixture: 9, th: 100, ta: 101, h: 2, a: 1, step: 0 },
  [ev(62, 100, 777, "A. Calafiori"), ev(30, 101, 5, "Z. Ali", "Penalty"), ev(80, 101, 6, "O. Gonzalez", "Own Goal"), { type: "Card", time: { elapsed: 5 }, team: { id: 100 }, player: { id: 1, name: "x" }, detail: "Yellow Card" },
   { ...ev(70, 100, 8, "M. Pen", "Missed Penalty") }]);
const L = c.puts["sc:9"] && c.puts["sc:9"].v.l;
check("consumer: sorted by minute, surname, Arabic only if confirmed, og credited to the OTHER side, pen tag",
  L && L.length === 3 && JSON.stringify(L[0]) === JSON.stringify(["a", 30, 0, "Ali", "زيد علي", "p"]) && JSON.stringify(L[1]) === JSON.stringify(["h", 62, 0, "Calafiori", "كالافيوري", ""])
  && JSON.stringify(L[2]) === JSON.stringify(["h", 80, 0, "Gonzalez", "", "og"]) && c.puts["sc:9"].o.expirationTtl === 8 * 3600 && c.sent.length === 0 && c.acked, c);
c = await consume({ kind: "live_scorers", fixture: 9, th: 100, ta: 101, h: 2, a: 0, step: 0 }, [ev(62, 100, 777, "A. Calafiori")]);
check("lag (1 of 2 goals listed): stores what it has and retries in 90s", c.puts["sc:9"] && c.sent.length === 1 && c.sent[0].b.step === 1 && c.sent[0].o.delaySeconds === 90, c);
c = await consume({ kind: "live_scorers", fixture: 9, th: 100, ta: 101, h: 2, a: 0, step: 2 }, [ev(62, 100, 777, "A. Calafiori")]);
check("lag on the last step: gives up (no more messages)", c.sent.length === 0 && c.acked, c);
c = await consume({ kind: "live_scorers", fixture: 9, th: 100, ta: 101, h: 1, a: 0, step: 0 }, [], { fail: true });
check("provider error: retry, nothing stored", c.sent.length === 1 && !c.puts["sc:9"], c);
c = await consume({ kind: "live_scorers", fixture: 9, th: 100, ta: 101, h: 0, a: 0, step: 0 }, []);
check("all goals cancelled (0-0, no events): key deleted", c.dels.includes("sc:9") && c.sent.length === 0, c);

process.exit(fail ? 1 : 0);
