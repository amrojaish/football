#!/usr/bin/env python3
"""
صفحة اللاعب بنمط FotMob (30 أكتوبر 2026، دفعة 5 بند 1) — الرأس والتبويبات الأربعة
===================================================================================
يستعمله make_players.build(). **بلا صور لاعبين** (قبل Google Play): دائرة رمزية بجهة البداية. **فقط ما نملكه**: أي حقل غائب يُخفى
(لا «-» ولا صفر مخترَع)، وأي عمود كله فارغ لا يظهر.

    الرأس      دائرة رمزية · الاسم · كبسولة النادي (شعار + اسم)؛ زر «متابعة» كبسولة بالشريط العلوي
    الملف      شبكة 3×2: الطول · العمر + تاريخ الميلاد · البلد (علم إن وُجد ملفه) · الرقم · المركز · (القدم المفضّلة: لا مصدر لها —
               لا تظهر) — ثم بطاقة «الموسم الحالي بالدوري»: شعار الدوري واسمه والموسم، مباريات · أهداف · صناعة · (تقييم إن وُجد)
    المباريات  صف لكل مباراة: التاريخ (بداية) والمسابقة (نهاية) أعلاه؛ شعار الخصم واسمه، شارة ف/ت/خ بالنتيجة؛ بالنهاية أيقونات
               أحداثه (هدف/صناعة/بطاقة) والدقائق والتقييم إن وُجدا
    الإحصائيات شريط اختيار «الدوري الموسم ▾» يفتح ورقة بمواسمه مجمَّعة بالسنة؛ تحته بطاقة: أهداف · صناعة · تقييم · مباريات · أساسي · دقائق
    المسيرة    صف لكل (موسم، نادٍ): الشعار والاسم والموسم، ثم مباريات · أهداف · صناعة · تقييم بأيقونات برأس الجدول

المصادر: player_info (الطول/الميلاد/الجنسية/الرقم/المركز)، lineup_players (المباريات/الأساسي/الرقم/المركز)، player_stats (الدقائق/
الأهداف/الصناعة/التقييم/البطاقات/البديل)، goals (الأهداف حيث لا player_stats). صفر طلبات API.
"""
from collections import defaultdict
from datetime import date
from html import escape

from i18n import league_name

# أعلام الدول الموجودة بالموقع فقط (flags/*.svg — دول الدوريات العشرة)؛ غيرها: الاسم وحده
NAT_FLAG = {"Jordan": "jo", "Iraq": "iq", "Saudi Arabia": "sa", "Egypt": "eg", "United Arab Emirates": "ae", "Qatar": "qa",
            "Morocco": "ma", "Tunisia": "tn", "Algeria": "dz", "Kuwait": "kw"}

PL = {
    "ar": {"height": "الطول", "age": "العمر", "country": "البلد", "shirt": "الرقم", "pos": "المركز", "cm": "سم", "y": "سنة",
           "matches": "مباريات", "goals": "أهداف", "assists": "صناعة", "rating": "التقييم", "started": "أساسي", "mins": "دقائق",
           "cur": "الموسم الحالي", "season": "الموسم", "choose": "اختر الموسم", "w": "ف", "d": "ت", "l": "خ",
           "months": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]},
    "en": {"height": "Height", "age": "Age", "country": "Country", "shirt": "Shirt", "pos": "Position", "cm": "cm", "y": "years",
           "matches": "Matches", "goals": "Goals", "assists": "Assists", "rating": "Rating", "started": "Started",
           "mins": "Minutes played", "cur": "Current season", "season": "Season", "choose": "Choose season",
           "w": "W", "d": "D", "l": "L",
           "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]},
}

