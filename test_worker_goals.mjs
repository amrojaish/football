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

async function run(prevM, live, finalsResp) {
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
    get: async () => JSON.stringify({ t: NOW - 3600, m: prevM }),
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

// 5f) final never resolved (still 2H in ids lookup; prev older than GIVEUP) -> no late event, written without f
r = await run({ 11: mEntry(11, 0, 0) }, [], [ft(11, 1, 0, "2H")]);
check("final not ready after give-up -> no event, no f", r.logs.length === 0 && !r.stored.f, r);

// 6) unchanged score and null->0 start
r = await run({ 1: mEntry(1, 1, 1), 4: { h: null, a: null, e: 1, s: "1H" } }, [fx(1, 1, 1), fx(4, 0, 0, "1H", 2)]);
check("no change / null->0 -> no event", r.logs.length === 0, r.logs);

// 7) public payload keeps old fields
r = await run({ 1: mEntry(1, 0, 0) }, [fx(1, 0, 0)]);
const e = r.stored.m[1];
check("payload keeps t, m.{h,a,e,s}", typeof r.stored.t === "number" && ["h", "a", "e", "s"].every((k) => k in e), r.stored);

process.exit(fail ? 1 : 0);
