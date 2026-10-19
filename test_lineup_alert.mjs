// «Lineups out» alert (19 Oct 2026, T_LINEUP = 256): poll window KO-60..KO+5 every 5 min, send once, both XIs required,
// quota guard, recipients by bit (club / match / league), ids batches of 20. Mocked provider + kickoffs file + push services,
// in-memory D1 shim (node:sqlite, all migrations), real encryption + decryption of the payloads. Arabic asserted by code points.
// Run: node --no-warnings test_lineup_alert.mjs
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { pathToFileURL, fileURLToPath } from "node:url";

const tmpDir = fileURLToPath(new URL("./.wrangler/tmp/", import.meta.url));
fs.mkdirSync(tmpDir, { recursive: true });
const tmp = path.join(tmpDir, "worker_lineup_test.mjs");
fs.copyFileSync(new URL("./worker.js", import.meta.url), tmp);
// fresh module per scenario: empty kickoffs cache and no remembered quota header
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

const b64u = (u) => Buffer.from(u).toString("base64url");
const vkp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const VAPID_PUBLIC_KEY = b64u(await crypto.subtle.exportKey("raw", vkp.publicKey));
const VAPID_PRIVATE_KEY = (await crypto.subtle.exportKey("jwk", vkp.privateKey)).d;

const clients = {};
const epOf = (name) => `https://fcm.googleapis.com/fcm/send/${name}`;
async function addSub(name, lang) {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const pub = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
  const auth = crypto.getRandomValues(new Uint8Array(16));
  const endpoint = epOf(name);
  clients[endpoint] = { priv: kp.privateKey, pubBytes: Buffer.from(pub, "base64url"), auth };
  db.prepare("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?,?)").run(endpoint, pub, b64u(auth), lang, 1, 1);
  return endpoint;
}
const subTeam = (ep, team, types) => db.prepare("INSERT OR REPLACE INTO sub_teams (endpoint, team_id, types) VALUES (?,?,?)").run(ep, team, types);
const subMatch = (ep, fx, types) => db.prepare("INSERT OR REPLACE INTO sub_matches (endpoint, fixture, created_at, types) VALUES (?,?,?,?)").run(ep, fx, 1, types);
const subLeague = (ep, lg, types) => db.prepare("INSERT OR REPLACE INTO sub_leagues (endpoint, league, types) VALUES (?,?,?)").run(ep, lg, types);
async function decrypt(endpoint, body) {
  const c = clients[endpoint];
  const buf = Buffer.from(body);
  const salt = buf.subarray(0, 16), idlen = buf[20];
  const serverPub = buf.subarray(21, 21 + idlen), ct = buf.subarray(21 + idlen);
  const spk = await crypto.subtle.importKey("raw", serverPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const secret = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: spk }, c.priv, 256));
  const hk = (saltB, ikm, info, len) => crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"])
    .then((k) => crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: saltB, info }, k, len * 8))
    .then((x) => new Uint8Array(x));
  const enc = new TextEncoder();
  const info = Buffer.concat([enc.encode("WebPush: info\0"), c.pubBytes, serverPub]);
  const prk = await hk(c.auth, secret, info, 32);
  const cek = await hk(salt, prk, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hk(salt, prk, enc.encode("Content-Encoding: nonce\0"), 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["decrypt"]);
  const plain = Buffer.from(await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ct));
  let end = plain.length;
  while (end > 0 && plain[end - 1] === 0) end--;
  return JSON.parse(plain.subarray(0, end - 1).toString("utf8"));
}

// ── mocks ──
const T_LINEUP = 256, T_REM = 64, LG = 387, FAISALY = 4531, WEHDAT = 4529, FX = 77;
const NAMES = { [FAISALY]: { ar: "الفيصلي", en: "Al-Faisaly" }, [WEHDAT]: { ar: "الوحدات", en: "Al-Wehdat" } };
// lineup state per fixture: "both" | "home" | "none" | "emptyxi"
let fxRows, lineupState, liveRemaining, idsRemaining, calls, pushes;
function reset() {
  fxRows = []; lineupState = {}; liveRemaining = "5000"; idsRemaining = "5000"; calls = []; pushes = [];
  db.exec("DELETE FROM ev_sent; DELETE FROM sub_teams; DELETE FROM sub_matches; DELETE FROM sub_leagues; DELETE FROM subscriptions");
}
const XI = [{ player: { id: 1, name: "P" } }];
const lineupsOf = (st, th, ta) => st === "both" ? [{ team: { id: th }, startXI: XI }, { team: { id: ta }, startXI: XI }]
  : st === "home" ? [{ team: { id: th }, startXI: XI }]
  : st === "emptyxi" ? [{ team: { id: th }, startXI: XI }, { team: { id: ta }, startXI: [] }] : [];
