#!/usr/bin/env python3
"""
Table zone bars + legend (zones.py, 27 Oct 2026, Amr #6) — mapping, fallback, and Playwright (ar + en, light + dark, 390px). Run:
    python C:\\Users\\User\\Projects\\Football\\test_zones.py [screenshot_dir]
Needs make_assets.py + make_leagues.py + make_live_tables.py + make_matches.py (SAU) built. Serves the repo on 127.0.0.1:8783 and mocks
the live worker. football.db is only read (the fallback case uses an in-memory copy).

  1) every provider description stored in api_standings (all leagues, all seasons) maps to a zone — none unknown
  2) zone_list for the 10 current tables matches the provider ranks (minus hidden categories: EGY Relegation group);
     legend = only categories present, fixed order and colours
  3) no descriptions (in-memory DB copy with description NULL): no bars, no legend, the old top/bottom rank colouring stays
  4) pages: league table + match Table tab — a bar on every zoned row (colour = category), at the start side (right in ar, left in
     en), none on unzoned rows; legend under the table with one entry per category present
  5) live table: a live result that reorders the table keeps the zones on the POSITIONS (not on the teams)
"""
import functools
import http.server
import json
import re
import socketserver
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import zones as zn  # noqa: E402
import make_matches as mm  # noqa: E402
from config import DB_FILE, LEAGUES  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "zones"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

# 1) mapping
descs = [r[0] for r in con.execute("SELECT DISTINCT description FROM api_standings WHERE description IS NOT NULL AND description != ''")]
unknown = [d for d in descs if zn.classify(d) is None]
check(f"1: all {len(descs)} stored provider descriptions map to a zone", not unknown, unknown)
check("1: fixed examples", [zn.classify(d)[0] for d in (
    "Promotion - AFC Champions League (League phase)", "Promotion - CAF Champions League (Qualification)",
    "Promotion - CAF Confederation Cup (Qualification)", "Promotion - AFC Champions League 2", "Promotion - Gulf Club Champions League",
    "Botola Pro (Relegation)", "Relegation - Ligue 2", "Relegation", "Promotion - Premier League (Championship Group)")]
      == ["cl", "clq", "cl2", "cl2", "reg", "rpo", "rel", "rel", "grp1"])
check("1: Arabic label uses the competition name", zn.classify("Promotion - CAF Champions League (Qualification)")[1] == "دوري أبطال أفريقيا – التصفيات")
check("1: unknown text -> no zone (not guessed)", zn.classify("Promotion - Something Else") is None and zn.classify("") is None)

# 2) current tables
SEASON = {r[0]: r[1] for r in con.execute("SELECT league_code, MAX(season) FROM api_standings GROUP BY 1")}
for code in LEAGUES:
    if (code, SEASON[code]) in zn.ZONE_OVERRIDE:   # (31 Oct 2026, batch 6 #5) hand-set zones replace the provider's
        continue
    zl = zn.zone_list(con, code, SEASON[code])
    prov = {r[0]: r[1] for r in con.execute("SELECT rank, description FROM api_standings WHERE league_code=? AND season=? AND description != ''",
                                            (code, SEASON[code]))}
    shown = {k for k, d in prov.items() if (zn.classify(d) or ("",))[0] not in zn.HIDDEN}
    check(f"2 {code}: one zone per described rank, hidden categories dropped ({len(shown)})", set(zl) == shown and len(zl) > 0, [sorted(zl), sorted(shown)])
egy = zn.zone_list(con, "EGY", SEASON["EGY"])
check("2 EGY: only Championship group 1-6 (Relegation group hidden: no bar, no legend)",
      {k: v[0] for k, v in egy.items()} == {i: "grp1" for i in range(1, 7)} and re.findall(r'class="zd z-(\w+)"', zn.legend(egy, "en")) == ["grp1"], egy)
