#!/usr/bin/env python3
"""
cup_tables (الموجة 3، 6 نوفمبر 2026): جداول مرحلة المجموعات/الدوري بالكؤوس — النقاط، كسر التعادل، تقسيم المجموعات،
وتبويب «الجدول» بصفحة الكأس + بطاقة النادي + api/v1/cups. الكؤوس الإقصائية بلا تبويب ولا CSS إضافي.
كل الكتابة على نسخة مؤقتة من football.db (md5 الأصل يُفحص بالنهاية). بلا شبكة.
    python C:\\Users\\User\\Projects\\Football\\test_cup_tables.py
"""
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
sys.argv = sys.argv[:1]
from _test_tmp import make_tmp  # noqa: E402
import cup_tables as CT  # noqa: E402
from config import COMPETITIONS, DB_FILE  # noqa: E402

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fail += 1


def m(mid, h, a, hg, ag, st="FT", rnd="Group Stage - 1", date="2026-10-10 18:00"):
    return {"match_id": mid, "home_id": h, "away_id": a, "home_goals": hg, "away_goals": ag, "status": st,
            "round": rnd, "date": date}


# ── 1) config: the 4 wave-3 cups and nothing else ───────────────────────────────────────────────────────────────
check("1 config: table modes = EGY-LC/AFC-CLE/AFC-CL2 groups, QAT-SLC/UAE-LC/JOR-SH league",
      {c: CT.mode(c) for c in COMPETITIONS if CT.mode(c)} == {"EGY-LC": "groups", "QAT-SLC": "league", "UAE-LC": "league", "JOR-SH": "league",
                                                              "AFC-CLE": "groups", "AFC-CL2": "groups", "GCC-CL": "groups",
                                                              "CAF-CL": "groups", "CAF-CC": "groups"})
check("1 config: line QAT-SLC 8, AFC-CLE 8, AFC-CL2 2",
      {c: CT.line(c) for c in COMPETITIONS if CT.line(c)} == {"QAT-SLC": 8, "AFC-CLE": 8, "AFC-CL2": 2, "GCC-CL": 2, "CAF-CL": 2, "CAF-CC": 2})
check("1 config: knockout cups have no table (SAU-KC, TUN-C)", CT.mode("SAU-KC") is None and CT.mode("TUN-C") is None and CT.mode("EGY") is None)
check("1 config: EGY-LC start 2026-10-07, JOR-SH end 2025-12-28",
      COMPETITIONS["EGY-LC"]["start"] == "2026-10-07" and COMPETITIONS["JOR-SH"]["end"] == "2025-12-28")
import match_round as MR  # noqa: E402
check("1 round labels: 1st/2nd Round mapped", MR.label("1st Round", "ar") == "الدور الأول" and MR.label("2nd Round", "en") == "2nd round")

# ── 2) is_table_round ───────────────────────────────────────────────────────────────────────────────────────────
check("2 table rounds", all(CT.is_table_round(r) for r in ("Group Stage - 1", "Group Stage", "League Phase - 8", "Regular Season - 3")))
check("2 knockout rounds", not any(CT.is_table_round(r) for r in ("Final", "Semi-finals", "Round of 16", "1st Round", "", None, "Group Stage X")))

# ── 3) points 3/1/0, finished only ──────────────────────────────────────────────────────────────────────────────
A, B_, C, D = 1, 2, 3, 4
# (الموجة 5ب) CAF-CC: «Caf Confederation Cup - N» مرحلة مجموعات، والتمهيديات تبقى للشجرة، ومجموعة من 3 فرق تُحسب عادياً
check("2 CAF-CC group round is a table round; prelims are not",
      CT.is_table_round("Caf Confederation Cup - 1") and CT.is_table_round("Regular season - 6")
      and not any(CT.is_table_round(r) for r in ("1st Preliminary Round", "2nd Preliminary Round")))
_cc = [{"match_id": i, "date": f"2026-12-0{i}", "round": r, "status": s, "home_id": h, "away_id": a, "home_goals": hg, "away_goals": ag}
       for i, (r, s, h, a, hg, ag) in enumerate((("Caf Confederation Cup - 1", "FT", 71, 72, 2, 0), ("Caf Confederation Cup - 2", "FT", 72, 73, 1, 1),
                                                 ("Caf Confederation Cup - 3", "NS", 73, 71, None, None), ("1st Preliminary Round", "FT", 71, 99, 5, 0)), 1)]
