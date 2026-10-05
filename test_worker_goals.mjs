// Scenarios for goal detection logging in worker.js (batch 1). Run: node test_worker_goals.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const tmp = path.join(os.tmpdir(), "worker_under_test.mjs");
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

// 5) fixture leaves the feed: no event, 'f' logic unchanged
r = await run({ 3: mEntry(3, 2, 1) }, [], [{ fixture: { id: 3, status: { short: "FT" } }, goals: { home: 3, away: 1 } }]);
check("match leaves feed -> no event; f has final score", r.logs.length === 0 && r.stored.f && r.stored.f[3].h === 3 && r.stored.f[3].a === 1 && r.stored.f[3].s === "FT" && Object.keys(r.stored.m).length === 0, r);

// 6) unchanged score and null->0 start
r = await run({ 1: mEntry(1, 1, 1), 4: { h: null, a: null, e: 1, s: "1H" } }, [fx(1, 1, 1), fx(4, 0, 0, "1H", 2)]);
check("no change / null->0 -> no event", r.logs.length === 0, r.logs);

// 7) public payload keeps old fields
r = await run({ 1: mEntry(1, 0, 0) }, [fx(1, 0, 0)]);
const e = r.stored.m[1];
check("payload keeps t, m.{h,a,e,s}", typeof r.stored.t === "number" && ["h", "a", "e", "s"].every((k) => k in e), r.stored);

process.exit(fail ? 1 : 0);
