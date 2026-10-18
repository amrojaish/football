#!/usr/bin/env python3
"""
Batch D2 (18 Oct 2026): match page H2H tab always shown + «Season so far» + both clubs' positions in Preview. Run:
    python C:\\Users\\User\\Projects\\Football\\test_match_preview.py
Needs the site built (make_assets.py, make_matches.py). Serves the repo itself on 127.0.0.1:8775. Live feed mocked.

1) H2H tab exists with 0 previous meetings: this fixture's shared match_row card on top (same data-mid, countdown time cell),
   «لا مواجهات سابقة» / "No previous meetings", then the season card; with meetings: card + summary + list + season card.
2) «Season so far» numbers vs independent SQL (current season, same competition, standings exclusions) for EGY, MAR, JOR
   fixtures: position (= the page's own Table tab rank), W-D-L, goals/conceded per match (1 decimal), clean sheets, biggest
   win / loss (score from the club's side + match link). Home on the start side (RTL and LTR).
3) Preview: both clubs' positions one under the other below the form card (rank + pts + played = Table tab); data-lt on the
   6 live leagues, none on JOR (static); a mocked live game moves the home club's points/played/rank via live_view.ltPaint.
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from config import DB_FILE, LEAGUES  # noqa: E402
from tiebreak import STANDINGS_EXCLUDED  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:700]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8775), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8775"

con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
con.row_factory = sqlite3.Row


def pick(lg, meetings):
    """first NS fixture of the league's current season with / without previous meetings"""
    season = con.execute("SELECT MAX(season) FROM matches WHERE league_code = ?", (lg,)).fetchone()[0]
    for r in con.execute("SELECT * FROM matches WHERE league_code = ? AND season = ? AND home_goals IS NULL AND status = 'NS' "
                         "ORDER BY date, match_id", (lg, season)):
        n = con.execute("SELECT COUNT(*) FROM matches WHERE home_goals IS NOT NULL AND match_id != ? AND "
                        "((home_id = ? AND away_id = ?) OR (home_id = ? AND away_id = ?))",
                        (r["match_id"], r["home_id"], r["away_id"], r["away_id"], r["home_id"])).fetchone()[0]
        if (n > 0) == meetings:
            return r, n
    return None, 0


def sql_season(m, tid):
    """independent: the club's finished games of this league+season from its own side, standings exclusions applied"""
    excl = ",".join(str(x) for x in (STANDINGS_EXCLUDED or {0}))
    q = f"""SELECT match_id, date, gf, ga FROM (
              SELECT match_id, date, home_goals AS gf, away_goals AS ga FROM matches WHERE home_id = ? AND league_code = ? AND season = ?
                     AND home_goals IS NOT NULL AND away_goals IS NOT NULL AND match_id NOT IN ({excl})
              UNION ALL
              SELECT match_id, date, away_goals, home_goals FROM matches WHERE away_id = ? AND league_code = ? AND season = ?
                     AND home_goals IS NOT NULL AND away_goals IS NOT NULL AND match_id NOT IN ({excl}))"""
    a = (m["league_code"], m["season"])
    g = con.execute(q, (tid, *a, tid, *a)).fetchall()
    p = len(g)
    big = lambda w: con.execute(q.replace("SELECT match_id, date, gf, ga FROM (", "SELECT match_id, gf, ga FROM (")
                                + (" WHERE gf > ga ORDER BY gf - ga DESC, gf DESC, date DESC LIMIT 1" if w
                                   else " WHERE gf < ga ORDER BY ga - gf DESC, ga DESC, date DESC LIMIT 1"), (tid, *a, tid, *a)).fetchone()
    fmt = lambda r: f'{r["gf"]} - {r["ga"]}|{r["match_id"]}.html' if r else "—"
    return {"wdl": f'{sum(x["gf"] > x["ga"] for x in g)} - {sum(x["gf"] == x["ga"] for x in g)} - {sum(x["gf"] < x["ga"] for x in g)}',
            "gpm": f'{sum(x["gf"] for x in g) / p:.1f}' if p else "—", "cpm": f'{sum(x["ga"] for x in g) / p:.1f}' if p else "—",
            "cs": str(sum(x["ga"] == 0 for x in g)) if p else "—", "bw": fmt(big(True)), "bl": fmt(big(False))}


