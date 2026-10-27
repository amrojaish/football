#!/usr/bin/env python3
"""
تبويب «المواسم» بصفحة الدوري (27 أكتوبر 2026، طلب عمرو #2)
==========================================================
بطاقة لكل موسم منتهٍ نملك بياناته (الأحدث أولاً): عنوان الموسم، البطل (شعار + اسم + «البطل»)، الوصيف («الوصيف») — من جدولنا النهائي
(`make_site3.get_table`، نفس جدول صفحة الموسم). النقر = صفحة ذلك الموسم (leagues/<code>-<season>.html، أو صفحة الدوري للموسم الأحدث).

الموسم يظهر فقط إن كان جدوله النهائي موثوقاً — لا تخمين:
    • كل مبارياته لُعبت (لا مباراة بلا نتيجة)، والموسم الجاري لا يظهر حتى ينتهي؛
    • و(أ) كل الفرق لعبت عدداً متقارباً (الفرق ≤ 2)، أو (ب) الموسم مقسوم ونعرف مجموعة البطولة من أوصاف المزوّد (zones: grp1)، أو
      (ج) أول وثاني المزوّد النهائيان (api_standings) = أول وثاني جدولنا.
    غير ذلك = يُتخطّى مع السبب (نظام مراحل بلا بيانات مجموعات — الكويت 2022-25، تونس 2022-23).
الموسم المقسوم (المصري): الترتيب داخل مجموعة البطولة (فرق وصف grp1) بنقاط الموسم كاملة — لا ترتيب المزوّد الذي قد يكون قديماً
(2024: جدولنا الأهلي 58 والمزوّد بيراميدز أولاً).

صفر طلبات API. `season_list(conn, code)` تُرجع (المعروضة، المتخطّاة) وتُستعمل بالاختبار والتقرير.
"""
from html import escape

from make_site3 import get_table, clean
from zones import classify

STR = {
    "ar": {"tab": "المواسم", "winner": "البطل", "runner": "الوصيف", "none": "لا مواسم مكتملة بعد", "open": "افتح الموسم"},
    "en": {"tab": "Seasons", "winner": "Winner", "runner": "Runner-up", "none": "No completed seasons yet", "open": "Open season"},
}

SEASONS_CSS = """
  /* تبويب «المواسم» (seasons_view.py) */
  .sgrid { display:grid; gap:10px; }
  .scard { display:block; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px;
           color:var(--text); text-decoration:none; }
  .scard:hover { border-color:var(--accent); }
  .scard .sct { font-size:15px; font-weight:700; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
  .scard .sct .sgo { color:var(--muted); width:16px; height:16px; display:inline-flex; }
  .scard .sct .sgo svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
  [dir="rtl"] .scard .sct .sgo svg { transform:scaleX(-1); }
  .scard .srow { display:flex; align-items:center; gap:10px; min-height:40px; }
  .scard .srow + .srow { border-top:1px solid var(--line); }
  .scard .srow img { width:28px; height:28px; object-fit:contain; flex:0 0 28px; }
  .scard .srow .sn { flex:1; min-width:0; font-size:14px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .scard .srow .sb { font-size:12px; font-weight:700; padding:2px 10px; border-radius:999px; white-space:nowrap; }
  .scard .srow.w .sb { background:color-mix(in srgb, #d4a017 22%, var(--card2)); color:var(--text); border:1px solid #d4a017; }
  .scard .srow.r .sb { background:var(--card2); color:var(--muted); border:1px solid var(--line); }
  .scard.cur { border-color:var(--accent); }
"""

_CACHE = {}


def _label(s):
    return f"{s}/{str(s + 1)[-2:]}"


def season_list(conn, code):
    """([{season, champ, runner}], [(season, سبب)]) — المواسم المكتملة الأحدث أولاً، والمتخطّاة بسببها"""
    if code in _CACHE:
        return _CACHE[code]
    shown, skipped = [], []
    seasons = [r[0] for r in conn.execute("SELECT DISTINCT season FROM matches WHERE league_code = ? ORDER BY season DESC", (code,))]
    for s in seasons:
        unplayed = conn.execute("SELECT COUNT(*) FROM matches WHERE league_code = ? AND season = ? AND home_goals IS NULL",
                                (code, s)).fetchone()[0]
        if unplayed:
            skipped.append((s, f"not finished ({unplayed} matches left)"))
            continue
        table = [dict(r) for r in get_table(conn, code, s)]
        if len(table) < 2:
            skipped.append((s, "no table"))
            continue
        prov = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT team_id, rank, description FROM api_standings WHERE league_code = ? AND season = ?", (code, s))}
        group = {tid for tid, (_, d) in prov.items() if (classify(d) or ("",))[0] == "grp1"}
        if group:   # موسم مقسوم: الترتيب داخل مجموعة البطولة
            table = [r for r in table if r["team_id"] in group] or table
        played = [r["played"] for r in table]
        even = max(played) - min(played) <= 2
        top_prov = [tid for tid, (rk, _) in sorted(prov.items(), key=lambda kv: kv[1][0]) if rk in (1, 2)]
        agree = len(top_prov) == 2 and top_prov == [table[0]["team_id"], table[1]["team_id"]]
        if not (even or group or agree):
            skipped.append((s, f"uneven games {min(played)}-{max(played)} (staged format, no group data)"))
            continue
        shown.append({"season": s, "champ": table[0], "runner": table[1],
                      "basis": "group" if group else ("even" if even else "provider")})
    _CACHE[code] = (shown, skipped)
    return _CACHE[code]


def seasons_tab_html(conn, code, lang, season, newest_season, logo_of, tname):
    """لوحة التبويب. logo_of(row) → src (thumbs/… أو رابط)، tname(row, lang) → اسم النادي. الموسم المعروض مُبرَز."""
    S = STR[lang]
    shown, _ = season_list(conn, code)
    if not shown:
        return f'<div class="empty">{S["none"]}</div>'
    cl = code.lower()
    cards = ""
    for x in shown:
        s = x["season"]
        href = f"{cl}.html" if s == newest_season else f"{cl}-{s}.html"

        def row(r, cls, badge):
            return (f'<div class="srow {cls}"><img src="{escape(logo_of(r) or "", quote=True)}" alt="" loading="lazy">'
                    f'<span class="sn">{escape(clean(tname(r, lang)) or "")}</span><span class="sb">{badge}</span></div>')
        cards += (f'<a class="scard{" cur" if s == season else ""}" href="{href}" data-season="{s}">'
                  f'<div class="sct"><bdi dir="ltr">{_label(s)}</bdi><span class="sgo" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></span></div>'
                  + row(x["champ"], "w", S["winner"]) + row(x["runner"], "r", S["runner"]) + '</a>')
    return f'<div class="sgrid">{cards}</div>'