IC = {
    "goal": '<svg viewBox="0 0 24 24" class="pic gl" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7l4 3-1.5 5h-5L8 10z"/></svg>',
    "assist": '<svg viewBox="0 0 24 24" class="pic as" aria-hidden="true"><path d="M4 16c3 0 5-1 7-4l2-3c1-1.5 2.5-2 4-2h3v4c0 4-3 7-8 7H4z"/></svg>',
    "apps": '<svg viewBox="0 0 24 24" class="pic" aria-hidden="true"><path d="M6 4h12v16H6z"/><path d="M9 8h6M9 12h6"/></svg>',
    "rating": '<svg viewBox="0 0 24 24" class="pic" aria-hidden="true"><path d="M12 4l2.4 5 5.6.6-4.2 3.8 1.2 5.6L12 16.3 7 19l1.2-5.6L4 9.6 9.6 9z"/></svg>',
}
PERSON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="9" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>')

CSS = """
  /* ── صفحة اللاعب بنمط FotMob (30 أكتوبر 2026، دفعة 5 بند 1 — player_layout.py) ── */
  .phd { display:flex; align-items:center; gap:14px; margin:4px 0 16px; text-align:start; }
  .pav { width:64px; height:64px; flex:0 0 64px; border-radius:50%; background:var(--card2); border:1px solid var(--line);
         display:flex; align-items:center; justify-content:center; color:var(--muted); }
  .pav svg { width:34px; height:34px; fill:none; stroke:currentColor; stroke-width:1.6; }
  .phd .pnm { min-width:0; }
  .phd h1 { font-size:22px; line-height:1.25; margin:0; overflow-wrap:anywhere; }
  .pclub { display:inline-flex; align-items:center; gap:7px; margin-top:6px; padding:4px 12px 4px 6px; border-radius:999px;
           background:var(--card); border:1px solid var(--line); color:var(--text); text-decoration:none; font-size:13px; font-weight:600;
           max-width:100%; }
  [dir="rtl"] .pclub { padding:4px 6px 4px 12px; }
  .pclub img { width:20px; height:20px; object-fit:contain; flex:0 0 20px; }
  .pclub span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pfol { min-height:40px; padding:0 16px; border-radius:999px; border:1px solid var(--line); background:var(--card);
          color:var(--text); font-family:inherit; font-size:14px; font-weight:700; cursor:pointer; }
  .pfol.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  /* الملف: شبكة 3×2 */
  .pgrid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); background:var(--card); border-radius:12px; margin-top:12px;
           overflow:hidden; }
  .pgc { padding:12px 8px; text-align:center; border-top:1px solid var(--line); border-inline-start:1px solid var(--line); min-width:0; }
  .pgc:nth-child(3n+1) { border-inline-start:none; }
  .pgc:nth-child(-n+3) { border-top:none; }
  .pgc .v { font-size:16px; font-weight:700; display:flex; align-items:center; justify-content:center; gap:6px; overflow-wrap:anywhere; }
  .pgc .v img { width:20px; height:15px; object-fit:cover; border-radius:2px; flex:0 0 20px; }
  .pgc .s { font-size:11px; color:var(--muted); margin-top:1px; }
  .pgc .k { font-size:12px; color:var(--muted); margin-top:3px; }
  /* بطاقة الموسم الحالي + بطاقة الإحصائيات */
  .pscur, .pstc { background:var(--card); border-radius:12px; margin-top:12px; padding:12px; }
  .pslg { display:flex; align-items:center; gap:8px; font-size:14px; font-weight:700; margin-bottom:10px; color:var(--text);
          text-decoration:none; }
  .pslg img { width:22px; height:22px; object-fit:contain; }
  .pslg small { color:var(--muted); font-weight:400; margin-inline-start:auto; }
  .psv { display:grid; grid-template-columns:repeat(auto-fit,minmax(70px,1fr)); gap:8px; }
  .psv div { text-align:center; }
  .psv b { display:block; font-size:20px; }
  .psv span { color:var(--muted); font-size:12px; }
  .psv .hi b { color:var(--accent); }
  /* المباريات */
  .pml2 { margin-top:12px; background:var(--card); border-radius:12px; overflow:hidden; }
  .pmr { display:block; padding:8px 12px; border-top:1px solid var(--line); color:var(--text); text-decoration:none; }
  .pmr:first-child { border-top:none; }
  .pmr.hidden { display:none; }
  .pmr:hover { background:var(--card2); }
  .pmt { display:flex; justify-content:space-between; gap:8px; color:var(--muted); font-size:11.5px; }
  .pmt span:last-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pmm { display:flex; align-items:center; gap:8px; min-height:36px; }
  .pmm img, .pmm .tfnl { width:22px; height:22px; object-fit:contain; flex:0 0 22px; }
  .pmo { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:14px; font-weight:600; }
  .pmres { min-width:48px; text-align:center; border-radius:6px; padding:2px 6px; font-size:13px; font-weight:700; color:#fff;
           unicode-bidi:isolate; direction:ltr; }
  .pmres.w { background:#17803a; } .pmres.d { background:#6b7280; } .pmres.l { background:#c62828; }
  .pmev { display:inline-flex; align-items:center; gap:4px; color:var(--muted); font-size:12px; white-space:nowrap; }
  .pmev .cy, .pmev .cr { width:8px; height:11px; border-radius:1px; display:inline-block; }
  .pmev .cy { background:#facc15; } .pmev .cr { background:#ef4444; }
  .pmev .n { font-size:11px; color:var(--text); font-weight:700; }
  .prt { min-width:30px; text-align:center; border-radius:5px; padding:1px 4px; font-size:12px; font-weight:700; color:#fff; }
  .prt.hi { background:#17803a; } .prt.mid { background:#d97706; } .prt.lo { background:#c62828; }
  .pic { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linejoin:round; flex:0 0 14px; }
  .pic.gl { color:var(--text); } .pic.as { color:var(--muted); }
  /* الإحصائيات: شريط الاختيار + الورقة */
  .psel { display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; min-height:46px; margin-top:12px;
          padding:0 14px; border-radius:12px; border:1px solid var(--line); background:var(--card); color:var(--text);
          font-family:inherit; font-size:14px; font-weight:700; cursor:pointer; text-align:start; }
  .psel i { font-style:normal; color:var(--muted); }
  .pstc[hidden] { display:none; }
  .pssh { position:fixed; inset:0; z-index:960; display:none; }
  .pssh.on { display:block; }
  .pssh .bd { position:absolute; inset:0; background:rgba(0,0,0,.55); }
  .pssh .sh { position:absolute; left:0; right:0; bottom:0; margin:0 auto; max-width:720px; max-height:75%; overflow-y:auto;
              background:var(--card); border-radius:18px 18px 0 0; padding:10px 16px calc(14px + env(safe-area-inset-bottom)); }
  .pssh h3 { font-size:15px; margin:4px 0 8px; }
  .pssh .yr { color:var(--muted); font-size:12px; margin:10px 0 2px; }
  .pssh button.opt { display:flex; align-items:center; gap:8px; width:100%; min-height:44px; background:none; border:none;
                     border-top:1px solid var(--line); color:var(--text); font-family:inherit; font-size:14px; cursor:pointer;
                     text-align:start; padding:0 4px; }
  .pssh button.opt img { width:20px; height:20px; object-fit:contain; }
  .pssh button.opt.on { color:var(--accent); font-weight:700; }
  /* المسيرة */
  .pcar { margin-top:12px; background:var(--card); border-radius:12px; overflow:hidden; }
  .pcr { display:grid; align-items:center; gap:6px; min-height:52px; padding:6px 12px; border-top:1px solid var(--line); }
  .pcr.hd { min-height:34px; border-top:none; color:var(--muted); }
  .pcr .c { text-align:center; font-weight:700; font-size:14px; font-variant-numeric:tabular-nums; }
  .pcr.hd .c { display:flex; justify-content:center; }
  .pcl { display:flex; align-items:center; gap:8px; min-width:0; color:var(--text); text-decoration:none; }
  .pcl img, .pcl .tfnl { width:24px; height:24px; object-fit:contain; flex:0 0 24px; }
  .pcl span { display:flex; flex-direction:column; min-width:0; line-height:1.25; }
  .pcl b { font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pcl small { color:var(--muted); font-size:12px; }
"""


