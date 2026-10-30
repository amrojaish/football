#!/usr/bin/env python3
"""
Player page, FotMob style (18 Oct 2026; FotMob layout batch 5, 30 Oct 2026). Run:
    python C:\\Users\\User\\Projects\\Football\\test_player_page.py
Needs the site built (make_assets.py, make_players.py). Serves the repo itself on 127.0.0.1:8777. Reads football.db read-only.

Players: cristiano-ronaldo (pid 874, player_info ok + real photo), b-bello-ilou (id 502755: player_info since 18 Oct 2026 with
height NULL and no photo — MAR then UAE/Al Ain, lineups, few stats), mohammad-qasem (IRQ, has an id but no lineups), m-al-attar (JOR scorer, no id).
Profile rows follow player_info column by column: a NULL column means its row is absent.
Checks: 4 tabs AR/EN (Profile default), photo vs empty round slot, profile fields = player_info / lineups (missing ones hidden),
matches tab = played matches from SQL (20 + «Show all»), IRQ/JOR goal events only + note, stats + career (apps from lineups)
kept, every goal row kept, slugs/stubs unchanged, 360px: no horizontal overflow on any tab.
"""
import functools
import http.server
import json
import socketserver
import sqlite3
import sys
import threading
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_players as MP  # noqa: E402
import player_layout as PLY  # noqa: E402
from config import DB_FILE  # noqa: E402
from player_pages import get_plan  # noqa: E402

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
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8777), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8777"

con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
plan = get_plan()
by_slug = {p["slug"]: p for p in plan["pages"]}
PLAYERS = ("cristiano-ronaldo", "b-bello-ilou", "mohammad-qasem", "m-al-attar")
check("setup: the 4 test players have pages", all(s in by_slug for s in PLAYERS), [s for s in PLAYERS if s not in by_slug])
info = {r["player_id"]: dict(r) for r in con.execute("SELECT * FROM player_info WHERE status = 'ok'")}


def played(pid):
    """independent SQL: finished matches the player played (minutes > 0 with stats; started, when the match has no stats row)"""
    if not pid:
        return 0
    q = """SELECT COUNT(*) FROM (
             SELECT ps.match_id FROM player_stats ps JOIN matches m ON m.match_id = ps.match_id
              WHERE ps.player_id = ? AND ps.minutes > 0 AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
             UNION
             SELECT lp.match_id FROM lineup_players lp JOIN matches m ON m.match_id = lp.match_id
              WHERE lp.player_id = ? AND lp.starter = 1 AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = lp.match_id AND ps.player_id = lp.player_id))"""
    return con.execute(q, (pid, pid)).fetchone()[0]


