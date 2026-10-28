#!/usr/bin/env python3
"""
«No matches on this day» under a filled Following section (Amr, 26 Oct 2026 night) — Playwright, ar + en, 390px. Run:
    python C:\\Users\\User\\Projects\\Football\\test_noday_follow.py [screenshot_dir]
Self-contained: a page with the real DAY_SCRIPT + FOLLOW_SECTION_SCRIPT (make_site3) and a stub FBPrefs; no site build needed.

Case of 26/10: today has no match in any league (static `.noday`), yesterday had two starred MAR matches. The empty card shows ONLY
when the day has zero matches in every section (Following included).
28 Oct 2026 (Amr: Today 28/10 showed yesterday's Abha 0-1 Al-Faisaly and US Biskra 0-1 MC Alger under Following): the FT+1-day
carry-over is gone — Following is a copy of the panel's own cards after DAY_SCRIPT's regroup, so it uses exactly the league sections'
day. Case 4 runs the real regroup in Asia/Amman: a match at 22:30 Amman yesterday (19:30Z) and one at 23:50 Amman yesterday that ends
after midnight stay under YESTERDAY; one at 00:30 Amman today (21:30Z yesterday in UTC — built into yesterday's panel, as the server
buckets by UTC) moves to TODAY — in its league section and in Following alike.
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


def card(mid, h, a, utc=None):
    t = f'<span class="time" data-utc="{utc}"></span>' if utc else ""
    return f'<a class="match" data-mid="{mid}" data-h="{h}" data-a="{a}" href="#">{t}{h} - {a}</a>'


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
        check(f"{lang}: today: yesterday's starred matches are NOT carried over (no FT+1 day) -> empty card, no Following",
              s["follow"] == 0 and s["noday"] == 1 and s["all"] == 0, s)
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
        # 4) late-night matches with real times, Amman timezone, real DAY_SCRIPT regroup: Following day == league section day
        ctx = br.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Amman")
        pg = ctx.new_page()
        y = yest.isoformat()
        late = [(7001, 9101, 9102, f"{y}T19:30:00Z"),   # 22:30 Amman yesterday
                (7002, 9103, 9104, f"{y}T20:50:00Z"),   # 23:50 Amman yesterday, finishes after midnight Amman
                (7003, 9105, 9106, f"{y}T21:30:00Z")]   # 00:30 Amman TODAY (UTC date still yesterday)
        sec4 = (f'<details class="lgsec" data-sec="SAU" open><summary><span class="lgname">SAU</span><span class="lgnum">3</span></summary>'
                f'<div class="lgbody">{"".join(card(*x) for x in late)}</div></details>')
        html = page(lang, [7001, 7002, 7003], [9101, 9103, 9105]).replace(
            f'<section class="daypanel" id="d{y}">', f'<section class="daypanel" id="d{y}">{sec4}', 1)
        f = tmp / f"late_{lang}.html"
        f.write_text(html.replace('"MAR"]', '"SAU","MAR"]'), encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_function("document.querySelector('.followsec')")
        ids = lambda day, sel: pg.evaluate("(a)=>[...document.querySelectorAll('#'+a[0]+' '+a[1])].map(e=>+e.dataset.mid).sort()",
                                           ["d" + day.isoformat(), sel])
        fy, ft = ids(yest, ".followsec .match"), ids(today, ".followsec .match")
        ly, lt = ids(yest, ".lgsec[data-sec=SAU] .match"), ids(today, ".lgsec[data-sec=SAU] .match")
        check(f"{lang} 4: 22:30 and 23:50 Amman yesterday stay under yesterday (league section and Following), never under today",
              7001 in ly and 7002 in ly and 7001 in fy and 7002 in fy and 7001 not in ft and 7002 not in ft, [ly, fy, lt, ft])
        check(f"{lang} 4: 00:30 Amman today (21:30Z yesterday) is under today in both — Following day == league section day",
              lt == [7003] and ft == [7003] and 7003 not in fy and 7003 not in ly, [ly, fy, lt, ft])
        pg.screenshot(path=str(SHOTS / f"late_{lang}.png"), full_page=True)
        ctx.close()
    br.close()

print(f"\n{'OK' if not fails else f'{fails} FAILED'}  (screenshots: {SHOTS})")
sys.exit(1 if fails else 0)
