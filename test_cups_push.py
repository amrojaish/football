#!/usr/bin/env python3
"""
Cups phase 2 (9 Nov 2026): the per-cup push switch on the site side (config.PUSH_CUPS). Default OFF. Bell on cup match pages and cup-only clubs only when ON,
30-min reminder rows (make_kickoffs) only when ON, no vote rows for cups, scorer-name SQL unchanged when OFF, config and worker.js agree. No network.
Pages use the real football.db read-only through a temp copy. Run from the repo root:
    python C:\\Users\\User\\Projects\\Football\\test_cups_push.py
"""
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from _test_tmp import make_tmp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import competitions as CP  # noqa: E402
import config  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


SRC = (ROOT / "worker.js").read_text(encoding="utf-8")
ids_in_worker = [int(x) for x in re.findall(r"\d+", re.search(r"const PUSH_CUP_LEAGUE_IDS = new Set\(\[(.*?)\]\);", SRC).group(1))]
check("default OFF: config.PUSH_CUPS is empty", config.PUSH_CUPS == ())
check("default OFF: worker PUSH_CUP_LEAGUE_IDS is empty", ids_in_worker == [])
check("config and worker agree", sorted(CP.provider_id(c) for c in config.PUSH_CUPS) == sorted(ids_in_worker), ids_in_worker)
check("every PUSH_CUPS code is a known cup", all(CP.is_cup(c) for c in config.PUSH_CUPS))
check("prepared live-only line is commented out, live list still 302 only",
      "const LIVE_ONLY_LEAGUE_IDS = new Set([302]);" in SRC and config.LIVE_CUPS == ("UAE-LC",))
check("bell gates use the switch", "CP.push_on" in (ROOT / "make_matches.py").read_text(encoding="utf-8") and "CP.push_on" in (ROOT / "make_site3.py").read_text(encoding="utf-8"))

# scorer-name SQL
check("OFF: scorer-name SQL is byte-identical to the cup gate", CP.no_cup_except_push_sql("m.league_code") == CP.no_cup_sql("m.league_code"))
CP.PUSH_CUPS = ("UAE-PC",)
sql = CP.no_cup_except_push_sql("m.league_code")
check("ON: that cup counts, the others stay excluded", "'UAE-PC'" not in sql and "'SAU-KC'" in sql, sql[:200])
CP.PUSH_CUPS = ()

# make_kickoffs
import make_kickoffs as MK  # noqa: E402
TMPD = make_tmp("cups_push_")
con = sqlite3.connect(TMPD / "k.db")
con.executescript("""
  CREATE TABLE matches (match_id INTEGER PRIMARY KEY, date TEXT, league_code TEXT, home_id INT, away_id INT, home_goals INT, status TEXT);
  CREATE TABLE teams (team_id INT PRIMARY KEY, name_en TEXT, name_en_official TEXT);
  INSERT INTO teams VALUES (1,'A',''),(2,'B','');
""")
now = int(time.time())
d = time.strftime("%Y-%m-%d %H:%M", time.gmtime(now + 3600))
con.executemany("INSERT INTO matches VALUES (?,?,?,1,2,NULL,'NS')", [(1, d, "SAU"), (2, d, "UAE-LC"), (3, d, "UAE-PC")])
con.commit()
b = MK.build(con, now)
check("OFF: league in f and v", [r[1] for r in b["f"]] == [1] and "1" in b["v"], b)
check("OFF: live-only cup in the poll window only; other cup absent", set(b["v"]) == {"1"} and len(b["k"]) == 1, b)
CP.PUSH_CUPS = ("UAE-PC",)
b = MK.build(con, now)
check("ON: that cup gets a reminder row with its provider id", sorted(r[1] for r in b["f"]) == [1, 3] and [r[4] for r in b["f"] if r[1] == 3] == [CP.provider_id("UAE-PC")], b)
check("ON: no vote row for a cup", set(b["v"]) == {"1"}, b["v"])
CP.PUSH_CUPS = ("UAE-LC",)
b = MK.build(con, now)
check("ON for a live-only cup: reminder row, no vote", sorted(r[1] for r in b["f"]) == [1, 2] and set(b["v"]) == {"1"}, b)
CP.PUSH_CUPS = ()
con.close()

