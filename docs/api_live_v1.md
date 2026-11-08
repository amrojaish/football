# Saffara live data — contract v1 (for the native app)

Status: v1, 2 Nov 2026. Source of truth: `worker.js` (Cloudflare Worker `saffara-live`). This file is **not published** on
saffara.app (`build_site.py` excludes `*.md`). `test_live_contract.mjs` parses the **contract block** at the end of this file and
runs the real worker code against it — if a worker change breaks a documented key or type, that test fails.

Base URL: `https://saffara-live.abujaishamr.workers.dev`

| Endpoint | What | Cache | Missing |
|---|---|---|---|
| `GET /` | live payload: matches in play + matches that just finished | `Cache-Control: no-store`; KV read `cacheTtl` 30 s | `{"t":0,"m":{}}` (200) |
| `GET /lineup?id=<fixture>` | official line-ups (KO-60 … KO+5 min window) | `public, max-age=60` | `404 {}`; bad id → `400 {"error":"bad id"}` |
| `GET /events?id=<fixture>` | event list of a live / just-finished match | `public, max-age=60` | `404 {}`; bad id → `400 {"error":"bad id"}` |

All responses are JSON (`application/json;charset=UTF-8`) with `Access-Control-Allow-Origin: *`.
`/pull` needs an admin token and is **not** for the app. `/push/*`, `/vote`, `/votes` are separate APIs (not covered here).

## Identifiers

* **Fixture ids** (keys of `m`, `f`, `v`, `st`; `?id=`) are the same ids as `api/v1/matches/<id>.json` and the site's
  `/matches/<id>.html`. Object keys are **strings** (`"1602976"`), file names use the same digits.
* **Team ids** (`th`, `ta`, line-up `home.id` / `away.id`) are the same ids as `api/v1/teams.json` / `teams/<id>.json`.
* **League ids** (`lg`) are the **provider's** league ids, not our codes. Mapping (from `config.LEAGUES`):
  JOR 387 · IRQ 542 · SAU 307 · EGY 233 · UAE 301 · QAT 305 · MAR 200 · TUN 202 · ALG 186 · KUW 330.
* **Player ids** in events/line-ups (`v` rows [7]/[8], `xi[].id`) are provider player ids = `api/v1/players/<id>.json` ids
  (a player without a page has no file).

## `GET /` — the live payload

```json
{"t": 1793631600,
 "m": {"1603077": {"h": 1, "a": 0, "e": 67, "s": "2H", "x": 2, "th": 2932, "ta": 2939, "lg": 307,
                   "nh": "Al-Hilal Saudi FC", "na": "Al-Ahli Jeddah"}},
 "f": {"1603070": {"h": 2, "a": 2, "s": "FT", "th": 2934, "ta": 10511, "lg": 307, "ft": 1793630500}},
 "v": {"1603077": [[23, 0, "g", "n", "S. Al-Dawsari", "M. Kanno", "h", 1234, 5678]]},
 "st": {"1603077": {"t": 1793631480, "h": [58, 11, 5, 6], "a": [42, 7, 2, 3]}}}
```

| Key | Type | Meaning |
|---|---|---|
| `t` | int | Unix seconds (UTC) of the last **successful** provider pull. `0` = no data yet. |
| `m` | object | Matches **in play**, keyed by fixture id. Empty object when nothing is live. |
| `m.<id>.h` / `.a` | int \| null | Home / away goals now. |
| `m.<id>.e` | int \| null | Elapsed minute from the provider at time `t` (e.g. 45 during 45+2). |
| `m.<id>.x` | int (optional) | Added time from the provider (`45+2` → `e` 45, `x` 2). Absent = 0 / unknown. |
| `m.<id>.s` | string | Status short code. In `m` only: `1H`, `HT`, `2H`, `ET`, `BT` (break before/within extra time), `P` (penalty shoot-out), `LIVE`. |
| `m.<id>.th` / `.ta` | int | Home / away team id. |
| `m.<id>.lg` | int | Provider league id (see mapping). |
| `m.<id>.nh` / `.na` | string | Provider's English team names — **fallback only**; use `api/v1/teams.json` names. |
| `f` | object (optional) | Matches that **finished or stopped** in the last 12 h, keyed by fixture id. Absent when none. |
| `f.<id>.h` / `.a` | int \| null | Final (or last) score. |
| `f.<id>.s` | string | `FT`, `AET`, `PEN`, `AWD`, `WO` (finished; `WO` has a null score) or `SUSP`, `ABD`, `PST`, `INT` (stopped/postponed). |
| `f.<id>.ft` | int | Unix seconds when the worker recorded it. |
| `f.<id>.th` / `.ta` / `.lg` | int (optional) | Team ids / provider league id. |
| `v` | object (optional) | Event lists of live matches, keyed by fixture id. **Absent** when the provider quota guard is on (remaining < 800 requests) — scores still update. |
| `v.<id>[]` | array (row) | `[minute, extra, type, detail, player, assist, side, player_id, assist_id]` — see below. |
| `st` | object (optional) | Live team stats for matches in play (refreshed every ~5 min per match). |
| `st.<id>.t` | int | Unix seconds of that stats fetch. |
| `st.<id>.h` / `.a` | array of 4 × (int \| null) | `[possession %, total shots, shots on target, corners]`; `null` = not provided. |

