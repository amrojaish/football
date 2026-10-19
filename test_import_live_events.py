"""import_live_events.py: compact worker events (ev:<id>) -> events table rows, IRQ/JOR only.
In-memory DB built from football.db's own CREATE statements (read-only), fetch replaced by a fake: no network, no writes to football.db.
Checks: column mapping like fetch_events.py (Card details, «Substitution N» per team in time order, Var detail, goals skipped,
team from side, clean_name), ft:1 guard, 404 skip, existing rows never touched (candidate filter + re-check inside apply),
none marker, window/league/status filters, second apply writes nothing.
Run: python C:\\Users\\User\\Projects\\Football\\test_import_live_events.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_live_events as ile  # noqa: E402
from config import DB_FILE  # noqa: E402

src = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
db = sqlite3.connect(":memory:")
for name in ("matches", "events"):
    db.execute(src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0])
src.close()

NOW = 1_792_400_000            # fixed clock
H, A = 4531, 4529
fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fail += 1


def date_of(secs_ago):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(NOW - secs_ago, timezone.utc).strftime("%Y-%m-%d %H:%M")


def add_match(mid, lg, secs_ago, status="FT"):
    db.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status) "
               "VALUES (?, ?, 2026, ?, ?, ?, 1, 0, ?)", (mid, lg, date_of(secs_ago), H, A, status))


ROWS = [  # [min, extra, type, detail, player, assist/in, side, pid, aid] — deliberately out of time order
    [63, 0, "s", "", "Out Two", "In Two", "h", 3, 4],
    [10, 0, "g", "n", "Scorer", "Helper", "h", 1, 2],
    [30, 0, "c", "y", "Booked\t", "", "a", 5, None],
    [45, 2, "c", "yr", "Sent Off", "", "a", 6, None],
    [55, 0, "s", "", "Out One", "In One", "h", 7, 8],
    [60, 0, "s", "", "Away Out", "Away In", "a", 9, 10],
    [70, 0, "v", "Goal cancelled", "", "", "h", None, None],
    [80, 0, "c", "r", "Straight Red", "", "h", 11, None],
]
PAYLOADS = {
    101: {"fixture": 101, "ft": 1, "l": ROWS},
    102: {"fixture": 102, "ft": 0, "l": ROWS},                        # not final
    103: None,                                                        # 404
    104: {"fixture": 104, "ft": 1, "l": [[12, 0, "g", "n", "Only Goal", "", "h", 1, None]]},   # goals only -> none marker
    105: {"fixture": 105, "ft": 1, "l": ROWS},                        # has a row already
}
calls = []


def fake_fetch(mid):
    calls.append(mid)
    p = PAYLOADS.get(mid)
    return (p, "ok") if p is not None else (None, "none stored")


add_match(101, "IRQ", 5 * 3600)
add_match(102, "JOR", 6 * 3600)
add_match(103, "IRQ", 7 * 3600)
add_match(104, "JOR", 8 * 3600)
add_match(105, "IRQ", 9 * 3600)
db.execute("INSERT INTO events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en) VALUES (105, ?, 20, 'Card', 'Yellow Card', 'Kept', '', '')", (H,))
add_match(106, "IRQ", 37 * 3600)           # outside 36 h
add_match(107, "SAU", 5 * 3600)            # not IRQ/JOR
add_match(108, "JOR", 5 * 3600, "NS")      # not finished
add_match(109, "JOR", -3600, "FT")         # kick-off in the future (bad data) -> excluded

cands = [c[0] for c in ile.candidates(db, NOW)]
check("candidates: IRQ/JOR, finished, last 36 h, no events rows -> 101 102 103 104 (not 105 with a row, 106 old, 107 SAU, 108 NS, 109 future)",
      cands == [104, 103, 102, 101], cands)

planned = {mid: (rows, why) for mid, _lg, rows, why in ile.plan(db, NOW, fetch=fake_fetch)}
check("only candidates are fetched (105 never requested)", sorted(calls) == [101, 102, 103, 104], calls)
check("ft:0 payload refused", planned[102] == (None, "not final (ft != 1)"), planned[102])
check("404 -> skipped with reason", planned[103] == (None, "none stored"), planned[103])

rows = planned[101][0]
want = [
    (101, A, 30, "Card", "Yellow Card", "Booked", "", ""),
    (101, A, 45, "Card", "Second Yellow card", "Sent Off", "", ""),
    (101, H, 55, "subst", "Substitution 1", "Out One", "", "In One"),
    (101, A, 60, "subst", "Substitution 1", "Away Out", "", "Away In"),
    (101, H, 63, "subst", "Substitution 2", "Out Two", "", "In Two"),
    (101, H, 70, "Var", "Goal cancelled", "", "", ""),
    (101, H, 80, "Card", "Red Card", "Straight Red", "", ""),
]
check("mapping: time order, goals skipped, team from side, Card details, Substitution N per team, Var detail, clean_name (tab stripped), player_ar empty",
      rows == want, rows)
check("goals-only final copy -> zero rows (none marker on apply)", planned[104] == ([], "ok"), planned[104])

before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
n = ile.apply(db, ile.plan(db, NOW, fetch=fake_fetch))
after = db.execute("SELECT match_id, type, COUNT(*) FROM events GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
check("apply writes 101 (7 rows) + 104 (none marker); 102/103 untouched; 105 keeps its single row", n == 2 and after == [
    (101, "Card", 3), (101, "Var", 1), (101, "subst", 3), (104, "none", 1), (105, "Card", 1)], [n, after])
check("  105's existing row unchanged", db.execute("SELECT player_en FROM events WHERE match_id = 105").fetchall() == [("Kept",)])

# a row appears between plan and apply (e.g. fetch_events ran): the re-check inside apply must skip it
calls.clear()
PAYLOADS[103] = {"fixture": 103, "ft": 1, "l": ROWS}
p2 = ile.plan(db, NOW, fetch=fake_fetch)
db.execute("INSERT INTO events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en) VALUES (103, ?, 1, 'Card', 'Yellow Card', 'Raced', '', '')", (H,))
n2 = ile.apply(db, p2)
check("row added after planning -> apply re-checks and skips (no overwrite)", n2 == 0
      and db.execute("SELECT COUNT(*) FROM events WHERE match_id = 103").fetchone()[0] == 1, n2)
check("second run: written fixtures are no longer candidates (only 102 left)", [c[0] for c in ile.candidates(db, NOW)] == [102],
      [c[0] for c in ile.candidates(db, NOW)])

print(f"TOTAL FAILS: {fail}")
sys.exit(1 if fail else 0)
