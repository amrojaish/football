#!/usr/bin/env python3
"""
Stadium (venues.py) + official squad / coach (squads.py) and the club page that reads them (29-30 Oct 2026, batch 2 C3/C7 data) —
offline: in-memory DBs + saved API-shaped samples (test_data/venues_sample, test_data/squads_sample), zero API calls,
football.db never written. Run:
    python C:\\Users\\User\\Projects\\Football\\test_venues_squads.py

  venues  parse /teams (team_merges id mapping, club without a venue skipped, capacity/surface optional) · migrate idempotent ·
          save keeps a known capacity when a later reply lacks it · --check prints and writes nothing (football.db md5 unchanged)
  card    venues row -> name, city, capacity, surface (AR/EN labels) · no venues table / no row -> the old match-venue fallback
  squads  parse /players/squads (players without an id skipped, position -> G/D/M/F) · current coach = same club, no end date ·
          save replaces the club/season list · an empty reply does not wipe a list · --check writes nothing
  tab     official list wins (its numbers/positions, apps from our lineups, Arabic name from our rows, age/nationality from
          player_info) · coach row from coaches · no official list -> lineup-based list + lineup coach (unchanged)
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import venues   # noqa: E402
import squads   # noqa: E402
import make_clubs as mc   # noqa: E402

VS = ROOT / "test_data" / "venues_sample"
SS = ROOT / "test_data" / "squads_sample"
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:500]))
    if not cond:
        fails += 1


def base_db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                            home_goals INTEGER, away_goals INTEGER, status TEXT, round TEXT, venue_name TEXT, venue_city TEXT, referee TEXT);
      CREATE TABLE lineups (match_id INTEGER, team_id INTEGER, formation TEXT, coach_en TEXT, coach_ar TEXT);
      CREATE TABLE lineup_players (match_id INTEGER, team_id INTEGER, player_id INTEGER, player_en TEXT, player_ar TEXT, number INTEGER,
                                   pos TEXT, grid TEXT, starter INTEGER);
      CREATE TABLE player_stats (match_id INTEGER, team_id INTEGER, player_id INTEGER, player_en TEXT, player_ar TEXT, pos TEXT);
      CREATE TABLE player_info (player_id INTEGER PRIMARY KEY, age INTEGER, nationality TEXT, position TEXT);
    """)
    c.executemany("INSERT INTO matches VALUES (?, 'SAU', 2026, ?, ?, ?, ?, ?, 'FT', '', ?, ?, '')", [
        (1, "2026-09-01 18:00", 2939, 2932, 2, 0, "King Saud University Stadium", "Riyadh"),
        (2, "2026-09-10 18:00", 2932, 2939, 1, 1, "Kingdom Arena", "Riyadh"),
        (3, "2026-09-20 18:00", 2939, 2933, 3, 1, "King Saud University Stadium", "Riyadh")])
    c.executemany("INSERT INTO lineups VALUES (?, 2939, '4-3-3', 'Lineup Coach', 'مدرب التشكيلة')", [(1,), (2,), (3,)])
    c.executemany("INSERT INTO lineup_players VALUES (?, 2939, ?, ?, ?, ?, ?, '', 1)", [
        (1, 874, "Cristiano Ronaldo", "كريستيانو رونالدو", 7, "F"), (2, 874, "Cristiano Ronaldo", "كريستيانو رونالدو", 7, "F"),
        (3, 874, "Cristiano Ronaldo", "كريستيانو رونالدو", 7, "F"),
        (1, 9999001, "T. Keeper", "", 1, "G"), (3, 9999001, "T. Keeper", "", 1, "G"),
        (2, 5555, "Lineup Only", "لاعب التشكيلة", 30, "M")])
    c.execute("INSERT INTO player_info VALUES (874, 41, 'Portugal', 'Attacker')")
    return c


# ── venues ──
saud = json.loads((VS / "SAU.json").read_text(encoding="utf-8"))["response"]
irq = json.loads((VS / "IRQ.json").read_text(encoding="utf-8"))["response"]
rows = venues.parse(saud, {28571: 5242})
check("venues.parse: 2 clubs with a venue, the club without a venue name skipped",
      [r[0] for r in rows] == [2939, 2932] and rows[0][2] == "Al-Awwal Park" and rows[0][5] == 25000 and rows[0][6] == "grass"
      and rows[1][5] is None, rows)
