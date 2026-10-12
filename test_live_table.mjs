// Live league table (assets_src/live_table.js): equality with get_table for the 7 current seasons, then synthetic cases.
// Run: node --no-warnings test_live_table.mjs   (needs python + football.db; read-only)
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const liveTable = require("./assets_src/live_table.js");
const cwd = fileURLToPath(new URL(".", import.meta.url));

let fail = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };
const ids = (res) => res.rows.map((r) => r.team_id);
const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

// ── 1) per league: no live matches -> order EXACTLY get_table's (and the numbers untouched) ──
const dump = JSON.parse(execFileSync("python", ["test_live_table_dump.py"], { cwd, encoding: "utf8", maxBuffer: 1 << 28 }));
for (const code of ["JOR", "IRQ", "SAU", "EGY", "UAE", "QAT", "MAR"]) {
  const { snapshot: s, expected } = dump[code];
  if (code === "JOR") {
    check("JOR: feature off -> null (static table stays)", liveTable(s, {}, {}) === null && s.rows.length > 0, { rules: s.rules });
    continue;
  }
  const res = liveTable(s, {}, {});
  const nums = res.rows.every((r, i) => ["played", "wins", "draws", "losses", "scored", "diff", "points"].every((k) => r[k] === s.rows[i][k]));
  const ties = (() => { const c = {}; s.rows.forEach((r) => { c[r.points] = (c[r.points] || 0) + 1; }); return Object.values(c).filter((n) => n > 1).length; })();
  check(`${code} ${s.season}: no live -> order == get_table (${expected.length} teams, ${s.counted_ids.length} matches, ${ties} points-tie groups, h2h=${s.rules.h2h}${s.rules.twoOnly ? " two-only" : ""})`,
    same(ids(res), expected) && nums && !res.live && res.addedF === 0 && res.addedLive === 0, { got: ids(res), expected });
}
check("null / missing snapshot -> null", liveTable(null, {}, {}) === null && liveTable({ rules: { enabled: true } }, {}, {}) === null);

// ── helpers for synthetic snapshots ──
const row = (team_id, played, wins, draws, losses, scored, diff, points) => ({ team_id, played, wins, draws, losses, scored, diff, points });
const snap = (rules, rows, matches = [], counted = matches.map((x) => x[0]), alias = {}) =>
  ({ league: "T", season: 2026, rules: { enabled: true, leagueId: 307, h2h: false, twoOnly: false, ...rules }, counted_ids: counted, rows, matches, alias });
const live = (id, th, ta, h, a, lg = 307, s = "2H") => ({ [id]: { h, a, e: 60, s, th, ta, lg } });

// ── 2) a live win changes the rank ──
{
  const s = snap({}, [row(1, 4, 3, 1, 0, 8, 5, 10), row(2, 4, 3, 0, 1, 7, 4, 9), row(3, 4, 1, 2, 1, 4, 0, 5), row(4, 4, 1, 2, 1, 3, -1, 5)]);
  const res = liveTable(s, live(900, 2, 3, 1, 0), {});
  check("live 1-0 for team 2 (9 -> 12 pts): team 2 goes 2nd -> 1st, team 1 down to 2nd", same(ids(res), [2, 1, 3, 4]) && res.rows[0].base_pos === 2 && res.rows[0].pos === 1
    && res.rows[0].points === 12 && res.rows[0].played === 5 && res.rows[0].diff === 5, res.rows);
  check("  live flag only on the two playing teams; the other rows untouched", res.rows.filter((r) => r.live).map((r) => r.team_id).sort().join() === "2,3"
    && res.rows.find((r) => r.team_id === 1).points === 10 && res.live && res.addedLive === 1 && res.addedF === 0, res.rows);
  const res2 = liveTable(s, live(900, 2, 3, 1, 1), {});
  check("  score 1-1: team 2 only +1 (10 pts) = team 1's 10 -> overall GD decides (team 1 +5 vs team 2 +4) -> 1, 2", same(ids(res2), [1, 2, 3, 4]), ids(res2));
  const res3 = liveTable(s, live(900, 2, 3, 0, 1), {});
  check("  team 3 leads 0-1 live: team 3 5 -> 8 pts (stays 3rd), team 2 stays 9", same(ids(res3), [1, 2, 3, 4]) && res3.rows[2].points === 8, res3.rows);
  check("  live match of ANOTHER league (lg 999) is ignored; null scores count as 0-0", same(ids(liveTable(s, live(901, 2, 3, 5, 0, 999), {})), [1, 2, 3, 4])
    && liveTable(s, { 902: { h: null, a: null, s: "1H", th: 3, ta: 4, lg: 307 } }, {}).rows.find((r) => r.team_id === 3).draws === 3, null);
  check("  team missing from the table (season start) gets a zero row", liveTable(s, live(903, 9, 4, 2, 0), {}).rows.find((r) => r.team_id === 9).points === 3, null);
  const sa = snap({}, s.rows, [], [], { 77: 2 });
  check("  alias map: provider id 77 -> our team 2", liveTable(sa, live(904, 77, 3, 1, 0), {}).rows[0].team_id === 2, null);
}