globalThis.fetch = async (url, init = {}) => {
  url = String(url);
  calls.push(url);
  if (url.includes("/fixtures?live=")) {
    const h = new Headers({ "x-ratelimit-requests-remaining": liveRemaining });
    return new Response(JSON.stringify({ errors: [], response: [] }), { status: 200, headers: h });
  }
  if (url.includes("/fixtures?ids=")) {
    const ids = url.split("ids=")[1].split("-").map(Number);
    const response = ids.map((id) => { const r = fxRows.find((x) => x[1] === id);
      return { fixture: { id, status: { short: "NS" } }, teams: { home: { id: r[2] }, away: { id: r[3] } }, lineups: lineupsOf(lineupState[id] || "none", r[2], r[3]) }; });
    return new Response(JSON.stringify({ errors: [], response }), { status: 200, headers: new Headers({ "x-ratelimit-requests-remaining": idsRemaining }) });
  }
  if (url === "https://saffara.app/assets/next_kickoffs.json") return new Response(JSON.stringify({ t: 1, k: fxRows.map((r) => r[0]), f: fxRows }), { status: 200 });
  if (url === "https://saffara.app/assets/team_names.json") return new Response(JSON.stringify(NAMES), { status: 200 });
  if (url.startsWith("https://fcm.googleapis.com/")) { pushes.push({ url, body: init.body }); return new Response(null, { status: 201 }); }
  return new Response("{}", { status: 404 });
};
const logs = [];
const origLog = console.log;
console.log = (s) => logs.push(String(s));
let fail = 0, passN = 0;
const check = (n, c, x) => { origLog((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); c ? passN++ : fail++; };

let queued = [];
const QUEUE = { send: async (body) => { if (body && body.kind === "live_scorers") return; queued.push(body); } };
// a 5-minute boundary at or just before real now (the reminder/kick-off file checks use Date.now; the lineup gate uses scheduledTime)
const BASE = Math.floor(Date.now() / 300000) * 300000;
const S0 = Math.floor(BASE / 1000);
async function tick(worker, { at = BASE, kvT = S0 - 60, kvM = {} } = {}) {
  logs.length = 0; calls = []; pushes = []; queued = [];
  const env = { API_KEY: "k", LIVE_KV: { get: async () => JSON.stringify({ t: kvT, m: kvM }), put: async () => {} }, DB, GOAL_QUEUE: QUEUE,
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT: "https://saffara.app", GOAL_PUSH: "on" };
  await worker.scheduled({ scheduledTime: at }, env, {});
  let g = 0;
  while (queued.length && g++ < 50) { const body = queued.shift(); await worker.queue({ messages: [{ body, ack() {}, retry() {} }] }, env); }
}
const idsCalls = () => calls.filter((u) => u.includes("/fixtures?ids="));
const msgs = async () => { const o = []; for (const p of pushes) o.push({ to: p.url, ...(await decrypt(p.url, p.body)) }); return o; };
const lineupMsgs = async () => (await msgs()).filter((m) => m.tag && m.tag.startsWith("lineup-"));
const row = (koOffsetMin, id = FX, th = FAISALY, ta = WEHDAT, lg = LG) => [S0 + koOffsetMin * 60, id, th, ta, lg, "Al Faisaly", "Al Wehdat"];
const TITLE_AR = "التشكيلة الرسمية";

// ═══ 1) poll window KO-60..KO+5, every 5 minutes ═══
for (const [ko, expect] of [[61, false], [60, true], [30, true], [0, true], [-5, true], [-6, false]]) {
  reset(); const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP);
  fxRows = [row(ko)];
  await tick(w);
  check(`window: kick-off ${ko >= 0 ? "in " + ko + " min" : -ko + " min ago"} -> ${expect ? "polls" : "no poll"}`, (idsCalls().length === 1) === expect, idsCalls());
}
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP); fxRows = [row(30)];
  for (const plus of [1, 2, 3, 4]) { await tick(w, { at: BASE + plus * 60000 }); if (idsCalls().length) break; }
  check("off-cycle minutes (:+1..:+4) -> no poll", idsCalls().length === 0, idsCalls());
  await tick(w, { at: BASE + 5 * 60000 });
  check("  next 5-minute mark -> polls", idsCalls().length === 1);
}

