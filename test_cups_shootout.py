#!/usr/bin/env python3
"""
Cups phase 3 (9 Nov 2026): shootout_kicks table + migrate, save_finished stores kicks (never in goals/events), backfill_shootout.py,
match page block AR+EN, Arabic badge «ترجيح» (EN stays PEN), live_view "(h-a pens)" (real browser, faked feed). No network.
Provider data: test_data/cups_wave1.json (1635605, named) and cups_wave0.json (1645511, nameless).
Pages use a TEMP COPY of football.db only (md5 of football.db checked at the end). Run from the repo root:
    python C:\\Users\\User\\Projects\\Football\\test_cups_shootout.py
"""
import copy
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from _test_tmp import make_tmp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import fetch_matches2 as FM  # noqa: E402
import match_score as MS  # noqa: E402
from config import DB_FILE  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails += 1


md5 = lambda p: hashlib.md5(Path(p).read_bytes()).hexdigest()  # noqa: E731
DB_MD5 = md5(DB_FILE)
W0 = json.loads((ROOT / "test_data" / "cups_wave0.json").read_text(encoding="utf-8"))
W1 = json.loads((ROOT / "test_data" / "cups_wave1.json").read_text(encoding="utf-8"))
NAMELESS = dict(W0["fixtures"]["pen"], events=W0["events_1645511"])   # 1645511, 10 kicks, 4-3, no names
NAMED = next(x for x in W1["ids"]["ids_825_0"] if x["fixture"]["id"] == 1635605)   # 12 kicks, 4-5, all named
TMPD = make_tmp("cups_so_")

# ── 1) table + migrate ─────────────────────────────────────────────────────────────────────────────────────
con = sqlite3.connect(TMPD / "small.db")
con.row_factory = sqlite3.Row
con.executescript("""
    CREATE TABLE matches (match_id INTEGER PRIMARY KEY, league_code TEXT, season INTEGER, date TEXT, home_id INTEGER, away_id INTEGER,
                          home_goals INTEGER, away_goals INTEGER, status TEXT);
    CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, player_en TEXT,
                        player_ar TEXT, detail TEXT);
    CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER, minute INTEGER, type TEXT, detail TEXT,
                         player_en TEXT, player_ar TEXT, assist_en TEXT);
""")
n_count = lambda t, col="fixture_id", mid=1635605: con.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} = ?", (mid,)).fetchone()[0]  # noqa: E731
check("1 before migrate: no table, save_kicks writes nothing and raises nothing", not MS.has_kicks(con) and MS.save_kicks(con, NAMED, NAMED["events"]) == 0)
FM.save_finished(con, "QAT-QC", 2025, NAMED, NAMED["events"], status="PEN")
check("1 before migrate: save_finished still works (6 goals)", con.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 6)
added = MS.migrate(con)
check("1 migrate creates the table and still returns the columns added", MS.has_kicks(con) and added == list(MS.COLS), added)
check("1 migrate again = no-op", MS.migrate(con) == [] and MS.has_kicks(con))
info = [(r["name"], r["pk"]) for r in con.execute("PRAGMA table_info(shootout_kicks)")]
check("1 columns and primary key (fixture_id, team_id, kick_no)",
      info == [("fixture_id", 1), ("team_id", 2), ("kick_no", 3), ("scored", 0), ("player_id", 0), ("player_name", 0)], info)

