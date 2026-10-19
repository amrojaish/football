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
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0008_sub_matches.sql", "0009_alert_types.sql"])
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

// 6) per-match subscriptions (13 Oct 2026): `matches` optional, replaced as a set, untouched when absent, deleted with the subscription
{
  reset(); db.exec("DELETE FROM sub_matches");
  const mrows = (id) => db.prepare("SELECT fixture FROM sub_matches WHERE endpoint = ? ORDER BY fixture").all(sub(id).endpoint).map((r) => r.fixture);
  const post = (id, extra) => call("/push/subscribe", { subscription: sub(id), teams: [962], lang: "ar", ...extra }, "9.9.9.9", {});
  let r6 = await post("m1", { matches: [1644210, 1612257, 1644210] });
  check("subscribe with matches -> rows stored (deduped), response reports the count", r6.status === 200 && JSON.stringify(mrows("m1")) === "[1612257,1644210]" && (await r6.json()).matches === 2, mrows("m1"));
  r6 = await post("m1", {});
  check("subscribe WITHOUT `matches` (old club button) leaves the match list untouched", r6.status === 200 && JSON.stringify(mrows("m1")) === "[1612257,1644210]", mrows("m1"));
  r6 = await post("m1", { matches: [5] });
  check("subscribe with a new list REPLACES it", JSON.stringify(mrows("m1")) === "[5]", mrows("m1"));
  r6 = await post("m1", { matches: [] });
  check("empty list clears the matches (teams stay)", mrows("m1").length === 0 && teamsOf("m1").length === 1, [mrows("m1"), teamsOf("m1")]);
  for (const [label, bad] of [["21 matches", Array.from({ length: 21 }, (_, i) => i + 1)], ["non-integer", ["x"]], ["zero id", [0]], ["negative id", [-3]], ["not an array", "7"]]) {
    r6 = await post("m2", { matches: bad });
    check(`invalid matches (${label}) -> 400`, r6.status === 400, r6.status);
  }
  await post("m3", { matches: [11, 12] });
  const j = sub("m3");
  const u = await call("/push/unsubscribe", { endpoint: j.endpoint, auth: j.keys.auth }, "9.9.9.9", {});
  check("unsubscribe also deletes the endpoint's match rows", u.status === 200 && mrows("m3").length === 0, mrows("m3"));
}

// 7) alert-type masks + league subscriptions (13 Oct 2026, 3E): tt/mt/lt = {id: mask 1..127}; absent = all on (127); leagues = provider ids
{
  reset(); db.exec("DELETE FROM sub_matches; DELETE FROM sub_leagues");
  const post = (id, extra, ip = "8.8.8.8") => call("/push/subscribe", { subscription: sub(id), teams: [962, 964], lang: "ar", ...extra }, ip, {});
  const tmask = (id) => Object.fromEntries(db.prepare("SELECT team_id, types FROM sub_teams WHERE endpoint = ?").all(sub(id).endpoint).map((r) => [r.team_id, r.types]));
  const mmask = (id) => Object.fromEntries(db.prepare("SELECT fixture, types FROM sub_matches WHERE endpoint = ?").all(sub(id).endpoint).map((r) => [r.fixture, r.types]));
  const lmask = (id) => Object.fromEntries(db.prepare("SELECT league, types FROM sub_leagues WHERE endpoint = ?").all(sub(id).endpoint).map((r) => [r.league, r.types]));
  let r7 = await post("t1", {});
  check("no masks sent (old club button) and nothing stored yet -> new teams get LEGACY = goals only (2): the old button only ever offered goals", r7.status === 200 && JSON.stringify(tmask("t1")) === '{"962":2,"964":2}', tmask("t1"));
  r7 = await post("t1", { tt: { 962: 2 | 16 }, matches: [11, 12], mt: { 11: 4 }, leagues: [233, 387], lt: { 233: 66 } });
  check("masks stored per entity (team 962 = goal+FT, match 11 = HT, league 233 = goal+red); unspecified ones: existing/legacy = goals only (2), new league = default 243 (115 + missed penalty)",
    JSON.stringify(tmask("t1")) === '{"962":18,"964":2}' && JSON.stringify(mmask("t1")) === '{"11":4,"12":2}' && JSON.stringify(lmask("t1")) === '{"233":66,"387":243}', [tmask("t1"), mmask("t1"), lmask("t1")]);
  r7 = await post("t1", { teams: [962] });
  check("resubscribe without leagues leaves the league rows untouched; an old client without masks KEEPS the stored mask of a team that was already there (962 stays 18)", JSON.stringify(lmask("t1")) === '{"233":66,"387":243}' && JSON.stringify(tmask("t1")) === '{"962":18}', [lmask("t1"), tmask("t1")]);
  r7 = await post("t3", { tt: { 962: 115 }, mt: {}, matches: [5], lt: {}, leagues: [233] });
  check("new client sends 115 for a new club; unspecified new match = goals only (2) and unspecified new league = 243", JSON.stringify(tmask("t3")) === '{"962":115,"964":2}' && JSON.stringify(mmask("t3")) === '{"5":2}' && JSON.stringify(lmask("t3")) === '{"233":243}', [tmask("t3"), mmask("t3"), lmask("t3")]);
  r7 = await post("t4", { tt: { 962: 511 }, mt: { 6: 256 }, matches: [6] }, "8.8.4.4");
  check("lineup bit: mask 511 (all, incl. 256) and 256 alone accepted and stored", r7.status === 200 && tmask("t4")["962"] === 511 && JSON.stringify(mmask("t4")) === '{"6":256}', [r7.status, tmask("t4"), mmask("t4")]);
  for (const [label, extra] of [["mask 0", { tt: { 962: 0 } }], ["mask 512 (above ALL_TYPES 511)", { tt: { 962: 512 } }], ["mask string", { mt: { 11: "7" }, matches: [11] }], ["unknown league", { leagues: [999] }], ["21 leagues", { leagues: Array.from({ length: 21 }, (_, i) => i) }], ["tt array", { tt: [1] }]]) {
    r7 = await post("t2", extra, "8.8.8." + label.length);
    check(`invalid ${label} -> 400`, r7.status === 400, r7.status);
  }
  const j = sub("t1");
  const u = await call("/push/unsubscribe", { endpoint: j.endpoint, auth: j.keys.auth }, "8.8.8.8", {});
  check("unsubscribe deletes team, match and league rows", u.status === 200 && Object.keys(tmask("t1")).length + Object.keys(mmask("t1")).length + Object.keys(lmask("t1")).length === 0, [tmask("t1"), mmask("t1"), lmask("t1")]);
}

process.exit(fail ? 1 : 0);
