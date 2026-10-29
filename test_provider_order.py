#!/usr/bin/env python3
"""
Table order = provider order (29 Oct 2026, Amr's decision; tiebreak.provider_order) — offline, in-memory DBs, no API. Run:
    python C:\\Users\\User\\Projects\\Football\\test_provider_order.py
Fixture: test_data/standings_1029.json — our finished 2026 matches + the provider /standings of 29 Oct 2026 (Part A report).

  SAU  Al-Kholood / Al-Khaleej / Al-Riyadh 12 pts: our H2H puts Riyadh 9th, provider (GD) Kholood 9th -> provider order wins
  EGY  Mokawloon / NBE / Masr 11 pts, NBE has not met the others: our 3-way H2H drops NBE below Masr -> provider order wins
  MAR  Meknès / Kawkab 10 pts, Kawkab won the H2H 1-0: our 2-team H2H puts Kawkab 1st, provider (GD) Meknès 1st -> provider order wins
  stale  TUN: the provider counted 3 matches that were still live in our DB (P/Pts differ) -> our own tie-break order, unchanged;
         also: extra provider rows, missing provider rows, and a provider row with no team id matched by elimination (Monastir)
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from make_site3 import get_table          # noqa: E402
import tiebreak                           # noqa: E402

FIX = json.loads((ROOT / "test_data" / "standings_1029.json").read_text(encoding="utf-8"))["leagues"]
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:500]))
    if not cond:
        fails += 1


def db(lg, provider=True, prov_rows=None):
    """in-memory DB with one league's 2026 matches + teams (+ provider rows unless provider=False)"""
    d = FIX[lg]
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE teams (team_id INTEGER PRIMARY KEY, short_name_ar TEXT, name_en TEXT, name_en_official TEXT, logo TEXT)")
    c.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER,"
              " away_id INTEGER, home_goals INTEGER, away_goals INTEGER, status TEXT)")
    c.execute("CREATE TABLE api_standings (league_code TEXT, season INTEGER, team_id INTEGER, rank INTEGER, played INTEGER,"
              " points INTEGER, fetched_at TEXT)")
    c.executemany("INSERT INTO teams VALUES (?, ?, ?, '', '')", [(t, n, n) for t, n in d["teams"]])
    c.executemany("INSERT INTO matches VALUES (?, ?, 2026, ?, ?, ?, ?, ?, 'FT')", [(m[0], lg, *m[1:]) for m in d["matches"]])
    if provider:
        c.executemany("INSERT INTO api_standings VALUES (?, 2026, ?, ?, ?, ?, '2026-10-29 16:30')",
                      [(lg, *r) for r in (prov_rows if prov_rows is not None else d["provider"])])
    return c


def order(c, lg):
    return [r["team_id"] for r in get_table(c, lg, 2026)]


def prov_order(lg):
    return [r[0] for r in sorted(FIX[lg]["provider"], key=lambda r: r[1])]


def pos(seq, tid):
    return seq.index(tid) + 1


# ── SAU: three teams on 12 pts ──
KHOLOOD, KHALEEJ, RIYADH = 10509, 2928, 10511
ours_own = order(db("SAU", provider=False), "SAU")
got = order(db("SAU"), "SAU")
check("SAU precondition: our own tie-break (H2H) puts Al-Riyadh above Al-Kholood", pos(ours_own, RIYADH) < pos(ours_own, KHOLOOD),
      [pos(ours_own, t) for t in (KHOLOOD, KHALEEJ, RIYADH)])
check("SAU: provider P/Pts = ours -> table = provider order exactly (Kholood 9, Khaleej 10, Riyadh 11)",
      got == prov_order("SAU") and [pos(got, t) for t in (KHOLOOD, KHALEEJ, RIYADH)] == [9, 10, 11], [pos(got, t) for t in (KHOLOOD, KHALEEJ, RIYADH)])

# ── EGY: three teams on 11 pts, NBE has not met the other two ──
MOK, NBE, MASR = 1575, 15570, 7520
ours_own = order(db("EGY", provider=False), "EGY")
got = order(db("EGY"), "EGY")
check("EGY precondition: our 3-way H2H drops NBE below Masr", pos(ours_own, MASR) < pos(ours_own, NBE), [pos(ours_own, t) for t in (MOK, NBE, MASR)])
check("EGY: table = provider order exactly (Mokawloon 7, NBE 8, Masr 9)",
      got == prov_order("EGY") and [pos(got, t) for t in (MOK, NBE, MASR)] == [7, 8, 9], [pos(got, t) for t in (MOK, NBE, MASR)])

# ── MAR: two teams on 10 pts, Kawkab won the H2H ──
MEKNES, KAWKAB = 22218, 971
ours_own = order(db("MAR", provider=False), "MAR")
got = order(db("MAR"), "MAR")
check("MAR precondition: our 2-team H2H puts Kawkab 1st", pos(ours_own, KAWKAB) == 1 and pos(ours_own, MEKNES) == 2)
check("MAR: table = provider order exactly (Meknès 1, Kawkab 2)", got == prov_order("MAR") and pos(got, MEKNES) == 1 and pos(got, KAWKAB) == 2,
      [pos(got, MEKNES), pos(got, KAWKAB)])

# ── stale / unusable provider table -> our own order ──
ours_own = order(db("TUN", provider=False), "TUN")
got = order(db("TUN"), "TUN")
check("stale TUN: provider counted 3 matches still live for us (P/Pts differ) -> our own tie-break order, unchanged",
      got == ours_own and got != prov_order("TUN"), {"got": got[:6], "prov": prov_order("TUN")[:6]})
check("stale TUN: the provider row without a team id (Monastir) is in the fixture (elimination case below uses it)",
      sum(1 for r in FIX["TUN"]["provider"] if r[0] is None) == 1)
# provider rows rebuilt from OUR table (same P/Pts), in a different but valid order, with Monastir's id blanked -> matched by elimination
c = db("TUN", provider=False)
rows = get_table(c, "TUN", 2026)
mine = sorted(rows, key=lambda r: (-r["points"], r["team_id"]))   # a valid order by points (ties by id, not by our tie-break)
fake = [[None if r["team_id"] == 992 else r["team_id"], i, r["played"], r["points"]] for i, r in enumerate(mine, 1)]
got = order(db("TUN", prov_rows=fake), "TUN")
check("elimination: one provider row with no team id + one team of ours left, P/Pts equal -> provider order used",
      got == [r["team_id"] for r in mine], {"got": got, "want": [r["team_id"] for r in mine]})
got = order(db("TUN", prov_rows=fake + [[None, 17, 6, 12]]), "TUN")
check("extra provider rows (accumulated NULL-id rows before 29 Oct 2026) -> our own order", got == ours_own)
got = order(db("TUN", prov_rows=fake[:-1]), "TUN")
check("a provider row missing -> our own order", got == ours_own)
bad = [list(r) for r in fake]
bad[3][3] += 3   # one team's points differ (deduction / unapplied award)
got = order(db("TUN", prov_rows=bad), "TUN")
check("one team's points differ -> our own order (no partial use of the provider ranks)", got == ours_own)
# team_merges: provider id 28571 -> our 5242 (IRQ Al Shorta)
check("team_merges.csv maps the provider's 28571 to our 5242 (IRQ Al Shorta)", tiebreak._team_merges().get(28571) == 5242)

print("FAILS:", fails)
sys.exit(1 if fails else 0)
