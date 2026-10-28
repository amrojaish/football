"""Unit test of the overdue fix (26 Oct 2026, IRQ 1628016): fetch_overdue.py, refresh_goal_names.py missing-goal mode,
i18n off_label «awaiting confirmation». In-memory SQLite, no network.
Run from the repo root: python test_overdue.py"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_backoff as BO  # noqa: E402
import fetch_overdue as FO  # noqa: E402
import i18n  # noqa: E402
import refresh_goal_names as RG  # noqa: E402

FO.DELAY = 0
RG.DELAY = 0
fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


H = 3600
NOW = 1_800_000_000.0


def kick(hours_ago):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(NOW - hours_ago * H))


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                              home_goals INTEGER, away_goals INTEGER, status TEXT);
        CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, player_en TEXT, player_ar TEXT, detail TEXT);
    """)
    BO.ensure_table(c)
    return c


def upcoming(c, mid, hours_ago, status="NS"):
    c.execute("INSERT INTO matches VALUES (?, 'IRQ', 2026, ?, 1, 2, NULL, NULL, ?)", (mid, kick(hours_ago), status))


def fx(mid, status, hours_ago, hg=None, ag=None, events=None):
    return {"fixture": {"id": mid, "date": kick(hours_ago).replace(" ", "T") + ":00+00:00", "status": {"short": status}},
            "teams": {"home": {"id": 1}, "away": {"id": 2}}, "goals": {"home": hg, "away": ag}, "events": events or []}


def ev(team, minute, name, detail="Normal Goal"):
    return {"type": "Goal", "detail": detail, "team": {"id": team}, "time": {"elapsed": minute}, "player": {"id": 9, "name": name}}


def row(c, mid):
    return dict(c.execute("SELECT date, status, home_goals, away_goals FROM matches WHERE match_id = ?", (mid,)).fetchone())


# ---- fetch_overdue: targets
c = db()
upcoming(c, 1, 30)            # stored kick-off 30 h ago, still NS  -> overdue
upcoming(c, 2, 1)             # 1 h ago: inside the 2 h grace       -> not yet
upcoming(c, 3, -24)           # tomorrow                            -> no
upcoming(c, 4, 30, "CANC")    # cancelled                           -> no
upcoming(c, 5, 30, "PST")     # postponed with a past date          -> overdue (provider may have a new date)
c.execute("INSERT INTO matches VALUES (6, 'IRQ', 2026, ?, 1, 2, 1, 0, 'FT')", (kick(30),))
ids = [r["match_id"] for r in FO.overdue_rows(c, 2026, NOW)]
check("overdue targets = past NS/PST without result, outside the 2 h grace, not cancelled", ids == [1, 5], ids)

# ---- fetch_overdue: one ids call, FT written with goals, new date written, unchanged recorded
calls = []


def fake(endpoint, params):
    calls.append((endpoint, params))
    return True, [fx(1, "FT", 6, 1, 0, [ev(1, 55, "A. Scorer")]), fx(5, "PST", -200)], ""


rep = FO.run(c, 2026, 3, False, fetch=fake, now=NOW)
check("one fixtures?ids call for both targets", calls == [("fixtures", {"ids": "1-5"})], calls)
check("FT: date/status/score from the provider (the IRQ 1628016 case)", row(c, 1) == {"date": kick(6), "status": "FT", "home_goals": 1, "away_goals": 0}, row(c, 1))
check("FT: goals written from the response events", [tuple(r) for r in c.execute("SELECT team_id, minute, player_en FROM goals WHERE match_id = 1")] == [(1, 55, "A. Scorer")])
check("PST: new date written, still no result", row(c, 5) == {"date": kick(-200), "status": "PST", "home_goals": None, "away_goals": None}, row(c, 5))
check("PST: attempt recorded (backoff), FT: none needed", [tuple(r)[:2] for r in c.execute("SELECT match_id, tries FROM stats_attempts WHERE kind = 'overdue'")] == [(5, 1)])
check("report counts", (rep["calls"], rep["finished"], rep["changed"]) == (1, 1, 1), rep)

# ---- fetch_overdue: provider still stale NS -> recorded, next try only on the schedule; failure not recorded
c = db()
upcoming(c, 7, 3)
rep = FO.run(c, 2026, 3, False, fetch=lambda e, p: (True, [fx(7, "NS", 3)], ""), now=NOW)
check("stale NS at the provider: row unchanged, attempt recorded", row(c, 7)["status"] == "NS" and
      c.execute("SELECT tries FROM stats_attempts WHERE match_id = 7").fetchone()[0] == 1)
rep = FO.run(c, 2026, 3, False, fetch=lambda e, p: (True, [], ""), now=NOW + 600)
check("not due again 10 min later (backoff)", rep["due"] == 0 and rep["calls"] == 0, rep)
c2 = db()
upcoming(c2, 8, 3)
FO.run(c2, 2026, 3, False, fetch=lambda e, p: (False, [], "HTTP 500"), now=NOW)
check("failed request: nothing recorded", c2.execute("SELECT COUNT(*) FROM stats_attempts").fetchone()[0] == 0)
c3 = db()
upcoming(c3, 9, 3)
FO.run(c3, 2026, 3, False, fetch=lambda e, p: (True, [fx(9, "AWD", 3)], ""), now=NOW)
check("non-final status (AWD) written, result left NULL", row(c3, 9)["status"] == "AWD" and row(c3, 9)["home_goals"] is None, row(c3, 9))
c4 = db()
for m in range(100, 145):
    upcoming(c4, m, 5)
