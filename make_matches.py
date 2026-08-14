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

⚠️ ملاحظات وأسماء اللاعبين في التصحيحات مكتوبة بالعربية فقط،
   فتظهر كما هي في النسخة الإنجليزية. ترجمتها مؤجلة لجلسة الأسماء.

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

BASE = DB_FILE.parent
CORRECTIONS_FILE = BASE / "match_corrections.csv"

ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


STYLE = """
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:#0f1419;
         color:#e8eaed; padding:24px 16px; line-height:1.6; }
  .wrap { max-width:760px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:14px; }
  .back { display:inline-block; color:#2f81f7; text-decoration:none;
          font-size:14px; }
  .back:hover { text-decoration:underline; }
  .lang { background:#161b22; color:#7d8590; border:1px solid #21262d;
          padding:6px 14px; border-radius:8px; font-size:13px;
          text-decoration:none; font-family:inherit; }
  .lang:hover { background:#1c2128; color:#e8eaed; }
  .meta-top { text-align:center; color:#7d8590; font-size:13px;
              margin-bottom:12px; }
  .head { background:#161b22; border-radius:12px; padding:24px 16px;
          display:grid; grid-template-columns:1fr auto 1fr;
          align-items:center; gap:12px; }
  .team { display:flex; flex-direction:column; align-items:center;
          gap:10px; min-width:0; text-decoration:none; color:#e8eaed; }
  .team img { width:60px; height:60px; object-fit:contain; }
  .team span { font-size:15px; text-align:center; }
  .team:hover span { color:#2f81f7; }
  .big { font-size:34px; font-weight:700; letter-spacing:2px;
         white-space:nowrap; }
  .fixed { background:#1f2937; border:1px solid #2f81f7;
           border-radius:10px; padding:14px 16px; margin-top:12px;
           font-size:13px; }
  .fixed b { color:#2f81f7; }
  .fixed .row { color:#7d8590; margin-top:4px; }
  h2 { font-size:16px; margin:26px 0 10px; padding-inline-start:10px;
       border-inline-start:3px solid #2f81f7; }
  .goals { background:#161b22; border-radius:10px; padding:6px; }
  .min { color:#2f81f7; font-weight:700; min-width:42px; }
  .who { flex:1; min-width:0; overflow:hidden;
         text-overflow:ellipsis; white-space:nowrap; }
  .for { color:#7d8590; font-size:12px; }
  .kind { color:#7d8590; font-size:11px; }
  .ev { display:flex; align-items:center; gap:12px; padding:10px 12px;
        border-bottom:1px solid #21262d; font-size:14px; }
  .ev:last-child { border-bottom:none; }
  .ic { min-width:26px; font-size:13px; }
  .out { color:#f85149; font-size:12px; }
  .in { color:#3fb950; font-size:12px; }
  .vtabs { display:flex; gap:8px; margin:26px 0 10px; }
  .vtab { background:#161b22; color:#7d8590; border:1px solid #21262d;
          padding:8px 16px; border-radius:8px; cursor:pointer;
          font-family:inherit; font-size:14px; }
  .vtab:hover { background:#1c2128; color:#e8eaed; }
  .vtab.on { background:#2f81f7; color:#fff; border-color:#2f81f7; }
  .minor.off { display:none; }
  .empty { background:#161b22; border-radius:10px; padding:20px;
           text-align:center; color:#7d8590; font-size:13px; }
  footer { text-align:center; color:#7d8590; font-size:12px;
           margin-top:36px; line-height:1.9; }
</style>
"""

CARD_ICON = {
    "Yellow Card": "🟨",
    "Red Card": "🟥",
    "Second Yellow card": "🟨🟥",
}


def clean(t):
    return (t or "").strip()


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
    """التصحيحات — عشان نعرض الشارة"""
    fixes = {}
    if not CORRECTIONS_FILE.exists():
        return fixes
    with open(CORRECTIONS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            mid = clean(r.get("match_id"))
            if not mid:
                continue
            fixes[int(mid)] = {
                "note": clean(r.get("note")),
                "source": clean(r.get("source")),
            }
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

    try:
        evs = conn.execute("""
            SELECT team_id, minute, type, detail, player_en, assist_en
            FROM events WHERE match_id = ? AND type != 'none'
            ORDER BY minute
        """, (mid,)).fetchall()
    except Exception:
        evs = []

    sub_arrow = "←" if lang == "ar" else "→"

    for e in evs:
        player = clean(e["player_en"]) or "—"
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
            inn = clean(e["assist_en"])
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


def build_page(m, h, a, items, fix, lang):
    """صفحة مباراة واحدة بلغة واحدة"""
    t = T[lang]
    mid = m["match_id"]
    season = m["season"]
    lg = league_name(m["league_code"], lang)
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
        total = (m["home_goals"] or 0) + (m["away_goals"] or 0)
        msg = t["goalless"] if total == 0 else t["no_details"]
        events_html = (f'<h2>{t["match_events"]}</h2>'
                       f'<div class="empty">{msg}</div>')

    # شارة التصحيح
    fix_block = ""
    if fix:
        fix_block = (
            f'<div class="fixed">'
            f'<b>{t["corrected"]}</b>'
            f'<div class="row">{fix["note"]}</div>'
            f'<div class="row">{t["source"]}: {fix["source"]}</div>'
            f'</div>'
        )

    home = f'{up}index.html'
    switch = (f'../en/matches/{mid}.html' if lang == "ar"
              else f'../../matches/{mid}.html')

    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{tname(h, lang)} × {tname(a, lang)}</title>\n'
        + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar">'
        f'<a class="back" href="{home}">{t["back_home"]}</a>'
        f'<a class="lang" href="{switch}">{SWITCH_LABEL[lang]}</a>'
        f'</div>\n'
        f'<div class="meta-top">{lg} · {t["season"]} {season}-{season+1}'
        f' · {m["date"]}</div>\n'
        f'<div class="head">'
        f'<a class="team" href="{up}clubs/{m["home_id"]}.html">'
        f'<img src="{logo_url(h, lang)}" alt="">'
        f'<span>{tname(h, lang)}</span></a>'
        f'<div class="big">{m["home_goals"]} - {m["away_goals"]}</div>'
        f'<a class="team" href="{up}clubs/{m["away_id"]}.html">'
        f'<img src="{logo_url(a, lang)}" alt="">'
        f'<span>{tname(a, lang)}</span></a>'
        f'</div>\n'
        f'{fix_block}\n'
        f'{events_html}\n'
        f'<footer>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
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
            html = build_page(m, h, a, items, fix, lang)
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