// ── 3) f results: never double counted ──
{
  const base = [row(1, 4, 3, 1, 0, 8, 5, 10), row(2, 4, 3, 0, 1, 7, 4, 9), row(3, 4, 1, 2, 1, 4, 0, 5), row(4, 4, 1, 2, 1, 3, -1, 5)];
  const s = snap({}, base, [[800, 2, 4, 2, 0]], [800, 1, 2, 3]);
  const fin = (h, a, o = {}) => ({ h, a, s: "FT", th: 2, ta: 4, lg: 307, ft: 1, ...o });
  let res = liveTable(s, {}, { 800: fin(2, 0) });
  check("f result whose id is already in counted_ids -> ignored (no double count), table == snapshot", res.addedF === 0 && res.rows.find((r) => r.team_id === 2).points === 9
    && same(ids(res), [1, 2, 3, 4]), res.rows);
  res = liveTable(s, {}, { 801: fin(1, 0, { th: 3, ta: 1 }) });
  check("f result NOT counted yet (id 801, team 3 beat team 1) -> added exactly once", res.addedF === 1 && res.rows.find((r) => r.team_id === 3).points === 8 && res.rows.find((r) => r.team_id === 3).played === 5
    && res.rows.find((r) => r.team_id === 1).losses === 1 && !res.live, res.rows);
  res = liveTable(s, live(801, 3, 1, 1, 0), { 801: fin(1, 0, { th: 3, ta: 1 }) });
  check("same id in m AND f -> counted once (f wins, no live flag)", res.addedF === 1 && res.addedLive === 0 && res.rows.find((r) => r.team_id === 3).points === 8, res.rows);
  const again = liveTable(s, {}, { 801: fin(1, 0, { th: 3, ta: 1 }) });
  check("calling again on the same snapshot does not mutate it (idempotent)", again.rows.find((r) => r.team_id === 3).points === 8 && s.rows.find((r) => r.team_id === 3).points === 5, s.rows);
  check("old-worker f (no lg/th/ta), non-final status, other league -> ignored",
    liveTable(s, {}, { 810: { h: 1, a: 0, s: "FT", ft: 1 } }).addedF === 0
    && liveTable(s, {}, { 811: fin(1, 0, { s: "SUSP", th: 3, ta: 1 }) }).addedF === 0
    && liveTable(s, {}, { 812: fin(1, 0, { lg: 999, th: 3, ta: 1 }) }).addedF === 0, null);
  check("AET and PEN finals are applied", liveTable(s, {}, { 813: fin(1, 0, { s: "AET", th: 3, ta: 1 }) }).addedF === 1
    && liveTable(s, {}, { 814: fin(1, 1, { s: "PEN", th: 3, ta: 1 }) }).addedF === 1, null);
}

// ── 4) head-to-head: MAR (two-team ties only) vs other rule sets ──
{
  // team 2 leads team 1 overall (GD +5 vs -3) but team 1 beat team 2 in their meeting; a live win by team 1 lifts it to 7 = team 2's 7
  const rows = [row(3, 4, 3, 1, 0, 9, 8, 10), row(2, 4, 2, 1, 1, 9, 5, 7), row(1, 4, 1, 1, 2, 2, -3, 4), row(4, 4, 0, 0, 4, 1, -10, 0)];
  const matches = [[10, 1, 2, 1, 0]];   // team 1 beat team 2 (counted)
  const lv = live(950, 1, 4, 3, 0);     // team 1 +3 pts live -> 7
  const mar = liveTable(snap({ h2h: true, twoOnly: true }, rows, matches), lv, {});
  check("MAR: team 1 reaches 7 pts = team 2 -> exactly TWO tied -> head-to-head (1 beat 2) puts team 1 above team 2 despite the worse GD", same(ids(mar), [3, 1, 2, 4]), ids(mar));
  const sau = liveTable(snap({ h2h: true }, rows, matches), lv, {});
  check("SAU/IRQ/EGY/UAE style (head-to-head, any group size): same order for a two-team tie", same(ids(sau), [3, 1, 2, 4]), ids(sau));
  const qat = liveTable(snap({ h2h: false }, rows, matches), lv, {});
  check("QAT style (no head-to-head): overall GD decides -> team 2 stays above team 1", same(ids(qat), [3, 2, 1, 4]), ids(qat));
  // three teams on 7: head-to-head would put team 5 first (it beat both); overall GD gives 2, 5, 1
  const rows3 = [row(3, 4, 3, 1, 0, 9, 8, 10), row(2, 4, 2, 1, 1, 9, 5, 7), row(5, 4, 2, 1, 1, 5, 1, 7), row(1, 4, 1, 1, 2, 2, -3, 4), row(4, 4, 0, 0, 4, 1, -10, 0)];
  const m3 = [[11, 5, 2, 2, 0], [12, 5, 1, 3, 0]];   // team 5 beat team 2 and team 1
  const mar3 = liveTable(snap({ h2h: true, twoOnly: true }, rows3, m3), lv, {});
  check("MAR three teams on 7 pts: head-to-head is SKIPPED (two-team-only rule) -> overall GD: 2 (+5), 5 (+1), 1 (0)", same(ids(mar3), [3, 2, 5, 1, 4]), ids(mar3));
  const sau3 = liveTable(snap({ h2h: true }, rows3, m3), lv, {});
  check("same three-team tie where head-to-head applies to any size: 5 first (6 h2h pts); 2 and 1 level on 0, so h2h GD: 2 (-2) above 1 (-3)", same(ids(sau3), [3, 5, 2, 1, 4]), ids(sau3));
}

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);
