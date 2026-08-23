#!/usr/bin/env python3
"""
توليد صفحة لكل مباراة — بلغتين
==================================
بيولّد نسختين لكل مباراة:
    matches/1538111.html       → العربي (RTL)
    en/matches/1538111.html    → الإنجليزي (LTR)

كل صفحة فيها:
  - الناديان بشعاريهما والنتيجة (روابط لصفحتَي النادي)
  - التاريخ والدوري والموسم
  - قائمة أحداث موحدة مرتبة بالدقيقة (أهداف + بطاقات + تبديلات)
  - خياران: كل الأحداث / الأحداث المهمة
  - ⭐ شارة "نتيجة مصححة" مع السبب والمصدر

⚠️ **لا تُعرض أي إشارة إلى التصحيح.** `match_corrections.csv`
   ملف عمل يُطبَّق على الديتابيس بعد كل سحب، والصفحة تعرض
   النتيجة الصحيحة وحدها.

⚠️ **الأهداف الملغاة** تُقرأ من `cancelled_goals` (ينقلها إليه
   `fix_goals.py` بدل حذفها) وتظهر بأيقونة 🚫 ووسم "هدف ملغى".
   أكثرها بلا اسم لاعب — المزوّد لا يسمّي الملغى — فيظهر السطر
   بالدقيقة والفريق فقط.

⚠️ **أسماء البطاقات والتبديلات** كانت تُعرض بالإنجليزية دائماً
   لأن استعلام `events` لم يكن يجلب `player_ar` أصلاً (بعكس
   قسم الأهداف). صُحِّح 21 أغسطس. واللاعب الداخل بالتبديل
   (`assist_en`) بلا عمود عربي في الجدول، فيُترجَم عبر
   `name_map()` — جدول بحث من كل الجداول المترجَمة.

صفر طلبات API.

التشغيل:
    python make_matches.py
    python make_matches.py JOR      <- دوري محدد فقط
"""

import sqlite3
import csv
import os
import sys
from config import DB_FILE, TEAMS_FILE
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from search_view import (SEARCH_CSS, search_box, search_script,
                         search_overlay)
from navbar import (NAV_CSS, navbar, settings_overlay,
                    nav_script)
from lineup_view import LINEUP_CSS, build_lineups
from theme import (VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON,
                   BACK_SCRIPT, back_button, head_meta)

BASE = DB_FILE.parent
CORRECTIONS_FILE = BASE / "match_corrections.csv"

# ⚠️ **جدول `events` يحمل `assist_en` بلا `assist_ar` مقابل.**
#    العمود يخصّ التبديلات حصراً (اللاعب الداخل) — 7,408 سجلاً،
#    كلها type='subst'، ولا هدف واحد. الاسم مضلِّل ومصدره المزوّد.
#    بدل تعديل بنية الجدول، نبني جدول بحث من كل الجداول التي
#    تحمل ترجمة: يغطي ~495 من 1,049 اسماً فوراً (درس 66).
_NAME_MAP = None


def name_map(conn):
    """player_en -> player_ar من كل جدول يحمل ترجمة. يُبنى مرة واحدة."""
    global _NAME_MAP
    if _NAME_MAP is not None:
        return _NAME_MAP
    m = {}
    for tbl in ("goals", "lineup_players", "player_stats", "events"):
        try:
            rows = conn.execute(f"""
                SELECT DISTINCT player_en, player_ar FROM {tbl}
                WHERE player_en IS NOT NULL AND player_en != ''
                  AND player_ar IS NOT NULL AND player_ar != ''
            """).fetchall()
        except sqlite3.OperationalError:
            continue
        for en, ar in rows:
            m.setdefault(en, ar)
    _NAME_MAP = m
    return m

ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