_t3 = CT.tables(_cc, "groups", None, "CAF-CC")
check("2 CAF-CC group of 3: one group, 3 rows, prelim team and goals left out",
      [len(g["rows"]) for g in _t3] == [3] and [(r["team"], r["played"], r["points"]) for r in _t3[0]["rows"]] == [(71, 1, 3), (73, 1, 1), (72, 2, 1)],
      _t3)
check("2 CAF-CC prelims go to the bracket", [m["match_id"] for m in CT.knockout_rows(_cc)] == [4])
rows = [m(1, A, B_, 2, 0), m(2, C, D, 1, 1), m(3, A, C, 0, 0), m(4, B_, D, 3, 1),
        m(5, A, D, None, None, "NS"), m(6, B_, C, 5, 0, "PST"), m(7, C, A, 1, 0, "AWD"), m(8, D, B_, 9, 0, "CANC"),
        m(9, A, B_, 4, 4, "FT", "Semi-finals")]
names = {A: "Alpha", B_: "Beta", C: "Gamma", D: "Delta"}
t = {r["team"]: r for r in CT.table(CT.stage_rows(rows), [A, B_, C, D], names.get)}
check("3 A: P3 W1 D1 L1 GF2 GA1 Pts4 (NS/PST/CANC/knockout ignored, AWD counted)",
      (t[A]["played"], t[A]["won"], t[A]["drawn"], t[A]["lost"], t[A]["gf"], t[A]["ga"], t[A]["points"]) == (3, 1, 1, 1, 2, 1, 4), t[A])
check("3 C: AWD win + 2 draws = 5 pts", t[C]["points"] == 5 and t[C]["played"] == 3, t[C])
check("3 D: 1 draw 1 loss = 1 pt, GD -2", (t[D]["points"], t[D]["gd"]) == (1, -2), t[D])
check("3 every team listed even with 0 games", len(CT.table([], [A, B_], names.get)) == 2)

# ── 4) tie-break: points → GD → GF → English name → id ──────────────────────────────────────────────────────────
tb = [m(11, A, 9, 3, 0), m(12, B_, 9, 1, 0),                 # A: GD+3 · B: GD+1 (both 3 pts)
      m(13, C, 9, 4, 2), m(14, D, 9, 3, 1),                 # C: GD+2 GF4 · D: GD+2 GF3
      m(15, 5, 9, 2, 1), m(16, 6, 9, 2, 1)]                 # 5 "Zulu", 6 "Echo": identical → name
nm2 = {A: "A", B_: "B", C: "C", D: "D", 5: "Zulu", 6: "echo", 9: "Nine"}
order = [r["team"] for r in CT.table(tb, [A, B_, C, D, 5, 6, 9], nm2.get)]
check("4 order: A(GD+3) C(GD+2,GF4) D(GD+2,GF3) echo Zulu (name, case-insensitive) B(GD+1) … Nine",
      order == [A, C, D, 6, 5, B_, 9], order)
same = [m(21, 7, 9, 1, 0), m(22, 8, 9, 1, 0)]
check("4 same name → team id", [r["team"] for r in CT.table(same, [8, 7], lambda _t: "X")][:2] == [7, 8])
check("4 pos numbering 1..n", [r["pos"] for r in CT.table(tb, [A, B_, C, D, 5, 6, 9], nm2.get)] == list(range(1, 8)))

# ── 5) group split from pairings ────────────────────────────────────────────────────────────────────────────────
gr = [m(31, 10, 11, 1, 0, date="2026-10-08 18:00"), m(32, 11, 12, None, None, "NS", date="2026-11-01 18:00"),
      m(33, 20, 21, 0, 0, date="2026-10-07 18:00"), m(34, 21, 22, None, None, "NS", date="2026-11-02 18:00"),
      m(35, 22, 20, None, None, "NS", date="2026-11-03 18:00"), m(36, 12, 10, None, None, "NS", date="2026-11-04 18:00"),
      m(37, 10, 21, None, None, "NS", "Quarter-finals", "2026-12-01 18:00")]  # knockout pairing must NOT merge groups
