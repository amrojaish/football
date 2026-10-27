#!/usr/bin/env python3
"""
import_league.py --apply guard (26 Oct 2026): the lock must be held by local AND the remote seq must equal the seq I pulled; the local DB
may already differ from the pull (a second import in the same lock window: ALG then KUW). Run:
    python C:\\Users\\User\\Projects\\Football\\test_import_league.py
1) require_local_lock with a fake state store: pass / refuse cases (no network).
2) two imports in one lock window on a TEMP COPY of football.db (temp CSVs + URL history): guard before each passes, ALG then KUW
   through the real apply path (run(..., real=True)), counts checked. Needs FootballBackups/football_newleagues_test.db; the real
   football.db and the repo CSVs are never written.
"""
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import import_league as il  # noqa: E402

SRC = Path(r"C:\Users\User\FootballBackups\football_newleagues_test.db")
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


def fake_ss(remote_seq, lock_holder, base_seq):
    meta = {"seq": remote_seq, "lock": ({"holder": lock_holder, "expires_at": "2026-10-27T02:00:00Z"} if lock_holder else None)}
    return SimpleNamespace(get_store=lambda: SimpleNamespace(get_meta=lambda: meta), lock_info=lambda m: m["lock"],
                           read_local_base=lambda: ({"seq": base_seq, "content_sha": "pulled"} if base_seq is not None else None))


def guard(ss):
    try:
        il.require_local_lock(ss)
        return "ok"
    except il.Abort as e:
        return str(e)


# ── 1) guard cases ──
check("lock held by local + remote seq unchanged -> pass (local DB may already be modified)", guard(fake_ss(1081, "local", 1081)) == "ok")
r = guard(fake_ss(1081, None, 1081))
check("no lock -> refuse", r != "ok" and "قفل" in r, r)
r = guard(fake_ss(1081, "ci", 1081))
check("lock held by CI -> refuse", r != "ok" and "قفل" in r, r)
r = guard(fake_ss(1082, "local", 1081))
check("remote seq moved since my pull (1081 -> 1082) -> refuse", r != "ok" and "1082" in r, r)
r = guard(fake_ss(1081, "local", None))
check("no pull record -> refuse", r != "ok", r)

# ── 2) two imports in one lock window, on a temp copy of the FIXED pre-import state ──
# (27 Oct 2026) independent of today's data: the target is the exact state the real ALG/KUW import ran on — the seq 1081 pull and the
# CSV/history snapshots saved with it (FootballBackups/alg-kuw-import-2026-10-26). Today's DB already holds ALG/KUW (collisions), its
# player 636280 is merged away (a pinned id) and its URL history lists the imported pages — replaying on it can only fail.
SNAP_DB = Path(r"C:\Users\User\FootballBackups\football-20261026-231510-seq1081.db")
SNAP_DIR = Path(r"C:\Users\User\FootballBackups\alg-kuw-import-2026-10-26")
if not (SRC.exists() and SNAP_DB.exists() and SNAP_DIR.exists()):
    check("test inputs present (source DB + seq 1081 snapshot + its CSV/history copies)", False, [str(SRC), str(SNAP_DB), str(SNAP_DIR)])
else:
    work = Path(tempfile.mkdtemp(prefix="test_import_two_"))
    for s_, d in ((SNAP_DB, "football.db"), (SNAP_DIR / "teams_arabic.csv", "teams_arabic.csv"),
                  (SNAP_DIR / "player_name_pins.csv", "player_name_pins.csv"), (SNAP_DIR / "player_url_history.json", "player_url_history.json")):
        shutil.copy2(s_, work / d)
    db, teams, pins, hist = work / "football.db", work / "teams_arabic.csv", work / "player_name_pins.csv", work / "player_url_history.json"
    # the real DB has matches.round since 27 Oct: the temp target gets it too, so the source must be migrated by run() to pass the
    # (unchanged, strict) schema check
    import match_round as _mr
    _w = sqlite3.connect(db)
    _mr.migrate(_w)
    _w.close()
    # the source is a scratch fetch copy: import from a TEMP copy of it (run() adds matches.round to it, like the real procedure)
    src = work / "source.db"
    shutil.copy2(SRC, src)
    held = fake_ss(1081, "local", 1081)                 # the lock window: same remote seq the whole time
    il.CHECK["on"] = False                              # apply semantics (club without Arabic = Abort)
    done = []
    for code in ("ALG", "KUW"):
        g = guard(held)
        check(f"{code}: guard passes inside the lock window" + (" (DB already modified by ALG)" if done else ""), g == "ok", g)
        try:
            il.run(code, src, db, teams, pins, hist, True)
            done.append(code)
        except il.Abort as e:
            check(f"{code}: import through the apply path", False, str(e))
    c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    n = {k: c.execute("SELECT COUNT(*) FROM matches WHERE league_code = ?", (k,)).fetchone()[0] for k in ("ALG", "KUW")}
    t = {k: c.execute("SELECT COUNT(*) FROM teams WHERE league_code = ? AND name_ar != '' AND short_name_ar != ''", (k,)).fetchone()[0]
         for k in ("ALG", "KUW")}
    qc = c.execute("PRAGMA quick_check").fetchone()[0]
    c.close()
    check(f"both imports done in one window: ALG {n['ALG']} matches / {t['ALG']} clubs, KUW {n['KUW']} / {t['KUW']}, quick_check {qc}",
          done == ["ALG", "KUW"] and n == {"ALG": 1009, "KUW": 518} and t == {"ALG": 23, "KUW": 14} and qc == "ok", [done, n, t, qc])
    check("real football.db untouched by the test", il.DB_FILE.resolve() != db.resolve())
    # (a) 27 Oct 2026: the name-redirect claim. /m-lahtimi-2 (name-only page "M. Lahtimi") was redirected by name to the Moroccan
    # player 182463 before KUW; the claim records him as owner, so the Kazma scorer with the same name gets a NEW suffix (guard passes)
    import player_pages as _pp
    _h = _pp.load_history(hist, seed=None)
    check("(a) /m-lahtimi-2 recorded as owned by 182463 (redirect claim)", _h.get("m-lahtimi-2", {}).get("pid") == 182463 and _h["m-lahtimi-2"].get("stub"), _h.get("m-lahtimi-2"))
    _c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True); _c.row_factory = sqlite3.Row
    _plan = _pp.build_plan(_c, _h, _pp.load_id_merges(), _pp.load_pins(pins)); _c.close()
    _kuw = [x["slug"] for x in _plan["pages"] if x["kind"] == "name" and x["display_en"] == "M. Lahtimi"]
    check(f"(a) the KUW 'M. Lahtimi' gets a new suffix {_kuw}, /m-lahtimi-2 still redirects to 182463's page",
          _kuw and "m-lahtimi-2" not in _kuw and _plan["stubs"].get("m-lahtimi-2") == next(x["slug"] for x in _plan["pages"] if x["pid"] == 182463),
          [_kuw, _plan["stubs"].get("m-lahtimi-2")])
    sc = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True)
    check("the temp source got matches.round automatically (target is migrated)", "round" in [r[1] for r in sc.execute("PRAGMA table_info(matches)")])
    sc.close()
    s0 = sqlite3.connect(SRC.as_uri() + "?mode=ro", uri=True)
    check("the checked-in test source itself is not modified", "round" not in [r[1] for r in s0.execute("PRAGMA table_info(matches)")])
    s0.close()

print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