# ── 2) import: save_finished stores kicks; goals and events stay free of them ──────────────────────────────
n = FM.save_finished(con, "QAT-QC", 2025, NAMED, NAMED["events"], status="PEN")
home, away = NAMED["teams"]["home"]["id"], NAMED["teams"]["away"]["id"]
get = lambda tid, mid=1635605: con.execute("SELECT kick_no, scored, player_id, player_name FROM shootout_kicks WHERE fixture_id = ? AND team_id = ? ORDER BY kick_no", (mid, tid)).fetchall()  # noqa: E731
check("2 named match: 12 kicks stored", n_count("shootout_kicks") == 12, n_count("shootout_kicks"))
check("2 home marks by kick_no (✓✗✓✓✓✗) and per-team numbering", [(r[0], r[1]) for r in get(home)] == [(1, 1), (2, 0), (3, 1), (4, 1), (5, 1), (6, 0)], [tuple(r) for r in get(home)])
check("2 away marks by kick_no (✓✓✗✓✓✓)", [r[1] for r in get(away)] == [1, 1, 0, 1, 1, 1], [tuple(r) for r in get(away)])
check("2 kicker id and name kept", tuple(get(home)[0])[2:] == (146, "A. Collado") and tuple(get(away)[5])[2:] == (281342, "A. Amaro"))
check("2 goals table has the 6 real goals only, no kick", n == 6 and n_count("goals", "match_id") == 6 and
      con.execute("SELECT COUNT(*) FROM goals WHERE minute = 120 AND match_id = 1635605").fetchone()[0] == 0)
check("2 events table holds no kick", n_count("events", "match_id") == 0)
FM.save_finished(con, "QAT-QC", 2025, NAMED, NAMED["events"], status="PEN")
check("2 second import: same 12 rows", n_count("shootout_kicks") == 12)
FM.save_finished(con, "QAT-QC", 2025, NAMED, [], status="PEN")
check("2 a response without events never deletes kicks", n_count("shootout_kicks") == 12)
FM.save_finished(con, "UAE-PC", 2026, NAMELESS, NAMELESS["events"], status="PEN")
hn = NAMELESS["teams"]["home"]["id"]
rows_nameless = con.execute("SELECT player_id, player_name, scored FROM shootout_kicks WHERE fixture_id = 1645511").fetchall()
check("2 nameless match: 10 kicks, NULL id and name, 7 scored", len(rows_nameless) == 10 and all(r[0] is None and r[1] is None for r in rows_nameless)
      and sum(r[2] for r in rows_nameless) == 7, [tuple(r) for r in rows_nameless])
check("2 nameless: home 4 of 5", sum(r[1] for r in get(hn, 1645511)) == 4)


def mutated(fn):
    x = copy.deepcopy(NAMED)
    fn(x)
    return x


def so_events(x):
    return [e for e in x["events"] if MS.is_shootout(e)]


def flip(x):
    so_events(x)[0]["detail"] = "Missed Penalty" if so_events(x)[0]["detail"] == "Penalty" else "Penalty"


def gap(x):
    so_events(x)[0]["time"]["extra"] = 40


def stranger(x):
    so_events(x)[0]["team"]["id"] = 123456


def odd_detail(x):
    so_events(x)[0]["detail"] = "Penalty Saved"


for label, fn, want in (("disagrees with score.penalty", flip, "score.penalty"), ("broken kick numbers", gap, "kick numbers"),
                        ("unknown team", stranger, "unexpected"), ("unknown detail", odd_detail, "unexpected")):
    x = mutated(fn)
    rows, problem = MS.kicks_of(x, x["events"])
    before = [tuple(r) for r in con.execute("SELECT * FROM shootout_kicks WHERE fixture_id = 1635605")]
    wrote = MS.save_kicks(con, x, x["events"])
    after = [tuple(r) for r in con.execute("SELECT * FROM shootout_kicks WHERE fixture_id = 1635605")]
    check(f"2 rejected whole ({label}), earlier rows kept", rows == [] and want in (problem or "") and wrote == 0 and before == after, (problem, wrote))
plain = copy.deepcopy(NAMED)
plain["events"] = [e for e in plain["events"] if not MS.is_shootout(e)]
check("2 PEN response with no tagged kicks: nothing to store, no problem", MS.kicks_of(plain, plain["events"]) == ([], None))
untagged = copy.deepcopy(NAMED)
untagged["fixture"]["id"] = 777
untagged["events"] = [{"time": {"elapsed": 120, "extra": None}, "team": {"id": home}, "player": {"id": None, "name": "X"}, "type": "Goal", "detail": "Normal Goal", "comments": None}]
check("2 untagged 120' goals (1528446 shape) are not kicks", MS.save_kicks(con, untagged, untagged["events"]) == 0)
check("2 FT fixture with no kicks: nothing written", MS.save_kicks(con, W0["fixtures"]["ft"], []) == 0)
con.close()

