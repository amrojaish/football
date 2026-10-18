#!/usr/bin/env python3
"""
Player page, FotMob style (18 Oct 2026). Run:
    python C:\\Users\\User\\Projects\\Football\\test_player_page.py
Needs the site built (make_assets.py, make_players.py). Serves the repo itself on 127.0.0.1:8777. Reads football.db read-only.

Players: cristiano-ronaldo (pid 874, player_info ok + real photo), b-bello-ilou (new id 502755, NO player_info row, MAR: lineups
without stats), mohammad-qasem (IRQ, has an id but no lineups), m-al-attar (JOR scorer, no id).
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
            # photo slot
            ph = pg.evaluate("() => { const x = document.querySelector('header .pph'); const r = x && x.getBoundingClientRect();"
                             " return x ? [x.tagName, x.getAttribute('src') || '', x.textContent.trim(), Math.round(r.width), Math.round(r.height), getComputedStyle(x).borderRadius] : null; }")
            if inf and inf.get("has_photo") == 1:
                check(f"{tag}: real photo (player_info.has_photo = 1) in the 72px round slot", ph and ph[0] == "IMG" and ph[1].endswith(f"/players/{pid}.png")
                      and ph[3] == 72 and ph[4] == 72 and ph[5] == "50%", ph)
            else:
                check(f"{tag}: empty round 72px slot, no image, no initials", ph and ph[0] == "SPAN" and ph[2] == "" and ph[3] == 72 and ph[5] == "50%", ph)
            # profile
            prof = dict(pg.evaluate(PROFILE_JS))
            if inf:
                a = MP.player_age(inf["birth_date"], date.today())
                nat = MP.NAT_AR.get(inf["nationality"], inf["nationality"]) if lang == "ar" else inf["nationality"]
                ok = (prof.get(P["age"]) == f"{a} {P['years']}" and prof.get(P["nat"]) == nat and prof.get(P["height"]) == f"{inf['height_cm']} {P['cm']}"
                      and prof.get(P["pos"]) == P["positions"][inf["position"]] and prof.get(P["num"]) == str(inf["number"]) and prof.get(P["club"]))
                check(f"{tag}: profile = player_info (age from birth date, nationality{' in Arabic' if lang == 'ar' else ''}, height, position, number) + club", ok, prof)
            elif pid and played(pid):
                check(f"{tag}: no player_info row -> age/nationality/height hidden, position + number from lineups/stats, club shown",
                      P["age"] not in prof and P["nat"] not in prof and P["height"] not in prof and P["pos"] in prof and P["num"] in prof and P["club"] in prof, prof)
            else:
                check(f"{tag}: nothing known but the club -> only the club row", list(prof) == [P["club"]], prof)
            # matches
            pg.click('.mtab[data-tab="matches"]'); pg.wait_for_timeout(200)
            n_sql = played(pid)
            cards = pg.locator('.mp[data-tab="matches"] .pms .match')
            vis = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"matches\"] .pms .match')].filter(c => c.getBoundingClientRect().height > 0).length")
            if n_sql:
                lines = pg.eval_on_selector_all('.mp[data-tab="matches"] .pms .match .pml', "els => els.map(e => e.textContent.trim())")
                ds = [tuple(int(x) for x in reversed(l.split(" · ")[0].split("/"))) for l in lines]
                check(f"{tag}: Matches = {n_sql} played matches (SQL), 20 shown, newest first, a stats line under each",
                      cards.count() == n_sql and vis == min(20, n_sql) and len(lines) == n_sql and ds == sorted(ds, reverse=True), (cards.count(), vis, n_sql, lines[:2]))
                if n_sql > 20:
                    pg.click('.mp[data-tab="matches"] .pmore'); pg.wait_for_timeout(200)
                    vis2 = pg.evaluate("() => [...document.querySelectorAll('.mp[data-tab=\"matches\"] .pms .match')].filter(c => c.getBoundingClientRect().height > 0).length")
                    check(f"{tag}: «Show all» reveals all {n_sql}", vis2 == n_sql, vis2)
                if inf:
                    check(f"{tag}: stats lines carry minutes and a rating", any("'" in l for l in lines) and pg.locator('.pms .pml b').count() > 0, lines[:3])
            else:
                old = pg.locator('.mp[data-tab="matches"] .note').all_inner_texts()
                check(f"{tag}: no lineups (IRQ/JOR) -> goal events only, the existing bottom note kept",
                      cards.count() == 0 and old == [MP.T[lang]["p_nodetail"]], (cards.count(), old))
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
            # stats + career kept
            pg.click('.mtab[data-tab="stats"]'); pg.wait_for_timeout(150)
            has_cards = pg.locator('.mp[data-tab="stats"] .cards .card').count() > 0
            has_tbl = pg.locator('.mp[data-tab="stats"] .stt').count() == 1
            check(f"{tag}: Stats tab keeps the stat cards" + (" and the season table" if page["stats_pid"] and inf else ""),
                  has_cards and (has_tbl or not inf), (has_cards, has_tbl))
            pg.click('.mtab[data-tab="career"]'); pg.wait_for_timeout(150)
            ca = pg.locator('.mp[data-tab="career"] th.ca').count()
            tot = pg.evaluate("() => { const x = document.querySelector('.mp[data-tab=\"career\"] tr.ct td.ca'); return x ? +x.textContent : null; }")
            cg = pg.evaluate("() => { const x = document.querySelector('.mp[data-tab=\"career\"] tr.ct td.cg'); return x ? +x.textContent : null; }")
            if n_sql:
                check(f"{tag}: Career keeps season x club x goals and adds apps from lineups (total {n_sql})", ca == 1 and tot == n_sql and cg == len(page["goals"]), (ca, tot, cg))
            else:
                check(f"{tag}: Career without lineups: no apps column, goals total kept", ca == 0 and cg == len(page["goals"]), (ca, cg))
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

# slugs + stubs unchanged
pages = {p.stem for p in (ROOT / "players").glob("*.html")}
want = {p["slug"] for p in plan["pages"]} | set(plan["stubs"])
check("every page slug and every redirect stub exists (URLs unchanged)", want <= pages, sorted(want - pages)[:5])
stub = next(iter(plan["stubs"]), None)
if stub:
    s = (ROOT / "players" / f"{stub}.html").read_text(encoding="utf-8")
    check(f"redirect stub {stub} still points to {plan['stubs'][stub]}", "saffara-redirect" in s and f"{plan['stubs'][stub]}.html" in s)

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
