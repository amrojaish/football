#!/usr/bin/env python3
"""سجلّ روابط اللاعبين كحالة دائمة (db-state): بناء بأسلوب CI (شجرة نظيفة بلا ملف الحالة، البذرة فقط) يضيف slug جديداً ويكتب
الملف؛ التعبئة/الفك (نفس pack/unpack الذي يصعد به db_push) تحفظه؛ البناء التالي (بعد db_pull) يحمله ويضيف عليه؛ لا يضيع شيء.
التشغيل: python test_url_history_state.py"""
import json
import sys
import tempfile
from pathlib import Path

import player_pages as pp
import state_sync as ss

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


def plan_of(*slugs):
    return {"pages": [{"slug": s, "pid": i + 1, "display_en": s.title()} for i, s in enumerate(slugs)]}


check("player_url_history.json is a state file (pulled/pushed with the DB)", "player_url_history.json" in ss.STATE_FILES, ss.STATE_FILES)

ci1 = Path(tempfile.mkdtemp())             # CI run 1: fresh checkout = seed only, state file absent (old archive or first run)
seed = ci1 / "seed.json"
pp.write_history({"old-page": {"pid": 5, "name": "Old Page"}}, seed)
state1 = ci1 / "player_url_history.json"
check("fresh CI tree: no state file yet; history = the seed", not state1.exists() and set(pp.load_history(state1, seed)) == {"old-page"})
n = pp.update_history(plan_of("new-slug"), state1, seed)
h = pp.load_history(state1, seed)
check("CI build adds the new slug and writes the state file (seed entries carried into it)", n >= 1 and state1.exists() and set(h) == {"old-page", "new-slug"}, h)
check("  the state file alone (no seed) already holds both", set(pp._read_history(state1)) == {"old-page", "new-slug"})

# push -> pull round trip with the real pack/unpack/content_sha used by db_push/db_pull (no network)
sha_before = ss.content_sha(ci1)
blob = ss.pack(ci1)
ci2 = Path(tempfile.mkdtemp())
got = ss.unpack(blob, ci2)
check("pack/unpack carries the history file", "player_url_history.json" in got and (ci2 / "player_url_history.json").exists(), got)
check("  a content change is visible to the push (sha differs from an empty state)", sha_before != ss.content_sha(Path(tempfile.mkdtemp())))

# CI run 2 (next deploy): state restored, no seed involvement; the earlier slug is still there and a newer one is added
state2 = ci2 / "player_url_history.json"
check("next CI build starts from the restored state: new-slug is kept", "new-slug" in pp.load_history(state2, None))
pp.update_history(plan_of("new-slug", "newer-slug"), state2, None)
h2 = pp.load_history(state2, None)
check("  and newer-slug is added, nothing lost", set(h2) == {"old-page", "new-slug", "newer-slug"}, h2)
check("  re-running with nothing new does not change the file", pp.update_history(plan_of("new-slug", "newer-slug"), state2, None) == 0)

# an old archive without the file still unpacks (state from before this change)
old = Path(tempfile.mkdtemp())
(old / "sitemap_state.json").write_text("{}", encoding="utf-8")
blob_old = ss.pack(old)
dst = Path(tempfile.mkdtemp())
check("old archive without the history file unpacks fine", ss.unpack(blob_old, dst) == ["sitemap_state.json"])

# the real seed is committed and non-empty; the state file name is gitignored (not committed)
seed_real = pp._read_history(pp.HISTORY_SEED)
check("committed seed holds the published URLs", len(seed_real) >= 3500 and "y-el-fahli-3" in seed_real, len(seed_real))
gi = (Path(__file__).resolve().parent / ".gitignore").read_text(encoding="utf-8")
check("state file is gitignored", "/player_url_history.json" in gi)

sys.exit(1 if fail else 0)
