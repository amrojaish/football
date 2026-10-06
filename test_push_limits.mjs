// Public-launch protections on /push/*: per-IP hourly limit (429), global subscription cap (503),
// 50-team cap, replace-list semantics, unsubscribe, /push/teams. No network: worker.fetch() + node:sqlite D1 shim.
// Run: node --no-warnings test_push_limits.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_limits_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const worker = (await import(pathToFileURL(tmp).href + "?" + Date.now())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const TEAMS = [962, 964, 965, 968, 969, 971, 973, 974, 975, 976];   // valid ids (TEAM_IDS)
const MANY = [962,964,965,968,969,971,973,974,975,976,977,1030,1031,1032,1036,1037,1039,1040,1041,1044,1046,1048,1074,1075,1572,1574,1575,1576,
  1577,2865,2867,2868,2869,2870,2871,2872,2873,2874,2875,2876,2877,2879,2893,2894,2895,2896,2897,2898,2899,2900,2901];   // 51 ids
const b64u = (n) => Buffer.alloc(n, 7).toString("base64url");
const sub = (id) => ({ endpoint: "https://fcm.googleapis.com/fcm/send/" + id, keys: { p256dh: b64u(65), auth: b64u(16) } });
const ORIGIN = "https://saffara.app";
const call = (p, body, ip = "1.1.1.1", env = {}) => worker.fetch(new Request("https://w.example" + p, {
  method: "POST", headers: { Origin: ORIGIN, "Content-Type": "application/json", "CF-Connecting-IP": ip }, body: JSON.stringify(body) }),
  { DB, ...env });
const subscribe = (id, teams, ip, env, lang = "ar") => call("/push/subscribe", { subscription: sub(id), teams, lang }, ip, env);
const teamsOf = (id) => db.prepare("SELECT team_id FROM sub_teams WHERE endpoint = ? ORDER BY team_id").all(sub(id).endpoint).map((r) => r.team_id);
const reset = () => db.exec("DELETE FROM subscriptions; DELETE FROM sub_teams; DELETE FROM rate_limit");

let fail = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) add / replace / remove semantics (the API replaces the whole list)
reset();
let r = await subscribe("a", [962], "9.9.9.1");
check("subscribe club A -> 200, list [A]", r.status === 200 && JSON.stringify(teamsOf("a")) === "[962]", [r.status, teamsOf("a")]);
r = await subscribe("a", [962, 964], "9.9.9.1");
check("add club B -> list [A,B]", r.status === 200 && JSON.stringify(teamsOf("a")) === "[962,964]", teamsOf("a"));
r = await subscribe("a", [964], "9.9.9.1");
check("remove club A -> list [B] only", JSON.stringify(teamsOf("a")) === "[964]", teamsOf("a"));
r = await call("/push/teams", { endpoint: sub("a").endpoint, auth: sub("a").keys.auth }, "9.9.9.1");
let j = await r.json();
check("/push/teams returns the stored list", r.status === 200 && JSON.stringify(j.teams) === "[964]", j);
r = await call("/push/teams", { endpoint: sub("a").endpoint, auth: b64u(17) }, "9.9.9.1");
check("/push/teams with wrong auth -> 403", r.status === 403);
r = await call("/push/teams", { endpoint: sub("nobody").endpoint, auth: sub("a").keys.auth }, "9.9.9.1");
j = await r.json();
check("/push/teams unknown endpoint -> empty list", r.status === 200 && j.teams.length === 0, j);
r = await call("/push/unsubscribe", { endpoint: sub("a").endpoint, auth: sub("a").keys.auth }, "9.9.9.1");
check("removing the last club = /push/unsubscribe -> row + teams gone",
  r.status === 200 && teamsOf("a").length === 0 && db.prepare("SELECT COUNT(*) c FROM subscriptions").get().c === 0);