check("venues.parse: provider id 28571 -> our 5242 via team_merges (IRQ Al Shorta)", venues.parse(irq, {28571: 5242})[0][0] == 5242)
c = base_db()
check("before migrate: has_venues False, get_venue None (card falls back)", not venues.has_venues(c) and venues.get_venue(c, 2939) is None)
html = mc.stadium_card(c, 2939, "en")
check("no venues table -> old fallback card: most frequent home venue from matches", "King Saud University Stadium" in html and "Capacity" not in html, html)
check("migrate creates the table, second run is a no-op", venues.migrate(c) is True and venues.migrate(c) is False and venues.has_venues(c))
check("save writes one row per club", venues.save(c, "SAU", rows) == 2)
venues.save(c, "SAU", [(2939, 1001, "Al-Awwal Park", "Riyadh", None, None, None)])
v = venues.get_venue(c, 2939)
check("a later reply without capacity/surface keeps the known values", v["capacity"] == 25000 and v["surface"] == "grass", v)
en, ar = mc.stadium_card(c, 2939, "en"), mc.stadium_card(c, 2939, "ar")
check("card EN: name, city, Capacity 25,000, Surface Grass", all(x in en for x in ("Al-Awwal Park", "Riyadh", "Capacity", "25,000", "Grass")), en)
check("card AR: السعة / الأرضية عشب طبيعي", all(x in ar for x in ("Al-Awwal Park", "السعة", "25,000", "الأرضية", "عشب طبيعي")), ar)
h2 = mc.stadium_card(c, 2932, "en")
check("venue without capacity: no Capacity row, surface shown (Artificial turf)", "Capacity" not in h2 and "Artificial turf" in h2, h2)
check("club with no venues row -> fallback still works", "King Saud University Stadium" not in mc.stadium_card(c, 2933, "en"))

# ── squads ──
sq = json.loads((SS / "squad_2939.json").read_text(encoding="utf-8"))["response"]
co = json.loads((SS / "coach_2939.json").read_text(encoding="utf-8"))["response"]
srows = squads.parse_squad(sq)
check("parse_squad: 3 players (the one without an id skipped), positions -> F/G/D, missing number = None",
      [(r[0], r[2], r[3]) for r in srows] == [(874, 7, "F"), (9999001, 24, "G"), (9999002, None, "D")], srows)
check("parse_coach: current coach = this club, no end date (not the old one)", squads.parse_coach(co, 2939)[1] == "A. Postecoglou")
check("parse_coach: other club id -> None", squads.parse_coach(co, 1234) is None)
c2 = base_db()
lineup_html = mc.squad_block(c2, 2939, "SAU", 2026, "en")
check("no squads tables -> lineup-based list + lineup coach (unchanged behaviour)",
      "Lineup Coach" in lineup_html and "Lineup Only" in lineup_html and "T. Keeper" in lineup_html, lineup_html[:300])
check("migrate creates squads + coaches, second run no-op", squads.migrate(c2) == ["squads", "coaches"] and squads.migrate(c2) == [])
check("save_squad + save_coach", squads.save_squad(c2, 2939, 2026, srows) == 3 and squads.save_coach(c2, 2939, squads.parse_coach(co, 2939)) == 1)
check("an empty reply does not wipe the list", squads.save_squad(c2, 2939, 2026, []) == 0 and len(squads.get_squad(c2, 2939, 2026)) == 3)
en = mc.squad_block(c2, 2939, "SAU", 2026, "en")
ar = mc.squad_block(c2, 2939, "SAU", 2026, "ar")
check("official list wins: its players only (no 'Lineup Only'), official number 24 for the keeper, unseen defender listed",
      "Lineup Only" not in en and ">24<" in en and "Test Defender" in en, en)
check("apps from our lineups: Ronaldo 3, keeper 2, defender 0", "3 <small>apps" in en and "2 <small>apps" in en and "0 <small>apps" in en, en)
check("coach row from coaches (A. Postecoglou · Australia · Age 61), not the lineup coach",
      "A. Postecoglou" in en and "Australia" in en and "Age 61" in en and "Lineup Coach" not in en, en)
check("age/nationality from player_info: Ronaldo 'Portugal · Age 41' (EN), «البرتغال» or Portugal in AR",
      "Portugal · Age 41" in en and ("البرتغال" in ar or "Portugal" in ar) and "العمر 41" in ar, ar)
check("AR name from our rows (كريستيانو رونالدو)", "كريستيانو رونالدو" in ar)
check("groups: Goalkeepers / Defenders / Attackers", all(x in en for x in ("Goalkeepers", "Defenders", "Attackers")))

# ── --check modes: no writes, no calls ──
db = ROOT / "football.db"
h0 = hashlib.md5(db.read_bytes()).hexdigest()
o1 = subprocess.run([sys.executable, str(ROOT / "venues.py"), "--check", "--from-json", str(VS)], capture_output=True, text=True,
                    encoding="utf-8", cwd=ROOT)
o2 = subprocess.run([sys.executable, str(ROOT / "squads.py"), "--check", "--from-json", str(SS)], capture_output=True, text=True,
                    encoding="utf-8", cwd=ROOT)
h1 = hashlib.md5(db.read_bytes()).hexdigest()
check("venues.py --check: reads the samples, prints the plan, exit 0", o1.returncode == 0 and "[فحص]" in o1.stdout and "SAU: 2" in o1.stdout,
      o1.stdout[-400:] + o1.stderr[-400:])
check("squads.py --check: 2939 -> 3 players + coach, exit 0", o2.returncode == 0 and "[فحص]" in o2.stdout and "3 لاعباً" in o2.stdout,
      o2.stdout[-400:] + o2.stderr[-400:])
check("football.db md5 unchanged by both --check runs", h0 == h1)

print("FAILS:", fails)
sys.exit(1 if fails else 0)
