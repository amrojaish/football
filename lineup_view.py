#!/usr/bin/env python3
"""
عرض التشكيلات — ملعب مرسوم
=============================
وحدة مستقلة. لا تشغّلها لحالها — `make_matches.py` بيستوردها.

بترسم لكل فريق ملعباً بالخطة الفعلية، اللاعبون موزّعون حسب
عمود `grid` القادم من المزوّد بصيغة "صف:عمود".

    الصف 1 = الحارس   ← أسفل الملعب
    الصف الأخير = المهاجمون ← أعلى الملعب

**التقييم دائماً ظاهر** كشارة على قميص اللاعب:
    أخضر  ≥ 7.5
    رمادي  6.5 – 7.5
    أحمر  < 6.5

⚠️ **التغطية: السعودي فقط** — المزوّد لا يوفّر تشكيلات للأردني
   ولا العراقي (درس 25). الدالة ترجع "" لهما، فلا يظهر القسم.

⚠️ **الاسم من `lineup_players` حصراً.** المزوّد يرجع اسمين
   مختلفين لنفس اللاعب:
       lineup_players : S. Al Hawsawi      (مختصر)
       player_stats   : Alhwsawi Sanousi Mohammed  (كامل)
   الربط بـ`player_id` لا بالاسم، والعرض من مصدر واحد فقط
   حتى لا يظهر اللاعب باسمين في نفس الصفحة.

⚠️ **الارتداد:** 132 لاعباً من 20,394 بلا `grid` (0.65%). لو نقص
   `grid` لأي أساسي في فريق، يُعرض ذلك الفريق **كقائمة نصية**
   بدل ملعب ناقص.

⚠️ الملعب `direction:ltr` دائماً — الملعب شيء مادي، ولا يُعكس
   بعكس اتجاه الصفحة (درس RTL 15).

الاستخدام:
    from lineup_view import LINEUP_CSS, build_lineups
"""

from collections import defaultdict

# الدوريات التي يوفّر المزوّد تشكيلاتها (درس 25)
LINEUP_LEAGUES = {"SAU"}

# حدود ألوان التقييم
RATE_GOOD = 7.5
RATE_BAD = 6.5


LINEUP_CSS = """
  .lu { margin-top:10px; }
  .luteam { background:var(--card); border:1px solid var(--line);
            border-radius:12px; padding:14px; margin-bottom:14px; }
  .luhead { display:flex; justify-content:space-between;
            align-items:center; gap:10px; margin-bottom:12px;
            flex-wrap:wrap; }
  .luname { display:flex; align-items:center; gap:8px;
            font-size:15px; font-weight:600; }
  .luname img { width:22px; height:22px; object-fit:contain; }
  .luform { color:var(--muted); font-size:13px; }
  .lucoach { color:var(--muted); font-size:12px; margin-top:2px; }

  .pitch { direction:ltr; background:var(--deep);
           border:1px solid var(--line); border-radius:10px;
           padding:14px 6px; display:flex; flex-direction:column-reverse;
           gap:10px; position:relative; overflow:hidden; }
  .pitch::before { content:""; position:absolute; left:8%; right:8%;
                   top:50%; border-top:1px dashed var(--line); }
  .prow { display:flex; justify-content:space-around;
          align-items:flex-start; gap:2px; position:relative; }

  .pp { display:flex; flex-direction:column; align-items:center;
        gap:3px; width:19%; min-width:44px; }
  .shirt { position:relative; width:32px; height:32px;
           border-radius:50%; background:var(--card2);
           border:1px solid var(--line); display:flex;
           align-items:center; justify-content:center;
           font-size:13px; font-weight:600; color:var(--text); }
  .rate { position:absolute; top:-5px; right:-7px; font-size:10px;
          padding:1px 4px; border-radius:5px; color:#fff;
          line-height:1.3; font-weight:600; }
  .rate.g { background:var(--green); }
  .rate.m { background:var(--muted); }
  .rate.b { background:var(--red); }
  .cap { position:absolute; bottom:-4px; left:-6px; font-size:9px;
         background:var(--accent); color:#fff; border-radius:4px;
         padding:0 3px; }
  .pn { font-size:10px; color:var(--muted); text-align:center;
        line-height:1.25; word-break:break-word; }

  .subs { margin-top:12px; }
  .subs h4 { font-size:12px; color:var(--muted); margin-bottom:6px;
             font-weight:600; }
  .sublist { display:flex; flex-wrap:wrap; gap:6px; }
  .sub { background:var(--card2); border:1px solid var(--line);
         border-radius:7px; padding:4px 9px; font-size:12px;
         display:flex; align-items:center; gap:5px; }
  .sub .num { color:var(--muted); font-size:11px; }
  .sub .r { font-size:10px; padding:0 4px; border-radius:4px;
            color:#fff; }
  .sub .r.g { background:var(--green); }
  .sub .r.m { background:var(--muted); }
  .sub .r.b { background:var(--red); }

  .lulist { display:flex; flex-wrap:wrap; gap:6px; }
  .lunote { color:var(--muted); font-size:12px; margin-bottom:8px; }
"""