def esc(s):
    return escape(str(s or ""), quote=True)


_LG = None


def league_logo_src(code, up):
    """شعار الدوري (المحلي ثم المزوّد ثم العلم) — نفس make_matches.league_logo_src"""
    global _LG
    if _LG is None:
        from config import LEAGUES
        from make_site3 import load_league_logos, FLAG
        logos, local = load_league_logos()
        _LG = {c: (local.get(c) or logos.get(c) or f"flags/{FLAG[c]}.svg") for c in LEAGUES if c in FLAG}
    src = _LG.get(code, "")
    return src if src.startswith("http") else (up + src if src else "")


def age(birth, today=None):
    try:
        y, m, d = (int(x) for x in str(birth)[:10].split("-"))
    except (ValueError, TypeError):
        return None, None
    today = today or date.today()
    return today.year - y - ((today.month, today.day) < (m, d)), (y, m, d)


def rating_cls(r):
    return "hi" if r >= 7 else ("mid" if r >= 6 else "lo")


def season_label(s):
    return f"{s}/{str(s + 1)[-2:]}"


def header_html(disp, team_tid, team, lang, upl, logo_fn, tname_fn):
    pill = ""
    if team:
        pill = (f'<a class="pclub" href="{upl}clubs/{team_tid}.html">{logo_fn(team)}'
                f'<span>{esc(tname_fn(team, lang))}</span></a>')
    return (f'<header class="phd"><span class="pav" aria-hidden="true">{PERSON}</span>'
            f'<div class="pnm"><h1>{esc(disp)}</h1>{pill}</div></header>')