gs = CT.tables(gr, "groups")
check("5 two groups of 3, knockout pairing ignored", [len(g["rows"]) for g in gs] == [3, 3], gs)
check("5 groups numbered by earliest match (20/21/22 first: 2026-10-07)", gs[0]["group"] == 1 and {r["team"] for r in gs[0]["rows"]} == {20, 21, 22}
      and gs[1]["group"] == 2 and {r["team"] for r in gs[1]["rows"]} == {10, 11, 12})
check("5 unplayed scheduled teams included (12 and 22 with 0 games)", all(any(r["team"] == x and r["played"] == 0 for g in gs for r in g["rows"]) for x in (12, 22)))
lg = CT.tables(gr, "league")
check("5 league mode: one table, 6 teams, group None", len(lg) == 1 and lg[0]["group"] is None and len(lg[0]["rows"]) == 6)
check("5 no table rounds → []", CT.tables([m(41, 1, 2, 1, 0, rnd="Final")], "league") == [] and CT.tables(gr, None) == [])
check("5 position()", CT.position(gs, 11) == (2, CT.position(gs, 11)[1]) and CT.position(gs, 999) == (None, None))
check("5 knockout_rows keeps only post-stage rounds", [x["match_id"] for x in CT.knockout_rows(gr)] == [37])

# ── 6) pages / club card / api on a TEMP COPY of football.db ────────────────────────────────────────────────────
md5_before = hashlib.md5(DB_FILE.read_bytes()).hexdigest()
tmp = make_tmp("cup_tables_")
db = tmp / "football.db"
shutil.copy2(DB_FILE, db)
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
con.execute("DELETE FROM matches WHERE league_code IN ('EGY-LC', 'QAT-SLC')")
G1, G2 = (1031, 15731, 14651), (1036, 1044, 16431)   # Masry/Abu Qair/Ceramica · Pyramids/Smouha/Future (real ids)
syn = [(9900001, G1[0], G1[1], 2, 0, "FT", "Group Stage - 1", "2026-10-07 15:00"),
       (9900002, G2[0], G2[1], 1, 1, "FT", "Group Stage - 1", "2026-10-08 15:00"),
       (9900003, G1[1], G1[2], None, None, "NS", "Group Stage - 2", "2026-12-07 15:00"),
       (9900004, G2[1], G2[2], None, None, "NS", "Group Stage - 2", "2026-12-08 15:00"),
       (9900005, G1[2], G1[0], None, None, "NS", "Group Stage - 3", "2026-12-17 15:00"),
       (9900006, G2[2], G2[0], None, None, "NS", "Group Stage - 3", "2026-12-18 15:00")]
for mid, h, a, hg, ag, st, rnd, d in syn:
    con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round) "
                "VALUES (?, 'EGY-LC', 2026, ?, ?, ?, ?, ?, ?, ?)", (mid, d, h, a, hg, ag, st, rnd))
q = [(9900100 + i, h, a) for i, (h, a) in enumerate([(G1[0], G2[0]), (G1[1], G2[1]), (G1[2], G2[2]), (1577, 1040), (1574, 1575),
                                                       (1037, 18021), (1572, 1039), (7520, 1046), (13819, 1041), (15570, 13822)])]
for mid, h, a in q:   # QAT-SLC-shaped league phase with 20 teams (line under 8th needs > 8 rows)
    con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round) "
                "VALUES (?, 'QAT-SLC', 2026, '2026-09-20 15:00', ?, ?, 1, 0, 'FT', 'Group Stage - 1')", (mid, h, a))
con.commit()
import make_clubs as MC  # noqa: E402
import make_cups as MK  # noqa: E402
from make_site3 import load_overrides  # noqa: E402
teams, logos = MC.load_teams(), load_overrides()
ar = MK.cup_page(con, "ar", "EGY-LC", logos, teams)
en = MK.cup_page(con, "en", "EGY-LC", logos, teams)
check("6 EGY-LC AR: «الجدول» tab + 2 group headings + note", 'data-cat="table">الجدول<' in ar and "<h3>المجموعة الرابعة</h3>" in ar
      and "<h3>المجموعة الثانية</h3>" in ar and "الترتيب محسوب من نتائج المباريات" in ar)
check("6 EGY-LC EN: Table tab + Group 1/2 + note", 'data-cat="table">Table<' in en and "<h3>Group 2</h3>" in en
      and "Standings computed from match results" in en)