def _rate_class(r):
    if r is None:
        return ""
    if r >= RATE_GOOD:
        return "g"
    if r < RATE_BAD:
        return "b"
    return "m"


def _pname(row, lang):
    """الاسم باللغة المطلوبة — يرتد للإنجليزي عند غياب الترجمة"""
    ar = (row["player_ar"] or "").strip()
    en = (row["player_en"] or "").strip()
    if lang == "ar" and ar:
        return ar
    return en or ar or "—"


def _rate_badge(rating, cls_prefix="rate"):
    if rating is None:
        return ""
    cls = _rate_class(rating)
    return (f'<span class="{cls_prefix} {cls}">'
            f'{rating:.1f}</span>')


def _player_chip(row, rating, captain, lang):
    """لاعب واحد على الملعب"""
    num = row["number"]
    num_txt = str(num) if num is not None else "—"
    cap = '<span class="cap">C</span>' if captain else ""

    return (
        f'<div class="pp">'
        f'<span class="shirt">{num_txt}'
        f'{_rate_badge(rating)}{cap}</span>'
        f'<span class="pn">{_pname(row, lang)}</span>'
        f'</div>'
    )


def _text_fallback(starters, ratings, caps, lang):
    """قائمة نصية — حين ينقص grid لأي أساسي"""
    out = ""
    for r in starters:
        pid = r["player_id"]
        num = r["number"]
        num_txt = f'<span class="num">{num}</span>' if num else ""
        cap = '<span class="cap">C</span>' if caps.get(pid) else ""
        out += (f'<span class="sub">{num_txt}'
                f'{_pname(r, lang)}'
                f'{_rate_badge(ratings.get(pid), "r")}{cap}</span>')
    return f'<div class="lulist">{out}</div>'


def _build_pitch(starters, ratings, caps, lang):
    """
    يرجع (html, ok).
    ok=False إن نقص grid لأي أساسي — عندها يستعمل النداء
    الأعلى القائمة النصية.
    """
    rows = defaultdict(list)

    for r in starters:
        g = (r["grid"] or "").strip()
        if ":" not in g:
            return "", False
        try:
            line, col = g.split(":", 1)
            rows[int(line)].append((int(col), r))
        except ValueError:
            return "", False

    if not rows:
        return "", False

    html = ""
    for line in sorted(rows):
        cells = ""
        for _, r in sorted(rows[line]):
            pid = r["player_id"]
            cells += _player_chip(r, ratings.get(pid),
                                  caps.get(pid), lang)
        html += f'<div class="prow">{cells}</div>'

    return f'<div class="pitch">{html}</div>', True


