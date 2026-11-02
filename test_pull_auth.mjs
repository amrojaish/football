// /pull auth (2 Nov 2026): the manual pull needs "Authorization: Bearer <ADMIN_TOKEN>" (same check as /push/admin-test).
// Without it (or with a wrong token / no ADMIN_TOKEN set): 401 {"error":"unauthorized"}, no API-Football request, no KV read/write.
// No network: fake fetch (API-Football live = empty list) and a fake LIVE_KV that counts get/put.
// Run: node --no-warnings test_pull_auth.mjs
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_pull_auth_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

let apiCalls = 0;
globalThis.fetch = async (url) => {
  if (String(url).startsWith("https://v3.football.api-sports.io")) {
    apiCalls++;
    return new Response(JSON.stringify({ errors: [], response: [] }),
      { status: 200, headers: { "x-ratelimit-requests-remaining": "5000" } });
  }
  return new Response("{}", { status: 404 });
};
let kvGets = 0, kvPuts = 0;
const LIVE_KV = { get: async () => { kvGets++; return null; }, put: async () => { kvPuts++; } };
const TOKEN = "s3cret-admin-token";
const env = { API_KEY: "k", ADMIN_TOKEN: TOKEN, LIVE_KV };

const reset = () => { apiCalls = 0; kvGets = 0; kvPuts = 0; };
const call = async (auth, e = env) => {
  const req = new Request("https://saffara-live.example/pull", { headers: auth ? { Authorization: auth } : {} });
  const r = await worker.fetch(req, e, { waitUntil: () => {} });
  let j = null; try { j = await r.json(); } catch (err) {}
  return { s: r.status, j, h: r.headers };
};

let fail = 0, pass = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? pass++ : fail++; };
const untouched = () => apiCalls === 0 && kvGets === 0 && kvPuts === 0;

// no header
reset();
let r = await call(null);
check("no Authorization -> 401 unauthorized", r.s === 401 && r.j && r.j.error === "unauthorized", r);
check("  same cors headers (ACAO *, JSON, no-store)", r.h.get("Access-Control-Allow-Origin") === "*"
  && /application\/json/.test(r.h.get("Content-Type") || "") && r.h.get("Cache-Control") === "no-store");
check("  pull not called: no API request, no KV read/write", untouched(), { apiCalls, kvGets, kvPuts });

// wrong token
reset();
r = await call("Bearer wrong-token");
check("wrong token -> 401", r.s === 401 && r.j.error === "unauthorized", r);
check("  pull not called", untouched(), { apiCalls, kvGets, kvPuts });

// right token, wrong scheme
reset();
r = await call(TOKEN);
check("token without 'Bearer ' -> 401", r.s === 401, r);
check("  pull not called", untouched(), { apiCalls, kvGets, kvPuts });

// ADMIN_TOKEN not configured: even a 'Bearer undefined' never passes
reset();
r = await call("Bearer undefined", { ...env, ADMIN_TOKEN: undefined });
check("ADMIN_TOKEN unset -> 401", r.s === 401, r);
check("  pull not called", untouched(), { apiCalls, kvGets, kvPuts });

// right token -> the pull path runs
reset();
r = await call("Bearer " + TOKEN);
check("right token -> 200", r.s === 200, r);
check("  pull ran: one API-Football live request", apiCalls === 1, { apiCalls });
check("  KV read (prev) and written (new payload)", kvGets === 1 && kvPuts === 1, { kvGets, kvPuts });
check("  payload shape {t, m}", r.j && typeof r.j.t === "number" && r.j.m && typeof r.j.m === "object", r.j);

// the public read route is unchanged (no auth)
reset();
const pub = await worker.fetch(new Request("https://saffara-live.example/"), env, { waitUntil: () => {} });
check("GET / still public -> 200", pub.status === 200, pub.status);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