# ── 3) backfill script (temp copy, temp cache, 0 requests) ─────────────────────────────────────────────────
BIG = TMPD / "football_so.db"
shutil.copy(DB_FILE, BIG)
_b = sqlite3.connect(BIG)   # the temp copy starts without the table, whether or not the real DB is migrated
_b.execute("DROP TABLE IF EXISTS shootout_kicks")
_b.commit()
_b.close()
cache = TMPD / "backups" / "cups_cache_x"
cache.mkdir(parents=True)
(cache / "ids_825_0.json").write_text(json.dumps({"response": [NAMED]}, ensure_ascii=False), encoding="utf-8")
(TMPD / "backups" / "not_a_cache").mkdir()
(TMPD / "backups" / "not_a_cache" / "ids_0.json").write_text(json.dumps({"response": [dict(NAMELESS)]}, ensure_ascii=False), encoding="utf-8")


def backfill(*a):
    return subprocess.run([sys.executable, str(ROOT / "backfill_shootout.py"), *a], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)


before = md5(BIG)
r = backfill("--db", str(BIG), "--cache", str(TMPD / "backups"), "--check")
check("3 --check: reports 1 match, 12 kicks", r.returncode == 0 and "with kicks 1" in r.stdout and "kicks 12" in r.stdout, r.stdout + r.stderr)
check("3 --check writes nothing, even without the table", md5(BIG) == before)
r = backfill("--db", str(BIG), "--cache", str(TMPD / "backups"))
check("3 without the table: refuses (exit 2)", r.returncode == 2 and md5(BIG) == before, r.stdout)
r = backfill("--db", str(BIG))
check("3 --cache is required", r.returncode == 2)
r = backfill("--check", "--cache", str(TMPD / "backups"))
check("3 --db is required", r.returncode == 2)
r = backfill("--db", str(BIG), "--cache", str(TMPD / "backups"), "--bogus")
check("3 unknown flag: exit 2, no write", r.returncode == 2 and md5(BIG) == before)
big = sqlite3.connect(BIG)
big.row_factory = sqlite3.Row
MS.migrate(big)
big.close()
r = backfill("--db", str(BIG), "--cache", str(TMPD / "backups"))
big = sqlite3.connect(BIG)
big.row_factory = sqlite3.Row
check("3 backfill writes 12 kicks; other folders ignored", r.returncode == 0 and big.execute("SELECT COUNT(*) FROM shootout_kicks").fetchone()[0] == 12, r.stdout)
g1 = big.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
big.close()
r = backfill("--db", str(BIG), "--cache", str(TMPD / "backups"))
big = sqlite3.connect(BIG)
big.row_factory = sqlite3.Row
check("3 backfill is repeatable and leaves goals alone", big.execute("SELECT COUNT(*) FROM shootout_kicks").fetchone()[0] == 12 and big.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == g1)

# ── 4/5) match page block and Arabic badge ─────────────────────────────────────────────────────────────────
import make_cups as MC  # noqa: E402
import make_matches as mm  # noqa: E402
import short_names as SN  # noqa: E402
from i18n import T  # noqa: E402

mm.LATEST_SEASON = 2026
mm.build_form_index(big)
teams = mm.load_teams()
cols = "match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status, round, " + ", ".join(MS.COLS)
row = lambda mid: big.execute(f"SELECT {cols} FROM matches WHERE match_id = ?", (mid,)).fetchone()  # noqa: E731
named_row = row(1635605)
h, a = teams.get(named_row["home_id"]), teams.get(named_row["away_id"])
kicks = mm.load_shootouts(big)
check("4 load_shootouts: only the backfilled match", set(kicks) == {1635605} and len(kicks[1635605]) == 12)


def marks(html):
    parts = html.split('class="son"')[1:]
    return [re.findall(r'<i class="(y|n)"', p) for p in parts]