def follow_pill(slug, aliases, t):
    return (f'<button class="pfol" id="followbtn" type="button" data-slug="{slug}" data-al="{",".join(aliases)}" '
            f'data-f="{esc(t["f_follow"])}" data-u="{esc(t["f_followed"])}" aria-pressed="false" '
            f'title="{esc(t["follow_player"])}">{esc(t["f_follow"])}</button>')


def profile_grid(info, plays, lang, up, nat_ar, positions):
    """شبكة 3×2 — الخلايا المتوفّرة فقط. يرجع (html، {حقل: bool}) للتغطية."""
    P = PL[lang]
    cells, have = [], {}
    info = info or {}
    if info.get("height_cm"):
        cells.append((f'{info["height_cm"]} {P["cm"]}', "", P["height"]))
        have["height"] = True
    a, ymd = age(info.get("birth_date"))
    if a is not None and 14 <= a <= 50:
        y, m, d = ymd
        cells.append((f'{a} {P["y"]}', f'{d} {P["months"][m - 1]} {y}', P["age"]))
        have["age"] = True
    nat = (info.get("nationality") or "").strip()
    if nat:
        fl = NAT_FLAG.get(nat)
        img = f'<img src="{up}flags/{fl}.svg" alt="" loading="lazy">' if fl else ""
        cells.append((f'{img}<span>{esc(nat_ar.get(nat, nat) if lang == "ar" else nat)}</span>', "", P["country"]))
        have["country"] = True
        have["flag"] = bool(fl)
    num = info.get("number")
    if num is None:
        num = next((e["number"] for e in plays if e.get("number") is not None), None)
    if num is not None:
        cells.append((str(num), "", P["shirt"]))
        have["shirt"] = True
    pos = info.get("position") or next((e.get("spos") or e.get("pos") for e in plays if e.get("spos") or e.get("pos")), None)
    if pos and positions.get(pos):
        cells.append((positions[pos], "", P["pos"]))
        have["pos"] = True
    if not cells:
        return "", have
    body = "".join(f'<div class="pgc"><div class="v">{v}</div>' + (f'<div class="s">{s}</div>' if s else "") +
                   f'<div class="k">{k}</div></div>' for v, s, k in cells)
    return f'<div class="pgrid">{body}</div>', have


