#!/usr/bin/env python3
"""
Refresh blank scorer names after full time (17 Oct 2026)
=========================================================
The provider sometimes sends a goal without a player name right after the match and fills it in later (e.g. IRQ 1627975, 1627044).
fetch_matches2.py never revisits a finished match, so the blank name stayed forever.

Targets: FINISHED matches of the current season that have at least one goal with a blank `player_en`
(match_corrections.csv matches are skipped: their goals are managed by hand).

Schedule (reuses fetch_backoff.SCHEDULE_HOURS = 0/1/6/24/72 h after full time, kind = "goals", then stop for good):
  * every provider reply (even one that changes nothing) is recorded as an attempt; failures (HTTP/network) are not.
  * ONE-TIME list: a current-season blank match older than 72 h with no attempt record at all is tried once
    (kind = "goals_once"), then never again.

Replacement rule (plan_update), per match, all or nothing:
  * the provider's goal count (type Goal, not "Missed Penalty" — same filter as the fetchers) must equal ours for EACH team,
    otherwise nothing changes and the reason is logged;
  * every named goal of ours must find its provider goal (same name, else same minute +-1) — a named goal is never removed
    or edited; the rest of the provider goals are paired with our blank rows in minute order;
  * only blank rows are updated: player_en, minute, detail (Normal/Penalty/Own Goal) from the provider; a provider goal that
    is still nameless leaves its row unchanged.
  * `goals` has no player_id column (README lesson 26), so the provider player id is not stored.

The Arabic name comes from the normal apply_players_ar.py step, which runs AFTER this step in update_all.py.

API: 1 call per due match, hard cap --budget (default 10) per run.

Usage:
    python refresh_goal_names.py --season 2026                 <- run (CI)
    python refresh_goal_names.py --season 2026 --check         <- no writes, no API: uses --raw-dir JSON where present
    python refresh_goal_names.py --check --raw-dir <dir>       <- dir holds events_<match_id>.json (saved raw replies)
"""
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path

import fetch_backoff as BO
from config import DB_FILE, BASE_DIR, SEASON

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
DEFAULT_BUDGET = 10
CORRECTIONS = BASE_DIR / "match_corrections.csv"


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def blank(s):
    return not (s or "").strip()


def corrected_ids(path=CORRECTIONS):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return {int(r["match_id"]) for r in csv.DictReader(f) if (r.get("match_id") or "").strip().isdigit()}
    except OSError:
        return set()


def blank_matches(conn, season, skip=()):
    """finished matches of the season with >= 1 blank-name goal -> rows (match_id, league_code, season, date)."""
    rows = conn.execute("""
        SELECT m.match_id, m.league_code, m.season, m.date FROM matches m
        WHERE m.status = 'FT' AND m.season = ?
          AND EXISTS (SELECT 1 FROM goals g WHERE g.match_id = m.match_id AND TRIM(COALESCE(g.player_en, '')) = '')
        ORDER BY m.date DESC""", (season,)).fetchall()
    return [r for r in rows if r["match_id"] not in skip]


def select_due(conn, rows, now=None):
    """-> [(row, kind)]: kind 'goals' = on the backoff schedule, 'goals_once' = the one-time old-match try."""
    now = time.time() if now is None else now
    BO.ensure_table(conn)
    due, _skipped = BO.filter_due(conn, "goals", rows, now)
    due_ids = {r["match_id"] for r in due}
    out = [(r, "goals") for r in due]
    seen = {(r[0], r[1]) for r in conn.execute("SELECT match_id, kind FROM stats_attempts WHERE kind IN ('goals', 'goals_once')")}
    for r in rows:
        mid = r["match_id"]
        if mid in due_ids or (mid, "goals") in seen or (mid, "goals_once") in seen:
            continue
        ft = BO._ft_ts(r["date"])
        if ft is not None and now - ft > BO.SCHEDULE_HOURS[-1] * 3600:
            out.append((r, "goals_once"))
    return out


def provider_goals(events):
    """provider events -> goals list, same filter as the fetchers (type Goal, no Missed Penalty)."""
    out = []
    for e in events or []:
        if e.get("type") != "Goal" or e.get("detail") == "Missed Penalty":
            continue
        p = e.get("player") or {}
        out.append({"team": (e.get("team") or {}).get("id"), "minute": (e.get("time") or {}).get("elapsed"),
                    "name": (p.get("name") or "").strip(), "pid": p.get("id"), "detail": e.get("detail") or ""})
    return out