**Event row** (`v.<id>[]`, also `/events` → `l[]`), a fixed-position array (indexes are stable; new fields are only ever
appended at the end):

| # | Type | Meaning |
|---|---|---|
| 0 | int | minute (elapsed) |
| 1 | int | added minutes (0 = none) |
| 2 | string | type: `g` goal · `c` card · `s` substitution · `v` VAR |
| 3 | string | detail — goal: `n` normal · `p` penalty · `o` own goal · `m` **missed** penalty (not a goal); card: `y` · `r` · `yr` (second yellow); VAR: provider text (≤ 30 chars, e.g. `Goal cancelled`, `Penalty confirmed`); subst: `""` |
| 4 | string | player name (provider, English, ≤ 40). Substitution: player **out**. |
| 5 | string | assist name; substitution: player **in**. `""` if none. |
| 6 | string | `h` / `a` — side of the event's team |
| 7 | int \| null | player id |
| 8 | int \| null | assist / player-in id |

Order is the provider's order (chronological). Arabic names: look up the id in `api/v1/players/<id>.json`.

### Internal keys — ignore, may change or disappear without notice

`g` (first time a match left the live feed), `r` (matches waiting for a final status), `ve` (events-enabled flag), `s` (site-only
live scorer lines `[side, minute, extra, surname, arabic, tag]`). A fixture id that is in `g` is **still listed in `m`** with its
last known score while the worker asks the provider for the final status (up to 10 min): treat it as "finished, awaiting
final" if your clock says the match should be over, otherwise as live.

## `GET /events?id=<fixture>`

Written while the match is live (every time its event list changes) and once more from the final reply (`ft: 1`). Kept 36 h.

```json
{"fixture": 1603077, "t": 1793631600, "th": 2932, "ta": 2939, "ft": 0, "l": [[23, 0, "g", "n", "S. Al-Dawsari", "M. Kanno", "h", 1234, 5678]]}
```

`fixture` int · `t` int (Unix s) · `th`/`ta` int · `ft` int (`0` = still live, `1` = final copy) · `l` array of event rows (same
format as above). A match that ended without any event has no entry (404).

## `GET /lineup?id=<fixture>`

Stored once both teams have a starting XI (polled every 5 min from KO-60 to KO+5). Kept 36 h. **Never available** for IRQ, JOR,
KUW (the provider has no line-ups for them).

```json
{"fixture": 1603077, "t": 1793628000,
 "home": {"id": 2932, "formation": "4-3-3", "coach": "J. Jesus",
          "xi": [{"id": 1234, "name": "S. Al-Dawsari", "number": 29, "pos": "F", "grid": "4:3"}],
          "subs": [{"id": 999, "name": "Sub Name", "number": 17, "pos": "M", "grid": null}]},
 "away": {"id": 2939, "formation": "4-4-2", "coach": "…", "xi": [], "subs": []}}
```

`home`/`away`: `id` int (team), `formation` string (`""` if unknown), `coach` string (`""`), `xi` / `subs` arrays of
`{id: int|null, name: string, number: int|null, pos: string (G/D/M/F or ""), grid: string|null ("row:col")}`.
After the match, the static `api/v1/matches/<id>.json` → `lineups` is the better source (Arabic names, stored for good).

## Update frequency

* Worker cron: every minute. With nothing live it pulls the provider only every **5 min**, except from KO-10 to KO+30 min of
  any scheduled match (every minute). While a match is live it pulls **twice a minute** (second pull ~30 s after the first).
* KV is read with `cacheTtl` 30 s, so a new payload reaches readers within ~30 s. Expect a score change on `GET /` within
  **~30–60 s** of the provider (the provider itself can lag a goal by 1–3 min).
* The site polls `GET /` every 60 s, every 30 s while anything is live, stops when nothing is live, and re-polls when the tab
  becomes visible again. Suggested for the app: the same, with a `?_=<timestamp>` cache-buster (the site does this).

## Empty, stale and failure behaviour

