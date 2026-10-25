#!/usr/bin/env python3
"""
Batch C (18 Oct 2026): FotMob-style match rows + league Matches tab day headers. Run:
    python C:\\Users\\User\\Projects\\Football\\test_match_rows.py
Needs the site built (make_assets.py, make_site3.py, make_clubs.py, make_leagues.py). Serves the repo itself on 127.0.0.1:8774.

C1) one compact centred row [home name][home logo][time|score][away logo][away name] from the shared match_row.match_row:
    order + tight gaps (LTR and RTL, home on the start side), one line per name with an ellipsis, score centred, live pill /
    PST / time kept — on a harness page built from the REAL make_site3.match_card + STYLE, and on real pages (home, league
    Matches tab, club page; the club page keeps its club links).
    v2: fixed-width centre column (80px, club 84px) -> logos align card to card; every real label fits (countdown, PST,
    score, live «2 - 1 FT» end label on its own line); names still end with an ellipsis at 360px.
C2) league Matches tab: played + upcoming of the current season, chronological (FotMob), full-width day headers, kickoff order
    inside a day, no date line under the cards, Amman (UTC+3) at build time, re-grouped + relabelled in the visitor's time zone;
    opening the tab scrolls «Today» (or the nearest upcoming day) to the top; a window of whole days (>= 10 before, >= 15 from
    the anchor) with «Earlier matches (N)» above (no jump) and «Later matches (N)» below; live pill on an upcoming card.
"""
import functools
import http.server
import json
import re
import socketserver
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_site3 as ms  # noqa: E402
import make_leagues as ml  # noqa: E402
from i18n import T  # noqa: E402
from matchtime import matchtime_script  # noqa: E402

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8774), functools.partial(Q, directory=str(ROOT)))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:8774"
TMP = ROOT / ".wrangler" / "tmp"
TMP.mkdir(parents=True, exist_ok=True)


class R(dict):
    def keys(self):
        return list(dict.keys(self))


def M(mid, d, hg=None, ag=None, status="FT", h=(962, "نهضة بركان", "Renaissance Berkane"), a=(964, "الوداد", "Wydad AC"), lg="MAR"):
    return R({"match_id": mid, "date": d, "home_goals": hg, "away_goals": ag, "league_code": lg, "season": 2026, "status": status,
              "home_id": h[0], "home": h[1], "home_en": h[2], "home_logo": "", "away_id": a[0], "away": a[1], "away_en": a[2], "away_logo": ""})


LONG = (25058, "نادي اتحاد طنجة الرياضي لكرة القدم للمحترفين", "Ittihad Riadi Tanger Football Club Professional Section")
LOGOS = {"962": "/thumbs/962.webp", "964": "/thumbs/964.webp", "25058": "/thumbs/25058.webp"}

# ═══ C2 unit: Amman day, ordering, labels ═══
d0, k0 = ml.match_day(M(1, "2026-10-12 22:30"))
check("C2: 2026-10-12 22:30 UTC -> Amman day 13 Oct (UTC+3)", d0 == date(2026, 10, 13), d0)
check("C2: date-only match keeps its stored day", ml.match_day(M(2, "2026-10-12"))[0] == date(2026, 10, 12))
days = ml.match_days([M(1, "2026-10-12 17:00"), M(2, "2026-10-13 20:00"), M(3, "2026-10-12 14:00"), M(4, "2026-10-13 14:00")])
check("C2: chronological (oldest day first), kickoff order inside a day",
      [(d.isoformat(), [m["match_id"] for m in ms_]) for d, ms_ in days] == [("2026-10-12", [3, 1]), ("2026-10-13", [4, 2])], days)
today = date(2026, 10, 13)
for lang, want in (("ar", ("اليوم", "أمس", "غداً", "الأحد 11 أكتوبر", "الخميس 1 يناير")),
                   ("en", ("Today", "Yesterday", "Tomorrow", "Sunday, 11 October", "Thursday, 1 January"))):
    t = T[lang]
    got = (ml.day_label(date(2026, 10, 13), today, t), ml.day_label(date(2026, 10, 12), today, t), ml.day_label(date(2026, 10, 14), today, t),
           ml.day_label(date(2026, 10, 11), today, t), ml.day_label(date(2026, 1, 1), today, t))
    check(f"C2 {lang}: labels Today / Yesterday / Tomorrow use the home day-strip words, others '{want[3]}'", got == want, got)