check("6 EGY-LC: no knockout yet → no bracket tab", 'data-cat="bracket"' not in ar)
check("6 EGY-LC: table CSS present", ".ctbl tr.cut" in ar)
i1, i2 = ar.index("<h3>المجموعة الرابعة</h3>"), len(ar)   # بترتيب الـconfig الرسمي: مجموعة المصري = الرابعة (آخر جدول بالعيّنة)
check("6 EGY-LC official group 4 = Masry's group, Masry first (3 pts)",
      f'data-t="{G1[0]}"' in ar[i1:i2] and ar[i1:].index(f'data-t="{G1[0]}"') < ar[i1:].index(f'data-t="{G1[1]}"'))
con.execute("INSERT INTO matches (match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round) "
            "VALUES (9900009, 'EGY-LC', 2026, '2027-01-20 15:00', ?, ?, NULL, NULL, 'NS', 'Semi-finals')", (G1[0], G2[0]))
ar2 = MK.cup_page(con, "ar", "EGY-LC", logos, teams)
check("6 EGY-LC with a semi-final: bracket tab back, bracket holds only the knockout tie",
      'data-cat="bracket"' in ar2 and ar2.count('<section class="bkcol') == 1
      and "دور المجموعات" not in ar2.split('<section class="panel" data-cat="bracket">')[1].split('<section class="panel"')[0])
qa = MK.cup_page(con, "ar", "QAT-SLC", logos, teams)
check("6 QAT-SLC: one table (no group heading), line under 8th only", "<h3>المجموعة" not in qa and qa.count('<tr class="cut"') == 1
      and '<tr class="cut" data-t=' in qa and qa.split('<tr class="cut"')[0].count("<tr data-t=") == 7)
ko = MK.cup_page(con, "ar", "SAU-KC", logos, teams) if con.execute(
    "SELECT 1 FROM matches WHERE league_code='SAU-KC' LIMIT 1").fetchone() else None
check("6 knockout cup (SAU-KC): no table tab, no table CSS, bracket tab kept",
      ko is None or ('data-cat="table"' not in ko and ".ctbl" not in ko and 'data-cat="bracket"' in ko))
card = MC.competitions_card(con, G1[0], None, 2026, [dict(r) for r in con.execute(
    "SELECT * FROM matches WHERE league_code='EGY-LC' AND (home_id=? OR away_id=?)", (G1[0], G1[0]))], "ar")
check("6 club card: «المجموعة 1 · المركز 1» for Masry (in the semi-final → bracket stage wins)", "المجموعة" in card or "نصف النهائي" in card, card)
con.execute("DELETE FROM matches WHERE match_id = 9900009")
card = MC.competitions_card(con, G1[1], None, 2026, [dict(r) for r in con.execute(
    "SELECT * FROM matches WHERE league_code='EGY-LC' AND (home_id=? OR away_id=?)", (G1[1], G1[1]))], "en")
check("6 club card EN: Group 4 · Rank 3 for Abu Qair (lost 0-2)", "Group 4 · Rank 3" in card, card)
import make_api as MA  # noqa: E402
cj = MA.cup_json(con, "EGY-LC", 2026, {"pages": []})
check("6 api: EGY-LC tables = 2 groups, rows with pos/team/p/w/d/l/gf/ga/gd/pts, no rounds",
      [g.get("group") for g in cj.get("tables", [])] == [1, 2] and set(cj["tables"][0]["rows"][0]) == {"pos", "team", "p", "w", "d", "l", "gf", "ga", "gd", "pts"}
      and "rounds" not in cj, json.dumps(cj, ensure_ascii=False)[:300])
cq = MA.cup_json(con, "QAT-SLC", 2026, {"pages": []})
check("6 api: QAT-SLC one table with line 8", len(cq["tables"]) == 1 and cq["tables"][0]["line"] == 8 and "group" not in cq["tables"][0])
if con.execute("SELECT 1 FROM matches WHERE league_code='TUN-C' LIMIT 1").fetchone():
    import player_pages as PP  # noqa: E402
    ck = MA.cup_json(con, "TUN-C", COMPETITIONS["TUN-C"]["season"], PP.get_plan())
    check("6 api: knockout cup (TUN-C) has no tables key", "tables" not in ck and "rounds" in ck)
con.close()
check("6 football.db untouched (md5)", hashlib.md5(DB_FILE.read_bytes()).hexdigest() == md5_before)