leg = zn.legend(zn.zone_list(con, "MAR", SEASON["MAR"]), "en")
check("2 MAR legend: clq, cl2, rpo, rel in order, nothing else", re.findall(r'class="zd z-(\w+)"', leg) == ["clq", "cl2", "rpo", "rel"], leg)
sau = {k: v[0] for k, v in zn.zone_list(con, "SAU", 2026).items()}
check("2 SAU 2026 override: 1-3 cl, 4-5 clq, 6 cl2, 7-8 reg, 16-18 rel",
      sau == {1: "cl", 2: "cl", 3: "cl", 4: "clq", 5: "clq", 6: "cl2", 7: "reg", 8: "reg", 16: "rel", 17: "rel", 18: "rel"}, sau)
check("2 data-zones: one slot per row", zn.data_attr({1: ("cl", "", ""), 3: ("rel", "", "")}, 4) == ' data-zones="cl,,rel,"')

# 3) fallback: no descriptions
mem = sqlite3.connect(":memory:")
con.backup(mem)
mem.row_factory = sqlite3.Row
# QAT (not SAU: SAU 2026 has hand-set zones that do not depend on descriptions)
mem.execute("UPDATE api_standings SET description = NULL WHERE league_code = 'QAT'")
m = mem.execute("SELECT * FROM matches WHERE league_code='QAT' AND season=? AND home_goals IS NOT NULL ORDER BY date DESC LIMIT 1",
                (SEASON["QAT"],)).fetchone()
mm.LATEST_SEASON = SEASON["QAT"]
mm._TABLES.clear()
html = mm.build_table_panel(mem, m, mm.load_teams(), "en")
check("3: no descriptions -> no zone classes, no data-zones, no legend; old top/bottom kept",
      "z-" not in html and "data-zones" not in html and "zleg" not in html and 'class="top"' in html and "bottom" in html)
mm._TABLES.clear()
html = mm.build_table_panel(con, m, mm.load_teams(), "en")
check("3: with descriptions -> zone classes + legend, no top/bottom", "z-cl" in html and "zleg" in html and 'class="top"' not in html)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8783), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8783"
LIVE = {"body": '{"t":0,"m":{}}'}

ROWS_JS = """(sel)=>{const t=document.querySelector(sel); if(!t) return null;
  const rows=[...t.querySelectorAll('tr[data-t]')].map(tr=>{const c=tr.children[0], b=getComputedStyle(c,'::before');
    return {t:tr.dataset.t, z:(tr.className.match(/z-(\\w+)/)||[])[1]||'', bar:b.content!=='none'&&b.content!=='normal'?b.backgroundColor:'',
            left:b.left, right:b.right};});
  const leg=t.nextElementSibling&&t.nextElementSibling.classList.contains('zleg')?[...t.nextElementSibling.querySelectorAll('.zd')].map(d=>d.className.split('z-')[1]):[];
  return {zones:(t.getAttribute('data-zones')||'').split(','), rows, leg};}"""


def hexrgb(h):
    h = h.lstrip("#")
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def verify(tag, r, lang):
    ok_bar = all((x["bar"] == hexrgb(zn.COLORS[x["z"]])) if x["z"] else (x["bar"] == "") for x in r["rows"])
    side = all((x["right"] == "0px") if lang == "ar" else (x["left"] == "0px") for x in r["rows"] if x["z"])
    pos_ok = all(x["z"] == (r["zones"][i] if i < len(r["zones"]) else "") for i, x in enumerate(r["rows"]))
    cats = [c for c in zn.ORDER if c in {x["z"] for x in r["rows"] if x["z"]}]
    check(f"{tag}: bar on zoned rows only, colour = category", ok_bar, [x for x in r["rows"] if (x["bar"] != "") != bool(x["z"])][:3])
    check(f"{tag}: bar at the start side ({'right' if lang == 'ar' else 'left'})", side, r["rows"][:2])
    check(f"{tag}: zones follow positions (data-zones)", pos_ok)
    check(f"{tag}: legend = categories present, in order", r["leg"] == cats, [r["leg"], cats])


