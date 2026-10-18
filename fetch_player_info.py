#!/usr/bin/env python3
"""
Player profiles from the provider (18 Oct 2026) — birth date, nationality, height, weight, position, number, photo flag
====================================================================================================================
Scope: player ids that HAVE a player page (player_pages.get_plan() -> stats_pid, ≈2,372). Ids without a page are out of scope.
Runs inside CI (update_all.py, after the other fetchers) against the state DB — no local DB writes.

Table `player_info` (CREATE TABLE IF NOT EXISTS here, like stats_attempts): one row per player id. Height/weight as integers
  (height_cm / weight_kg): the provider's format varies ("183", "179 cm").
  status 'ok'    = profile returned (fields may still be blank: new ids often have no birth/nationality/height);
  status 'empty' = the provider answered with no profile;
  status 'error' = a PERSISTENT failure: HTTP 4xx (not 429) or an error body that is not about the quota (text in last_error).
  'empty' / 'error' are retried at +1 d, +7 d, +30 d after the last try, then re-checked every REFRESH_DAYS (180) like profiles.
  TRANSIENT failures (HTTP 5xx, 429 after its waits, timeouts, network) are NOT recorded: the id stays due for the next run.
  An error body that looks like a quota / rate-limit message is checked against the real remaining count (the reply's
  x-ratelimit-requests-remaining, else the free /status): remaining >= MIN_REMAINING -> it is about this id after all and is
  recorded as 'error' (normal backoff) and the run goes on; remaining below the floor (or unknown) -> the run stops, unrecorded.
  'ok' rows are refreshed after REFRESH_DAYS (180).
Photo flag `has_photo`: GET of the photo (the image CDN, not the counted API) and SHA-256 of the bytes: equal to the provider's
  generic silhouette (SILHOUETTE_SHA256) -> 0, any other image -> 1, failure -> NULL (retried next run, max PHOTO_CHECKS per run).

Quota (the live worker shares it): every run first reads the free /status; nothing is fetched under MIN_REMAINING (3,500), and the
  run stops as soon as a reply's x-ratelimit-requests-remaining drops under it. Daily cap DAILY_CAP (1,500, UTC day) counted in
  `player_info_calls` (every call, failures included); per-run budget --budget (default 100). 1 request per second.

Usage:
    python fetch_player_info.py                               <- CI: fetch due ids, write player_info
    python fetch_player_info.py --check [--ids 1,2,3]         <- real API calls, NO writes (in-memory DB copy), raw JSON saved
                                                                 to <DB_BACKUP_DIR>/player_info_check/
    python fetch_player_info.py --check --from-json DIR       <- zero API calls: parse DIR/<id>.json (saved raw replies)
    options: --budget N · --daily-cap N · --min-remaining N · --no-photo (skip the CDN photo check)
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
DEFAULT_BUDGET = 100
DAILY_CAP = 1500
MIN_REMAINING = 3500
REFRESH_DAYS = 180
EMPTY_RETRY_DAYS = [1, 7, 30]      # wait after the 1st / 2nd / 3rd 'empty'/'error' answer; from the 4th on: every REFRESH_DAYS
PHOTO_CHECKS = 200
# the provider's "no photo" silhouette (identical bytes for every id without a photo; 5,192 bytes at the time of writing)
SILHOUETTE_SHA256 = "2ff7d52a628fce5d954c58480dde4e47396db4bb405b7b7d6a6567134bf86422"
PHOTO_CDN = "https://media.api-sports.io/football/players/"
DAY = 86400

COLS = ("name", "firstname", "lastname", "age", "birth_date", "birth_place", "birth_country", "nationality",
        "height_cm", "weight_kg", "number", "position", "photo")


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def ensure_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS player_info (
        player_id INTEGER PRIMARY KEY,
        name TEXT, firstname TEXT, lastname TEXT, age INTEGER, birth_date TEXT, birth_place TEXT, birth_country TEXT,
        nationality TEXT, height_cm INTEGER, weight_kg INTEGER, number INTEGER, position TEXT, photo TEXT,
        has_photo INTEGER,
        status TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0, fetched_at INTEGER, last_try INTEGER NOT NULL, last_error TEXT)""")
    conn.execute("CREATE TABLE IF NOT EXISTS player_info_calls (day TEXT PRIMARY KEY, n INTEGER NOT NULL)")


def utc_day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def calls_today(conn, now):
    r = conn.execute("SELECT n FROM player_info_calls WHERE day = ?", (utc_day(now),)).fetchone()
    return r[0] if r else 0