n = []
FO.run(c4, 2026, 2, False, fetch=lambda e, p: (n.append(p["ids"].count("-") + 1), (True, [], ""))[1], now=NOW)
check("budget 2 = 2 calls of <= 20 ids", n == [20, 20], n)

# ---- refresh_goal_names: missing goal rows
p = [{"team": 1, "minute": 55, "name": "A. Scorer", "pid": 9, "detail": "Normal Goal"}]
u, ins, why = RG.plan_missing([], p, 1)
check("plan_missing: 1-0 with 0 rows -> 1 insert", (u, ins, why) == ([], [(1, 55, "A. Scorer", "Normal Goal")], "ok"), (u, ins, why))
u, ins, why = RG.plan_missing([], p, 2)
check("plan_missing: provider total != score -> nothing", (u, ins) == ([], []) and why.startswith("provider_total"), why)
ours = [{"id": 1, "team_id": 1, "minute": 10, "player_en": "B. Other"}]
p2 = p + [{"team": 1, "minute": 10, "name": "B. Other", "pid": 8, "detail": "Normal Goal"}]
u, ins, why = RG.plan_missing(ours, p2, 2)
check("plan_missing: named row kept, only the missing one inserted", (u, ins, why) == ([], [(1, 55, "A. Scorer", "Normal Goal")], "ok"), (u, ins, why))
ours = [{"id": 1, "team_id": 1, "minute": 30, "player_en": "Z. Unknown"}]   # no name match, no goal within +-1 min
u, ins, why = RG.plan_missing(ours, p2, 2)
check("plan_missing: named row not at the provider -> nothing", (u, ins) == ([], []) and why.startswith("named_goal_not_in_provider"), why)
ours = [{"id": 1, "team_id": 1, "minute": 10, "player_en": ""}]
u, ins, why = RG.plan_missing(ours, p2, 2)
check("plan_missing: blank row filled + leftover inserted", (u, ins, why) == ([(1, "B. Other", 10, "Normal Goal")], [(1, 55, "A. Scorer", "Normal Goal")], "ok"), (u, ins, why))

c = db()
c.execute("INSERT INTO matches VALUES (20, 'IRQ', 2026, ?, 1, 2, 1, 0, 'FT')", (kick(30),))
rep = RG.run(c, 2026, 10, False, fetch=lambda mid: (True, [ev(1, 55, "A. Scorer")], ""), now=NOW)
check("run: missing match inserted (kind goals_missing)", rep["inserted"] == 1 and
      [tuple(r) for r in c.execute("SELECT team_id, minute, player_en FROM goals WHERE match_id = 20")] == [(1, 55, "A. Scorer")], rep["lines"])
check("run: attempt recorded as goals_missing", c.execute("SELECT kind FROM stats_attempts WHERE match_id = 20").fetchone()[0] == "goals_missing")
c = db()
c.execute("INSERT INTO matches VALUES (21, 'IRQ', 2026, ?, 1, 2, 1, 0, 'FT')", (kick(30),))
rep = RG.run(c, 2026, 10, False, fetch=lambda mid: (True, [], ""), now=NOW)
check("run: provider still without events -> unchanged, retried later on the schedule",
      rep["inserted"] == 0 and c.execute("SELECT tries FROM stats_attempts WHERE match_id = 21").fetchone()[0] == 1, rep["lines"])

# ---- i18n: off labels (28 Oct 2026: the «awaiting confirmation» label is gone — an overdue match renders like an upcoming one)
t = i18n.T["ar"]
check("off_label: NS 2 h after kick-off -> normal", i18n.off_label("NS", t, kick(2), NOW) == "")
check("off_label: FT never", i18n.off_label("FT", t, kick(40), NOW) == "")
check("off_label: date without time never", i18n.off_label("NS", t, "2020-01-01", NOW) == "")
check("off_label: no date = old behaviour", i18n.off_label("NS", t) == "" and i18n.off_label("PST", t) == t["st_pst"])
check("off_label: SUSP shown as postponed", i18n.off_label("SUSP", t, kick(40), NOW) == t["st_pst"])
import make_site3 as MS  # noqa: E402
_od = kick(5)   # NS, kick-off 5 h ago, no result yet (an overdue row: overdue_rows picks it up for the re-fetch)
_card = MS.match_card({"match_id": 900, "date": _od, "home_goals": None, "away_goals": None, "league_code": "IRQ", "season": 2026,
                       "status": "NS", "home_id": 1, "away_id": 2, "home": "A", "home_en": "A", "home_logo": "", "away": "B",
                       "away_en": "B", "away_logo": ""}, "en", {}, show_league=False, upcoming=True)
check("overdue match renders its kick-off time exactly like an upcoming match (time cell, no status label)",
      'class="score time"' in _card and f'data-utc="{_od[:10]}T{_od[11:16]}:00Z"' in _card and "score pst" not in _card, _card[:400])

print(f"\nTOTAL FAILS: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