# ── 7) real provider data (optional: wave-3 cache on this machine) ──────────────────────────────────────────────
cache = Path(r"C:\Users\User\FootballBackups\cups_cache_wave3_20261106")
if cache.exists():
    def rows_of(lid, season):
        full = {}
        for f in cache.glob(f"ids_{lid}_{season}_*.json"):
            for x in json.loads(f.read_text(encoding="utf-8"))["response"]:
                full[x["fixture"]["id"]] = x
        return [{"match_id": i, "home_id": x["teams"]["home"]["id"], "away_id": x["teams"]["away"]["id"],
                 "home_goals": x["goals"]["home"], "away_goals": x["goals"]["away"], "status": x["fixture"]["status"]["short"],
                 "round": x["league"]["round"], "date": x["fixture"]["date"]} for i, x in full.items()]
    eg = CT.tables(rows_of(895, 2026), "groups")
    check("7 real EGY-LC: 4 groups × 5, no team twice", [len(g["rows"]) for g in eg] == [5, 5, 5, 5]
          and len({r["team"] for g in eg for r in g["rows"]}) == 20)
    qs = CT.tables(rows_of(677, 2026), "league")
    check("7 real QAT-SLC: one table of 19", len(qs) == 1 and len(qs[0]["rows"]) == 19)
    uae = CT.tables(rows_of(302, 2026), "league")
    check("7 real UAE-LC: one table of 14, everyone P3", len(uae[0]["rows"]) == 14 and {r["played"] for r in uae[0]["rows"]} == {3})
    jo = CT.tables(rows_of(816, 2025), "league")[0]["rows"]
    check("7 real JOR-SH: 10 teams P9, Al Faisaly (4531) 24 pts first", len(jo) == 10 and {r["played"] for r in jo} == {9}
          and (jo[0]["team"], jo[0]["points"]) == (4531, 24))
    check("7 real JOR-SH: points total = 3·W + D over 45 games", sum(r["points"] for r in jo) == sum(3 * r["won"] + r["drawn"] for r in jo)
          and sum(r["played"] for r in jo) == 90)
else:
    print("SKIP 7 (no wave-3 cache on this machine)")

# ── 8) wave 4: h2h tie-break, official group names, team id aliases ───────────────────────────────────────────
from config import ENABLED_CUPS, TEAM_ID_ALIASES  # noqa: E402
import team_alias as TA  # noqa: E402
check("8 config: tiebreak AFC-CLE league, AFC-CL2 h2h, nothing else",
      {c: CT.tiebreak(c) for c in COMPETITIONS if CT.tiebreak(c)} == {"AFC-CLE": "league", "AFC-CL2": "h2h", "GCC-CL": "h2h",
                                                                      "CAF-CL": "h2h", "CAF-CC": "h2h"})
# "league" rule: points → GD → goals → wins → team id (asc); never h2h, never the name
L1, L2, L3, L4, L5 = 205, 201, 203, 204, 202
lr = [m(331, L1, L3, 1, 0), m(332, L1, L4, 1, 1), m(333, L2, L5, 1, 0), m(334, L2, L4, 1, 1),   # L1/L2: 4 pts, +1, 2 goals, 1 win
      m(335, L3, L4, 2, 2), m(336, L3, L5, 2, 2)]                                                # L3: 2 pts
order_l = [r["team"] for r in CT.table(lr, [L1, L2, L3, L4, L5], {L1: "Aaa", L2: "Zzz"}.get, rule="league")]
check("8 league rule: full tie (pts/GD/goals/wins) → lower team id first (201 before 205, name ignored)", order_l[:2] == [L2, L1], order_l)
lwins = [m(341, 702, 709, 1, 0), m(342, 702, 708, 0, 1), m(343, 702, 707, 0, 0),    # 702: W1 L1 D1 → 4 pts, GD 0, 1 goal
         m(344, 701, 709, 0, 0), m(345, 701, 708, 0, 0), m(346, 701, 707, 1, 1),    # 701: D3 → 3 pts … make it 4:
         m(347, 701, 706, 0, 0)]                                                     # 701: D4 → 4 pts, GD 0, 1 goal, 0 wins
check("8 league rule: pts/GD/goals level → more wins first, even with the higher id (702 W1 before 701 W0)",
      [r["team"] for r in CT.table(lwins, [701, 702, 706, 707, 708, 709], None, rule="league") if r["team"] in (701, 702)] == [702, 701])