def season_agg(plays, goal_rows):
    """{(season, league): {matches, started, mins, goals, assists, rating}} — None = لا مصدر (يُخفى)."""
    out = defaultdict(lambda: {"matches": 0, "started": None, "mins": None, "goals": None, "assists": None, "_r": [],
                               "_stats": False})
    for e in plays:
        k = (e["m"]["season"], e["m"]["league_code"])
        d = out[k]
        d["matches"] += 1
        st = e.get("starter")
        if st is None and e.get("stats") and e.get("sub") is not None:
            st = 0 if e["sub"] else 1
        if st is not None:
            d["started"] = (d["started"] or 0) + (1 if st == 1 else 0)
        if e.get("stats"):
            d["_stats"] = True
            if e.get("minutes") is not None:
                d["mins"] = (d["mins"] or 0) + e["minutes"]
            if e.get("goals") is not None:
                d["goals"] = (d["goals"] or 0) + e["goals"]
            if e.get("assists") is not None:
                d["assists"] = (d["assists"] or 0) + e["assists"]
            if e.get("rating"):
                d["_r"].append(float(e["rating"]))
    # الأهداف من جدول goals حيث لا player_stats (العكسية مستثناة)
    gcount = defaultdict(int)
    for g in goal_rows or ():
        if (g.get("detail") or "") != "Own Goal":
            gcount[(g["season"], g["league_code"])] += 1
    for k, n in gcount.items():
        d = out[k]
        if not d["_stats"] or d["goals"] is None:
            d["goals"] = n
    for d in out.values():
        if d["matches"] and d["goals"] is None:
            d["goals"] = 0
        d["rating"] = round(sum(d["_r"]) / len(d["_r"]), 2) if d["_r"] else None
        if not d["_stats"]:
            d["assists"] = None   # بلا player_stats لا مصدر للصناعة
    return dict(out)


def _stat_cells(d, lang, keys):
    P = PL[lang]
    out = ""
    for k in keys:
        v = d.get(k)
        if v is None or (k in ("assists", "mins", "started") and v is None):
            continue
        if k == "matches" and not v:
            continue
        txt = f"{v:.2f}" if k == "rating" else (f"{int(v):,}" if k == "mins" else str(v))
        hi = ' class="hi"' if k == "goals" else ""
        out += f'<div{hi}><b>{txt}</b><span>{P[k]}</span></div>'
    return out


def current_card(agg, cur_lg, latest_season, lang, up, league_logo_fn):
    """بطاقة الموسم الحالي بالدوري الحالي (تتحدّث مع كل بناء). "" إن لا شيء."""
    if not cur_lg:
        return ""
    d = agg.get((latest_season.get(cur_lg), cur_lg))
    if not d or not (d["matches"] or d["goals"]):
        return ""
    P = PL[lang]
    src = league_logo_fn(cur_lg, up)
    img = f'<img src="{src}" alt="" loading="lazy">' if src else ""
    cells = _stat_cells(d, lang, ("matches", "goals", "assists", "rating"))
    return (f'<div class="pscur"><a class="pslg" href="{up}{"en/" if lang == "en" else ""}leagues/{cur_lg.lower()}.html">{img}'
            f'<span>{esc(league_name(cur_lg, lang))}</span><small dir="ltr">{season_label(latest_season[cur_lg])}</small></a>'
            f'<div class="psv">{cells}</div></div>')