# bells
big = TMPD / "football.db"
shutil.copy(config.DB_FILE, big)
con = sqlite3.connect(big)
con.row_factory = sqlite3.Row
check("OFF: push_cup_clubs is empty", CP.push_cup_clubs(con) == set())
CP.PUSH_CUPS = ("CAF-CL",)
clubs = CP.push_cup_clubs(con)
n_expected = con.execute("SELECT COUNT(*) FROM (SELECT home_id FROM matches WHERE league_code='CAF-CL' UNION SELECT away_id FROM matches WHERE league_code='CAF-CL')").fetchone()[0]
check("ON: push_cup_clubs = the cup's clubs", len(clubs) == n_expected and n_expected > 10, (len(clubs), n_expected))
# every enabled cup's clubs are subscribable once its switch is on
known = set()
for block in (re.search(r"const BASE_TEAM_IDS = \[(.*?)\];", SRC, re.S).group(1), re.sub(r"\b\d+:\s*\[", "[", re.search(r"const PENDING_TEAM_IDS = \{(.*?)\n\};", SRC, re.S).group(1))):
    known |= {int(x) for x in re.findall(r"\d+", block)}
cup_lists = {int(k): {int(x) for x in re.findall(r"\d+", re.sub(r"//[^\n]*", "", v))} for k, v in re.findall(r"\n  (\d+): \[(.*?)\n  \],", re.search(r"const PUSH_CUP_TEAM_IDS = \{(.*?)\n\};", SRC, re.S).group(1), re.S)}
for code in CP.PUSH_CUPS:   # CAF-CL here, the largest list
    need = {r[0] for r in con.execute("SELECT home_id FROM matches WHERE league_code = ? UNION SELECT away_id FROM matches WHERE league_code = ?", (code, code))}
    miss = need - known - cup_lists.get(CP.provider_id(code), set())
    check(f"{code}: every club is subscribable", not miss, miss)
CP.PUSH_CUPS = ()

import make_clubs as MCL  # noqa: E402
import make_matches as mm  # noqa: E402
mm.LATEST_SEASON = 2026
mm.build_form_index(con)
teams = mm.load_teams()
row = lambda q: con.execute(f"SELECT * FROM matches WHERE {q} LIMIT 1").fetchone()  # noqa: E731
cup = row("league_code = 'CAF-CL' AND status = 'FT'")
lg = row("league_code = 'SAU' AND status = 'FT'")
page = lambda r: mm.build_page(r, teams.get(r["home_id"]), teams.get(r["away_id"]), [], None, "ar")  # noqa: E731
check("OFF: cup match page has the star, no bell", 'id="mstar"' in page(cup) and 'id="pushbtn"' not in page(cup))
check("OFF: league match page keeps its bell", 'id="pushbtn"' in page(lg))
CP.PUSH_CUPS = ("CAF-CL",)
check("ON: cup match page shows the bell", 'id="pushbtn"' in page(cup))
other = row("league_code = 'CAF-CC' AND status = 'FT'")
check("ON for one cup: another cup's page stays without a bell", 'id="pushbtn"' not in page(other))
CP.PUSH_CUPS = ()
cup_only, lg_club = 5468, 2932   # AS Sobemap (CAF only), Al-Hilal
club = lambda t, lg: dict(teams[t], league=lg)  # noqa: E731
CP.PUSH_CUP_CLUBS.clear()
check("OFF: cup-only club has no bell", "fgbell" not in MCL.follow_group(cup_only, club(cup_only, ""), "ar"))
check("league club keeps its bell", "fgbell" in MCL.follow_group(lg_club, club(lg_club, "SAU"), "ar"))
CP.PUSH_CUP_CLUBS.add(cup_only)
check("ON: cup-only club shows the bell", "fgbell" in MCL.follow_group(cup_only, club(cup_only, ""), "ar"))
CP.PUSH_CUP_CLUBS.clear()
con.close()

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