lw2 =[m(351, 401, 409, 2, 0), m(352, 401, 408, 0, 0), m(353, 401, 407, 0, 0),    # 401: W1 D2 = 5 pts, +2, 2 goals
       m(354, 402, 409, 1, 0), m(355, 402, 408, 1, 0), m(356, 402, 407, 0, 2),    # 402: W2 L1 = 6 pts
       m(357, 403, 409, 2, 0), m(358, 403, 408, 0, 0), m(359, 403, 406, 0, 0)]    # 403: same as 401
check("8 league rule: GD/goals level → id when wins equal (401 before 403)",
      [r["team"] for r in CT.table(lw2, [401, 402, 403, 406, 407, 408, 409], None, rule="league") if r["team"] in (401, 403)] == [401, 403])
cle_rows = [m(601, 2523, 2780, 3, 0), m(602, 302, 2776, 3, 0), m(603, 2523, 2789, 0, 1), m(604, 302, 2750, 0, 1),
            m(605, 2523, 2764, 2, 1), m(606, 302, 946, 2, 1)]   # Kyoto 302 and JDT 2523 fully level, never meet
cle_t = CT.tables(cle_rows, "groups", None, "AFC-CLE")
east = next(g for g in cle_t if g["name"]["en"] == "East")["rows"]
check("8 tables(code=AFC-CLE): league rule applied — Kyoto (302) above JDT (2523) on a full tie",
      [r["team"] for r in east][:2] == [302, 2523], [r["team"] for r in east])
check("8 config: wave-3 cups keep the old sort (no tiebreak); EGY-LC has official group names, the others stay numbered",
      all(CT.tiebreak(c) is None for c in ("EGY-LC", "QAT-SLC", "UAE-LC", "JOR-SH"))
      and all(CT.group_names(c) == () for c in ("QAT-SLC", "UAE-LC", "JOR-SH"))
      and [(g["en"], len(g["teams"])) for g in CT.group_names("EGY-LC")] == [(f"Group {i}", 5) for i in range(1, 5)])
check("8 config: AFC-CLE/AFC-CL2 enabled; AFC-CLE id 17, season 2026, 2026-08-11 → 2027-02-16",
      "AFC-CLE" in ENABLED_CUPS and "AFC-CL2" in ENABLED_CUPS
      and (COMPETITIONS["AFC-CLE"]["id"], COMPETITIONS["AFC-CLE"]["season"], COMPETITIONS["AFC-CLE"]["start"], COMPETITIONS["AFC-CLE"]["end"])
      == (17, 2026, "2026-08-11", "2027-02-16"))
cle, cl2 = CT.group_names("AFC-CLE"), CT.group_names("AFC-CL2")
check("8 group names: CLE «غرب آسيا»/West, «شرق آسيا»/East, 16 teams each",
      [(g["ar"], g["en"], len(g["teams"])) for g in cle] == [("غرب آسيا", "West", 16), ("شرق آسيا", "East", 16)])
check("8 group names: CL2 «المجموعة A..H»/Group A..H in A-H order, 4 teams each",
      [(g["ar"], g["en"], len(g["teams"])) for g in cl2] == [(f"المجموعة {x}", f"Group {x}", 4) for x in "ABCDEFGH"])
allids = [t for g in cle + cl2 for t in g["teams"]]
check("8 group names: 64 distinct teams, no alias ids, Al Shorta 5242 + East Bengal 3463 in Group D",
      len(allids) == len(set(allids)) == 64 and not set(allids) & set(TEAM_ID_ALIASES) and {5242, 3463} <= set(cl2[3]["teams"]))

# h2h: X, Y, Z on 6 pts. Overall: Z +4, then Y (GD 0, GF 3), X (GD 0, GF 2). Head-to-head: Y beat X and Z, X beat Z → Y, X, Z.
X, Y, Z, F1, F2 = 101, 102, 103, 190, 191
h = [m(301, Y, X, 1, 0), m(302, Y, Z, 1, 0), m(303, X, Z, 1, 0), m(304, X, F1, 1, 0), m(305, Z, F1, 5, 0),
     m(306, Z, F2, 1, 0), m(307, F2, Y, 3, 1), m(308, X, F2, 0, 1), m(309, F1, F2, 0, 0)]
nmh = {X: "X", Y: "Y", Z: "Z", F1: "F1", F2: "F2"}
check("8 league rule: never uses h2h (table h2h flag ignored when rule given)",
      [r["team"] for r in CT.table(h, [X, Y, Z, F1, F2], nmh.get, h2h=True, rule="league")]
      == [r["team"] for r in CT.table(h, [X, Y, Z, F1, F2], None, rule="league")])