STYLE = """
<style>""" + VARS + """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.6; }
  .wrap { max-width:760px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:14px; }
  .back { display:inline-block; color:var(--accent); text-decoration:none;
          font-size:14px; }
  .back:hover { text-decoration:underline; }
  .lang { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:var(--card2); color:var(--text); }
  .meta-top { text-align:center; color:var(--muted); font-size:13px;
              margin-bottom:12px; }
  .head { background:var(--card); border-radius:12px; padding:24px 16px;
          display:grid; grid-template-columns:1fr auto 1fr;
          align-items:center; gap:12px; }
  .team { display:flex; flex-direction:column; align-items:center;
          gap:10px; min-width:0; text-decoration:none; color:var(--text); }
  .team img { width:60px; height:60px; object-fit:contain; }
  .team span { font-size:15px; text-align:center; }
  .team:hover span { color:var(--accent); }
  .big { font-size:34px; font-weight:700; letter-spacing:2px;
         white-space:nowrap; }
  .big.soon { font-size:15px; font-weight:600; letter-spacing:0;
              color:var(--accent); white-space:normal; text-align:center; }
  h2 { font-size:16px; margin:26px 0 10px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  .goals { background:var(--card); border-radius:10px; padding:6px; }
  .min { color:var(--accent); font-weight:700; min-width:42px; }
  .who { flex:1; min-width:0; overflow:hidden;
         text-overflow:ellipsis; white-space:nowrap; }
  .for { color:var(--muted); font-size:12px; }
  .kind { color:var(--muted); font-size:11px; }
  .who.cancelled { text-decoration:line-through; opacity:.6; }
  .ev { display:flex; align-items:center; gap:12px; padding:10px 12px;
        border-bottom:1px solid var(--line); font-size:14px; }
  .ev:last-child { border-bottom:none; }
  .ic { min-width:26px; font-size:13px; }
  .out { color:var(--red); font-size:12px; }
  .in { color:var(--green); font-size:12px; }
  .vtabs { display:flex; gap:8px; margin:26px 0 10px; }
  .vtab { background:var(--card); color:var(--muted); border:1px solid var(--line);
          padding:8px 16px; border-radius:8px; cursor:pointer;
          font-family:inherit; font-size:14px; }
  .vtab:hover { background:var(--card2); color:var(--text); }
  .vtab.on { background:var(--accent); color:var(--bg); border-color:var(--accent); }
  .minor.off { display:none; }
  .st { display:grid; grid-template-columns:52px 1fr 52px;
        align-items:center; gap:10px; padding:9px 12px;
        border-bottom:1px solid var(--line); font-size:13px; }
  .st:last-child { border-bottom:none; }
  .st .v { font-weight:700; }
  .st .v.a { text-align:start; }
  .st .v.b { text-align:end; }
  .st .mid { text-align:center; }
  .st .lbl { color:var(--muted); font-size:11px; display:block; }
  .bar { display:flex; height:5px; border-radius:3px;
         overflow:hidden; background:var(--line); margin-top:3px; }
  .bar i { display:block; height:100%; }
  .bar .x { background:var(--accent); }
  .bar .y { background:var(--muted); }
  .empty { background:var(--card); border-radius:10px; padding:20px;
           text-align:center; color:var(--muted); font-size:13px; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }
""" + LINEUP_CSS + SEARCH_CSS + NAV_CSS + """
</style>"""

CARD_ICON = {
    "Yellow Card": "🟨",
    "Red Card": "🟥",
    "Second Yellow card": "🟨🟥",
}


def clean(t):
    return (t or "").strip()


def t_cancelled(lang):
    """وسم الهدف الملغى — نص محلي هنا بدل إضافة مفتاح لـi18n"""
    return "هدف ملغى" if lang == "ar" else "Disallowed goal"


def goal_kind(detail, lang):
    """نوع الهدف مترجَم"""
    t = T[lang]
    return {
        "Normal Goal": "",
        "Penalty": t["penalty"],
        "Own Goal": t["own_goal"],
    }.get(detail, clean(detail))


def load_teams():
    teams = {}
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "short": clean(r.get("short_name_ar")),
                "name_en": (clean(r.get("name_en_official"))
                            or clean(r.get("name_en"))),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


def tname(t, lang):
    """اسم النادي حسب اللغة"""
    if lang == "ar":
        return t["short"] or t["name_en"]
    return t["name_en"] or t["short"]


def logo_url(t, lang):
    """
    matches/x.html      → ../logos/
    en/matches/x.html   → ../../logos/
    """
    up = "../" if lang == "ar" else "../../"
    if t["logo_local"]:
        return up + t["logo_local"]
    return t["logo"] or ""