* **Nothing live:** `{"t": <last pull>, "m": {}}` (plus `f` if something ended in the last 12 h).
* **Provider/worker failure:** the worker keeps the **last good payload** (no partial writes); `t` simply stops advancing.
  Treat the payload as **stale** when matches are in `m` and `now - t > 180 s` (show the last score with a "may be delayed" hint).
* **Network error / non-200:** the site silently keeps what it shows (static page) and tries again next poll. The app should do
  the same: never blank a match because the live call failed.
* **Quota guard:** `v` (events), `st` and new `/events` writes stop; `m` and `f` scores continue.

## Combining with `api/v1` (static files)

1. Static files (`index.json`, `days/…`, `matches/<id>.json`, `teams/…`, `leagues/…`) are rebuilt by the site deploy roughly
   every 30 min. They carry everything that does not change during a match (teams, kickoff, round, venue, line-ups after the
   match, stats after the match, h2h, tables).
2. Live payload **overrides** only score, status and minute, and only for the fixture ids it contains:
   * id in `m` → show live: `score = {h, a}`, `status = s`, minute from `e` (+`x`), clock running from `t` for `1H`/`2H`/`ET`.
   * id in `f` → show final/stopped: `score = {h, a}`, `status = s` — until the static file shows the same final state.
   * id in neither → use the static file.
3. Events while live: `v.<id>` (or `/events?id=`); after the static file has `events`, prefer the static list (it has Arabic
   names, own-goal attribution and cancelled goals).
4. League tables during play: recompute from the static `leagues/<CODE>.json` table + live scores in `m`/`f` (the site does this
   with `assets/table_<CODE>_<season>.json`; the rules are in `assets_src/live_table.js`). Optional.
5. Never trust `nh`/`na` for display; use `teams.json`.

## Stability

* **Stable (v1):** everything in the tables above except the "Internal keys" section. Changes to stable keys will only be
  additive (new keys, new appended event-row fields).
* **Internal (may change):** `g`, `r`, `ve`, `s`, and `nh`/`na` are fallbacks only.
* `test_live_contract.mjs` runs the real worker code and checks every stable path below.

## Contract block (machine-checked)

Format: `<endpoint> <path> <type> <flag>`. Endpoints: `live` = `GET /`, `events` = `/events?id=`, `lineup` = `/lineup?id=`.
Path: `.` separates keys, `*` = every key of an object, `[]` = every item of an array, `[n]` = fixed index. Types: `int`,
`string`, `object`, `array`, `null` combined with `|`. Flags: `stable` (always present when the parent exists), `optional`
(stable meaning, may be absent), `internal` (type-checked only if present).

```contract
live t int stable
live m object stable
live m.* object stable
live m.*.h int|null stable
live m.*.a int|null stable
live m.*.e int|null stable
live m.*.s string stable
live m.*.x int optional
live m.*.th int stable
live m.*.ta int stable
live m.*.lg int stable
live m.*.nh string optional
live m.*.na string optional
live f object optional
live f.* object optional
live f.*.h int|null optional
live f.*.a int|null optional
live f.*.s string optional
live f.*.ft int optional
live f.*.th int optional
live f.*.ta int optional
live f.*.lg int optional
live v object optional
live v.* array optional
live v.*[] array optional
live v.*[][0] int optional
live v.*[][1] int optional
live v.*[][2] string optional
live v.*[][3] string optional
live v.*[][4] string optional
live v.*[][5] string optional
live v.*[][6] string optional
live v.*[][7] int|null optional
live v.*[][8] int|null optional
live st object optional
live st.* object optional
live st.*.t int optional
live st.*.h array optional
live st.*.h[] int|null optional
live st.*.a array optional
live st.*.a[] int|null optional
live g object internal
live r object internal
live ve int internal
live s object internal
events fixture int stable
events t int stable
events th int stable
events ta int stable
events ft int stable
events l array stable
events l[] array stable
events l[][0] int stable
events l[][2] string stable
events l[][6] string stable
events l[][7] int|null stable
events l[][8] int|null stable
lineup fixture int stable
lineup t int stable
lineup home object stable
lineup home.id int stable
lineup home.formation string stable
lineup home.coach string stable
lineup home.xi array stable
lineup home.xi[] object stable
lineup home.xi[].id int|null stable
lineup home.xi[].name string stable
lineup home.xi[].number int|null stable
lineup home.xi[].pos string stable
lineup home.xi[].grid string|null stable
lineup home.subs array stable
lineup home.subs[] object stable
lineup home.subs[].id int|null stable
lineup home.subs[].name string stable
lineup away object stable
lineup away.id int stable
lineup away.formation string stable
lineup away.coach string stable
lineup away.xi array stable
lineup away.subs array stable
```