with sync_playwright() as p:
    br = p.chromium.launch()
    for theme in ("dark", "light"):
        for lang in ("ar", "en"):
            pre = "" if lang == "ar" else "/en"
            ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');%s}catch(e){}" % ("localStorage.setItem('theme','light');" if theme == "light" else ""))
            ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*",
                                                                                                         "Content-Type": "application/json"}, body=LIVE["body"]))
            pg = ctx.new_page()
            for code in ("EGY", "SAU", "MAR", "JOR"):
                pg.goto(f"{BASE}{pre}/leagues/{code.lower()}.html", wait_until="load"); pg.wait_for_timeout(300)
                r = pg.evaluate(ROWS_JS, ".panel[data-cat='standings'] table")
                if theme == "dark":
                    verify(f"4 {lang} league {code}", r, lang)
                pg.screenshot(path=str(SHOTS / f"league_{code}_{lang}_{theme}.png"))
                tbl = pg.locator(".panel[data-cat='standings'] table")
                tbl.evaluate("t=>{const l=t.nextElementSibling; (l||t).scrollIntoView({block:'center'});}")
                pg.wait_for_timeout(150)
                pg.screenshot(path=str(SHOTS / f"league_{code}_{lang}_{theme}_legend.png"))
            # match Table tab (SAU, finished)
            pg.goto(f"{BASE}{pre}/matches/{m['match_id']}.html", wait_until="load")
            pg.locator(".mtabs button", has_text="الترتيب" if lang == "ar" else "Table").first.click(); pg.wait_for_timeout(300)
            r = pg.evaluate(ROWS_JS, "table.lgt")
            if theme == "dark":
                verify(f"4 {lang} match {m['match_id']} Table tab", r, lang)
            pg.screenshot(path=str(SHOTS / f"match_table_SAU_{lang}_{theme}.png"))
            ctx.close()

    # 5) live re-sort: the team at the last relegation place wins 9-0 live -> climbs; zones stay on the positions
    snap = json.loads((ROOT / "assets" / f"table_SAU_{SEASON['SAU']}.json").read_text(encoding="utf-8"))
    order = [r["team_id"] for r in snap["rows"]]
    low, other = order[-1], order[0]
    LIVE["body"] = json.dumps({"t": 1, "m": {"99999901": {"h": 9, "a": 0, "e": 60, "s": "2H", "th": low, "ta": other,
                                                         "lg": LEAGUES["SAU"]["id"]}}})
    for lang in ("ar", "en"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
        ctx.add_init_script("try{localStorage.setItem('fbSetupDone','1');}catch(e){}")
        ctx.route("https://saffara-live.abujaishamr.workers.dev/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*",
                                                                                                     "Content-Type": "application/json"}, body=LIVE["body"]))
        pg = ctx.new_page()
        pg.goto(f"{BASE}{'' if lang == 'ar' else '/en'}/leagues/sau.html", wait_until="load")
        try:
            pg.wait_for_selector(".ltlive", timeout=8000)
        except Exception:
            pass
        r = pg.evaluate(ROWS_JS, ".panel[data-cat='standings'] table")
        moved = [x["t"] for x in r["rows"]].index(str(low)) if r else -1
        check(f"5 {lang}: live result reorders the table (last place {low} climbs to #{moved + 1})", 0 <= moved < len(order) - 1, moved)
        check(f"5 {lang}: zones stay on positions after the live re-sort", all(x["z"] == (r["zones"][i] or "") for i, x in enumerate(r["rows"])),
              [(i + 1, x["t"], x["z"]) for i, x in enumerate(r["rows"])][-4:])
        check(f"5 {lang}: the climbing team lost its relegation bar", r["rows"][moved]["z"] != "rel" or r["zones"][moved] == "rel", r["rows"][moved])
        pg.locator(".panel[data-cat='standings'] table tr[data-t]").last.scroll_into_view_if_needed()
        pg.screenshot(path=str(SHOTS / f"live_resort_SAU_{lang}.png"))
        ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