plain = CT.table(h, [X, Y, Z, F1, F2], nmh.get)
hh = CT.table(h, [X, Y, Z, F1, F2], nmh.get, h2h=True)
check("8 setup: X, Y, Z level on 6 pts", {r["team"]: r["points"] for r in plain if r["team"] in (X, Y, Z)} == {X: 6, Y: 6, Z: 6}, plain)
check("8 plain sort: Z, Y, X by overall GD then goals", [r["team"] for r in plain if r["team"] in (X, Y, Z)] == [Z, Y, X], plain)
check("8 h2h sort: Y (h2h 6 pts), X (3), Z (0) beat overall GD", [r["team"] for r in hh if r["team"] in (X, Y, Z)] == [Y, X, Z], hh)
check("8 h2h never crosses a points gap", [r["points"] for r in hh] == sorted((r["points"] for r in hh), reverse=True))
P, Q, R = 111, 112, 113   # P and Q level on points and drew 2-2 → h2h level → overall GD decides (P +3, Q +1)
hq = [m(311, P, Q, 2, 2), m(312, P, R, 3, 0), m(313, Q, R, 1, 0)]
check("8 h2h level → overall GD: P above Q", [r["team"] for r in CT.table(hq, [P, Q, R], None, h2h=True)][:2] == [P, Q])
S1, S2, S3, S4 = 121, 122, 123, 124   # both 6 pts; h2h 1-0 and 0-2 → h2h pts 3-3, h2h GD S2 +1 → S2 above S1 (overall S1 +4, S2 +2)
hg = [m(321, S1, S2, 1, 0), m(322, S2, S1, 2, 0), m(323, S1, S3, 5, 0), m(324, S2, S4, 1, 0), m(325, S3, S4, 0, 0)]
check("8 h2h points level → h2h GD (S2) beats overall GD (S1); plain sort keeps S1 first",
      [r["team"] for r in CT.table(hg, [S1, S2, S3, S4], None, h2h=True)][:2] == [S2, S1]
      and [r["team"] for r in CT.table(hg, [S1, S2, S3, S4])][:2] == [S1, S2])

# tables(code=…): named groups by membership, in config order
cfg_rows = [m(400 + i, g["teams"][0], g["teams"][1], 1, 0) for i, g in enumerate(cl2)]
cfg_rows += [m(450 + i, g["teams"][2], g["teams"][3], 0, 0) for i, g in enumerate(cl2)]
cfg_rows += [m(470 + i, g["teams"][1], g["teams"][2], None, None, "NS", date="2026-12-01 18:00") for i, g in enumerate(cl2)]
cfg_rows.reverse()   # display order must follow the config, not match dates/ids
nt = CT.tables(cfg_rows, "groups", None, "AFC-CL2")
check("8 tables(code=AFC-CL2): 8 groups A..H in config order, group = 1..8, names ar/en",
      [(g["group"], g["name"]["en"], g["name"]["ar"]) for g in nt] == [(i, f"Group {x}", f"المجموعة {x}") for i, x in enumerate("ABCDEFGH", 1)])
check("8 tables(code=AFC-CL2): each group holds exactly its 4 config teams",
      all({r["team"] for r in g["rows"]} == set(c["teams"]) for g, c in zip(nt, cl2)))
check("8 tables without code = old numbered groups, no name key", all("name" not in g for g in CT.tables(cfg_rows, "groups")))
check("8 group_title / position_entry", CT.group_title(nt[3], "ar") == "المجموعة D" and CT.group_title(nt[3], "en") == "Group D"
      and CT.group_title({"group": 1, "rows": []}, "ar") is None and CT.position_entry(nt, cl2[3]["teams"][0])[0] is nt[3])
st_ = CT.tables(cfg_rows + [m(499, 9001, 9002, 1, 0)], "groups", None, "AFC-CL2")
check("8 a component outside every named group is appended after them, numbered, without name",
      len(st_) == 9 and st_[-1]["group"] == 9 and "name" not in st_[-1] and {r["team"] for r in st_[-1]["rows"]} == {9001, 9002})