def count_call(conn, now):
    conn.execute("INSERT INTO player_info_calls (day, n) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET n = n + 1", (utc_day(now),))


def page_ids():
    """player ids with a player page (the same plan make_players.py builds from)"""
    from player_pages import get_plan
    return sorted({p["stats_pid"] for p in get_plan()["pages"] if p["stats_pid"]})


def select_due(conn, ids, now):
    """-> [(pid, reason)] in order: never fetched, then 'empty'/'error' rows whose retry is due (+1/+7/+30 d, then every 180 d),
    then 'ok' rows older than 180 d"""
    rows = {r[0]: r for r in conn.execute("SELECT player_id, status, tries, last_try, fetched_at FROM player_info")}
    new, retry, stale = [], [], []
    for pid in ids:
        r = rows.get(pid)
        if r is None:
            new.append((pid, "new"))
        elif r[1] in ("empty", "error"):
            n = r[2]
            wait = EMPTY_RETRY_DAYS[n - 1] if 1 <= n <= len(EMPTY_RETRY_DAYS) else REFRESH_DAYS
            if now - r[3] >= wait * DAY:
                retry.append((pid, f"retry {n}" if n <= len(EMPTY_RETRY_DAYS) else "recheck"))
        elif r[1] == "ok" and r[4] and now - r[4] >= REFRESH_DAYS * DAY:
            stale.append((pid, "refresh"))
    return new + retry + stale


def measure(v):
    """provider height/weight -> int: the format varies ("183" / "179 cm" / "72 kg") -> leading 2-3 digits, else None"""
    m = re.match(r"\s*(\d{2,3})", str(v)) if v is not None else None
    return int(m.group(1)) if m else None


def parse(reply):
    """provider reply (dict with 'response') -> dict of COLS, or None when the provider has no profile"""
    resp = (reply or {}).get("response") or []
    if not resp:
        return None
    pl = (resp[0] or {}).get("player") or {}
    if not pl:
        return None
    b = pl.get("birth") or {}
    s = lambda v: (str(v).strip() or None) if v is not None else None
    num = pl.get("number")
    return {"name": s(pl.get("name")), "firstname": s(pl.get("firstname")), "lastname": s(pl.get("lastname")),
            "age": pl.get("age") if isinstance(pl.get("age"), int) else None,
            "birth_date": s(b.get("date")), "birth_place": s(b.get("place")), "birth_country": s(b.get("country")),
            "nationality": s(pl.get("nationality")), "height_cm": measure(pl.get("height")), "weight_kg": measure(pl.get("weight")),
            "number": num if isinstance(num, int) else None, "position": s(pl.get("position")), "photo": s(pl.get("photo"))}


def save_miss(conn, pid, status, now, error=None):
    """'empty' / 'error' answer: tries + 1 and last_try (the backoff clock). An existing 'ok' profile is never downgraded:
    its fields stay, and its refresh clock (fetched_at) restarts, so the next refresh waits another REFRESH_DAYS."""
    conn.execute("""INSERT INTO player_info (player_id, status, tries, last_try, last_error) VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(player_id) DO UPDATE SET
                    status = CASE WHEN status = 'ok' THEN 'ok' ELSE excluded.status END,
                    tries = CASE WHEN status = 'ok' THEN tries ELSE tries + 1 END,
                    fetched_at = CASE WHEN status = 'ok' THEN excluded.last_try ELSE fetched_at END,
                    last_try = excluded.last_try, last_error = excluded.last_error""", (pid, status, now, error))


def save(conn, pid, info, now):
    if info is None:
        save_miss(conn, pid, "empty", now)
        return
    vals = [info[c] for c in COLS]
    conn.execute(f"""INSERT INTO player_info (player_id, {", ".join(COLS)}, status, tries, fetched_at, last_try)
                     VALUES (?, {", ".join("?" * len(COLS))}, 'ok', 0, ?, ?)
                     ON CONFLICT(player_id) DO UPDATE SET {", ".join(f"{c} = excluded.{c}" for c in COLS)},
                     status = 'ok', tries = 0, fetched_at = excluded.fetched_at, last_try = excluded.last_try, last_error = NULL""",
                 (pid, *vals, now, now))


# failure kinds (the reason string's prefix): "persistent: ..." recorded with backoff · "quota: ..." stop the run · else transient
def failure_kind(reason):
    r = reason or ""
    return "persistent" if r.startswith("persistent:") else ("quota" if r.startswith("quota:") else "transient")


