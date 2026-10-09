// Idle gate: the worker polls every minute from 10 min before any kickoff (assets/next_kickoffs.json) until 30 min after,
// instead of skipping 5 min after the last idle write. No new API requests. File missing/corrupt = old 5-min idle.
// Run: node --no-warnings test_kickoff_poll.mjs
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_kickoff_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const NOW = Math.floor(Date.now() / 1000);
let apiCalls, fileCalls, kickoffs, fileMode;
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) { apiCalls++; return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200 }); }
  if (url === "https://saffara.app/assets/next_kickoffs.json") {
    fileCalls++;
    if (fileMode === "404") return new Response("nope", { status: 404 });
    if (fileMode === "bad") return new Response("{not json", { status: 200 });
    return new Response(JSON.stringify({ t: NOW, k: kickoffs }), { status: 200 });
  }
  return new Response("{}", { status: 404 });
};
const origLog = console.log;
console.log = () => {};
let puts;
async function tick(prev, ks, mode = "ok", worker = null) {
  apiCalls = 0; fileCalls = 0; puts = 0; kickoffs = ks; fileMode = mode;
  const kv = { get: async () => JSON.stringify(prev), put: async () => { puts++; } };
  await (worker || await loadWorker()).scheduled({}, { API_KEY: "k", LIVE_KV: kv }, {});
}
let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };
const idle = { t: NOW - 60, m: {} };   // idle, last write 1 min ago: normally skipped until 5 min

await tick(idle, []);
check("idle, no kickoffs -> skipped (no API call, no KV write)", apiCalls === 0 && puts === 0, [apiCalls, puts]);
await tick(idle, [NOW + 15 * 60]);
check("kickoff in 15 min -> still skipped", apiCalls === 0 && puts === 0, [apiCalls, puts]);
await tick(idle, [NOW + 9 * 60]);
check("kickoff in 9 min -> polled this minute", apiCalls === 1 && puts === 1, [apiCalls, puts]);
await tick(idle, [NOW - 20 * 60]);
check("kickoff 20 min ago, still not live -> polled", apiCalls === 1 && puts === 1, [apiCalls, puts]);
await tick(idle, [NOW - 40 * 60]);
check("kickoff 40 min ago, never went live -> back to idle skip", apiCalls === 0 && puts === 0, [apiCalls, puts]);
await tick(idle, [NOW - 40 * 60, NOW + 5 * 60, NOW + 300 * 60]);
check("any one kickoff in the window is enough", apiCalls === 1, apiCalls);
await tick(idle, [NOW + 60], "404");
check("file 404 -> old behaviour (skipped)", apiCalls === 0 && puts === 0, [apiCalls, puts]);
await tick(idle, [NOW + 60], "bad");
check("file corrupt -> old behaviour (skipped)", apiCalls === 0 && puts === 0, [apiCalls, puts]);
await tick({ t: NOW - 400, m: {} }, []);
check("idle for 400 s (> 5 min window) -> polled as before", apiCalls === 1 && puts === 1, [apiCalls, puts]);
await tick({ t: NOW - 30, m: { 1: { h: 0, a: 0, e: 10, s: "1H" } } }, []);
check("live matches -> polled, kickoff file not even fetched", apiCalls >= 1 && fileCalls === 0, [apiCalls, fileCalls]);
const w = await loadWorker();
await tick(idle, [NOW + 60], "ok", w);
await tick(idle, [NOW + 60], "ok", w);
check("file cached between minutes in the same isolate (2nd tick fetches nothing)", fileCalls === 0, fileCalls);
console.log = origLog;
origLog(fail ? `${fail} FAILED` : "all passed");
process.exit(fail ? 1 : 0);