def _build_subs(subs, ratings, caps, lang, t):
    """قائمة البدلاء — التقييم يظهر لمن شارك فقط"""
    if not subs:
        return ""

    out = ""
    for r in subs:
        pid = r["player_id"]
        num = r["number"]
        num_txt = f'<span class="num">{num}</span>' if num else ""
        cap = '<span class="cap">C</span>' if caps.get(pid) else ""
        out += (f'<span class="sub">{num_txt}'
                f'{_pname(r, lang)}'
                f'{_rate_badge(ratings.get(pid), "r")}{cap}</span>')

    return (f'<div class="subs"><h4>{t["subs"]}</h4>'
            f'<div class="sublist">{out}</div></div>')


def _team_block(conn, mid, team, team_html_name, logo, lang, t):
    """كتلة فريق واحد: رأس + ملعب + بدلاء"""
    tid = team

    info = conn.execute("""
        SELECT formation, coach_en, coach_ar
        FROM lineups WHERE match_id = ? AND team_id = ?
    """, (mid, tid)).fetchone()

    players = list(conn.execute("""
        SELECT player_id, player_en, player_ar, number, pos,
               grid, starter
        FROM lineup_players
        WHERE match_id = ? AND team_id = ?
    """, (mid, tid)))

    if not players:
        return ""

    # التقييمات — الربط بـplayer_id لا بالاسم
    ratings, caps = {}, {}
    for r in conn.execute("""
            SELECT player_id, rating, captain, minutes
            FROM player_stats WHERE match_id = ? AND team_id = ?
        """, (mid, tid)):
        if r["rating"] is not None:
            ratings[r["player_id"]] = r["rating"]
        if r["captain"]:
            caps[r["player_id"]] = 1

    starters = [p for p in players if p["starter"]]
    subs = [p for p in players if not p["starter"]]

    pitch, ok = _build_pitch(starters, ratings, caps, lang)
    if not ok:
        pitch = (f'<div class="lunote">{t["lu_nogrid"]}</div>'
                 + _text_fallback(starters, ratings, caps, lang))

    formation = ""
    coach = ""
    if info:
        f = (info["formation"] or "").strip()
        if f:
            formation = f'<span class="luform">{t["formation"]} {f}</span>'
        c_ar = (info["coach_ar"] or "").strip()
        c_en = (info["coach_en"] or "").strip()
        c = c_ar if (lang == "ar" and c_ar) else c_en
        if c:
            coach = f'<div class="lucoach">{t["coach"]}: {c}</div>'

    return (
        f'<div class="luteam">'
        f'<div class="luhead">'
        f'<span class="luname"><img src="{logo}" alt="">'
        f'{team_html_name}</span>{formation}</div>'
        f'{coach}'
        f'{pitch}'
        f'{_build_subs(subs, ratings, caps, lang, t)}'
        f'</div>'
    )


def build_lineups(conn, m, h, a, lang, T,
                  tname, logo_url):
    """
    قسم التشكيلات كاملاً — يرجع "" إن لم توجد داتا.

    m         : صف المباراة
    h, a      : قاموسا الناديين
    tname     : دالة اسم النادي  (من make_matches)
    logo_url  : دالة رابط الشعار (من make_matches)
    """
    if m["league_code"] not in LINEUP_LEAGUES:
        return ""

    t = T[lang]
    mid = m["match_id"]

    try:
        n = conn.execute("""
            SELECT COUNT(*) FROM lineups WHERE match_id = ?
        """, (mid,)).fetchone()[0]
    except Exception:
        return ""

    if not n:
        return ""

    blocks = ""
    for team_row, tid in ((h, m["home_id"]), (a, m["away_id"])):
        blocks += _team_block(conn, mid, tid,
                              tname(team_row, lang),
                              logo_url(team_row, lang),
                              lang, t)

    if not blocks:
        return ""

    return f'<h2>{t["lineups"]}</h2><div class="lu">{blocks}</div>'