# aliases
fx = {"fixture": {"id": 1}, "league": {"id": 18, "season": 2026},
      "teams": {"home": {"id": 28571, "name": "Al Shorta"}, "away": {"id": 21137, "name": "East Bengal II"}},
      "events": [{"team": {"id": 28571}, "player": {"id": 5, "name": "x"}}, {"team": {"id": 21137}}],
      "lineups": [{"team": {"id": 28571}, "startXI": [{"player": {"id": 7}}]}, {"team": {"id": 21137}}],
      "statistics": [{"team": {"id": 28571}, "statistics": []}, {"team": {"id": 21137}, "statistics": []}],
      "players": [{"team": {"id": 28571}, "players": [{"player": {"id": 28571}}]}, {"team": {"id": 21137}, "players": []}]}
ax = TA.alias_fixture(fx)
check("8 config: TEAM_ID_ALIASES = {28571: 5242, 21137: 3463}", TEAM_ID_ALIASES == {28571: 5242, 21137: 3463})
check("8 alias_fixture: teams/events/lineups/statistics/players team ids remapped",
      (ax["teams"]["home"]["id"], ax["teams"]["away"]["id"]) == (5242, 3463)
      and [b["team"]["id"] for k in ("events", "lineups", "statistics", "players") for b in ax[k]] == [5242, 3463] * 4)
check("8 alias_fixture: player ids untouched (player id 28571 stays), input not mutated, idempotent",
      ax["players"][0]["players"][0]["player"]["id"] == 28571 and fx["teams"]["home"]["id"] == 28571 and TA.alias_fixture(ax) == ax)
check("8 alias_fixture on a bare lineups list (fetch_lineups --refetch shape)",
      [b["team"]["id"] for b in TA.alias_fixture(fx["lineups"])] == [5242, 3463])
import import_cups as IC  # noqa: E402
md5_8 = hashlib.md5(DB_FILE.read_bytes()).hexdigest()
tmp8 = make_tmp("cup_alias_")
db8 = tmp8 / "football.db"
shutil.copy2(DB_FILE, db8)
c8 = sqlite3.connect(db8)
full = dict(fx, fixture={"id": 9800001, "date": "2026-10-01T18:00:00+00:00", "timestamp": 1790000000,
                         "status": {"short": "FT"}, "venue": {}},
            goals={"home": 1, "away": 0},
            score={"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 1, "away": 0},
                   "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}},
            league={"id": 18, "season": 2026, "round": "Group Stage - 1"},
            events=[{"type": "Goal", "detail": "Normal Goal", "team": {"id": 28571}, "time": {"elapsed": 10},
                     "player": {"id": 5, "name": "Scorer"}, "assist": {}},
                    {"type": "Card", "detail": "Yellow Card", "team": {"id": 21137}, "time": {"elapsed": 20},
                     "player": {"id": 6, "name": "Booked"}, "assist": {}}])
IC.import_code(c8, "AFC-CL2", [full], {9800001: full})
c8.commit()
hits = {}
for t in [r[0] for r in c8.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
    cols = [r[1] for r in c8.execute(f"PRAGMA table_info({t})")]
    if "match_id" not in cols:
        continue
    for col in cols:
        if col in ("team_id", "home_id", "away_id"):
            n = c8.execute(f"SELECT COUNT(*) FROM {t} WHERE match_id = 9800001 AND {col} IN (28571, 21137)").fetchone()[0]
            if n:
                hits[f"{t}.{col}"] = n
row = c8.execute("SELECT home_id, away_id FROM matches WHERE match_id = 9800001").fetchone()
gl = [r[0] for r in c8.execute("SELECT team_id FROM goals WHERE match_id = 9800001")]
ev = [r[0] for r in c8.execute("SELECT team_id FROM events WHERE match_id = 9800001")]
ms = sorted(r[0] for r in c8.execute("SELECT team_id FROM match_stats WHERE match_id = 9800001"))
c8.close()
check("8 import_code writes 5242/3463 to matches/goals/events/match_stats, never 28571/21137",
      row is not None and tuple(row) == (5242, 3463) and gl == [5242] and ev == [3463] and ms == [3463, 5242] and not hits,
      (row, gl, ev, ms, hits))
check("8 football.db untouched by the alias test (md5)", hashlib.md5(DB_FILE.read_bytes()).hexdigest() == md5_8)

print(f"\n{'ALL PASS' if not fail else f'{fail} FAILED'}")
sys.exit(1 if fail else 0)