t = T["ar"]
check("C2 ar: 'الاثنين 12 أكتوبر' format (weekday day month)", ml.day_label(date(2026, 10, 12), date(2026, 10, 20), t) == "الاثنين 12 أكتوبر")
check("C2 en: 'Monday, 12 October' format", ml.day_label(date(2026, 10, 12), date(2026, 10, 20), T["en"]) == "Monday, 12 October")
played = [M(100 + i, f"2026-10-{13 + i // 3:02d} {12 + i % 3}:00", 1, 0) for i in range(24)]        # 13-20 Oct, 8 days x 3
upc = [M(200 + i, f"2026-10-{26 + i // 3:02d} {12 + i % 3}:00" if i < 18 else f"2026-11-{1 + (i - 18) // 3:02d} 18:0{i % 3}",
         status="PST" if i == 4 else "NS") for i in range(30)]                                             # 26 Oct - 4 Nov, 10 days x 3
top, bottom = ml.matches_tab(played + upc, "en", LOGOS, today=date(2026, 10, 25))
html = top + bottom
vis_days = re.findall(r'<div class="mday" data-day="([^"]+)"', top)
check("C2: no date line under the cards in the Matches tab", 'class="date"' not in html)
check("C2: anchor = nearest upcoming day (26 Oct); visible window = 4 past days (12 >= 10) + 5 days from the anchor (15 >= 15)",
      vis_days == ["2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"], vis_days)
check("C2: «Earlier matches (12)» above the list, «Later matches (15)» below, hidden days tagged past/future",
      top.startswith('<button class="more" data-mdir="past">') and "(12)" in top.split("</button>")[0]
      and 'data-mdir="future"' in bottom and "(15)" in bottom
      and top.count('data-side="past"') == 4 and top.count('data-side="future"') == 5, (top[:120], bottom))
check("C2: days in chronological order across past and upcoming", re.findall(r'data-day="([^"]+)"', top) == sorted(re.findall(r'data-day="([^"]+)"', top)))
check("C2: upcoming fixtures render as upcoming cards (time + countdown), PST keeps its label",
      top.count('class="match soon"') == 30 and top.count('data-cd="card"') == 29 and top.count('score pst') == 1)
check("C2: every card carries its UTC kickoff (data-k) for the visitor-time-zone regroup", top.count("data-k=") == 54)
arch, arch_b = ml.matches_tab(played, "en", LOGOS, today=date(2026, 11, 30))
check("C2: finished season (archive): anchor = last day, last >= 10 matches visible (4 days), no «Later» button",
      re.findall(r'<div class="mday" data-day="([^"]+)"', arch) == ["2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20"][-5:]
      and arch_b == "" and 'data-mdir="past"' in arch, re.findall(r'<div class="mday" data-day="([^"]+)"', arch))
check("C2: empty season -> the existing empty message", "empty" in ml.matches_tab([], "en", LOGOS)[0])

# harness pages (real match_card + STYLE)
SPAN_SCAN = """(sel) => {
  const rtl = getComputedStyle(document.documentElement).direction === 'rtl', out = [];
  [...document.querySelectorAll(sel)].filter(c => c.getBoundingClientRect().width > 0).slice(0, 40).forEach((c, i) => {
    const hs = c.querySelector('.side:not(.away)'), as = c.querySelector('.side.away'), sc = c.querySelector('.score');
    const R = e => e.getBoundingClientRect(), hn = R(hs.querySelector('span')), hi = R(hs.querySelector('img')),
          an = R(as.querySelector('span')), ai = R(as.querySelector('img')), s = R(sc), cr = R(c);
    const seq = rtl ? [hn.left - hi.right, hi.left - s.right, s.left - ai.right, ai.left - an.right]
                    : [hi.left - hn.right, s.left - hi.right, ai.left - s.right, an.left - ai.right];
    const one = el => { const cs = getComputedStyle(el); return el.getBoundingClientRect().height <= parseFloat(cs.fontSize) * 1.6 && cs.whiteSpace === 'nowrap'; };
    const homeStart = rtl ? hs.getBoundingClientRect().left > s.left : hs.getBoundingClientRect().right < s.right;
    out.push({i, live: c.classList.contains('live'), gaps: seq.map(x => Math.round(x)), one: one(hs.querySelector('span')) && one(as.querySelector('span')),
              homeStart, centre: Math.round((s.left + s.right) / 2 - (cr.left + cr.right) / 2),
              inside: hn.left >= cr.left - 0.5 && an.left >= cr.left - 0.5 && hn.right <= cr.right + 0.5 && an.right <= cr.right + 0.5,
              ell: [hs, as].some(x => { const sp = x.querySelector('span'); return sp.scrollWidth > sp.clientWidth + 1 && getComputedStyle(sp).textOverflow === 'ellipsis'; }),
              score: sc.textContent.trim(), cls: sc.className, pill: !!c.querySelector('.lvpill'),
              sl: Math.round(s.left), sr: Math.round(s.right), fit: sc.scrollWidth <= sc.clientWidth + 1});
  });
  return out;
}"""