TABS = {"ar": ["الملف", "المباريات", "الإحصائيات", "المسيرة"], "en": ["Profile", "Matches", "Stats", "Career"]}
PROFILE_JS = """() => [...document.querySelectorAll('.mp[data-tab="profile"] .pfr')].map(r => [r.querySelector('.k').textContent.trim(), r.querySelector('.v').textContent.trim()])"""
# elements inside a horizontal scroll box (the season-stats table's .stw, overflow-x:auto by design) are clipped there,
# so only the box itself must fit the screen
OVERFLOW_JS = """() => { const w = document.documentElement.clientWidth, bad = [];
    const inScroller = e => { for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) {
        const o = getComputedStyle(x).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
    document.querySelectorAll('.mp.on *').forEach(e => { if (inScroller(e)) return; const r = e.getBoundingClientRect();
        if (r.width && (r.right > w + 0.5 || r.left < -0.5)) bad.push(e.className || e.tagName); });
    return {hscroll: document.documentElement.scrollWidth > w, bad: bad.slice(0, 5)}; }"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        P = MP.PT[lang]
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
        for slug in PLAYERS:
            page = by_slug[slug]
            pid = page["stats_pid"]
            inf = info.get(pid) if pid else None
            tag = f"{lang} {slug}"
            pg.goto(f"{BASE}{pre}/players/{slug}.html"); pg.wait_for_timeout(400)
            labels = pg.eval_on_selector_all(".mtabs .mtab", "els => els.map(e => e.textContent.trim())")
            on = pg.eval_on_selector_all(".mp.on", "els => els.map(e => e.getAttribute('data-tab'))")
            check(f"{tag}: 4 tabs {TABS[lang]}, Profile open by default", labels == TABS[lang] and on == ["profile"], (labels, on))
            # (30 Oct 2026, batch 5) header: round placeholder avatar, never a player photo; name + club pill; Follow pill in the top bar
            hd = pg.evaluate("() => ({av: !!document.querySelector('.phd .pav svg'), img: document.querySelectorAll('img[src*=\"football/players/\"]').length,"
                             " h1: (document.querySelector('.phd h1') || {}).textContent || '', fol: !!document.querySelector('.pfol')})")
            check(f"{tag}: placeholder avatar, no player photo, name + Follow pill", hd["av"] and hd["img"] == 0 and hd["h1"] and hd["fol"], hd)
            # profile grid (3x2): each player_info field shown when set, absent when NULL
            grid = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"profile\"] .pgc')].map(c => [c.querySelector('.k').textContent.trim(), c.querySelector('.v').textContent.trim()])")
            gd = dict(grid)
            L = PLY.PL[lang]
            if inf:
                want = {
                    L["height"]: f"{inf['height_cm']} {L['cm']}" if inf["height_cm"] is not None else None,
                    L["country"]: (MP.NAT_AR.get(inf["nationality"], inf["nationality"]) if lang == "ar" else inf["nationality"]) if inf["nationality"] else None,
                    L["shirt"]: str(inf["number"]) if inf["number"] is not None else None,
                    L["pos"]: P["positions"][inf["position"]] if inf["position"] else None,
                }
                ok = all((k not in gd) if v is None else (gd.get(k) == v) for k, v in want.items())
                ok = ok and ((L["age"] in gd) == bool(inf["birth_date"]))
                check(f"{tag}: profile grid = player_info (height, age, country, shirt, position; NULL fields hidden)", ok, grid)
            elif pid and played(pid):
                check(f"{tag}: no player_info row -> height/age/country hidden, position + shirt from lineups/stats",
                      L["height"] not in gd and L["age"] not in gd and L["country"] not in gd and L["pos"] in gd and L["shirt"] in gd, grid)
            else:
                check(f"{tag}: nothing known -> no profile grid", grid == [], grid)
            # matches
            pg.click('.mtab[data-tab="matches"]'); pg.wait_for_timeout(200)
            n_sql = played(pid)
            rows_ = pg.locator('.mp[data-tab="matches"] .pml2 .pmr')
            vis = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"matches\"] .pml2 .pmr')].filter(c => c.getBoundingClientRect().height > 0).length")
            if n_sql:
                mids = pg.eval_on_selector_all('.mp[data-tab="matches"] .pml2 .pmr', "els => els.map(e => +e.getAttribute('href').match(/(\\d+)\\.html/)[1])")
                ds = [con.execute("SELECT date FROM matches WHERE match_id = ?", (m,)).fetchone()[0] for m in mids]
                check(f"{tag}: Matches = {n_sql} played matches (SQL), 20 shown, newest first",
                      rows_.count() == n_sql and vis == min(20, n_sql) and ds == sorted(ds, reverse=True), (rows_.count(), vis, n_sql))
                if n_sql > 20:
                    pg.click('.mp[data-tab="matches"] .pmore'); pg.wait_for_timeout(200)
                    vis2 = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"matches\"] .pml2 .pmr')].filter(c => c.getBoundingClientRect().height > 0).length")
                    check(f"{tag}: «Show all» reveals all {n_sql}", vis2 == n_sql, vis2)
                if pid and con.execute("SELECT 1 FROM player_stats WHERE player_id = ? AND rating IS NOT NULL LIMIT 1", (pid,)).fetchone():
                    check(f"{tag}: rows carry minutes and a rating badge", pg.locator('.pml2 .pmev span').count() > 0 and pg.locator('.pml2 .prt').count() > 0)
            else:
                old = pg.locator('.mp[data-tab="matches"] .note').all_inner_texts()
                check(f"{tag}: no lineups (IRQ/JOR) -> goal events only, the existing bottom note kept",
                      rows_.count() == 0 and old == [MP.T[lang]["p_nodetail"]], (rows_.count(), old))
            # MAR: lineups without player stats -> starts only, one short note under the list; nobody else gets a .pnote
            mar = con.execute(
                "SELECT 1 FROM lineup_players lp JOIN matches m ON m.match_id = lp.match_id WHERE lp.player_id = ? AND lp.starter = 1 "
                "AND m.league_code = 'MAR' AND m.home_goals IS NOT NULL AND NOT EXISTS (SELECT 1 FROM player_stats ps "
                "WHERE ps.match_id = lp.match_id AND ps.player_id = lp.player_id) LIMIT 1", (pid or -1,)).fetchone() is not None
            pn = pg.locator('.mp[data-tab="matches"] .pnote').all_inner_texts()
            check(f"{tag}: «{P['starts_only']}» note {'shown (MAR starts without stats)' if mar else 'absent'}",
                  pn == ([P["starts_only"]] if mar else []), pn)
            g = pg.locator('.mp[data-tab="matches"] a.g').count()
            check(f"{tag}: every goal kept in «all goals» ({len(page['goals'])})", g == len(page["goals"]), (g, len(page["goals"])))
            # stats: season selector + card; the detailed season table kept when player_stats exists
            pg.click('.mtab[data-tab="stats"]'); pg.wait_for_timeout(150)
            sel = pg.locator('.mp[data-tab="stats"] #psel').count() == 1
            card = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"stats\"] .pstc')].filter(c => !c.hidden).length")
            has_tbl = pg.locator('.mp[data-tab="stats"] .stt').count() == 1
            has_ps = bool(pid and con.execute("SELECT 1 FROM player_stats WHERE player_id = ? AND minutes > 0 LIMIT 1", (pid,)).fetchone())
            check(f"{tag}: Stats tab: season selector + one visible card" + (" + season table" if has_ps else ""),
                  sel and card == 1 and (has_tbl or not has_ps), (sel, card, has_tbl))
            # career: one row per (season, club) of matches played + goals; matches column only with lineup data
            pg.click('.mtab[data-tab="career"]'); pg.wait_for_timeout(150)
            crow = pg.locator('.mp[data-tab="career"] .pcar .pcr:not(.hd)').count()
            keys = {(r["season"], r["team_id"]) for r in page["goals"] if r["detail"] != "Own Goal"}
            keys |= {(r["season"], r["team_id"]) for r in page["goals"]}
            if pid:
                keys |= {(r[0], r[1]) for r in con.execute(
                    """SELECT m.season, x.team_id FROM (SELECT match_id, team_id FROM player_stats WHERE player_id = ? AND minutes > 0
                       UNION SELECT match_id, team_id FROM lineup_players WHERE player_id = ? AND starter = 1) x
                       JOIN matches m ON m.match_id = x.match_id WHERE m.home_goals IS NOT NULL""", (pid, pid))}
            hcols = pg.locator('.mp[data-tab="career"] .pcar .pcr.hd .c').count()
            check(f"{tag}: Career = {len(keys)} (season, club) rows; matches column {'shown' if n_sql else 'absent'}",
                  crow == len(keys) and (hcols >= 2 if n_sql else hcols >= 1), (crow, len(keys), hcols))
            # 360px, every tab
            pg.set_viewport_size({"width": 360, "height": 800})
            ov = []
            for k in ("profile", "matches", "stats", "career"):
                pg.click(f'.mtab[data-tab="{k}"]'); pg.wait_for_timeout(120)
                r = pg.evaluate(OVERFLOW_JS)
                if r["hscroll"] or r["bad"]:
                    ov.append((k, r))
            check(f"{tag}: 360px: no horizontal overflow on any tab", not ov, ov)
            pg.set_viewport_size({"width": 390, "height": 844})
        check(f"{lang}: no page errors", not errs, errs)
        ctx.close()
    b.close()

# slugs + stubs unchanged — against the CURRENT plan (27 Oct 2026; the local players/ folder can be older than the data)
from player_pages import load_history  # noqa: E402
served = {p["slug"] for p in plan["pages"]} | set(plan["stubs"])
published = set(load_history())
check(f"every published URL ({len(published)}) is a page or a redirect of the current plan (URLs unchanged, no 404)",
      published <= served, sorted(published - served)[:5])
page_slugs = {p["slug"] for p in plan["pages"]}
check("every redirect points to a page of the plan (no redirect to a redirect / missing page)",
      all(d in page_slugs for d in plan["stubs"].values()), [(k, v) for k, v in plan["stubs"].items() if v not in page_slugs][:5])
stub = next(iter(plan["stubs"]), None)
if stub:
    s = MP.redirect_html("ar", plan["stubs"][stub], stub)
    check(f"redirect stub {stub} markup points to {plan['stubs'][stub]}", "saffara-redirect" in s and f"{plan['stubs'][stub]}.html" in s)

# Career rows (30 Oct 2026, batch 5): every built page lists each (season, club) once, newest season first
import re  # noqa: E402
ROW_RE = re.compile(r'<div class="pcr" [^>]*><a class="pcl" href="[^"]*clubs/(\d+)\.html">.*?<small dir="ltr">(\d{4})/')
built = sorted(p["slug"] for p in plan["pages"])
for lang, d in (("ar", ROOT / "players"), ("en", ROOT / "en" / "players")):
    bad, n = [], 0
    for f in (d / f"{s}.html" for s in built):
        if not f.exists():
            continue
        rows = ROW_RE.findall(f.read_text(encoding="utf-8"))
        if not rows:
            continue
        n += 1
        ks = [(int(y), c) for c, y in rows]
        if len(ks) != len(set(ks)) or [k[0] for k in ks] != sorted((k[0] for k in ks), reverse=True):
            bad.append(f.stem)
    check(f"{lang}: career rows unique (season, club), newest first, on all {n} pages with a career list", n > 0 and not bad, bad[:5])

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