SEASON_JS = """() => { const out = {}; document.querySelectorAll('.ssf .ssfr').forEach(r => { const v = r.querySelectorAll('.v');
    const cell = x => { const a = x.querySelector('a'); return a ? a.textContent.trim() + '|' + a.getAttribute('href') : x.textContent.trim(); };
    out[r.getAttribute('data-k')] = [cell(v[0]), cell(v[1])]; }); return out; }"""
TABLE_JS = """() => { const o = {}; document.querySelectorAll('.lgt tr[data-t]').forEach((tr, i) => { const c = tr.children;
    o[tr.getAttribute('data-t')] = [parseInt(c[0].textContent, 10), c[7].textContent.trim(), c[2].textContent.trim()]; }); return o; }"""
POS_JS = """() => [...document.querySelectorAll('.ltpos .lprow')].map(x => [x.getAttribute('data-t'), x.querySelector('.lpr').textContent.trim(),
    x.querySelector('.lpp').textContent.trim(), x.querySelector('.lpm').textContent.trim(), x.classList.contains('lvrow')])"""

LIVE = {"body": '{"t":0,"m":{}}'}


def live(route):
    route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"])


H2H_NONE = {"ar": "لا مواجهات سابقة", "en": "No previous meetings"}
cases = []
for lg in ("EGY", "MAR", "JOR"):
    r, _ = pick(lg, False)
    if r:
        cases.append((lg, r, 0))
    r, n = pick(lg, True)
    if r:
        cases.append((lg, r, n))
