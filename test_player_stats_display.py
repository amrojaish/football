#!/usr/bin/env python3
"""
All stored player stats on the player page + match overlay (28 Oct 2026). Offline: synthetic in-memory DB, no football.db,
no network. Run:
    python C:\\Users\\User\\Projects\\Football\\test_player_stats_display.py
Checks: season table grouped (General / Attack / Passing / Defence / Discipline / Goalkeeping) in ONE table; a stat shows only
when the player has a non-null value for it in some season, a season without one shows "—" (never 0); all-zero columns hidden
(except apps/mins/goals/assists/conceded/pct); per-90 under shots/tackles/interceptions from the minutes where the stat exists;
Goalkeeping for keepers only; the 4 new columns (player_stats_extra): ADD COLUMN only, idempotent, read/written only once they
exist; fetcher extract() maps them (provider spelling "commited"); overlay shows them when set and hides NULL.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_players as MP  # noqa: E402
import player_stats_extra as PX  # noqa: E402
import fetch_player_stats as FPS  # noqa: E402
from lineup_view import _stat_rows  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:700]))
    if not cond:
        fails += 1


COLS = ("match_id INTEGER, team_id INTEGER, player_id INTEGER, player_en TEXT, player_ar TEXT, minutes INTEGER, rating REAL, "
        "captain INTEGER, substitute INTEGER, pos TEXT, shots_total INTEGER, shots_on INTEGER, goals INTEGER, conceded INTEGER, "
        "assists INTEGER, saves INTEGER, passes_total INTEGER, passes_key INTEGER, passes_pct INTEGER, tackles INTEGER, "
        "blocks INTEGER, interceptions INTEGER, duels_total INTEGER, duels_won INTEGER, dribbles_try INTEGER, dribbles_ok INTEGER, "
        "fouls_drawn INTEGER, fouls_made INTEGER, yellow INTEGER, red INTEGER, pen_scored INTEGER, pen_missed INTEGER, "
        "pen_saved INTEGER, PRIMARY KEY (match_id, player_id)")      # = the real table before the migration


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER)")
    c.execute(f"CREATE TABLE player_stats ({COLS})")
    c.executemany("INSERT INTO matches VALUES (?, ?, ?)", [(1, "EGY", 2026), (2, "EGY", 2026), (3, "EGY", 2025), (4, "SAU", 2026),
                                                            (5, "SAU", 2026)])
    return c


def ins(c, **kw):
    kw.setdefault("minutes", 90)
    kw.setdefault("pos", "M")
    c.execute(f"INSERT INTO player_stats ({', '.join(kw)}) VALUES ({', '.join('?' * len(kw))})", list(kw.values()))


# ── outfield player 7: two EGY 2026 matches with full stats, one EGY 2025 match with only minutes/rating ──
c = db()
ins(c, match_id=1, player_id=7, rating=7.0, goals=1, assists=0, shots_total=3, shots_on=2, passes_total=40, passes_pct=30, passes_key=2,
    tackles=2, interceptions=1, blocks=0, duels_total=10, duels_won=6, dribbles_try=4, dribbles_ok=2, fouls_drawn=1, fouls_made=2,
    yellow=1, red=0, pen_scored=0, pen_missed=0, captain=1, saves=0)
ins(c, match_id=2, player_id=7, minutes=45, rating=6.0, goals=0, assists=1, shots_total=1, shots_on=0, passes_total=20, passes_pct=16,
    passes_key=0, tackles=1, interceptions=2, blocks=0, duels_total=6, duels_won=2, dribbles_try=1, dribbles_ok=1, fouls_drawn=0,
    fouls_made=0, yellow=0, red=0, pen_scored=0, pen_missed=0, captain=0, saves=0)
ins(c, match_id=3, player_id=7, minutes=80, rating=6.5)
s = MP.season_stats_rows(c)[7]
r26 = next(r for r in s if r["season"] == 2026)
r25 = next(r for r in s if r["season"] == 2025)
check("rows: 2026 sums (shots 4, inter 3, tackles 3, captain 1, pct 46/60 -> 77) and 2025 keeps NULL as None (not 0)",
      (r26["shots"], r26["inter"], r26["tackles"], r26["captain"], r26["pct"]) == (4, 3, 3, 1, 77)
      and r25["shots"] is None and r25["tackles"] is None and r25["yel"] is None and r25["pct"] is None, [r26, r25])
check("per-90 minutes counted only where the stat exists: m_shots 135 (2026), None (2025)",
      r26["m_shots"] == 135 and r25["m_shots"] is None, [r26["m_shots"], r25["m_shots"]])
check("new columns absent (no migration) -> NULL, no SQL error", all(r26[k] is None for k in ("offsides", "dpast", "pen_won", "pen_comm")), r26)

for lang in ("ar", "en"):
    t = MP.T[lang]
    h = MP.season_stats_table(s, lang, t)
    check(f"{lang}: ONE table, groups in order General/Attack/Passing/Defence/Discipline (no Goalkeeping for an outfielder)",
          h.count('<table class="stt">') == 1 and [g for g in ("ps_grp_gen", "ps_grp_att", "ps_grp_pas", "ps_grp_def", "ps_grp_dis", "ps_grp_gk")
                                                    if f'>{t[g]}</th>' in h] == ["ps_grp_gen", "ps_grp_att", "ps_grp_pas", "ps_grp_def", "ps_grp_dis"], h[:600])
    for k in ("ps_shots_on", "ps_inter", "ps_duels", "ps_dribbles", "ps_fdrawn", "ps_fmade", "ps_yellow", "ps_captain"):
        check(f"{lang}: stored-but-hidden stat now shown: {t[k]}", f">{t[k]}</th>" in h)
    for k in ("ps_blocks", "ps_red", "ps_pen_scored", "ps_pen_missed", "ps_offsides", "ps_dpast", "ps_pen_won", "ps_pen_comm", "ps_saves"):
        check(f"{lang}: hidden (all zero or all NULL): {t[k]}", f">{t[k]}</th>" not in h)
    row25 = h[h.index('<span class="yr">2025</span>'):].split("</tr>")[0]
    check(f"{lang}: 2025 row (minutes + rating only): NULL stats print '—', never 0", "<td>0</td>" not in row25 and row25.count("<td>—</td>") >= 8
          and "<td>80</td>" in row25 and "<td>6.50</td>" in row25, row25)
    row26 = h[h.index('<span class="yr">2026</span>'):].split("</tr>")[0]
    # shots 4 in 135' -> 2.7/90 ; tackles 3 -> 2.0/90 ; interceptions 3 -> 2.0/90 ; dribbles 3/5 ; duels 8/16 ; pct 77%
    check(f"{lang}: per-90 under shots/tackles/interceptions only (4 -> 2.7/90, 3 -> 2.0/90 twice)",
          '4<span class="p90">2.7/90</span>' in row26 and row26.count('3<span class="p90">2.0/90</span>') == 2 and row26.count('class="p90"') == 3, row26)
    check(f"{lang}: pairs and pass %: dribbles 3/5, duels 8/16, 77%", "<td>3/5</td>" in row26 and "<td>8/16</td>" in row26 and "<td>77%</td>" in row26, row26)

# ── goalkeeper 9: Goalkeeping group (saves/conceded), conceded 0 still shown ──
c = db()
ins(c, match_id=4, player_id=9, pos="G", rating=7.2, saves=4, conceded=0, passes_total=30, passes_pct=21, pen_saved=None, goals=0, assists=0)
h = MP.season_stats_table(MP.season_stats_rows(c)[9], "en", MP.T["en"])
check("keeper: Goalkeeping group with Saves 4 and Conceded 0 (a real zero); Pens saved NULL -> no column",
      ">Goalkeeping</th>" in h and ">Saves</th>" in h and '<td class="g0">4</td>' in h and ">Conceded</th>" in h and ">Pens saved</th>" not in h, h)

# ── migration: ADD COLUMN only, data untouched, idempotent; then the new fields flow through ──
c = db()
ins(c, match_id=4, player_id=11, rating=7.0, shots_total=2)
before_cols = [r[1] for r in c.execute("PRAGMA table_info(player_stats)")]
before_rows = [tuple(r) for r in c.execute("SELECT * FROM player_stats")]
check("before migration: present() = []", PX.present(c) == [])
added = PX.migrate(c)
after_cols = [r[1] for r in c.execute("PRAGMA table_info(player_stats)")]
check("migrate adds exactly offsides/dribbles_past/pen_won/pen_committed at the end, old columns unchanged",
      added == PX.NAMES and after_cols == before_cols + PX.NAMES, after_cols)
check("migrate keeps every existing row; new columns NULL for them (no backfill)",
      [tuple(r)[:len(before_cols)] for r in c.execute("SELECT * FROM player_stats")] == before_rows
      and c.execute("SELECT COUNT(*) FROM player_stats WHERE offsides IS NOT NULL OR dribbles_past IS NOT NULL "
                    "OR pen_won IS NOT NULL OR pen_committed IS NOT NULL").fetchone()[0] == 0)
check("migrate again: nothing added", PX.migrate(c) == [])
ins(c, match_id=5, player_id=11, rating=6.8, shots_total=1, offsides=2, dribbles_past=1, pen_won=1, pen_committed=0)
h = MP.season_stats_table(MP.season_stats_rows(c)[11], "en", MP.T["en"])
check("after migration: new match values show (Offsides 2, Dribbled past 1, Pens won 1); Pens conceded all 0 -> hidden",
      ">Offsides</th>" in h and ">Dribbled past</th>" in h and ">Pens won</th>" in h and ">Pens conceded</th>" not in h, h)

# ── fetcher: provider block -> the 4 new keys (SAU-like values, EGY-like nulls) ──
sau = {"games": {"minutes": 90}, "offsides": 1, "dribbles": {"attempts": 2, "success": 1, "past": 3},
       "penalty": {"won": 1, "commited": 0, "scored": 0, "missed": 0, "saved": None}}
egy = {"games": {"minutes": 90}, "offsides": 0, "dribbles": {"attempts": 2, "success": 1, "past": None},
       "penalty": {"won": None, "commited": None, "scored": 0, "missed": None, "saved": None}}
e1, e2 = FPS.extract({"statistics": [sau]}), FPS.extract({"statistics": [egy]})
check("fetcher extract: SAU-like -> offsides 1, dribbles_past 3, pen_won 1, pen_committed 0 ('commited' spelling)",
      [e1[k] for k in PX.NAMES] == [1, 3, 1, 0], e1)
check("fetcher extract: EGY-like nulls stay None (offsides 0 kept)", [e2[k] for k in PX.NAMES] == [0, None, None, None], e2)
check("fetcher extract keeps every old column", all(k in e1 for k in FPS.COLS))

# ── match overlay: new fields shown when set, hidden when NULL ──
ov = _stat_rows({"pos": "F", "minutes": 90, "rating": 7.1, "offsides": 2, "dribbles_past": 1, "pen_won": 1, "pen_committed": None}, "en")
check("overlay: Offsides 2, Dribbled past 1, Penalties won 1 shown; Penalties conceded (NULL) hidden",
      "Offsides</span><span class=\"v\">2" in ov and "Dribbled past</span><span class=\"v\">1" in ov
      and "Penalties won</span><span class=\"v\">1" in ov and "Penalties conceded" not in ov, ov)
ov_old = _stat_rows({"pos": "F", "minutes": 90, "rating": 7.1}, "ar")
check("overlay before migration (keys absent): nothing new, no error", "تسلل" not in ov_old and "مراوغات ضده" not in ov_old, ov_old)

# ── goals fallback (fill_goals): player_stats goals NULL -> the page's own goal rows for that season + league (no own goals) ──
srows = [{"season": 2026, "league_code": "EGY", "apps": 5, "goals": 2, "assists": 1},       # stored: kept even if goals rows differ
         {"season": 2023, "league_code": "EGY", "apps": 10, "goals": None, "assists": None},  # NULL: 2 normal + 1 pen = 3 (own goal out)
         {"season": 2022, "league_code": "EGY", "apps": 3, "goals": None, "assists": None},   # NULL, no goal rows -> 0
         {"season": 2023, "league_code": "SAU", "apps": 2, "goals": None, "assists": None}]   # other league same year -> not mixed in
goal_rows = [{"season": 2023, "league_code": "EGY", "detail": "Normal Goal"}, {"season": 2023, "league_code": "EGY", "detail": "Penalty"},
             {"season": 2023, "league_code": "EGY", "detail": "Normal Goal"}, {"season": 2023, "league_code": "EGY", "detail": "Own Goal"},
             {"season": 2026, "league_code": "EGY", "detail": "Normal Goal"}, {"season": 2021, "league_code": "EGY", "detail": "Normal Goal"}]
f = MP.fill_goals(srows, goal_rows)
check("fill_goals: stored 2 kept (goals table says 1), NULL -> 3 (own goal excluded), NULL without rows -> 0, other league -> 0",
      [r["goals"] for r in f] == [2, 3, 0, 0], f)
check("fill_goals: assists have no second source -> NULL stays None (shown '—'), stored 1 kept", [r["assists"] for r in f] == [1, None, None, None], f)
check("fill_goals: input rows untouched (copies)", srows[1]["goals"] is None)
h = MP.season_stats_table(f, "en", MP.T["en"])
r23 = h[h.index('Egyptian Premier League <span class="yr">2023'):].split("</tr>")[0]
check("table: 2023 EGY shows Goals 3 (not '—') and Assists '—' (not 0)",
      '<td class="g0">3</td><td>—</td>' in r23, r23)

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
