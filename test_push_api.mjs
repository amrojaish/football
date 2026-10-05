// Local test of /push/* against `wrangler dev --local` (D1 local). Run:
//   npx wrangler dev --local --port 8799 --var VAPID_PUBLIC_KEY:<pub>   (other terminal)
//   node test_push_api.mjs [http://127.0.0.1:8799]
import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
const BASE = process.argv[2] || "http://127.0.0.1:8799";
const ORIGIN = "https://saffara.app";
const b64u = (n) => Buffer.alloc(n, 7).toString("base64url");
const P256DH = b64u(65), AUTH = b64u(16), AUTH2 = Buffer.alloc(16, 9).toString("base64url");
const EP = "https://fcm.googleapis.com/fcm/send/test-endpoint-1";
const sub = (o = {}) => ({ subscription: { endpoint: EP, keys: { p256dh: P256DH, auth: AUTH } }, teams: [962, 964], lang: "ar", ...o });
const post = (path, body, origin = ORIGIN) => fetch(BASE + path, {
  method: "POST", headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}) },
  body: typeof body === "string" ? body : JSON.stringify(body) });
const dbDir = ".wrangler/state/v3/d1/miniflare-D1DatabaseObject";
const dbFile = fs.readdirSync(dbDir).filter((f) => f.endsWith(".sqlite") && f !== "metadata.sqlite")[0];
const sql = (q) => { const d = new DatabaseSync(path.join(dbDir, dbFile), { readOnly: true }); try { return d.prepare(q).all(); } finally { d.close(); } };

let fail = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };
const teamsOf = () => sql(`SELECT team_id FROM sub_teams WHERE endpoint='${EP}' ORDER BY team_id`).map((r) => r.team_id);

await post("/push/unsubscribe", { endpoint: EP, auth: AUTH });   // clean start
let r = await fetch(BASE + "/push/key", { headers: { Origin: ORIGIN } });
let j = await r.json();
check("GET /push/key -> public key + CORS for saffara.app", r.status === 200 && j.key?.length === 87 && r.headers.get("access-control-allow-origin") === ORIGIN, [r.status, j]);

r = await post("/push/subscribe", sub());
check("subscribe ok", r.status === 200 && (await r.json()).teams === 2);
check("  rows: 1 sub, teams [962,964]", sql("SELECT COUNT(*) c FROM subscriptions")[0].c === 1 && JSON.stringify(teamsOf()) === "[962,964]", teamsOf());

r = await post("/push/subscribe", sub({ teams: [965, 968, 965], lang: "en" }));
check("re-subscribe with other teams (dup ignored)", r.status === 200 && JSON.stringify(teamsOf()) === "[965,968]"
  && sql("SELECT COUNT(*) c FROM subscriptions")[0].c === 1 && sql("SELECT lang FROM subscriptions")[0].lang === "en", teamsOf());

r = await post("/push/subscribe", sub({ subscription: { endpoint: EP, keys: { p256dh: P256DH, auth: AUTH2 } } }));
check("subscribe with other auth on existing endpoint -> 403, rows untouched", r.status === 403 && JSON.stringify(teamsOf()) === "[965,968]");

r = await post("/push/unsubscribe", { endpoint: EP, auth: AUTH2 });
check("unsubscribe wrong auth -> 403, row kept", r.status === 403 && sql("SELECT COUNT(*) c FROM subscriptions")[0].c === 1);

r = await post("/push/unsubscribe", { endpoint: EP, auth: AUTH });
check("unsubscribe right auth -> deleted incl. teams", r.status === 200 && (await r.json()).deleted === true
  && sql("SELECT COUNT(*) c FROM subscriptions")[0].c === 0 && teamsOf().length === 0);

// boundary: exactly 50 teams -> accepted, all 50 rows stored (json_each path)
r = await post("/push/subscribe", sub({ teams: [962,964,965,968,969,971,973,974,975,976,977,1030,1031,1032,1036,1037,1039,1040,1041,1044,1046,1048,1074,1075,1572,1574,1575,1576,1577,2865,2867,2868,2869,2870,2871,2872,2873,2874,2875,2876,2877,2879,2893,2894,2895,2896,2897,2898,2899,2900] }));
check("50 teams accepted and stored", r.status === 200 && teamsOf().length === 50, r.status);
await post("/push/unsubscribe", { endpoint: EP, auth: AUTH });

const bad = [
  ["unknown team id", sub({ teams: [1] })],
  ["non-integer team", sub({ teams: ["962"] })],
  ["51 teams", sub({ teams: Array.from({ length: 51 }, (_, i) => 962 + i) })],
  ["teams not array", sub({ teams: 962 })],
  ["bad lang", sub({ lang: "fr" })],
  ["http endpoint", sub({ subscription: { endpoint: "http://fcm.googleapis.com/x", keys: { p256dh: P256DH, auth: AUTH } } })],
  ["unknown host", sub({ subscription: { endpoint: "https://evil.example.com/x", keys: { p256dh: P256DH, auth: AUTH } } })],
  ["lookalike host", sub({ subscription: { endpoint: "https://fcm.googleapis.com.evil.com/x", keys: { p256dh: P256DH, auth: AUTH } } })],
  ["bad p256dh", sub({ subscription: { endpoint: EP, keys: { p256dh: "short", auth: AUTH } } })],
  ["bad auth", sub({ subscription: { endpoint: EP, keys: { p256dh: P256DH, auth: "!!" } } })],
  ["missing subscription", { teams: [962], lang: "ar" }],
  ["not json", "{nope"],
];
for (const [n, body] of bad) { r = await post("/push/subscribe", body); check("400: " + n, r.status === 400, r.status); }
r = await post("/push/unsubscribe", { endpoint: "https://evil.example.com/x", auth: AUTH });
check("400: unsubscribe bad endpoint", r.status === 400);
r = await post("/push/subscribe", "x".repeat(9000));
check("400: body too large", r.status === 400);
check("  no rows written by bad input", sql("SELECT COUNT(*) c FROM subscriptions")[0].c === 0);

r = await post("/push/subscribe", sub(), "https://evil.example.com");
check("foreign Origin -> 400, no CORS header", r.status === 400 && !r.headers.get("access-control-allow-origin"));
r = await fetch(BASE + "/push/subscribe", { method: "OPTIONS", headers: { Origin: "https://evil.example.com", "Access-Control-Request-Method": "POST" } });
check("preflight from foreign Origin -> 400", r.status === 400 && !r.headers.get("access-control-allow-origin"), r.status);
r = await fetch(BASE + "/push/subscribe", { method: "OPTIONS", headers: { Origin: ORIGIN, "Access-Control-Request-Method": "POST" } });
check("preflight from saffara.app -> 204 + allow-origin", r.status === 204 && r.headers.get("access-control-allow-origin") === ORIGIN);

r = await fetch(BASE + "/", { headers: { Origin: "https://evil.example.com" } });
j = await r.json();
check("live payload unchanged: GET / -> {t,m}, ACAO *", r.status === 200 && "t" in j && "m" in j && r.headers.get("access-control-allow-origin") === "*", j);

process.exit(fail ? 1 : 0);
