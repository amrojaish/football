#!/usr/bin/env python3
"""
Redirect claims on the CURRENT data (27 Oct 2026) — the ownership record for name-redirected links must not change any published link.
Run: python C:\\Users\\User\\Projects\\Football\\test_slug_claims.py

On a read-only copy of football.db and a TEMP copy of player_url_history.json:
  before = build_plan of the committed player_pages.py (git HEAD), current history
  after  = new player_pages: build_plan -> update_history (records the claims into the temp history) -> build_plan again
For every published slug (history key): owner = page (pid / name) or redirect target. The diff before -> after must be EMPTY
(/m-lahtimi-2 stays the Kazma scorer's page, as live). The real history file and football.db are never written.
"""
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import player_pages as pp  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:900]))
    if not cond:
        fails += 1


md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()  # noqa: E731
DB_MD5, H_MD5 = md5(ROOT / "football.db"), md5(pp.HISTORY_FILE)

tmp = Path(tempfile.mkdtemp(prefix="slug_claims_"))
head_src = subprocess.run(["git", "show", "HEAD:player_pages.py"], cwd=ROOT, capture_output=True, check=True).stdout
(tmp / "player_pages_head.py").write_bytes(head_src)
spec = importlib.util.spec_from_file_location("player_pages_head", tmp / "player_pages_head.py")
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)

hist_tmp = tmp / "player_url_history.json"
shutil.copy2(pp.HISTORY_FILE, hist_tmp)
con = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
merges, pins = pp.load_id_merges(), pp.load_pins()


def owners(plan, keys):
    pages = {x["slug"]: ("page", x["pid"] if x["pid"] else "name:" + x["display_en"]) for x in plan["pages"]}
    return {k: pages.get(k) or (("stub", plan["stubs"][k]) if k in plan["stubs"] else ("none",)) for k in keys}


h0 = pp.load_history(hist_tmp, seed=None)
before = owners(old.build_plan(con, dict(h0), merges, pins), h0.keys())
p1 = pp.build_plan(con, pp.load_history(hist_tmp, seed=None), merges, pins)
n = pp.update_history(p1, hist_tmp, seed=None)
h1 = pp.load_history(hist_tmp, seed=None)
claimed = sorted(k for k in h0 if h0[k].get("pid") is None and h1.get(k, {}).get("pid") is not None)
after = owners(pp.build_plan(con, h1, merges, pins), h0.keys())
diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
check(f"current DB: slug -> owner diff for {len(before)} published slugs = EMPTY (claims recorded: {len(claimed)})", not diff, diff)
check("/m-lahtimi-2 stays the Kazma scorer's name page (as live)", after.get("m-lahtimi-2") == ("page", "name:M. Lahtimi")
      and h1.get("m-lahtimi-2", {}).get("pid") is None, [after.get("m-lahtimi-2"), h1.get("m-lahtimi-2")])
check("claims only on redirects, each to a player page (pid) — none on live pages",
      all(after[k][0] == "stub" and h1[k].get("stub") for k in claimed), [(k, after[k], h1[k]) for k in claimed if after[k][0] != "stub"][:5])
check("real football.db and player_url_history.json untouched", md5(ROOT / "football.db") == DB_MD5 and md5(pp.HISTORY_FILE) == H_MD5)
print("claimed:", claimed[:20], "..." if len(claimed) > 20 else "")
print(f"\n{'OK' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
