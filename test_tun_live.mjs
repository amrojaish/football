// TUN live (26 Oct 2026, worker step 11 prep): PENDING_LEAGUE_IDS 202 on -> the Tunisian league rides the single fixtures?live= poll,
// its fixtures land in the live payload (lg 202) with the provider's added time (status.extra -> x, only when sent), TUN clubs and the
// league are accepted by /push/subscribe, the league cap = 8 (site MAXL); ALG 186 / KUW 330 stay off.
// Run: node --no-warnings test_tun_live.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_tun_live_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
const loadWorker = async () => (await import(pathToFileURL(tmp).href + "?" + Math.random())).default;

const db = new DatabaseSync(":memory:");
for (const f of ["0001_push.sql", "0002_dispatch_log.sql", "0003_rate_limit.sql", "0004_goal_log.sql", "0006_scorer_update.sql",
                 "0007_scorer_update_correction.sql", "0008_sub_matches.sql", "0009_alert_types.sql"])
  db.exec(fs.readFileSync(new URL("./migrations/" + f, import.meta.url), "utf8"));
const stmt = (sql, args = []) => ({
  bind: (...a) => stmt(sql, a),
  first: async () => db.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  _run: () => db.prepare(sql).run(...args),
});
const DB = { prepare: (s) => stmt(s), batch: async (l) => { l.forEach((x) => x._run()); return []; } };

const EST = 980, CA = 988, FX = 1607500, FX2 = 1607501;   // ES Tunis vs Club Africain; second TUN fixture without added time
let live, apiCalls, written;
const fx = (id, short, el, extra) => ({
  fixture: { id, status: extra === undefined ? { short, elapsed: el } : { short, elapsed: el, extra } },
  goals: { home: 1, away: 0 }, events: [],
  teams: { home: { id: EST, name: "ES Tunis" }, away: { id: CA, name: "Club Africain" } }, league: { id: 202 },
});
globalThis.fetch = async (url) => {
  url = String(url);
  if (url.startsWith("https://v3.football.api-sports.io")) {
    apiCalls.push(url);
    return new Response(JSON.stringify({ errors: [], response: live }), { status: 200, headers: { "x-ratelimit-requests-remaining": "5000" } });
  }
  return new Response("{}", { status: 404 });
};
const origLog = console.log;
console.log = () => {};
const NOW = Math.floor(Date.now() / 1000);
async function tick() {
  written = null; apiCalls = [];
  const kv = { get: async () => JSON.stringify({ t: NOW - 3600, m: {} }), put: async (k, v) => { if (k === "live") written = JSON.parse(v); } };
  const env = { API_KEY: "k", LIVE_KV: kv, DB, GOAL_QUEUE: { send: async () => {} }, GOAL_PUSH: "off" };
  await (await loadWorker()).scheduled({}, env, {});
}
let fail = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// 1) the single live poll includes 202 (not 186/330); TUN fixtures land in m with lg 202 and the added time
live = [fx(FX, "1H", 45, 2), fx(FX2, "2H", 63)];
await tick();
const q = apiCalls[0] || "";
const ids = (q.match(/live=([\d-]+)/) || [, ""])[1].split("-");
check("one fixtures?live= request; league list = the 7 + Tunisia 202 (ALG 186 / KUW 330 off)",
  apiCalls.length === 1 && ids.length === 8 && ids.includes("202") && !ids.includes("186") && !ids.includes("330"), apiCalls);
const m = (written && written.m) || {};
check("TUN fixture in the live payload: score, minute, status, league 202, both clubs",
  m[FX] && m[FX].h === 1 && m[FX].a === 0 && m[FX].e === 45 && m[FX].s === "1H" && m[FX].lg === 202 && m[FX].th === EST && m[FX].ta === CA, m[FX]);
check("  provider added time passed through as x (45+2 -> e 45, x 2)", m[FX] && m[FX].x === 2, m[FX]);
check("  no added time from the provider -> no x field (payload unchanged for everything else)", m[FX2] && !("x" in m[FX2]), m[FX2]);

// 2) /push/subscribe: TUN clubs + the Tunisian league accepted; ALG league rejected; cap 8 leagues
const worker = await loadWorker();
const b64u = (n) => Buffer.alloc(n, 7).toString("base64url");
const sub = (id) => ({ endpoint: "https://fcm.googleapis.com/fcm/send/" + id, keys: { p256dh: b64u(65), auth: b64u(16) } });
const call = (body, ip) => worker.fetch(new Request("https://w.example/push/subscribe", {
  method: "POST", headers: { Origin: "https://saffara.app", "Content-Type": "application/json", "CF-Connecting-IP": ip }, body: JSON.stringify(body) }), { DB });
let r = await call({ subscription: sub("tun1"), teams: [EST, CA], leagues: [202], lang: "ar" }, "2.2.2.1");
const rows = (t, col) => db.prepare(`SELECT ${col} x FROM ${t} WHERE endpoint = ? ORDER BY x`).all(sub("tun1").endpoint).map((x) => x.x);
check("TUN clubs (980, 988) and the Tunisian league (202) are accepted", r.status === 200 && JSON.stringify(rows("sub_teams", "team_id")) === "[980,988]"
  && JSON.stringify(rows("sub_leagues", "league")) === "[202]", [r.status, rows("sub_teams", "team_id"), rows("sub_leagues", "league")]);
r = await call({ subscription: sub("alg1"), teams: [EST], leagues: [186], lang: "ar" }, "2.2.2.2");
check("ALG league 186 still rejected (flag off)", r.status === 400, r.status);
const ALL8 = [387, 542, 307, 233, 301, 305, 200, 202];
r = await call({ subscription: sub("all8"), teams: [EST], leagues: ALL8, lang: "en" }, "2.2.2.3");
check("all 8 enabled leagues in one subscription = accepted (league cap 8 = site MAXL)", r.status === 200, r.status);
r = await call({ subscription: sub("nine"), teams: [EST], leagues: [...ALL8, 186], lang: "en" }, "2.2.2.4");
check("9 leagues = rejected", r.status === 400, r.status);

origLog(fail ? `${fail} failed` : "all passed");
process.exit(fail ? 1 : 0);