def api_get(pid):
    """-> (ok, reply dict, remaining or None, reason). Same retry rules as fetch_stats.get (429 waits, timeouts retried).
    reason "persistent: HTTP 404" / "persistent: API {...}" = the id itself fails (recorded); "quota: ..." = provider says the
    request limit is reached (run stops); anything else (5xx, timeout, network, 429 after waits) = transient (not recorded)."""
    import requests
    from config import API_BASE, headers
    for attempt in range(1, 4):
        try:
            r = requests.get(f"{API_BASE}/players/profiles", headers=headers(), params={"player": pid}, timeout=30)
            rem = r.headers.get("x-ratelimit-requests-remaining")
            rem = int(rem) if rem and rem.lstrip("-").isdigit() else None
            if r.status_code == 429:
                time.sleep(attempt * 10)
                continue
            if 400 <= r.status_code < 500:
                return False, None, rem, f"persistent: HTTP {r.status_code}"
            if r.status_code != 200:
                return False, None, rem, f"HTTP {r.status_code}"
            data = r.json()
            errs = data.get("errors")
            if errs and isinstance(errs, (dict, list)):
                txt = json.dumps(errs, ensure_ascii=False)[:200]
                if any(w in txt.lower() for w in ("request", "ratelimit", "rate limit", "token", "access")):
                    return False, None, rem, f"quota: {txt}"
                return False, None, rem, f"persistent: API {txt}"
            return True, data, rem, ""
        except Exception as e:
            if attempt == 3:
                return False, None, None, type(e).__name__
            time.sleep(attempt * 3)
    return False, None, None, "rate limited"


def status_remaining():
    """free /status read -> remaining calls today, or None"""
    try:
        import requests
        from config import API_BASE, headers
        q = ((requests.get(f"{API_BASE}/status", headers=headers(), timeout=30).json().get("response") or {}).get("requests") or {})
        return q.get("limit_day", 0) - q.get("current", 0)
    except Exception:
        return None


def photo_flag(pid):
    """CDN GET + SHA-256 of the image -> 0 the provider's silhouette, 1 a real photo, None on failure / not an image"""
    import hashlib
    import requests
    try:
        r = requests.get(f"{PHOTO_CDN}{pid}.png", timeout=15)
        if r.status_code != 200 or not r.content or not (r.headers.get("Content-Type") or "").startswith("image/"):
            return None
        return 0 if hashlib.sha256(r.content).hexdigest() == SILHOUETTE_SHA256 else 1
    except Exception:
        return None