def load_corrections():
    """
    معرّفات المباريات المصحّحة — للإحصاء في نهاية التشغيل فقط.

    ⚠️ **لا يُعرض منها شيء على الموقع.** كانت تُقرأ لعرض شارة
       "نتيجة مصححة يدوياً" مع سببها ومصدرها، وأُلغيت في
       23 أغسطس: الزائر يريد النتيجة الصحيحة لا سيرة تصحيحها.
    """
    fixes = {}
    if not CORRECTIONS_FILE.exists():
        return fixes
    with open(CORRECTIONS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            mid = clean(r.get("match_id"))
            if mid:
                fixes[int(mid)] = True
    return fixes


def build_items(conn, mid, lang):
    """كل أحداث المباراة بقائمة واحدة مرتبة بالدقيقة"""
    items = []

    for g in conn.execute("""
        SELECT team_id, minute, player_en, player_ar, detail
        FROM goals WHERE match_id = ? ORDER BY minute
    """, (mid,)):
        who = (clean(g["player_ar"]) if lang == "ar" else "")
        who = who or clean(g["player_en"]) or "—"
        items.append({
            "min": g["minute"] if g["minute"] is not None else 999,
            "team": g["team_id"], "icon": "⚽", "major": True,
            "body": f'<span class="who">{who}</span>',
            "kind": goal_kind(g["detail"], lang),
        })

    # ⚠️ الأهداف الملغاة — منقولة إلى cancelled_goals لا محذوفة
    #    (fix_goals.py، 21 أغسطس). الجدول قد لا يكون موجوداً في
    #    نسخة أقدم من الديتابيس، فالفشل يُتجاهَل بصمت.
    #    ⚠️ أغلبها بلا اسم لاعب — المزوّد لا يسمّي الملغى عادةً،
    #    فيظهر السطر بالدقيقة والفريق فقط، وهذا مقصود.
    try:
        for c in conn.execute("""
            SELECT team_id, minute, player_en, player_ar
            FROM cancelled_goals
            WHERE match_id = ? AND reason = 'zero_zero_match'
            ORDER BY minute
        """, (mid,)):
            nm = (clean(c["player_ar"]) if lang == "ar" else "")
            nm = nm or clean(c["player_en"])
            items.append({
                "min": c["minute"] if c["minute"] is not None else 999,
                "team": c["team_id"], "icon": "🚫", "major": False,
                "body": (f'<span class="who cancelled">{nm}</span>'
                         if nm else ""),
                "kind": t_cancelled(lang),
            })
    except Exception:
        pass

    try:
        evs = conn.execute("""
            SELECT team_id, minute, type, detail,
                   player_en, player_ar, assist_en
            FROM events WHERE match_id = ? AND type != 'none'
            ORDER BY minute
        """, (mid,)).fetchall()
    except Exception:
        evs = []

    sub_arrow = "←" if lang == "ar" else "→"

    names = name_map(conn) if lang == "ar" else {}

    for e in evs:
        # ⚠️ كان يعرض player_en دائماً — فترجمات البطاقات
        #    والتبديلات في `events` لم تكن تظهر إطلاقاً رغم
        #    تطبيقها على الجدول (بعكس قسم الأهداف أعلاه).
        player = ""
        if lang == "ar":
            player = clean(e["player_ar"]) or names.get(clean(e["player_en"]), "")
        player = player or clean(e["player_en"]) or "—"
        mn = e["minute"] if e["minute"] is not None else 999

        if e["type"] == "Card":
            red = e["detail"] in ("Red Card", "Second Yellow card")
            items.append({
                "min": mn, "team": e["team_id"],
                "icon": CARD_ICON.get(e["detail"], "🟨"),
                "major": red,
                "body": f'<span class="who">{player}</span>',
                "kind": "",
            })
        elif e["type"] == "subst":
            inn_en = clean(e["assist_en"])
            inn = (names.get(inn_en, "") if lang == "ar" else "") or inn_en
            items.append({
                "min": mn, "team": e["team_id"], "icon": "🔄",
                "major": False,
                "body": (f'<span class="who">'
                         f'<span class="in">{inn}</span> {sub_arrow} '
                         f'<span class="out">{player}</span></span>'),
                "kind": "",
            })
        else:
            items.append({
                "min": mn, "team": e["team_id"], "icon": "📺",
                "major": False,
                "body": f'<span class="who">{clean(e["detail"])}</span>',
                "kind": "",
            })

    items.sort(key=lambda x: x["min"])
    return items


STAT_ROWS = [
    ("possession", "possession", "%"),
    ("shots_total", "shots", ""),
    ("shots_on", "shots_on", ""),
    ("corners", "corners", ""),
    ("fouls", "fouls", ""),
    ("offsides", "offsides", ""),
    ("saves", "saves", ""),
    ("passes_total", "passes", ""),
    ("passes_pct", "pass_acc", "%"),
    ("xg", "xg", ""),
]


def build_stats(conn, mid, home_id, away_id, lang):
    """قسم إحصائيات المباراة — فارغ إن لم توجد داتا"""
    t = T[lang]
    try:
        rows = conn.execute("""
            SELECT * FROM match_stats WHERE match_id = ?
        """, (mid,)).fetchall()
    except Exception:
        return ""

    if len(rows) < 2:
        return ""

    data = {r["team_id"]: r for r in rows}
    A = data.get(home_id)
    B = data.get(away_id)
    if A is None or B is None:
        return ""

    out = ""
    for col, key, unit in STAT_ROWS:
        va, vb = A[col], B[col]
        if va is None and vb is None:
            continue
        va = va or 0
        vb = vb or 0
        tot = va + vb
        pa = (va / tot * 100) if tot else 50
        pb = 100 - pa

        # الأرقام العشرية (xG) تُعرض برقمين
        fa = f"{va:.2f}" if isinstance(va, float) else str(va)
        fb = f"{vb:.2f}" if isinstance(vb, float) else str(vb)

        out += (
            f'<div class="st">'
            f'<span class="v a">{fa}{unit}</span>'
            f'<span class="mid"><span class="lbl">{t[key]}</span>'
            f'<span class="bar"><i class="x" style="width:{pa:.0f}%"></i>'
            f'<i class="y" style="width:{pb:.0f}%"></i></span></span>'
            f'<span class="v b">{fb}{unit}</span>'
            f'</div>'
        )

    if not out:
        return ""

    return f'<h2>{t["stats"]}</h2><div class="goals">{out}</div>'
def build_page(m, h, a, items, fix, lang, stats_html="", lineup_html=""):
    """صفحة مباراة واحدة بلغة واحدة"""
    t = T[lang]
    mid = m["match_id"]
    season = m["season"]
    lg = league_name(m["league_code"], lang)
    is_upcoming = m["home_goals"] is None or m["away_goals"] is None
    
    up = "../" if lang == "ar" else "../../"

    # قائمة الأحداث
    if items:
        rows = ""
        for it in items:
            side = h if it["team"] == m["home_id"] else a
            cls = "" if it["major"] else " minor"
            mn = "؟" if it["min"] == 999 else it["min"]
            kind_html = (f'<span class="kind">{it["kind"]}</span>'
                         if it["kind"] else "")
            rows += (
                f'<div class="ev{cls}"><span class="min">{mn}\'</span>'
                f'<span class="ic">{it["icon"]}</span>{it["body"]}'
                f'{kind_html}'
                f'<span class="for">{tname(side, lang)}</span></div>'
            )

        has_minor = any(not it["major"] for it in items)
        tabs = ""
        if has_minor:
            tabs = (f'<div class="vtabs">'
                    f'<button class="vtab on" data-v="all">'
                    f'{t["view_all_events"]}</button>'
                    f'<button class="vtab" data-v="key">'
                    f'{t["view_key_events"]}</button>'
                    f'</div>')

        events_html = (f'<h2>{t["match_events"]}</h2>{tabs}'
                       f'<div class="goals" id="evbox">{rows}</div>')
    else:
        if is_upcoming:
            msg = t["not_started"]
        else:
            total = (m["home_goals"] or 0) + (m["away_goals"] or 0)
            msg = t["goalless"] if total == 0 else t["no_details"]
        events_html = (f'<h2>{t["match_events"]}</h2>'
                       f'<div class="empty">{msg}</div>')

    # ⚠️ **لا شارة تصحيح.** النتيجة المعروضة هي الصحيحة أصلاً،
    #    وإخبار الزائر أن المزوّد أخطأ لا يعنيه — يريد النتيجة
    #    لا سيرة تصحيحها. `match_corrections.csv` ملف عمل يُطبَّق
    #    بعد كل سحب، ولا يظهر منه شيء على الموقع (قرار 23 أغسطس).
    fix_block = ""

    home = '../index.html'
    switch = (f'../en/matches/{mid}.html' if lang == "ar"
              else f'../../matches/{mid}.html')

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{tname(h, lang)} × {tname(a, lang)} — {t["site_title"]}</title>\n'
        + head_meta(f'{tname(h, lang)} × {tname(a, lang)}',
                    f'{lg} · {m["date"]}',
                    "../" if lang == "ar" else "../../")
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<span style="display:flex;gap:8px;align-items:center">'
        f'{back_button(t["back"])}'
        f'</span>'
        f'<span style="display:flex;gap:8px">'
        f'</span>'
        f'</div>\n'
        f'<div class="meta-top">{lg} · {t["season"]} {season}-{season+1}'
        f' · {m["date"]}</div>\n'
        f'<div class="head">'
        f'<a class="team" href="../clubs/{m["home_id"]}.html">'
        f'<img src="{logo_url(h, lang)}" alt="">'
        f'<span>{tname(h, lang)}</span></a>'
        f'<div class="big{" soon" if is_upcoming else ""}">'
        f'{t["upcoming"] if is_upcoming else str(m["home_goals"]) + " - " + str(m["away_goals"])}'
        f'</div>'
        f'<a class="team" href="../clubs/{m["away_id"]}.html">'
        f'<img src="{logo_url(a, lang)}" alt="">'
        f'<span>{tname(a, lang)}</span></a>'
        f'</div>\n'
        f'{fix_block}\n'
        f'{events_html}\n'
        f'{stats_html}\n'
        f'{lineup_html}\n'
        f'<footer><a href="../about.html" style="color:var(--accent);text-decoration:none">{t["about"]}</a><br>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        '<script>\n'
        'document.querySelectorAll(".vtab").forEach(function(t){\n'
        't.addEventListener("click",function(){\n'
        'var key=this.dataset.v==="key";\n'
        'document.querySelectorAll(".vtab").forEach(function(x){\n'
        'x.classList.toggle("on",x===t);});\n'
        'document.querySelectorAll(".ev.minor").forEach(function(e){\n'
        'e.classList.toggle("off",key);});\n'
        '});});\n'
        '</script>\n'
                + search_overlay(t)
        + navbar(t, 1, "", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT + BACK_SCRIPT
        + nav_script(t)
        + search_script(t, 1 if lang == "ar" else 2, lang) +
        '</body>\n</html>'
    )


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    teams = load_teams()
    fixes = load_corrections()

    os.makedirs(BASE / "matches", exist_ok=True)
    os.makedirs(BASE / "en" / "matches", exist_ok=True)

    q = """SELECT match_id, league_code, season, date,
                  home_id, away_id, home_goals, away_goals
           FROM matches"""
    params = []
    if ONLY:
        q += " WHERE league_code = ?"
        params.append(ONLY)

    matches = conn.execute(q, params).fetchall()

    made = skipped = fixed_n = 0

    for m in matches:
        mid = m["match_id"]
        h = teams.get(m["home_id"])
        a = teams.get(m["away_id"])

        if not h or not a:
            skipped += 1
            continue

        fix = fixes.get(mid)
        if fix:
            fixed_n += 1

        for lang in LANGS:
            items = build_items(conn, mid, lang)
            stats_html = build_stats(conn, mid, m["home_id"],
                                     m["away_id"], lang)
            lineup_html = build_lineups(conn, m, h, a, lang, T,
                                        tname, logo_url)
            html = build_page(m, h, a, items, fix, lang, stats_html,
                              lineup_html)
            out = ((BASE / "matches" / f"{mid}.html") if lang == "ar"
                   else (BASE / "en" / "matches" / f"{mid}.html"))
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)

        made += 1

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} مباراة × لغتين")
    print("  matches/  +  en/matches/")
    if fixed_n:
        print(f"  منها {fixed_n} بشارة 'نتيجة مصححة'")
    if skipped:
        print(f"  متخطى: {skipped} (نادٍ غير موجود بجدول teams)")
    print(f"{'=' * 55}")
    print("""
  جرّب:
      start matches\\1252470.html
      start en\\matches\\1252470.html
    """)


if __name__ == "__main__":
    main()