def aligned(rs):
    """fixed centre column: every non-live card's time/score box at the same x (+-1px), and every label fits inside it"""
    xs = [(r["sl"], r["sr"]) for r in rs if not r["live"]]
    return bool(xs) and max(x[0] for x in xs) - min(x[0] for x in xs) <= 1 and max(x[1] for x in xs) - min(x[1] for x in xs) <= 1 \
        and all(r["fit"] for r in rs)


def row_ok(r, live_ok=True):
    # gaps: name-logo and logo-score touch (>= -1) and stay tight (<= 12px); score centred unless a live pill takes a column
    return (all(-1 <= g <= 12 for g in r["gaps"]) and r["one"] and r["homeStart"] and r["inside"]
            and (r["live"] or abs(r["centre"]) <= 2))


def harness(lang):
    cards = [ms.match_card(M(9001, "2026-10-12 18:00", 2, 1), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9002, "2026-10-19 18:00"), lang, LOGOS, show_league=False, upcoming=True, club_ids=True),
             ms.match_card(M(9003, "2026-10-19 18:00", status="PST"), lang, LOGOS, show_league=False, upcoming=True, club_ids=True),
             ms.match_card(M(9004, "2026-10-12 18:00", 0, 0, h=LONG), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9005, "2026-10-12 18:00", 3, 3, a=LONG), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9006, "2026-10-12 18:00", 1, 0, h=LONG, a=LONG), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9007, "2026-10-12 18:00", 1, 0), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9008, SOON(30 * 60 + 50)), lang, LOGOS, show_league=False, upcoming=True, club_ids=True),
             ms.match_card(M(9009, SOON(80)), lang, LOGOS, show_league=False, upcoming=True, club_ids=True),
             ms.match_card(M(9010, "2026-10-12 18:00", 10, 10), lang, LOGOS, show_league=False, club_ids=True),
             ms.match_card(M(9011, "2026-10-19 18:00"), lang, LOGOS, show_league=False, upcoming=True, club_ids=True),
             ms.match_card(M(9012, "2026-10-19 18:00"), lang, LOGOS, show_league=False, upcoming=True, club_ids=True)]
    page = (f'<!DOCTYPE html><html lang="{lang}" dir="{ms.DIR[lang]}"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">' + ms.THEME_HEAD + ms.STYLE + '</head><body><div class="wrap">'
            '<details class="lgsec" open><summary><span class="lgname">h</span></summary><div class="lgbody">' + "".join(cards)
            + '</div></details></div>' + matchtime_script() + '</body></html>')
    (TMP / f"rows_harness_{lang}.html").write_text(page, encoding="utf-8")


# countdown wordings of matchtime.py (card): «بعد N د» / "in N min", under a minute «خلال دقيقة» / "in <1 min", at 0 «بلشت» / "Starting"
CD_RE = re.compile(r"بعد \d+ د|خلال دقيقة|بلشت|in \d+ min|in <1 min|Starting")


def SOON(secs):
    """kickoff `secs` from now, minute precision (the stored format) -> the card counts down («بعد N د» / "in N min")"""
    return (datetime.now(timezone.utc) + timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M")


def days_harness(lang):
    ms_ = [M(1, "2026-10-12 22:30", 1, 0), M(2, "2026-10-13 14:00", 2, 2), M(3, "2026-10-12 17:00", 0, 1), M(4, "2026-10-11 15:00", 1, 1)]
    html, more = ml.matches_tab(ms_, lang, LOGOS, today=date(2026, 10, 13))
    page = (f'<!DOCTYPE html><html lang="{lang}" dir="{ms.DIR[lang]}"><head><meta charset="UTF-8">' + ms.THEME_HEAD + ms.STYLE
            + ml.LOCAL_STYLE + f'</head><body><div class="wrap"><section class="panel visible" data-cat="matches">{html}{more}</section></div>'
            + ml.league_days_script(lang) + '</body></html>')
    (TMP / f"days_harness_{lang}.html").write_text(page, encoding="utf-8")


LIVE = {"body": '{"t":0,"m":{}}'}


def live(route):
    route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=LIVE["body"])