fin = con.execute("SELECT * FROM matches WHERE league_code = 'EGY' AND home_goals IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
cases.append(("EGY", fin, -1))
check("setup: fixtures found (EGY/MAR/JOR with and without meetings, one finished)", len({c[0] for c in cases}) == 3 and any(c[2] == 0 for c in cases)
      and any(c[2] > 0 for c in cases), [(c[0], c[1]["match_id"], c[2]) for c in cases])

with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("https://saffara-live.abujaishamr.workers.dev/**", live)
        pg.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
        for lg, m, n in cases:
            mid, tag = m["match_id"], f"{lang} {lg} {m['match_id']}" + (" (0 meetings)" if n == 0 else (" (finished)" if n < 0 else f" ({n} meetings)"))
            pg.goto(f"{BASE}{pre}/matches/{mid}.html"); pg.wait_for_timeout(500)
            has_tab = pg.locator('.mtab[data-tab="h2h"]').count() == 1
            check(f"{tag}: H2H tab shown", has_tab)
            if not has_tab:
                continue
            pg.click('.mtab[data-tab="h2h"]'); pg.wait_for_timeout(200)
            card = pg.evaluate("""() => { const c = document.querySelector('[data-tab="h2h"].mp .fxc .match'); if (!c) return null;
                return [c.getAttribute('data-mid'), c.querySelector('.score').className, c.querySelector('.score').textContent.trim(),
                        !!document.querySelector('[data-tab="h2h"].mp .fxc + .h2hnone, [data-tab="h2h"].mp .fxc + .h2h')]; }""")
            if n < 0:
                ok = card and card[0] == str(mid) and card[2] == f'{m["home_goals"]} - {m["away_goals"]}'
            else:
                ok = card and card[0] == str(mid) and "time" in card[1]
            check(f"{tag}: this fixture's card on top of H2H (data-mid, {'score' if n < 0 else 'time/countdown'}), meetings or empty line right under it",
                  ok and card[3], card)
            none_txt = pg.locator('[data-tab="h2h"].mp .h2hnone').all_inner_texts()
            if n == 0:
                check(f"{tag}: «{H2H_NONE[lang]}» line, no summary bar", none_txt == [H2H_NONE[lang]] and pg.locator('[data-tab="h2h"].mp .h2hbar').count() == 0, none_txt)
            elif n > 0:
                cnt = pg.locator('[data-tab="h2h"].mp .h2hlist a').count()
                check(f"{tag}: meetings summary + list ({cnt} = {n}), no empty line", cnt == n and not none_txt, [cnt, n])
            # season so far vs SQL (+ position = the page's Table tab)
            got = pg.evaluate(SEASON_JS)
            tbl = pg.evaluate(TABLE_JS)
            want = {}
            for side, tid in ((0, m["home_id"]), (1, m["away_id"])):
                s = sql_season(m, tid)
                for k, v in s.items():
                    want.setdefault(k, [None, None])[side] = v
                want.setdefault("pos", [None, None])[side] = str(tbl[str(tid)][0]) if str(tid) in tbl else "—"
            gl = got   # each cell: plain value, or "score|match link" for biggest win/loss (the «vs Opp» note sits outside the link)
            plain_ok = all(gl.get(k) == want[k] for k in ("pos", "wdl", "gpm", "cpm", "cs"))
            bw_ok = all(gl.get(k) == want[k] for k in ("bw", "bl"))
            check(f"{tag}: «Season so far» = SQL (position = Table tab, W-D-L, goals/conceded per match 1 dp, clean sheets, biggest win/loss + link)",
                  plain_ok and bw_ok, {"got": gl, "want": want})
            side_ok = pg.evaluate("""() => { const r = document.querySelector('.ssf .ssfr'); if (!r) return false; const v = r.querySelectorAll('.v');
                const rtl = getComputedStyle(document.documentElement).direction === 'rtl', a = v[0].getBoundingClientRect(), z = v[1].getBoundingClientRect();
                return rtl ? a.left > z.left : a.left < z.left; }""")
            check(f"{tag}: home club's column on the start side", side_ok)
            # Preview positions (upcoming only)
            if n >= 0:
                pos = pg.evaluate(POS_JS)
                lt = pg.evaluate("() => { const x = document.querySelector('.ltpos'); return x ? x.getAttribute('data-lt') : 'missing'; }")
                below = pg.evaluate("() => { const f = document.querySelector('.mp[data-tab=\"events\"] .tfcard'), x = document.querySelector('.mp[data-tab=\"events\"] .ltpos'); return !!x && (!f || (f.compareDocumentPosition(x) & 4) > 0); }")
                want_pos = [[str(t_), str(tbl[str(t_)][0]), tbl[str(t_)][1], tbl[str(t_)][2], False] for t_ in (m["home_id"], m["away_id"]) if str(t_) in tbl]
                check(f"{tag}: Preview lists both clubs (home first) with rank/pts/played = Table tab, below the form card", pos == want_pos and below, {"got": pos, "want": want_pos})
                check(f"{tag}: live attrs {'absent (JOR static)' if lg == 'JOR' else 'present (data-lt=' + lg + ')'}",
                      (lt is None) if lg == "JOR" else (lt == lg), lt)
        check(f"{lang}: no page errors", not errs, errs)
        # live rank update (EGY fixture with 0 meetings): the fixture itself live at 5-0 for the home club
        lg, m, _ = next(c for c in cases if c[0] == "EGY" and c[2] == 0)
        pg.goto(f"{BASE}{pre}/matches/{m['match_id']}.html"); pg.wait_for_timeout(400)
        before = {x[0]: x for x in pg.evaluate(POS_JS)}
        LIVE["body"] = json.dumps({"t": 0, "m": {str(m["match_id"]): {"lg": LEAGUES["EGY"]["id"], "th": m["home_id"], "ta": m["away_id"],
                                                                       "h": 5, "a": 0, "s": "2H", "e": 60}}})
        pg.reload(); pg.wait_for_timeout(2500)
        after = {x[0]: x for x in pg.evaluate(POS_JS)}
        tbl_live = pg.evaluate(TABLE_JS)
        LIVE["body"] = '{"t":0,"m":{}}'
        h = str(m["home_id"])
        check(f"{lang} live: ltPaint updates the Preview block: home +3 pts, +1 played, rank = live Table tab, live mark",
              int(after[h][2]) == int(before[h][2]) + 3 and int(after[h][3]) == int(before[h][3]) + 1 and after[h][1] == str(tbl_live[h][0]) and after[h][4],
              {"before": before.get(h), "after": after.get(h), "table": tbl_live.get(h)})
        card = pg.evaluate(f"""() => {{ const c = document.querySelector('.fxc .match'); return [c.classList.contains('live'), (c.querySelector('.lvpill') || {{}}).textContent || '']; }}""")
        check(f"{lang} live: the H2H fixture card goes live too (pill 60')", card[0] and card[1] == "60'", card)
        ctx.close()
    b.close()

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