def matches_rows(plays, goal_rows, teams, lang, upl, logo_fn, tname_fn, limit=20, more_label=""):
    """صفوف المباريات بنمط FotMob."""
    if not plays:
        return ""
    P = PL[lang]
    gm = defaultdict(int)
    for g in goal_rows or ():
        if (g.get("detail") or "") != "Own Goal":
            gm[g["match_id"]] += 1
    out = ""
    for i, e in enumerate(plays):
        m = e["m"]
        me = e["team"]
        home = m["home_id"] == me
        opp_id = m["away_id"] if home else m["home_id"]
        opp = teams.get(opp_id)
        mg, og = (m["home_goals"], m["away_goals"]) if home else (m["away_goals"], m["home_goals"])
        res = "w" if mg > og else ("l" if mg < og else "d")
        dd = str(m["date"]).split()[0].split("-")
        dtxt = f"{int(dd[2])} {P['months'][int(dd[1]) - 1]} {dd[0]}" if len(dd) == 3 else ""
        ev = ""
        g = e.get("goals") if e.get("stats") else gm.get(e["mid"], 0)
        if g:
            ev += IC["goal"] + (f'<span class="n">{g}</span>' if g > 1 else "")
        if e.get("assists"):
            ev += IC["assist"] + (f'<span class="n">{e["assists"]}</span>' if e["assists"] > 1 else "")
        if e.get("yellow"):
            ev += '<i class="cy"></i>'
        if e.get("red"):
            ev += '<i class="cr"></i>'
        if e.get("minutes"):
            ev += f"<span>{e['minutes']}'</span>"
        rt = ""
        if e.get("rating"):
            r = float(e["rating"])
            rt = f'<span class="prt {rating_cls(r)}">{r:.1f}</span>'
        lg = logo_fn(opp) if opp else '<span class="tfnl"></span>'
        out += (f'<a class="pmr{" hidden" if i >= limit else ""}" href="{upl}matches/{e["mid"]}.html">'
                f'<div class="pmt"><span>{dtxt}</span><span>{esc(league_name(m["league_code"], lang))}</span></div>'
                f'<div class="pmm">{lg}<span class="pmo">{esc(tname_fn(opp, lang)) if opp else ""}</span>'
                f'<span class="pmres {res}">{m["home_goals"]} - {m["away_goals"]}</span>'
                f'<span class="pmev">{ev}</span>{rt}</div></a>')
    more = (f'<button class="pmore">{more_label} ({len(plays) - limit})</button>' if len(plays) > limit and more_label else "")
    return f'<div class="pml2">{out}</div>{more}'


def stats_tab(agg, lang, up, league_logo_fn):
    """شريط «الدوري الموسم ▾» + ورقة المواسم مجمَّعة بالسنة + بطاقة لكل (موسم، دوري) — الأحدث ظاهرة. "" إن لا شيء."""
    keys = sorted((k for k, d in agg.items() if d["matches"] or d["goals"]), key=lambda k: (-k[0], k[1]))
    if not keys:
        return ""
    P = PL[lang]
    first = keys[0]
    lbl = lambda k: f'{league_name(k[1], lang)} {season_label(k[0])}'
    cards = ""
    for k in keys:
        cells = _stat_cells(agg[k], lang, ("goals", "assists", "rating", "matches", "started", "mins"))
        cards += (f'<div class="pstc" data-k="{k[0]}-{k[1]}"{"" if k == first else " hidden"}><div class="psv">{cells}</div></div>')
    sheet, yr = "", None
    for k in keys:
        if k[0] != yr:
            yr = k[0]
            sheet += f'<div class="yr" dir="ltr">{season_label(yr)}</div>'
        src = league_logo_fn(k[1], up)
        img = f'<img src="{src}" alt="" loading="lazy">' if src else ""
        sheet += (f'<button type="button" class="opt{" on" if k == first else ""}" data-k="{k[0]}-{k[1]}" data-l="{esc(lbl(k))}">'
                  f'{img}<span>{esc(league_name(k[1], lang))}</span></button>')
    return (f'<button type="button" class="psel" id="psel" aria-haspopup="dialog"><span id="pselt">{esc(lbl(first))}</span><i>▾</i></button>'
            f'{cards}<div class="pssh" id="pssh"><div class="bd"></div><div class="sh" role="dialog" aria-modal="true">'
            f'<h3>{P["choose"]}</h3>{sheet}</div></div>')