for lang, title in (("ar", "ركلات الترجيح"), ("en", "Penalty shootout")):
    so = mm.shootout_html(big, named_row, h, a, kicks[1635605], lang)
    page = mm.build_page(named_row, h, a, [], None, lang, so_html=so)
    check(f"4 {lang}: title «{title}»", f"<h3>{title}</h3>" in so)
    check(f"4 {lang}: one row per team, home first, marks in kick_no order", marks(so) == [list("ynyyyn"), list("yynyyy")], marks(so))
    check(f"4 {lang}: green check and red cross", so.count("✓") == 9 and so.count("✗") == 3 and ".sok i.y{color:var(--green)}" in so and ".sok i.n{color:var(--red)}" in so)
    check(f"4 {lang}: 12 names under the marks", so.count("<small>") == 12, so.count("<small>"))
    check(f"4 {lang}: block sits under the score, before the tabs", page.index('data-mid="1635605"') < page.index('class="so"') < page.index('class="mtabs"') if 'class="mtabs"' in page else page.index('data-mid="1635605"') < page.index('class="so"'))
    check(f"4 {lang}: block needs no match.css change", "<style>" in so)
ar_name = big.execute("SELECT player_ar FROM lineup_players WHERE match_id = 1635605 AND player_id = 12764").fetchone()
snm = SN.match_map(big, 1635605)
so_ar, so_en = (mm.shootout_html(big, named_row, h, a, kicks[1635605], x) for x in ("ar", "en"))
check("4 EN shows the provider name (shortened as elsewhere)", mm.html_escape(SN.apply(snm, "Roger Guedes")) in so_en)
if ar_name and ar_name[0]:
    check("4 AR shows the Arabic name from the lineup", mm.html_escape(SN.apply(snm, ar_name[0])) in so_ar, ar_name[0])
fake = [dict(r) for r in kicks[1635605]]
fake[0].update(player_id=999999999, player_name="Z. Fallback<b>")
fake[1].update(player_id=None, player_name=None)
so = mm.shootout_html(big, named_row, h, a, fake, "ar")
check("4 AR falls back to the English name; names are escaped", "Fallback&lt;b&gt;" in so and "Fallback<b>" not in so)
check("4 a kick with no name: mark only", so.count("<small>") == 11, so.count("<small>"))
nameless = [dict(r, player_id=None, player_name=None) for r in kicks[1635605]]
so = mm.shootout_html(big, named_row, h, a, nameless, "en")
check("4 unnamed shootout: marks, no names, narrow columns", "<small>" not in so and "--w:30px" in so and marks(so) == [list("ynyyyn"), list("yynyyy")])
uneven = [dict(r) for r in kicks[1635605] if not (r["team_id"] == named_row["home_id"] and r["kick_no"] == 6)]
so = mm.shootout_html(big, named_row, h, a, uneven, "en")
check("4 teams with unequal kicks stay aligned (blank cell)", so.count('<span class="sok"></span>') == 1 and "--n:6" in so)
for lang in ("ar", "en"):
    check(f"4 {lang}: no kicks = no block", mm.shootout_html(big, named_row, h, a, None, lang) == "" and mm.shootout_html(big, named_row, h, a, [], lang) == "")
    page = mm.build_page(named_row, h, a, [], None, lang)
    check(f"4 {lang}: page without kicks has no block, keeps the pens line", 'class="so"' not in page and "4 - 5" in page)

for lang, badge in (("ar", "ترجيح"), ("en", "PEN")):
    page = mm.build_page(named_row, h, a, [], None, lang)
    check(f"5 {lang}: badge is «{badge}»", f'<span class="ftb">{badge}</span>' in page)
ft = big.execute(f"SELECT {cols} FROM matches WHERE status = 'FT' AND home_goals IS NOT NULL LIMIT 1").fetchone()
aet = big.execute(f"SELECT {cols} FROM matches WHERE status = 'AET' LIMIT 1").fetchone()
for label, r_, want in (("FT", ft, "FT"), ("AET", aet, "AET")):
    page = mm.build_page(r_, teams.get(r_["home_id"]), teams.get(r_["away_id"]), [], None, "ar")
    check(f"5 ar: {label} badge unchanged", f'<span class="ftb">{want}</span>' in page)