// 2) 50-team cap
reset();
r = await subscribe("m", MANY.slice(0, 50), "9.9.9.2");
check("50 clubs accepted", r.status === 200 && teamsOf("m").length === 50, r.status);
r = await subscribe("m", MANY.slice(0, 51), "9.9.9.2");
j = await r.json();
check("51 clubs -> 400 bad teams", r.status === 400 && j.error === "bad teams", [r.status, j]);

// 3) per-IP hourly limit: 20 pass, the 21st is 429 with Retry-After; other IPs unaffected
reset();
const codes = [];
for (let i = 0; i < 21; i++) codes.push((await subscribe("r" + (i % 3), [962], "5.5.5.5")).status);
check("20 requests/hour OK, 21st -> 429", codes.slice(0, 20).every((c) => c === 200) && codes[20] === 429, codes);
r = await subscribe("r0", [962], "5.5.5.5");
const ra = Number(r.headers.get("Retry-After"));
check("  429 carries Retry-After (1..3600 s) and error=rate_limited", r.status === 429 && ra >= 1 && ra <= 3600 && (await r.json()).error === "rate_limited", [r.status, ra]);
r = await subscribe("other", [962], "6.6.6.6");
check("  a different IP is not limited", r.status === 200, r.status);
r = await call("/push/unsubscribe", { endpoint: sub("r0").endpoint, auth: sub("r0").keys.auth }, "5.5.5.5");
check("  unsubscribe is never rate limited", r.status === 200, r.status);
const rows = db.prepare("SELECT k FROM rate_limit").all();
check("  raw IP is not stored (hash only)", rows.length >= 1 && rows.every((x) => !x.k.includes("5.5.5.5") && /^[0-9a-f]{16}:\d+$/.test(x.k)), rows);
// pruning: a request that opens a new (IP, hour) bucket deletes buckets whose hour has passed
db.exec("UPDATE rate_limit SET exp = 1, k = k || 'x'");
await subscribe("p", [962], "7.7.7.7");
check("  pruning removes buckets whose hour has passed", db.prepare("SELECT COUNT(*) c FROM rate_limit WHERE exp = 1").get().c === 0);
// env override
reset();
codes.length = 0;
for (let i = 0; i < 3; i++) codes.push((await subscribe("e", [962], "4.4.4.4", { SUBSCRIBE_PER_HOUR: "2" })).status);
check("SUBSCRIBE_PER_HOUR env override respected", JSON.stringify(codes) === "[200,200,429]", codes);

// 4) global cap: new subscriptions -> 503, existing endpoints can still update/remove
reset();
const env2 = { MAX_SUBSCRIPTIONS: "3" };
for (let i = 0; i < 3; i++) await subscribe("c" + i, [962], "8.8.8." + i, env2);
r = await subscribe("c3", [962], "8.8.8.9", env2);
j = await r.json();
check("cap reached -> new subscriber gets 503 {error:full}", r.status === 503 && j.error === "full" && db.prepare("SELECT COUNT(*) c FROM subscriptions").get().c === 3, [r.status, j]);
r = await subscribe("c1", [962, 964], "8.8.8.1", env2);
check("  existing subscriber can still update its list", r.status === 200 && teamsOf("c1").length === 2, r.status);
r = await call("/push/unsubscribe", { endpoint: sub("c0").endpoint, auth: sub("c0").keys.auth }, "8.8.8.0", env2);
r = await subscribe("c3", [962], "8.8.8.9", env2);
check("  after someone leaves, a new subscriber fits again", r.status === 200, r.status);
reset();
for (let i = 0; i < 2; i++) await subscribe("d" + i, [962], "3.3.3." + i, { MAX_SUBSCRIPTIONS: "" });
check("default cap is 5000 (empty env value -> default)", db.prepare("SELECT COUNT(*) c FROM subscriptions").get().c === 2);

// 5) invalid / foreign-origin requests still handled before touching limits wrongly
r = await worker.fetch(new Request("https://w.example/push/subscribe", { method: "POST", headers: { Origin: "https://evil.example" }, body: "{}" }), { DB });
check("foreign origin still rejected (400)", r.status === 400, r.status);

process.exit(fail ? 1 : 0);
