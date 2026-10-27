#!/usr/bin/env python3
"""
«No matches on this day» under a filled Following section (Amr, 26 Oct 2026 night) — Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_noday_follow.py [screenshot_dir]
Self-contained: a page with the real DAY_SCRIPT + FOLLOW_SECTION_SCRIPT (make_site3) and a stub FBPrefs; no site build needed.

Case of 26/10: today has no match in any league (static `.noday`), yesterday had two starred MAR matches (FT+1 day rule copies them
into today's Following section). The empty card must show ONLY when the day has zero matches in every section (Following included).
"""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_site3 as ms  # noqa: E402
from i18n import T  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "football_test_shots" / "noday_follow"
SHOTS.mkdir(parents=True, exist_ok=True)
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


def card(mid, h, a):
    return f'<a class="match" data-mid="{mid}" data-h="{h}" data-a="{a}" href="#">{h} - {a}</a>'


def page(lang, stars, clubs):
    t = T[lang]
    today = date.today()
    yest, tom = today - timedelta(days=1), today + timedelta(days=1)
    noday = f'<div class="noday">{t["d_none"]}</div>'
    sec = (f'<details class="lgsec" data-sec="MAR" open><summary><span class="lgname">MAR</span><span class="lgnum">2</span></summary>'
           f'<div class="lgbody">{card(1646855, 9001, 9002)}{card(1646856, 9003, 9004)}</div></details>')
    tabs = "".join(f'<button class="daytab" data-day="{d.isoformat()}"><span class="dn"></span></button>' for d in (yest, today, tom))
    panels = (f'<section class="daypanel" id="d{yest.isoformat()}">{sec}</section>'
              f'<section class="daypanel visible" id="d{today.isoformat()}">{noday}</section>'
              f'<section class="daypanel" id="d{tom.isoformat()}">{noday}</section>')
    prefs = ("<script>window.FBPrefs={getClubs:function(){return %s;},getPlayers:function(){return [];},"
             "getMatches:function(){return %s;}};</script>" % (json.dumps(clubs), json.dumps(stars)))
    return (f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'
            f'<div class="daynav"><div class="daytabs" id="daytabs">{tabs}</div></div>{panels}{prefs}'
            f'{ms.day_script(t, ["MAR"])}{ms.follow_section_script(t, 0)}</body></html>')


def state(pg, day):
    return pg.evaluate("""(id)=>{ const p=document.getElementById(id);
        return {noday: p.querySelectorAll('.noday').length, follow: p.querySelectorAll('.followsec .match').length,
                all: p.querySelectorAll('.match').length}; }""", "d" + day.isoformat())


today = date.today()
yest, tom = today - timedelta(days=1), today + timedelta(days=1)
tmp = Path(tempfile.mkdtemp(prefix="noday_"))
with sync_playwright() as p:
    br = p.chromium.launch()
    for lang in ("ar", "en"):
        pg = br.new_page(viewport={"width": 390, "height": 844})
        # 1) the 26/10 case: two starred matches from yesterday, today empty
        f = tmp / f"stars_{lang}.html"
        f.write_text(page(lang, [1646855, 1646856], []), encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_function("document.querySelector('.followsec')")
        s = state(pg, today)
        check(f"{lang}: today = 2 followed matches (yesterday's starred, FT+1 day) and NO empty card", s["follow"] == 2 and s["noday"] == 0, s)
        s = state(pg, tom)
        check(f"{lang}: tomorrow (nothing anywhere) keeps the empty card", s["noday"] == 1 and s["all"] == 0, s)
        s = state(pg, yest)
        check(f"{lang}: yesterday: league section + Following, no empty card", s["noday"] == 0 and s["follow"] == 2, s)
        pg.screenshot(path=str(SHOTS / f"stars_{lang}.png"), full_page=True)
        # 2) nothing followed: today stays empty with exactly one empty card
        f = tmp / f"none_{lang}.html"
        f.write_text(page(lang, [], []), encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_load_state("load")
        s = state(pg, today)
        check(f"{lang}: no follows -> today shows the empty card once, no Following section", s["noday"] == 1 and s["follow"] == 0, s)
        # 3) followed club whose match was yesterday (not starred): no FT+1 carry-over -> today still empty
        f = tmp / f"club_{lang}.html"
        f.write_text(page(lang, [], [9001]), encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_function("document.querySelector('.followsec')")
        s = state(pg, today)
        check(f"{lang}: followed club played yesterday -> today keeps the empty card", s["noday"] == 1 and s["follow"] == 0, s)
        pg.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