def career_rows(plays, goal_rows, teams, lang, upl, logo_fn, tname_fn):
    """صف لكل (موسم، نادٍ)، الأحدث أولاً: مباريات · أهداف · صناعة · تقييم — الأعمدة الموجودة فقط."""
    rows = defaultdict(lambda: {"apps": 0, "goals": 0, "assists": None, "_r": [], "_g": False})
    for e in plays:
        r = rows[(e["m"]["season"], e["team"])]
        r["apps"] += 1
        if e.get("stats"):
            if e.get("goals"):
                r["goals"] += e["goals"]
                r["_g"] = True
            if e.get("assists") is not None:
                r["assists"] = (r["assists"] or 0) + e["assists"]
            if e.get("rating"):
                r["_r"].append(float(e["rating"]))
    for g in goal_rows or ():
        if (g.get("detail") or "") == "Own Goal":
            continue
        r = rows[(g["season"], g["team_id"])]
        if not r["_g"]:
            r.setdefault("_gg", 0)
            r["_gg"] = r.get("_gg", 0) + 1
    for r in rows.values():
        if not r["_g"]:
            r["goals"] = r.get("_gg", 0)
        r["rating"] = round(sum(r["_r"]) / len(r["_r"]), 2) if r["_r"] else None
    if not rows:
        return ""
    for r in rows.values():
        if not r["apps"]:
            r["apps"] = None   # بلا تشكيلات/إحصائيات لذاك الموسم: لا مصدر للمباريات (لا «0»)
    show = {"apps": any(r["apps"] for r in rows.values()), "goals": True,
            "assists": any(r["assists"] is not None for r in rows.values()),
            "rating": any(r["rating"] is not None for r in rows.values())}
    cols = [c for c in ("apps", "goals", "assists", "rating") if show[c]]
    tmpl = "minmax(0,1fr) " + " ".join("44px" for _ in cols)
    icon = {"apps": IC["apps"], "goals": IC["goal"], "assists": IC["assist"], "rating": IC["rating"]}
    P = PL[lang]
    names = {"apps": P["matches"], "goals": P["goals"], "assists": P["assists"], "rating": P["rating"]}
    head = (f'<div class="pcr hd" style="grid-template-columns:{tmpl}"><span></span>'
            + "".join(f'<span class="c" title="{names[c]}" aria-label="{names[c]}">{icon[c]}</span>' for c in cols) + '</div>')
    body = ""
    for (season, tid) in sorted(rows, key=lambda k: (-k[0], k[1])):
        r = rows[(season, tid)]
        tm = teams.get(tid)
        lg = logo_fn(tm) if tm else '<span class="tfnl"></span>'
        cells = ""
        for c in cols:
            v = r.get(c)
            cells += f'<span class="c">{"" if v is None else (f"{v:.2f}" if c == "rating" else v)}</span>'
        body += (f'<div class="pcr" style="grid-template-columns:{tmpl}"><a class="pcl" href="{upl}clubs/{tid}.html">{lg}'
                 f'<span><b>{esc(tname_fn(tm, lang)) if tm else tid}</b><small dir="ltr">{season_label(season)}</small></span></a>'
                 f'{cells}</div>')
    return f'<div class="pcar">{head}{body}</div>'


def stats_select_script():
    """ورقة اختيار الموسم بتبويب الإحصائيات (لا تخزين)."""
    return ('<script>\n(function(){\n'
            'var b=document.getElementById("psel"),sh=document.getElementById("pssh");if(!b||!sh)return;\n'
            'var tl=document.getElementById("pselt");\n'
            'function close(){sh.classList.remove("on");document.body.style.overflow="";}\n'
            'b.addEventListener("click",function(){sh.classList.add("on");document.body.style.overflow="hidden";});\n'
            'sh.querySelector(".bd").addEventListener("click",close);\n'
            'document.addEventListener("keydown",function(e){if(e.key==="Escape")close();});\n'
            'sh.querySelectorAll("button.opt").forEach(function(o){o.addEventListener("click",function(){\n'
            'var k=o.getAttribute("data-k");\n'
            'document.querySelectorAll(".pstc").forEach(function(c){c.hidden=c.getAttribute("data-k")!==k;});\n'
            'sh.querySelectorAll("button.opt").forEach(function(x){x.classList.toggle("on",x===o);});\n'
            'tl.textContent=o.getAttribute("data-l");close();});});\n'
            '})();\n</script>')