// ═══ 2) send once, both XIs, payload ═══
reset(); { const w = await loadWorker();
  const en = await addSub("en", "en"), ar = await addSub("ar", "ar");
  subTeam(en, FAISALY, T_LINEUP); subTeam(ar, WEHDAT, T_LINEUP);
  fxRows = [row(40)]; lineupState[FX] = "none";
  await tick(w);
  check("no lineups yet -> polled, nothing sent, no ev_sent row", idsCalls().length === 1 && pushes.length === 0
    && !db.prepare("SELECT 1 x FROM ev_sent WHERE kind='lineup'").get());
  lineupState[FX] = "home";
  await tick(w, { at: BASE + 5 * 60000 });
  check("only the home XI -> nothing sent", idsCalls().length === 1 && pushes.length === 0);
  lineupState[FX] = "emptyxi";
  await tick(w, { at: BASE + 10 * 60000 });
  check("away lineup present but startXI empty -> nothing sent", idsCalls().length === 1 && pushes.length === 0);
  lineupState[FX] = "both";
  await tick(w, { at: BASE + 15 * 60000 });
  const m = await lineupMsgs();
  const mEn = m.find((x) => x.to === en), mAr = m.find((x) => x.to === ar);
  check("both XIs -> one push to each subscriber", m.length === 2 && mEn && mAr, m);
  check("  EN: 'Lineups out', 'Al-Faisaly vs Al-Wehdat', link to the Lineups tab", mEn && mEn.title === "Lineups out" && mEn.body === "Al-Faisaly vs Al-Wehdat"
    && mEn.url === `/en/matches/${FX}.html#lineups`, mEn);
  check("  AR: title by code points, both club names, /matches/<id>.html#lineups", mAr && mAr.title === TITLE_AR
    && mAr.body.includes(NAMES[FAISALY].ar) && mAr.body.includes(NAMES[WEHDAT].ar) && mAr.url === `/matches/${FX}.html#lineups`, mAr);
  check("  ev_sent row (fixture, 'lineup')", !!db.prepare("SELECT 1 x FROM ev_sent WHERE fixture=? AND kind='lineup'").get(FX));
  await tick(w, { at: BASE + 20 * 60000 });
  check("send once: next cycle -> no poll for that fixture, no push", idsCalls().length === 0 && pushes.length === 0, { c: idsCalls(), p: pushes.length });
}

// ═══ 3) recipients by bit ═══
reset(); { const w = await loadWorker();
  const t = await addSub("team", "en"), tNo = await addSub("teamNo", "en"), mt = await addSub("match", "en"), lg = await addSub("league", "en"),
    lgOther = await addSub("leagueOther", "en"), both = await addSub("both", "en");
  subTeam(t, FAISALY, T_LINEUP); subTeam(tNo, FAISALY, 499 & ~T_LINEUP);
  subMatch(mt, FX, T_LINEUP); subLeague(lg, LG, T_LINEUP); subLeague(lgOther, 233, T_LINEUP);
  subTeam(both, WEHDAT, T_LINEUP); subLeague(both, LG, T_LINEUP);
  fxRows = [row(20)]; lineupState[FX] = "both";
  await tick(w);
  const to = (await lineupMsgs()).map((x) => x.to).sort();
  check("recipients = club/match/league subs WITH bit 256 only; club+league sub gets one", JSON.stringify(to) === JSON.stringify([both, lg, mt, t].sort()), to);
}
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, 499 & ~T_LINEUP); subLeague(a, LG, 255);
  fxRows = [row(20)]; lineupState[FX] = "both";
  await tick(w);
  check("no subscriber has bit 256 (old masks 243/255) -> no API call at all", idsCalls().length === 0 && pushes.length === 0, idsCalls());
}

// ═══ 4) quota guard ═══
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP);
  fxRows = [row(5)]; lineupState[FX] = "both"; liveRemaining = "799";
  await tick(w);   // kick-off in 5 min -> the live fetch runs this minute and reports 799 remaining
  check("live header 799 (< 800) -> lineup poll skipped, no push", calls.some((u) => u.includes("fixtures?live=")) && idsCalls().length === 0 && pushes.length === 0, calls);
  check("  skip logged", logs.some((l) => l.includes('"lineup_poll"') && l.includes('"skipped":"quota"')));
  liveRemaining = "800";
  await tick(w, { at: BASE + 5 * 60000 });
  check("  header back to 800 -> polls and sends", idsCalls().length === 1 && (await lineupMsgs()).length === 1);
}
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP);
  fxRows = Array.from({ length: 25 }, (_, i) => row(50, 1000 + i)); idsRemaining = "700";
  await tick(w);
  check("ids reply itself reports 700 -> stops after the first batch (1 call, not 2)", idsCalls().length === 1, idsCalls().length);
}

// ═══ 5) batching + call count ═══
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP);
  fxRows = Array.from({ length: 25 }, (_, i) => row(50, 1000 + i));
  await tick(w);
  const ids = idsCalls().map((u) => u.split("ids=")[1].split("-").length);
  check("25 fixtures -> 2 calls (20 + 5)", JSON.stringify(ids) === "[20,5]", ids);
  const L = logs.map((l) => { try { return JSON.parse(l); } catch (e) { return {}; } }).find((x) => x.type === "lineup_poll");
  check("  lineup_poll log counts calls and fixtures", L && L.calls === 2 && L.fixtures === 25, L);
}

// ═══ 6) GOAL_PUSH off / provider error ═══
reset(); { const w = await loadWorker();
  const a = await addSub("a", "en"); subTeam(a, FAISALY, T_LINEUP); fxRows = [row(30)]; lineupState[FX] = "both";
  logs.length = 0; calls = []; queued = [];
  await w.scheduled({ scheduledTime: BASE }, { API_KEY: "k", LIVE_KV: { get: async () => JSON.stringify({ t: S0 - 60, m: {} }), put: async () => {} }, DB, GOAL_QUEUE: QUEUE, GOAL_PUSH: "off" }, {});
  check("GOAL_PUSH off -> no lineup poll", idsCalls().length === 0);
}

console.log = origLog;
origLog(`${passN} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
