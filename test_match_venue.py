#!/usr/bin/env python3
"""
Venue + referee (28 Oct 2026, match_venue.py) — offline: in-memory DBs, no football.db, no API. Run:
    python C:\\Users\\User\\Projects\\Football\\test_match_venue.py
Checks: OLD schema (columns absent) = every writer behaves exactly as before (no error, nothing written); migrate() = ADD COLUMN only
(3 nullable TEXT columns at the end, rows untouched, idempotent); NEW schema = save_finished / the upcoming insert fill
venue_name / venue_city / referee from the fixture reply and keep an existing value the new reply lacks (across INSERT OR REPLACE);
the season-wide update never blanks a value; the match info card shows «stadium, city» and «referee» rows when present and hides
them when NULL / absent (provider text as-is).
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import match_venue as MV  # noqa: E402
import fetch_matches2 as FM  # noqa: E402
import make_matches as MM  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


def db(rnd=True):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER,
                 away_id INTEGER, home_goals INTEGER, away_goals INTEGER, status TEXT)""")
    if rnd:
        c.execute("ALTER TABLE matches ADD COLUMN round TEXT")
    c.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, "
              "player_en TEXT, player_ar TEXT, detail TEXT)")
    return c


def fx(mid, venue=("Petrosport Stadium", "Cairo"), referee="I. Ghuloum", hg=1, ag=0):
    v = {"id": 485, "name": venue[0], "city": venue[1]} if venue else {"id": None, "name": None, "city": None}
    return {"fixture": {"id": mid, "date": "2026-08-21T14:00:00+00:00", "venue": v, "referee": referee, "status": {"short": "FT"}},
            "league": {"round": "Regular Season - 3"}, "teams": {"home": {"id": 1}, "away": {"id": 2}}, "goals": {"home": hg, "away": ag}}


def row(c, mid):
    return tuple(c.execute("SELECT venue_name, venue_city, referee FROM matches WHERE match_id = ?", (mid,)).fetchone())


# ── OLD schema: no-op everywhere ──
c = db()
check("old schema: has_venue False, current() None", MV.has_venue(c) is False and MV.current(c, 1) is None)
FM.save_finished(c, "EGY", 2026, fx(1), [])
r = c.execute("SELECT * FROM matches WHERE match_id = 1").fetchone()
check("old schema: save_finished writes the row exactly as before (9 + round columns, no venue)",
      r is not None and r["home_goals"] == 1 and r["round"] == "Regular Season - 3" and "venue_name" not in r.keys(), dict(r))
check("old schema: save() is a no-op (0)", MV.save(c, fx(1)) == 0)

# ── migration: ADD COLUMN only ──
before_cols = [x[1] for x in c.execute("PRAGMA table_info(matches)")]
before_rows = [tuple(x) for x in c.execute("SELECT * FROM matches")]
added = MV.migrate(c)
after_cols = [x[1] for x in c.execute("PRAGMA table_info(matches)")]
types = {x[1]: (x[2], x[3]) for x in c.execute("PRAGMA table_info(matches)")}
check("migrate: exactly venue_name/venue_city/referee appended (TEXT, nullable), old columns unchanged",
      added == list(MV.COLS) and after_cols == before_cols + list(MV.COLS) and all(types[k] == ("TEXT", 0) for k in MV.COLS), after_cols)
check("migrate: rows kept, new columns NULL (no backfill by itself)",
      [tuple(x)[:len(before_cols)] for x in c.execute("SELECT * FROM matches")] == before_rows and row(c, 1) == (None, None, None))
check("migrate again: nothing added", MV.migrate(c) == [])

# ── NEW schema: fill and preserve ──
FM.save_finished(c, "EGY", 2026, fx(1), [])
check("new schema: save_finished fills venue/city/referee from the reply", row(c, 1) == ("Petrosport Stadium", "Cairo", "I. Ghuloum"), row(c, 1))
FM.save_finished(c, "EGY", 2026, fx(1, referee=None), [])
check("INSERT OR REPLACE with a reply WITHOUT referee keeps the known referee (and venue)",
      row(c, 1) == ("Petrosport Stadium", "Cairo", "I. Ghuloum"), row(c, 1))
FM.save_finished(c, "EGY", 2026, fx(1, venue=("Cairo Stadium", "Cairo"), referee="M. Adel"), [])
check("a new non-null value replaces the old one", row(c, 1) == ("Cairo Stadium", "Cairo", "M. Adel"), row(c, 1))
check("season-wide update (no REPLACE) with nulls never blanks: save() -> 0 changes",
      MV.save(c, fx(1, venue=None, referee=None)) == 0 and row(c, 1) == ("Cairo Stadium", "Cairo", "M. Adel"))
c.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, status) VALUES (2, 'EGY', 2026, '2026-11-01 17:00', 1, 2, 'NS')")
check("season-wide update fills an upcoming row (referee not announced yet -> NULL)",
      MV.save(c, fx(2, referee=None)) == 1 and row(c, 2) == ("Petrosport Stadium", "Cairo", None), row(c, 2))
check("venue_of: blank strings -> None", MV.venue_of(fx(3, venue=("  ", ""), referee=" ")) == (None, None, None))

# ── match info card ──
base = {"match_id": 9, "league_code": "EGY", "season": 2026, "date": "2026-11-01 17:00", "status": "NS", "round": "Regular Season - 3"}


def card(**kw):
    return MM.info_card(dict(base, **kw), "ar", "2026-11-01", "17:00", "")


h = card(venue_name="Petrosport Stadium", venue_city="Cairo", referee="I. Ghuloum")
check("card: present -> «Petrosport Stadium, Cairo» row + «I. Ghuloum» row (provider text as-is)",
      'data-k="venue"' in h and ">Petrosport Stadium, Cairo<" in h and 'data-k="ref"' in h and ">I. Ghuloum<" in h, h[-500:])
h = card(venue_name="Petrosport Stadium", venue_city=None, referee=None)
check("card: venue without city -> «Petrosport Stadium» only; NULL referee -> no referee row",
      ">Petrosport Stadium<" in h and 'data-k="ref"' not in h, h[-400:])
h = card(venue_name=None, venue_city=None, referee=None)
check("card: all NULL -> neither row", 'data-k="venue"' not in h and 'data-k="ref"' not in h)
h = card()
check("card: columns absent (old schema) -> neither row, no error", 'data-k="venue"' not in h and 'data-k="ref"' not in h)

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