def run(conn, ids, now, budget=DEFAULT_BUDGET, daily_cap=DAILY_CAP, min_remaining=MIN_REMAINING, fetch=None, remaining=None,
        photo=None, raw_dir=None, from_json=None, write=True, status=None):
    """-> report dict. fetch(pid) -> (ok, reply, remaining, reason); photo(pid) -> 1/0/None; remaining = /status before start;
    status() -> remaining now (free /status), used when a quota-looking error reply carries no remaining header."""
    ensure_tables(conn)
    due = select_due(conn, ids, now)
    rep = {"in_scope": len(ids), "due": len(due), "calls": 0, "ok": 0, "empty": 0, "errors": 0, "failed": 0, "photo": {1: 0, 0: 0, None: 0},
           "stop": "", "lines": []}
    if from_json is None:
        if remaining is not None and remaining < min_remaining:
            rep["stop"] = f"remaining {remaining} < {min_remaining}: nothing fetched"
            return rep
        left = min(budget, max(0, daily_cap - calls_today(conn, now)))
        if left == 0:
            rep["stop"] = f"daily cap {daily_cap} reached"
            return rep
    else:
        left = len(due)
    for pid, why in due:
        if left <= 0:
            rep["stop"] = rep["stop"] or "budget / daily cap"
            break
        if from_json is not None:
            f = Path(from_json) / f"{pid}.json"
            if not f.exists():
                continue
            ok, reply, rem, reason = True, json.loads(f.read_text(encoding="utf-8")), None, ""
        else:
            ok, reply, rem, reason = fetch(pid)
            rep["calls"] += 1
            count_call(conn, now)
            left -= 1
            if raw_dir and reply is not None:
                Path(raw_dir).mkdir(parents=True, exist_ok=True)
                (Path(raw_dir) / f"{pid}.json").write_text(json.dumps(reply, ensure_ascii=False, indent=1), encoding="utf-8")
        if not ok:
            kind = failure_kind(reason)
            if kind == "quota":
                # quota-looking body: trust the real remaining count, not the wording
                now_rem = rem if rem is not None else (status() if status else None)
                if now_rem is not None and now_rem >= min_remaining:
                    kind, reason = "persistent", "persistent: " + reason[len("quota: "):] + f" (remaining {now_rem})"
                else:
                    rep["failed"] += 1
                    rep["lines"].append(f"{pid} [{why}] failed ({reason}); not recorded")
                    rep["stop"] = f"provider quota/rate error with remaining {now_rem}: {reason}"
                    break
            if kind == "persistent":
                save_miss(conn, pid, "error", now, reason[len("persistent: "):])
                rep["errors"] += 1
                rep["lines"].append(f"{pid} [{why}] error ({reason}); recorded, backoff")
            else:
                rep["failed"] += 1
                rep["lines"].append(f"{pid} [{why}] failed ({reason}); not recorded")
        else:
            info = parse(reply)
            save(conn, pid, info, now)
            if info is None:
                rep["empty"] += 1
                rep["lines"].append(f"{pid} [{why}] empty")
            else:
                rep["ok"] += 1
                hp = photo(pid) if photo and info["photo"] else None
                if photo and info["photo"]:
                    conn.execute("UPDATE player_info SET has_photo = ? WHERE player_id = ?", (hp, pid))
                    rep["photo"][hp] += 1
                have = [k for k in ("birth_date", "nationality", "height_cm", "weight_kg", "position", "number") if info[k] not in (None, "")]
                rep["lines"].append(f"{pid} [{why}] ok: " + (", ".join(have) or "no fields") + ("" if not photo else f", photo={hp}"))
        if rem is not None and rem < min_remaining:
            rep["stop"] = f"remaining {rem} < {min_remaining}"
            break
        if fetch is not None and from_json is None:
            time.sleep(DELAY)
    # photo flag for earlier 'ok' rows whose photo check failed (CDN only, no quota)
    if photo:
        for (pid,) in conn.execute("SELECT player_id FROM player_info WHERE status = 'ok' AND has_photo IS NULL AND photo IS NOT NULL "
                                   "LIMIT ?", (PHOTO_CHECKS,)).fetchall():
            conn.execute("UPDATE player_info SET has_photo = ? WHERE player_id = ?", (photo(pid), pid))
    if write:
        conn.commit()
    return rep


def main():
    check = "--check" in sys.argv
    from_json = arg("--from-json")
    ids_arg = arg("--ids")
    budget = int(arg("--budget", DEFAULT_BUDGET))
    cap = int(arg("--daily-cap", DAILY_CAP))
    min_rem = int(arg("--min-remaining", MIN_REMAINING))
    no_photo = "--no-photo" in sys.argv
    if not DB_FILE.exists():
        print("football.db not found")
        return 1
    if check:
        src = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        conn = sqlite3.connect(DB_FILE)
    scope = page_ids()
    ids = [int(x) for x in ids_arg.split(",")] if ids_arg else scope
    out_of_scope = [x for x in ids if x not in set(scope)]
    if out_of_scope:
        print(f"  ⚠️ not in scope (no player page), skipped: {out_of_scope}")
        ids = [x for x in ids if x not in set(out_of_scope)]
    now = int(time.time())
    fetch = remaining = None
    if from_json is None:
        from config import check_key
        if not check_key():
            return 0
        fetch = api_get
        remaining = status_remaining()
    raw_dir = None
    if check and from_json is None:
        base = os.environ.get("DB_BACKUP_DIR") or str(Path.home() / "FootballBackups")
        raw_dir = Path(base) / "player_info_check"
    rep = run(conn, ids, now, budget, cap, min_rem, fetch=fetch, remaining=remaining, photo=None if no_photo else photo_flag,
              raw_dir=raw_dir, from_json=from_json, write=not check, status=status_remaining if from_json is None else None)
    for ln in rep["lines"]:
        print("   ", ln)
    if check and raw_dir:
        print(f"  raw replies: {raw_dir}")
    # ⚠️ the one-line summary is printed LAST: update_all.py keeps only the last 12 lines of a step's output
    print(f"  player profiles{' [check: no writes]' if check else ''}: in scope {rep['in_scope']} (pages) · due {rep['due']} · "
          f"API calls {rep['calls']} · ok {rep['ok']} · empty {rep['empty']} · errors {rep['errors']} · failed (transient) {rep['failed']} · "
          f"photo real/silhouette/unknown {rep['photo'][1]}/{rep['photo'][0]}/{rep['photo'][None]}"
          + (f" · stop: {rep['stop']}" if rep["stop"] else "") + (f" · /status remaining before: {remaining}" if remaining is not None else ""))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