def groups(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('[data-mdays] .mday')].map(g => [g.getAttribute('data-day'), g.querySelector('.mdh').textContent,
        [...g.querySelectorAll('.match')].map(c => +c.getAttribute('data-mid'))])""")


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, pre in (("ar", ""), ("en", "/en")):
        harness(lang); days_harness(lang)
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=theme, timezone_id="Asia/Amman")
            ctx.add_init_script(f"try{{localStorage.setItem('theme','{theme}')}}catch(e){{}}")
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.route("https://saffara-live.abujaishamr.workers.dev/**", live)
            pg.route("https://static.cloudflareinsights.com/**", lambda r: r.abort())
            tag = f"{lang}/{theme}"
            # ── C1 harness ──
            pg.goto(f"{BASE}/.wrangler/tmp/rows_harness_{lang}.html"); pg.wait_for_timeout(300)
            # the live script's end labels on two cards (what live_view writes into a list card's .score)
            pg.evaluate("""([end, inter]) => {
                document.querySelector('[data-mid="9011"] .score').innerHTML = '<span class="lvfin">2 - 1</span> <span class="lvend">' + end + '</span>';
                document.querySelector('[data-mid="9012"] .score').innerHTML = '<span class="lvend">' + inter + '</span>'; }""",
                        [T[lang]["lv_end"], T[lang].get("lv_int", "متوقفة مؤقتاً")])
            rs = pg.evaluate(SPAN_SCAN, ".match")
            cd = [r["score"] for r in rs[7:9]]
            check(f"C1 {tag} harness: all 12 cards = [name][logo] score [logo][name], tight gaps, one line, home on the start side, score centred",
                  len(rs) == 12 and all(row_ok(r) for r in rs), [r for r in rs if not row_ok(r)][:3])
            check(f"C1 {tag} harness: fixed centre column -> time/score boxes aligned card to card, every label fits (countdowns {cd}, PST, 10 - 10, FT end, interrupted)",
                  aligned(rs) and all(CD_RE.fullmatch(x) for x in cd), [(r["score"], r["sl"], r["sr"], r["fit"]) for r in rs])
            check(f"C1 {tag} harness: long names end with an ellipsis (no wrap)", all(r["ell"] for r in rs[3:6]), [r["ell"] for r in rs])
            check(f"C1 {tag} harness: upcoming time, PST label and FT score kept",
                  "time" in rs[1]["cls"] and "pst" in rs[2]["cls"] and rs[2]["score"] and rs[0]["score"] == "2 - 1", [(r["cls"], r["score"]) for r in rs[:3]])
            # live: the same transformation live_view applies (class live, pill before the first .side, score span)
            pg.evaluate("""() => { const c = document.querySelector('[data-mid="9007"]'); c.classList.add('live');
                const p = document.createElement('span'); p.className = 'lvpill'; p.textContent = "67"; c.insertBefore(p, c.querySelector('.side'));
                c.querySelector('.score').innerHTML = '<span class="lvscore">1 - 0</span> <span class="lv"><span class="dot"></span>67\\'</span>'; }""")
            r = [x for x in pg.evaluate(SPAN_SCAN, ".match") if x["live"]]
            pos = pg.evaluate("""() => { const c = document.querySelector('[data-mid="9007"]'), p = c.querySelector('.lvpill').getBoundingClientRect(),
                h = c.querySelector('.side').getBoundingClientRect(), rtl = getComputedStyle(document.documentElement).direction === 'rtl';
                return rtl ? p.left >= h.right - 1 : p.right <= h.left + 1; }""")
            check(f"C1 {tag} harness: live card keeps the minute pill at the start, row order + one line intact", len(r) == 1 and r[0]["pill"] and row_ok(r[0]) and pos, r)
            pg.set_viewport_size({"width": 360, "height": 800}); pg.wait_for_timeout(200)
            rs = pg.evaluate(SPAN_SCAN, ".match")
            check(f"C1 {tag} harness 360px: rows intact, long names still end with an ellipsis, centre column aligned",
                  all(row_ok(r) for r in rs) and all(r["ell"] for r in rs[3:6]) and aligned(rs), [r for r in rs if not row_ok(r)][:2])
            pg.set_viewport_size({"width": 390, "height": 844})
            # ── C1 real pages ──
            pg.goto(f"{BASE}{pre}/index.html"); pg.wait_for_timeout(900)
            rs = pg.evaluate(SPAN_SCAN, ".daypanel.visible .match")
            check(f"C1 {tag} home: {len(rs)} visible cards in the compact centred row", rs and all(row_ok(r) for r in rs), [r for r in rs if not row_ok(r)][:3])
            check(f"C1 {tag} home: centre column aligned across the visible cards, labels fit", aligned(rs), [(r["score"], r["sl"], r["sr"], r["fit"]) for r in rs][:8])
            pg.goto(f"{BASE}{pre}/clubs/962.html"); pg.wait_for_timeout(700)
            rs = pg.evaluate(SPAN_SCAN, ".spanel.on .match:not(.hidden), .match:not(.hidden)")
            links = pg.evaluate("() => [...document.querySelectorAll('.match .side')].slice(0, 4).map(s => s.tagName + ':' + (s.getAttribute('href') || ''))")
            check(f"C1 {tag} club 962: {len(rs)} cards in the same row layout", rs and all(row_ok(r) for r in rs), [r for r in rs if not row_ok(r)][:3])
            check(f"C1 {tag} club 962: centre column aligned (84px), labels fit", aligned(rs) and all(r["sr"] - r["sl"] == 84 for r in rs),
                  [(r["score"], r["sl"], r["sr"]) for r in rs][:6])
            check(f"C1 {tag} club 962: team sides stay club links (a.side href)", links and all(x.startswith("A:") and x.endswith(".html") for x in links), links)
            # ── C2 real league page (current season: played + upcoming) ──
            pg.goto(f"{BASE}{pre}/leagues/egy.html"); pg.wait_for_timeout(700)
            pg.click('.tab[data-cat="matches"]'); pg.wait_for_timeout(400)
            gs = groups(pg)
            ks = pg.evaluate("""() => [...document.querySelectorAll('[data-mdays] .mday')].map(g => [...g.querySelectorAll('.match')].map(c => c.getAttribute('data-k') || ''))""")
            check(f"C2 {tag} league EGY: day groups chronological, each with a full-width header",
                  len(gs) > 3 and [g[0] for g in gs] == sorted(g[0] for g in gs) and all(g[1] for g in gs), gs[:3])
            hw = pg.evaluate("() => { const h = document.querySelector('.mday:not(.hidden) .mdh').getBoundingClientRect(), b = document.querySelector('[data-mdays]').getBoundingClientRect(); return [Math.round(h.width), Math.round(b.width)]; }")
            check(f"C2 {tag} league EGY: header spans the full list width", hw[0] == hw[1], hw)
            check(f"C2 {tag} league EGY: kickoff order inside every day", all(k == sorted(k) for k in ks), ks[:3])
            check(f"C2 {tag} league EGY: no date line under any card in the Matches tab", pg.locator('[data-cat="matches"] .match .date').count() == 0)
            up = pg.evaluate("""() => [...document.querySelectorAll('[data-cat="matches"] .match.soon')].filter(c => c.getBoundingClientRect().height > 0).map(c => c.querySelector('.score').className)""")
            check(f"C2 {tag} league EGY: upcoming fixtures of the current season listed ({len(up)} visible, time/countdown cells)", len(up) >= 10 and all("time" in x or "pst" in x for x in up), up[:5])
            anc = pg.evaluate("""() => { const a = window.FBLeagueDays && FBLeagueDays.anchor(); if (!a) return null; const n = new Date(), p = x => (x < 10 ? '0' : '') + x,
                today = n.getFullYear() + '-' + p(n.getMonth() + 1) + '-' + p(n.getDate()), vis = [...document.querySelectorAll('.mday:not(.hidden)')];
                return {day: a.getAttribute('data-day'), top: Math.round(a.getBoundingClientRect().top), today,
                        first_ge: (vis.find(g => g.getAttribute('data-day') >= today) || vis[vis.length - 1]).getAttribute('data-day'),
                        above: vis.indexOf(a), scrollY: Math.round(window.scrollY)}; }""")
            check(f"C2 {tag} league EGY: opening the tab scrolls «Today»/the nearest upcoming day to the top, past days above it",
                  anc and anc["day"] == anc["first_ge"] and 0 <= anc["top"] <= 16 and anc["above"] > 0 and anc["scrollY"] > 0, anc)
            rs = pg.evaluate(SPAN_SCAN, '[data-cat="matches"] .mday:not(.hidden) .match')
            check(f"C2 {tag} league EGY: cards in the compact row, centre column aligned across played and upcoming",
                  rs and all(row_ok(r) for r in rs) and aligned(rs), [r for r in rs if not row_ok(r)][:2] or [(r["score"], r["sl"], r["sr"]) for r in rs][:6])
            total = pg.locator('[data-cat="matches"] .match').count()
            vis = lambda: pg.evaluate("() => [...document.querySelectorAll('[data-cat=\"matches\"] .match')].filter(c => c.getBoundingClientRect().height > 0).length")
            v0 = vis()
            # the user scrolls up to «Earlier» and taps it: measure the anchor at that moment, tap in-page (no Playwright auto-scroll)
            pg.evaluate("() => document.querySelector('[data-cat=\"matches\"] .more[data-mdir=\"past\"]').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
            y0 = pg.evaluate("() => Math.round(FBLeagueDays.anchor().getBoundingClientRect().top)")
            pg.evaluate("() => document.querySelector('[data-cat=\"matches\"] .more[data-mdir=\"past\"]').click()"); pg.wait_for_timeout(300)
            y1 = pg.evaluate("() => Math.round(FBLeagueDays.anchor().getBoundingClientRect().top)")
            v1 = vis()
            pg.click('[data-cat="matches"] .more[data-mdir="future"]'); pg.wait_for_timeout(300)
            v2 = vis()
            check(f"C2 {tag} league EGY: «Earlier» reveals the past days without moving the anchor ({y0} -> {y1}px), «Later» the rest ({v0} -> {v1} -> {v2} of {total})",
                  10 <= v0 < v1 < v2 == total and abs(y1 - y0) <= 2, [v0, v1, v2, total, y0, y1])
            check(f"C1/C2 {tag}: no page errors", not errs, errs)
            ctx.close()
        # ── C2 live: an upcoming card in the league list goes live through the existing live script (pill + score) ──
        ctx = b.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Amman")
        pg = ctx.new_page()
        pg.route("https://saffara-live.abujaishamr.workers.dev/**", live)
        pg.goto(f"{BASE}{pre}/leagues/egy.html"); pg.wait_for_timeout(500)
        mid = pg.evaluate("() => document.querySelector('[data-cat=\"matches\"] .mday:not(.hidden) .match.soon').getAttribute('data-mid')")
        LIVE["body"] = json.dumps({"t": 0, "m": {mid: {"h": 1, "a": 0, "s": "2H", "e": 67}}})
        pg.reload(); pg.wait_for_timeout(1200)
        pg.click('.tab[data-cat="matches"]'); pg.wait_for_timeout(300)
        st = pg.evaluate(f"""() => {{ const c = document.querySelector('[data-mid="{mid}"]'); return [c.classList.contains('live'), (c.querySelector('.lvpill') || {{}}).textContent || '',
            c.querySelector('.score').textContent.trim()]; }}""")
        LIVE["body"] = '{"t":0,"m":{}}'
        check(f"C2 {lang} league EGY: upcoming card {mid} goes live via live_view: pill 67 (circle, no apostrophe — UI batch 3) + score 1 - 0", st[0] and st[1] == "67" and st[2].startswith("1 - 0"), st)
        ctx.close()
        # ── C2 visitor time zone: regroup + relabel (fixed clock 13 Oct 2026 12:00 UTC) ──
        for tz, want in (("Asia/Amman", [["2026-10-11", 2, [4]], ["2026-10-12", 1, [3]], ["2026-10-13", 0, [1, 2]]]),
                         ("Europe/London", [["2026-10-11", 2, [4]], ["2026-10-12", 1, [3, 1]], ["2026-10-13", 0, [2]]])):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, timezone_id=tz)
            pg = ctx.new_page()
            pg.clock.set_fixed_time("2026-10-13T12:00:00Z")
            pg.goto(f"{BASE}/.wrangler/tmp/days_harness_{lang}.html"); pg.wait_for_timeout(300)
            gs = groups(pg)
            t = T[lang]
            labels = [t["d_today"], t["d_yesterday"], ml.day_label(date(2026, 10, 11), date(2026, 10, 13), t)]
            exp = [[d, labels[i], ids] for d, i, ids in want]
            check(f"C2 {lang} {tz}: match 1 (12 Oct 22:30 UTC) lands on the visitor's local day, kickoff order kept, labels relative to the visitor's today",
                  gs == exp, {"got": gs, "want": exp})
            a = pg.evaluate("() => FBLeagueDays.anchor().getAttribute('data-day')")
            check(f"C2 {lang} {tz}: anchor = the visitor's «Today» (13 Oct)", a == "2026-10-13", a)
            ctx.close()
    b.close()

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
