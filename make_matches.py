#!/usr/bin/env python3
"""
توليد صفحة لكل مباراة
=======================
بيعمل مجلد matches/ وفيه ملف HTML لكل مباراة:
  matches/1538111.html

كل صفحة فيها:
  - الناديان بشعاريهما والنتيجة (روابط لصفحتَي النادي)
  - التاريخ والدوري والموسم
  - الأهداف بدقائقها ومسجّليها، مقسومة على الفريقين
  - ⭐ شارة "نتيجة مصححة" إذا كانت المباراة في match_corrections.csv
    مع السبب والمصدر — هذه ميزة لا يعرضها أي تطبيق آخر

صفر طلبات API.

التشغيل:
    python make_matches.py
    python make_matches.py JOR      <- دوري محدد فقط
"""

import sqlite3
import csv
import os
import sys
from config import DB_FILE, TEAMS_FILE, LEAGUES

OUT_DIR = DB_FILE.parent / "matches"
CORRECTIONS_FILE = DB_FILE.parent / "match_corrections.csv"

ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


STYLE = """
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:#0f1419;
         color:#e8eaed; padding:24px 16px; line-height:1.6; }
  .wrap { max-width:760px; margin:0 auto; }
  .back { display:inline-block; color:#2f81f7; text-decoration:none;
          font-size:14px; margin-bottom:18px; }
  .back:hover { text-decoration:underline; }
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
  h2 { font-size:16px; margin:26px 0 10px; padding-right:10px;
       border-right:3px solid #2f81f7; }
  .goals { background:#161b22; border-radius:10px; padding:6px; }
  .g { display:flex; align-items:center; gap:12px; padding:10px 12px;
       border-bottom:1px solid #21262d; font-size:14px; }
  .g:last-child { border-bottom:none; }
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
KIND_AR = {
    "Normal Goal": "",
    "Penalty": "ركلة جزاء",
    "Own Goal": "هدف عكسي",
}


def clean(t):
    return (t or "").strip()


def load_teams():
    teams = {}
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "short": clean(r.get("short_name_ar")) or clean(r.get("name_en")),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


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


def logo_url(t):
    if t["logo_local"]:
        return "../" + t["logo_local"]
    return t["logo"] or ""


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    teams = load_teams()
    fixes = load_corrections()

    os.makedirs(OUT_DIR, exist_ok=True)

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

        league_ar = LEAGUES.get(m["league_code"], {}).get(
            "name_ar", m["league_code"])
        season = m["season"]

       # الأهداف والأحداث بقائمة واحدة مرتبة بالدقيقة
        items = []

        for g in conn.execute("""
            SELECT team_id, minute, player_en, player_ar, detail
            FROM goals WHERE match_id = ? ORDER BY minute
        """, (mid,)):
            who = clean(g["player_ar"]) or clean(g["player_en"]) or "—"
            kind = KIND_AR.get(g["detail"], clean(g["detail"]))
            items.append({
                "min": g["minute"] if g["minute"] is not None else 999,
                "team": g["team_id"], "icon": "⚽", "major": True,
                "body": f'<span class="who">{who}</span>',
                "kind": kind,
            })

        try:
            evs = conn.execute("""
                SELECT team_id, minute, type, detail, player_en, assist_en
                FROM events WHERE match_id = ? AND type != 'none'
                ORDER BY minute
            """, (mid,)).fetchall()
        except Exception:
            evs = []

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
                             f'<span class="in">{inn}</span> ← '
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
                    f'<span class="for">{side["short"]}</span></div>'
                )

            has_minor = any(not it["major"] for it in items)
            tabs = ""
            if has_minor:
                tabs = ('<div class="vtabs">'
                        '<button class="vtab on" data-v="all">كل الأحداث</button>'
                        '<button class="vtab" data-v="key">الأحداث المهمة</button>'
                        '</div>')

            goals_block = (f'<h2>أحداث المباراة</h2>{tabs}'
                           f'<div class="goals" id="evbox">{rows}</div>')
        else:
            total = (m["home_goals"] or 0) + (m["away_goals"] or 0)
            msg = ("انتهت بالتعادل السلبي" if total == 0
                   else "لا تتوفر تفاصيل هذه المباراة")
            goals_block = f'<h2>أحداث المباراة</h2><div class="empty">{msg}</div>'

        events_block = ""
        # شارة التصحيح
        fix_block = ""
        if mid in fixes:
            f = fixes[mid]
            fixed_n += 1
            fix_block = (
                f'<div class="fixed">'
                f'<b>⭐ نتيجة مصححة يدوياً</b>'
                f'<div class="row">{f["note"]}</div>'
                f'<div class="row">المصدر: {f["source"]}</div>'
                f'</div>'
            )

        html = (
            '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{h["short"]} × {a["short"]}</title>\n'
            + STYLE +
            '</head>\n<body>\n<div class="wrap">\n'
            '<a class="back" href="../index.html">→ رجوع للصفحة الرئيسية</a>\n'
            f'<div class="meta-top">{league_ar} · موسم {season}-{season+1}'
            f' · {m["date"]}</div>\n'
            f'<div class="head">'
            f'<a class="team" href="../clubs/{m["home_id"]}.html">'
            f'<img src="{logo_url(h)}" alt=""><span>{h["short"]}</span></a>'
            f'<div class="big">{m["home_goals"]} - {m["away_goals"]}</div>'
            f'<a class="team" href="../clubs/{m["away_id"]}.html">'
            f'<img src="{logo_url(a)}" alt=""><span>{a["short"]}</span></a>'
            f'</div>\n'
            f'{fix_block}\n'
            f'{goals_block}\n'
            f'{events_block}\n'
            '<footer>الأسماء والشعارات المصححة من إعداد المطوّر<br>'
            'البيانات الأساسية من API-Football</footer>\n'
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

        with open(OUT_DIR / f"{mid}.html", "w", encoding="utf-8") as f:
            f.write(html)
        made += 1

    conn.close()

    print(f"\n{'=' * 55}")
    print(f"  تم توليد {made} صفحة مباراة بمجلد matches/")
    if fixed_n:
        print(f"  منها {fixed_n} بشارة 'نتيجة مصححة'")
    if skipped:
        print(f"  متخطى: {skipped} (نادٍ غير موجود بجدول teams)")
    print(f"{'=' * 55}")
    print("""
  جرّب: افتح matches/1538111.html (الحسين × الفيصلي المصححة)

  الخطوة الجاية: ربط النتائج بالصفحة الرئيسية
  وصفحات الأندية بصفحاتها
    """)


if __name__ == "__main__":
    main()