check("5 card label is «ترجيح» in Arabic, Pens in English", T["ar"]["pens_short"] == "ترجيح" and T["en"]["pens_short"] == "Pens")
tie = {"a": named_row["home_id"], "b": named_row["away_id"], "agg": (3, 3), "pens": (4, 5), "winner": named_row["away_id"], "round": "Semi-finals",
       "done": True, "placeholder": False, "legs": [{"status": "PEN", "home_goals": 3, "away_goals": 3, "date": "2026-02-01 18:00", "match_id": 1635605}]}
try:
    tie_ar = MC.tie_html(tie, teams, "ar")
    check("5 bracket ar: no literal PEN", ">PEN<" not in tie_ar and " PEN" not in tie_ar, tie_ar[:300])
except Exception as e:
    check("5 bracket renders", False, repr(e))
big.close()

# ── 6) live_view: "(h-a pens)" in a real browser against a faked feed ──────────────────────────────────────
import live_view as LV  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PAGE = """<!doctype html><html><body>
<div class="match" data-mid="1"><div class="score time">18:00</div></div>
<div class="match" data-mid="2"><div class="score time">18:00</div></div>
<div class="match" data-mid="3"><div class="score time">18:00</div></div>
<div class="match" data-mid="4"><div class="score time">18:00</div></div>
<div class="big soon" data-mid="%s"><span class="score">18:00</span><div class="kick"></div></div>
%s</body></html>"""
FEED = {"t": 1800000000, "m": {
    "1": {"h": 1, "a": 1, "e": 120, "s": "P", "p": {"h": 2, "a": 3}, "th": 1, "ta": 2, "lg": 3},
    "2": {"h": 1, "a": 1, "e": 120, "s": "P", "th": 1, "ta": 2, "lg": 3}},
    "f": {"3": {"h": 1, "a": 1, "s": "PEN", "p": {"h": 4, "a": 5}, "ft": 1800000000},
          "4": {"h": 2, "a": 0, "s": "FT", "ft": 1800000000}}}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for lang, word in (("ar", "ترجيح"), ("en", "pens")):
        for big_id, want_badge in (("9", None), ("3", "ترجيح" if lang == "ar" else "PEN")):
            feed = copy.deepcopy(FEED)
            feed["f"].setdefault("9", {"h": 0, "a": 0, "s": "FT", "ft": 1800000000})
            ctx = br.new_context()
            ctx.route(LV.LIVE_SRC + "**", lambda rt: rt.fulfill(status=200, content_type="application/json",
                                                                headers={"Access-Control-Allow-Origin": "*"}, body=json.dumps(feed)))
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.set_content(PAGE % (big_id, LV.live_script(T[lang], 0)))
            pg.wait_for_selector('.match[data-mid="1"] .lvscore', timeout=8000)
            pg.wait_for_timeout(150)
            txt = lambda m: pg.inner_text(f'.match[data-mid="{m}"] .score')  # noqa: E731
            check(f"6 {lang}: P with p shows (2-3 {word})", f"(2-3 {word})" in txt("1").replace("\n", " "), txt("1"))
            check(f"6 {lang}: P without p shows nothing extra", word not in txt("2") and pg.locator('.match[data-mid="2"] .lvpso').count() == 0, txt("2"))
            check(f"6 {lang}: PEN in f with p shows (4-5 {word})", f"(4-5 {word})" in txt("3").replace("\n", " ") and "1 - 1" in txt("3"), txt("3"))
            check(f"6 {lang}: FT in f shows nothing extra", word not in txt("4") and pg.locator('.match[data-mid="4"] .lvpso').count() == 0, txt("4"))
            if want_badge:
                bt = pg.inner_text(".big .ftb")
                check(f"6 {lang}: match page badge after the whistle is «{want_badge}», with the pens score", bt == want_badge and f"(4-5 {word})" in pg.inner_text(".big").replace("\n", " "), (bt, pg.inner_text(".big")))
            check(f"6 {lang}: no script errors", not errs, errs)
            ctx.close()
    br.close()

check("football.db untouched", md5(DB_FILE) == DB_MD5)
print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