def plan_update(ours, prov):
    """ours: [{id, team_id, minute, player_en}], prov: provider_goals(). -> (updates, reason).
    updates = [(goal_id, name, minute, detail)] (empty + reason when nothing may change)."""
    teams = {g["team_id"] for g in ours} | {p["team"] for p in prov}
    updates = []
    for t in sorted(teams, key=lambda x: (x is None, x)):
        o = [g for g in ours if g["team_id"] == t]
        p = [x for x in prov if x["team"] == t]
        if len(o) != len(p):
            return [], f"count_differs team {t}: ours {len(o)} provider {len(p)}"
        used = set()
        for g in (g for g in o if not blank(g["player_en"])):
            nm = g["player_en"].strip().casefold()
            cand = [i for i, x in enumerate(p) if i not in used and x["name"].casefold() == nm]
            if not cand:
                cand = [i for i, x in enumerate(p) if i not in used and x["minute"] is not None and g["minute"] is not None
                        and abs(x["minute"] - g["minute"]) <= 1]
            if not cand:
                return [], f"named_goal_not_in_provider team {t}: min {g['minute']}"
            used.add(min(cand, key=lambda i: abs((p[i]["minute"] or 0) - (g["minute"] or 0))))
        rest = sorted((x for i, x in enumerate(p) if i not in used), key=lambda x: (x["minute"] if x["minute"] is not None else 999))
        bl = sorted((g for g in o if blank(g["player_en"])), key=lambda g: (g["minute"] if g["minute"] is not None else 999, g["id"]))
        for g, x in zip(bl, rest):
            if x["name"]:
                updates.append((g["id"], x["name"], x["minute"], x["detail"] or "Normal Goal"))
    if not updates:
        return [], "provider_names_blank"
    return updates, "ok"


def apply_updates(conn, updates):
    for gid, name, minute, detail in updates:
        # guard: only a row that is still blank is ever touched
        conn.execute("UPDATE goals SET player_en = ?, minute = ?, detail = ? WHERE id = ? AND TRIM(COALESCE(player_en, '')) = ''",
                     (name, minute, detail, gid))


def load_raw(raw_dir, mid):
    if not raw_dir:
        return None
    p = Path(raw_dir) / f"events_{mid}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("response", [])
    except (OSError, ValueError):
        return None


def run(conn, season, budget, check, raw_dir=None, fetch=None, now=None):
    """-> dict(report). conn.row_factory = sqlite3.Row. fetch(mid) -> (ok, events, reason); default = provider API."""
    due = select_due(conn, blank_matches(conn, season, corrected_ids()), now)
    rep = {"targets": len(due), "calls": 0, "would_call": 0, "updated_matches": 0, "filled": 0, "skipped": [], "lines": []}
    if fetch is None and not check:
        from fetch_stats import get

        def fetch(mid):
            return get("fixtures/events", {"fixture": mid})
    for r, kind in due[:budget] if not check else due:
        mid = r["match_id"]
        raw = load_raw(raw_dir, mid) if check else None
        if check and raw is None:
            rep["would_call"] += 1
            rep["lines"].append(f"{mid} {r['league_code']} [{kind}] would call the API")
            continue
        if raw is None:
            ok, events, reason = fetch(mid)
            rep["calls"] += 1
            if not ok:
                rep["lines"].append(f"{mid} [{kind}] fetch failed ({reason}); not recorded")
                time.sleep(DELAY)
                continue
        else:
            events = raw
        ours = [dict(x) for x in conn.execute("SELECT id, team_id, minute, player_en FROM goals WHERE match_id = ? ORDER BY minute, id", (mid,))]
        updates, why = plan_update(ours, provider_goals(events))
        if updates:
            apply_updates(conn, updates)
            rep["updated_matches"] += 1
            rep["filled"] += len(updates)
            rep["lines"].append(f"{mid} {r['league_code']} [{kind}] filled {len(updates)} of {sum(1 for g in ours if blank(g['player_en']))} blank goals")
        else:
            rep["skipped"].append((mid, why))
            rep["lines"].append(f"{mid} {r['league_code']} [{kind}] unchanged: {why}")
        if not check:
            BO.record_empty(conn, kind, mid, now)
        if fetch is not None and raw is None:
            time.sleep(DELAY)
    if not check:
        conn.commit()
    return rep


def main():
    check = "--check" in sys.argv
    season = int(arg("--season", SEASON))
    budget = int(arg("--budget", DEFAULT_BUDGET))
    raw_dir = arg("--raw-dir")
    if not DB_FILE.exists():
        print("football.db not found")
        return 1
    if check:
        src = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        from config import check_key
        conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    if not check and not check_key():
        return 0
    rep = run(conn, season, budget, check, raw_dir)
    print(f"  blank-scorer refresh (season {season}){' [check: no writes, no API]' if check else ''}: "
          f"due {rep['targets']} · API calls {rep['calls']}{' (would call: %d)' % rep['would_call'] if check else ''} "
          f"· matches updated {rep['updated_matches']} · goals filled {rep['filled']} · unchanged {len(rep['skipped'])}")
    for ln in rep["lines"]:
        print("   ", ln)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
