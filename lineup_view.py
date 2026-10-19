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

⚠️ **التغطية داتا-محورة لا مقفلة بدوري:** الدالة تتحقق من وجود
   صفوف فعلية بـ`lineups` لكل مباراة وترجع "" إن لم توجد — لا
   قائمة دوريات ثابتة. الأردني والعراقي يرجعان "" تلقائياً لأن
   المزوّد لا يوفّر لهما تشكيلات أصلاً (درس 25)، لا بسبب استثناء
   مكتوب هنا. ⚠️ **حتى 4 سبتمبر كان هنا `LINEUP_LEAGUES = {"SAU"}`
   يقفل القسم على السعودي وحده صراحة** — فبقيت تشكيلات المصري
   والإماراتي مخزَّنة بالديتابيس ولا تظهر على الموقع إطلاقاً رغم
   اكتمالها، بلا أي رسالة خطأ (نفس نمط درس 21: سكربت قديم كُتب
   وقت ما كان السعودي الدوري الوحيد بتشكيلات، وافتراضه الصامت بقي
   بعد ما صار غيره يملك نفس الداتا). أُزيل القفل ليعتمد على الداتا
   الفعلية فقط.

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

# ⚠️ **التسميات محلية هنا لا في i18n.py.** خمسة وعشرون حقلاً
#    تخصّ هذه الوحدة وحدها؛ إضافتها لـi18n تضخّمه بمفاتيح لا
#    يستعملها أحد غيرها. النمط نفسه المتبع في make_matches.py.
STAT_SECTIONS = [
    ("gen", "عام", "General", [
        ("minutes", "الدقائق", "Minutes", None),
        ("rating", "التقييم", "Rating", None),
    ]),
    ("att", "هجوم", "Attack", [
        ("goals", "أهداف", "Goals", None),
        ("assists", "صناعة", "Assists", None),
        ("shots_total", "تسديدات", "Shots", "shots_on"),
        ("dribbles_try", "مراوغات", "Dribbles", "dribbles_ok"),
    ]),
    ("pas", "تمرير", "Passing", [
        # ⚠️ `passes_pct` **عدد التمريرات الصحيحة لا نسبة مئوية** —
        #    رغم اسمه. فُحص على 26,926 سجلاً: 100% منها
        #    passes_pct ≤ passes_total، و30 سجلاً تتجاوز 100.
        #    عرضه كنسبة كان يُظهر حارساً مرّر 20 بدقة "15%".
        ("passes_total", "تمريرات", "Passes", "passes_pct"),
        ("passes_key", "تمريرات مفتاحية", "Key passes", None),
    ]),
    ("def", "دفاع", "Defence", [
        ("tackles", "تدخلات", "Tackles", None),
        ("interceptions", "اعتراضات", "Interceptions", None),
        ("blocks", "تصديات دفاعية", "Blocks", None),
        ("duels_total", "مواجهات", "Duels", "duels_won"),
    ]),
    ("gk", "حراسة", "Goalkeeping", [
        ("saves", "تصديات", "Saves", None),
        ("conceded", "أهداف مستقبَلة", "Conceded", None),
        ("pen_saved", "ركلات جزاء مصدودة", "Penalties saved", None),
    ]),
    ("dis", "انضباط", "Discipline", [
        ("fouls_made", "أخطاء مرتكبة", "Fouls", None),
        ("fouls_drawn", "أخطاء عليه", "Fouls drawn", None),
        ("yellow", "إنذارات", "Yellow", None),
        ("red", "طرد", "Red", None),
        ("pen_scored", "ركلات جزاء مسجّلة", "Penalties scored", None),
        ("pen_missed", "ركلات جزاء ضائعة", "Penalties missed", None),
    ]),
]

# الحقول التي تُعرض حتى لو كانت صفراً (البقية تُخفى)
SHOW_ZERO = {"minutes", "rating", "conceded"}

# حقول تُعرض مع نسبتها المئوية بجانب النسبة الخام
WITH_PCT = {"passes_total", "duels_total", "dribbles_try", "shots_total"}

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
  .rate { position:absolute; top:-11px; right:-12px; font-size:12px;
          padding:1px 4px; border-radius:5px; color:#fff;
          line-height:1.3; font-weight:600; }
  .rate.g { background:var(--green); }
  .rate.m { background:var(--muted); }
  .rate.b { background:var(--red); }
  .cap { position:absolute; bottom:-4px; left:-6px; font-size:12px;
         background:var(--accent); color:#fff; border-radius:4px;
         padding:0 3px; }
  .pn { font-size:12px; color:var(--muted); text-align:center;
        line-height:1.25; word-break:break-word; }

  .subs { margin-top:12px; }
  .subs h4 { font-size:12px; color:var(--muted); margin-bottom:6px;
             font-weight:600; }
  .sublist { display:flex; flex-wrap:wrap; gap:6px; }
  .sub { background:var(--card2); border:1px solid var(--line);
         border-radius:7px; padding:4px 9px; font-size:12px;
         display:flex; align-items:center; gap:5px; }
  .sub .num { color:var(--muted); font-size:12px; }
  .sub .r { font-size:12px; padding:0 4px; border-radius:4px;
            color:#fff; }
  .sub .r.g { background:var(--green); }
  .sub .r.m { background:var(--muted); }
  .sub .r.b { background:var(--red); }

  .lulist { display:flex; flex-wrap:wrap; gap:6px; }

  /* لوحة تفاصيل اللاعب */
  .pp, .sub.cl { cursor:pointer; }
  .pp:hover .shirt, .sub.cl:hover { border-color:var(--accent); }
  .stovl { position:fixed; inset:0; background:rgba(0,0,0,.72);
           display:none; align-items:center; justify-content:center;
           z-index:960; padding:18px; }
  .stovl.on { display:flex; }
  .stbox { background:var(--card); border:1px solid var(--line);
           border-radius:16px; width:100%; max-width:440px;
           max-height:82vh; overflow-y:auto; padding:18px; }
  .sthead { display:flex; align-items:center; gap:10px;
            margin-bottom:4px; }
  .sthead .nm { font-size:16px; font-weight:600; flex:1;
                min-width:0; }
  .stsub { color:var(--muted); font-size:12px; margin-bottom:14px; }
  .stsec { margin-bottom:12px; }
  .stsec h4 { font-size:12px; color:var(--muted); font-weight:600;
              margin-bottom:5px; letter-spacing:.3px; }
  .strow { display:flex; justify-content:space-between;
           padding:6px 2px; border-bottom:1px solid var(--line);
           font-size:13px; }
  .stsec .strow:last-child { border-bottom:none; }
  .strow .v { font-weight:600; }
  .stclose { display:block; width:100%; margin-top:8px;
             background:var(--card2); color:var(--text);
             border:1px solid var(--line); border-radius:10px;
             padding:11px; font-size:14px; cursor:pointer;
             font-family:inherit; }
  .stnone { color:var(--muted); font-size:13px; padding:10px 0; }
  .lunote { color:var(--muted); font-size:12px; margin-bottom:8px; }

  /* ملعب واحد للفريقين (12 أكتوبر، نمط FotMob بلا صور): المضيف بالنصف العلوي والضيف بالسفلي، اللاعبون بمواقع grid؛ يظهر فقط حين
     للفريقين خطة + 11 grid، وإلا تبقى القوائم/الملاعب القديمة كما كانت. */
  .fpitch { --pitch:#1f4d31; --pl:rgba(255,255,255,.4); direction:ltr; position:relative; width:100%;
            aspect-ratio:2/3; border-radius:12px; overflow:hidden; background:var(--pitch);
            margin:10px 0 14px; border:1px solid var(--line); }
  :root[data-theme="light"] .fpitch { --pitch:#4a9a64; --pl:rgba(255,255,255,.75); }
  .fpitch svg { position:absolute; inset:0; width:100%; height:100%; }
  .fpitch svg * { fill:none; stroke:var(--pl); stroke-width:1.2; vector-effect:non-scaling-stroke; }
  .fpt { position:absolute; inset-inline-start:8px; display:flex; align-items:center; gap:6px; z-index:3;
         background:rgba(0,0,0,.45); color:#fff; border-radius:12px; padding:3px 9px 3px 4px; font-size:12px;
         font-weight:600; max-width:80%; }
  .fpt img { width:18px; height:18px; object-fit:contain; background:#fff; border-radius:50%; padding:1px; }
  .fpt span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; direction:auto; }
  .fpt.top { top:8px; }
  .fpt.bot { bottom:8px; }
  .fp { position:absolute; transform:translate(-50%,-50%); width:68px; display:flex; flex-direction:column;
        align-items:center; z-index:2; }
  .fs { position:relative; width:30px; height:30px; border-radius:50%; display:flex; align-items:center;
        justify-content:center; font-size:12px; font-weight:700; color:#fff;
        border:2px solid rgba(255,255,255,.9); box-shadow:0 1px 3px rgba(0,0,0,.45); }
  .fs.h { background:#2f81f7; }
  .fs.a { background:#d29922; color:#1a1300; }
  .fn { margin-top:2px; font-size:10px; line-height:1.15; color:#fff; text-align:center; max-width:68px;
        text-shadow:0 1px 2px rgba(0,0,0,.8); display:-webkit-box; -webkit-line-clamp:2;
        -webkit-box-orient:vertical; overflow:hidden; direction:auto; unicode-bidi:plaintext; }
  .fi { position:absolute; font-size:10px; line-height:1; background:rgba(0,0,0,.65); border-radius:8px;
        padding:1px 2px; color:#fff; }
  .fi.c { top:-5px; left:-6px; font-weight:800; font-size:9px; background:#d29922; color:#1a1300; }
  .fi.g { top:-6px; right:-8px; }
  .fi.k { bottom:-4px; right:-8px; }
  .fi.o { bottom:-4px; left:-8px; color:#f85149; }
  .fi.r { bottom:-4px; left:50%; transform:translateX(-50%); font-size:9px; font-weight:700; }
  .fp[data-p] { cursor:pointer; }
  /* التشكيلة الحيّة (19 أكتوبر 2026): شارة فوق الملعب المرسوم من /lineup قبل أن يحملها البناء الثابت */
  .lubadge { display:inline-block; margin:2px 0 4px; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:700;
             background:var(--accent); color:#fff; }
"""


def _stat_rows(st, lang):
    """أقسام الإحصائيات — يُخفى الفارغ والصفري إلا المستثنى"""
    if not st:
        return ""

    is_gk = (st.get("pos") or "") == "G"
    out = ""

    for key, ar, en, fields in STAT_SECTIONS:
        # ⚠️ قسم الحراسة للحارس فقط، وبقية الأقسام لغيره —
        #    عرض "تصديات: 0" لمهاجم ضجيج لا معلومة.
        if key == "gk" and not is_gk:
            continue
        rows = ""
        for f, lab_ar, lab_en, pair in fields:
            v = st.get(f)
            if v is None:
                continue
            if not v and f not in SHOW_ZERO:
                continue
            if pair is not None:
                p = st.get(pair)
                if p is None:
                    val = str(v)
                elif f in WITH_PCT and v:
                    val = f"{p}/{v} ({round(p / v * 100)}%)"
                else:
                    val = f"{p}/{v}"
            else:
                val = str(v)
            lab = lab_ar if lang == "ar" else lab_en
            rows += (f'<div class="strow"><span>{lab}</span>'
                     f'<span class="v">{val}</span></div>')
        if rows:
            head = ar if lang == "ar" else en
            out += f'<div class="stsec"><h4>{head}</h4>{rows}</div>'

    return out


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

    pid = row["player_id"]
    click = f' data-p="{pid}"' if pid is not None and pid > 0 else ""
    return (
        f'<div class="pp"{click}>'
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
        cl = ' class="sub cl" data-p="%s"' % pid if pid is not None and pid > 0 \
            else ' class="sub"'
        out += (f'<span{cl}>{num_txt}'
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
        cl = ' class="sub cl" data-p="%s"' % pid if pid is not None and pid > 0 \
            else ' class="sub"'
        out += (f'<span{cl}>{num_txt}'
                f'{_pname(r, lang)}'
                f'{_rate_badge(ratings.get(pid), "r")}{cap}</span>')

    return (f'<div class="subs"><h4>{t["subs"]}</h4>'
            f'<div class="sublist">{out}</div></div>')


def _parse_grid(g):
    g = (g or "").strip()
    if ":" not in g:
        return None
    try:
        a, b = g.split(":", 1)
        return int(a), int(b)
    except ValueError:
        return None


def _load_team(conn, mid, tid):
    """(formation, starters, ratings, caps, stat_rows) لفريق بمباراة — للملعب الموحَّد."""
    info = conn.execute("SELECT formation FROM lineups WHERE match_id = ? AND team_id = ?", (mid, tid)).fetchone()
    players = list(conn.execute("""
        SELECT player_id, player_en, player_ar, number, pos, grid, starter
        FROM lineup_players WHERE match_id = ? AND team_id = ?""", (mid, tid)))
    stats = {}
    for r in conn.execute("SELECT * FROM player_stats WHERE match_id = ? AND team_id = ?", (mid, tid)):
        if r["player_id"] is not None:
            stats[r["player_id"]] = r
    formation = (info["formation"] or "").strip() if info else ""
    return formation, [p for p in players if p["starter"]], stats


def _pitch_ready(formation, starters):
    """خطة + 11 أساسياً بـgrid صالح وفريد لكل منهم (وإلا يبقى العرض القديم)."""
    if not formation or len(starters) != 11:
        return False
    seen = set()
    for p in starters:
        g = _parse_grid(p["grid"])
        if g is None or g in seen:
            return False
        seen.add(g)
    return True


def _full_pitch(conn, mid, home, away, lang, t):
    """
    ملعب واحد (SVG للخطوط + عناصر مطلقة): home أعلى، away أسفل. خطوط الـgrid: الصف 1 = الحارس.
    ⚠️ العمود يزداد من يسار الفريق إلى يمينه بمنظوره: الفريق السفلي (يهاجم للأعلى) يسار→يمين كما هو،
       والعلوي (يهاجم للأسفل) معكوس. ترجع "" إن لم يكن للفريقين خطة + 11 grid.
    home/away: (team_id, name, logo).
    """
    data = {}
    for key, (tid, _nm, _lg) in (("h", home), ("a", away)):
        f, st, stats = _load_team(conn, mid, tid)
        if not _pitch_ready(f, st):
            return ""
        data[key] = (f, st, stats)
    out_names, in_names = set(), set()
    try:
        for e in conn.execute("SELECT player_en, assist_en FROM events WHERE match_id = ? AND type = 'subst'", (mid,)):
            if e["player_en"]:
                out_names.add(e["player_en"].strip())
    except Exception:
        pass

    html = ""
    for key, (tid, nm, lg) in (("h", home), ("a", away)):
        f, st, stats = data[key]
        rows = defaultdict(list)
        for p in st:
            r, c = _parse_grid(p["grid"])
            rows[r].append((c, p))
        lines = sorted(rows)
        nlines = len(lines)
        for k, r in enumerate(lines):
            cells = sorted(rows[r], key=lambda x: x[0])
            n = len(cells)
            frac = (k / (nlines - 1)) if nlines > 1 else 0
            y = (7 + frac * 37) if key == "h" else (93 - frac * 37)
            for i, (_c, p) in enumerate(cells):
                xi = (n - 1 - i) if key == "h" else i
                x = (xi + 1) / (n + 1) * 100
                pid = p["player_id"]
                srow = stats.get(pid)
                icons = ""
                if srow is not None:
                    if srow["captain"]:
                        icons += '<span class="fi c">C</span>'
                    g = srow["goals"] or 0
                    if g:
                        icons += f'<span class="fi g">&#9917;{"" if g == 1 else g}</span>'
                    if srow["red"]:
                        icons += '<span class="fi k">&#128997;</span>'
                    elif srow["yellow"]:
                        icons += '<span class="fi k">&#129000;</span>'
                    rt = srow["rating"]
                    if rt is not None:
                        icons += f'<span class="fi r">{rt:.1f}</span>'
                if (p["player_en"] or "").strip() in out_names:
                    icons += '<span class="fi o">&#8595;</span>'
                num = p["number"]
                click = f' data-p="{pid}"' if pid is not None and pid > 0 else ""
                html += (f'<div class="fp"{click} style="left:{x:.1f}%;top:{y:.1f}%">'
                         f'<span class="fs {key}">{num if num is not None else "—"}{icons}</span>'
                         f'<span class="fn">{_pname(p, lang)}</span></div>')
        form_txt = f' <bdi dir="ltr">{f}</bdi>' if f else ""   # الأرقام LTR: 4-4-2 لا 2-4-4 داخل نص عربي
        html += (f'<div class="fpt {"top" if key == "h" else "bot"}"><img src="{lg}" alt="">'
                 f'<span>{nm}{form_txt}</span></div>')

    return f'<div class="fpitch">{PITCH_SVG}{html}</div>'


# خطوط الملعب: مشتركة بين الملعب الثابت والتشكيلة الحيّة (LIVE_LINEUP_SCRIPT)
PITCH_SVG = ('<svg viewBox="0 0 200 300" preserveAspectRatio="none" aria-hidden="true">'
             '<rect x="4" y="4" width="192" height="292"/><line x1="4" y1="150" x2="196" y2="150"/>'
             '<circle cx="100" cy="150" r="26"/>'
             '<rect x="50" y="4" width="100" height="44"/><rect x="76" y="4" width="48" height="16"/>'
             '<rect x="50" y="252" width="100" height="44"/><rect x="76" y="280" width="48" height="16"/></svg>')


def _team_block(conn, mid, team, team_html_name, logo, lang, t, stats, pitch_on=True):
    """كتلة فريق واحد: رأس + ملعب + بدلاء.
    `stats` قاموس يُملأ هنا: player_id -> صف player_stats كاملاً."""
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

    # التقييمات والإحصائيات — الربط بـplayer_id لا بالاسم
    ratings, caps = {}, {}
    for r in conn.execute("""
            SELECT * FROM player_stats
            WHERE match_id = ? AND team_id = ?
        """, (mid, tid)):
        pid = r["player_id"]
        if r["rating"] is not None:
            ratings[pid] = r["rating"]
        if r["captain"]:
            caps[pid] = 1
        if pid is not None:
            stats[pid] = {k: r[k] for k in r.keys()}

    starters = [p for p in players if p["starter"]]
    subs = [p for p in players if not p["starter"]]

    pitch, ok = _build_pitch(starters, ratings, caps, lang)
    if not ok:
        pitch = (f'<div class="lunote">{t["lu_nogrid"]}</div>'
                 + _text_fallback(starters, ratings, caps, lang))
    if not pitch_on:
        pitch = ""   # الملعب الموحَّد فوق: هنا المدرب + البدلاء فقط

    formation = ""
    coach = ""
    if info:
        f = (info["formation"] or "").strip()
        if f:
            formation = f'<span class="luform">{t["formation"]} <bdi dir="ltr">{f}</bdi></span>'
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

    stats = {}
    blocks = ""
    full = _full_pitch(conn, mid,
                       (m["home_id"], tname(h, lang), logo_url(h, lang)),
                       (m["away_id"], tname(a, lang), logo_url(a, lang)), lang, t)
    for team_row, tid in ((h, m["home_id"]), (a, m["away_id"])):
        blocks += _team_block(conn, mid, tid,
                              tname(team_row, lang),
                              logo_url(team_row, lang),
                              lang, t, stats, pitch_on=not full)

    if not blocks:
        return ""

    # ⚠️ **الأسماء من lineup_players لا من player_stats** — المزوّد
    #    يرجع اسمين مختلفين لنفس اللاعب، فنُبقي مصدراً واحداً
    #    للعرض حتى لا يظهر باسمين في الصفحة ذاتها.
    names = {}
    for r in conn.execute("""
            SELECT player_id, player_en, player_ar, number, pos
            FROM lineup_players WHERE match_id = ?
        """, (mid,)):
        if r["player_id"] is not None:
            names[r["player_id"]] = (_pname(r, lang), r["number"],
                                     r["pos"] or "")

    panels = _panels(stats, names, lang)
    if not panels:
        return f'<h2>{t["lineups"]}</h2>{full}<div class="lu">{blocks}</div>'

    close = "إغلاق" if lang == "ar" else "Close"
    overlay = (
        f'<div class="stovl" id="stovl"><div class="stbox">'
        f'<div class="sthead"><span class="nm" id="stnm"></span></div>'
        f'<div class="stsub" id="stsub"></div>'
        f'<div id="stbody"></div>'
        f'<button class="stclose" id="stclose">{close}</button>'
        f'</div></div>'
    )
    return (f'<h2>{t["lineups"]}</h2>{full}<div class="lu">{blocks}</div>'
            f'{overlay}{panels}')


def _panels(stats, names, lang):
    """
    لوحات التفاصيل — تُبنى بالكامل وقت التوليد لا بالمتصفح.

    ⚠️ **HTML جاهز لا JSON.** بناء الصفوف في JavaScript كان يعني
       تكرار منطق الإخفاء والنِّسب والتسميات بلغتين داخل السكربت.
       هنا يُبنى كل شيء في بايثون ويُخزَّن مخفياً، والسكربت
       ينسخه فقط. النتيجة: بضع كيلوبايتات مقابل صفر منطق مكرر.

    ⚠️ لا يُبنى شيء للاعب بلا إحصائيات — الضغط عليه لا يفتح شيئاً.
    """
    POS_LABEL = {'G': ('حارس مرمى', 'Goalkeeper'),
                 'D': ('مدافع', 'Defender'),
                 'M': ('وسط', 'Midfielder'),
                 'F': ('مهاجم', 'Forward')}
    out = ""
    for pid, st in stats.items():
        # ⚠️ لا لوحة للاعب لا شريحة له. `player_stats` قد يحوي
        #    لاعبين غائبين عن `lineup_players` لنفس المباراة —
        #    لوحاتهم لا يفتحها شيء، وأسماؤهم تأتي من المصدر
        #    الآخر فتظهر بصيغة مختلفة (تحذير رأس الملف).
        if pid not in names:
            continue
        rows = _stat_rows(st, lang)
        if not rows:
            continue
        nm, num, pos = names[pid]
        pos = pos or (st.get("pos") or "")
        bits = []
        if num is not None:
            bits.append(("رقم " if lang == "ar" else "No. ") + str(num))
        pl = POS_LABEL.get(pos)
        if pl:
            bits.append(pl[0] if lang == "ar" else pl[1])
        sub = " · ".join(bits)
        out += (f'<div class="stp" id="stp{pid}" style="display:none" '
                f'data-nm="{nm}" data-sub="{sub}">{rows}</div>')
    return f'<div style="display:none">{out}</div>' if out else ""


LINEUP_SCRIPT = """
<script>
(function(){
  var ovl=document.getElementById('stovl');
  if(!ovl)return;
  var nm=document.getElementById('stnm');
  var sb=document.getElementById('stsub');
  var bd=document.getElementById('stbody');

  function open(pid){
    var src=document.getElementById('stp'+pid);
    if(!src)return;                 // لاعب بلا إحصائيات
    nm.textContent=src.getAttribute('data-nm')||'';
    sb.textContent=src.getAttribute('data-sub')||'';
    bd.innerHTML=src.innerHTML;
    ovl.classList.add('on');
  }
  function close(){ ovl.classList.remove('on'); }

  document.querySelectorAll('[data-p]').forEach(function(el){
    el.addEventListener('click',function(){ open(this.dataset.p); });
  });
  var cb=document.getElementById('stclose');
  if(cb)cb.addEventListener('click',close);
  ovl.addEventListener('click',function(e){ if(e.target===ovl)close(); });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape')close();
  });
})();
</script>"""


# ── التشكيلة الحيّة (19 أكتوبر 2026) ──
# صفحة مباراة بلا تشكيلة ثابتة (قادمة، أو انتهت منذ أقل من 36 ساعة) تحمل لوحة «التشكيلات» مخفية + زرها مخفياً. LIVE_LINEUP_SCRIPT يجلب
# /lineup?id= من الـworker (يكتبه sendLineups بين KO-60 و KO+5) ويرسم الملعب نفسه (_full_pitch/_team_block) ثم يُظهر التبويب.
# البناء الثابت يغلب: حين تصل التشكيلة لجدول lineups لا تُولَّد اللوحة الحيّة أصلاً فلا طلب.
# الأسماء العربية: خريطة pid -> اسم عربي للاعبي الفريقين المعروفين (lineup_players ثم players_ar.csv)، مضمّنة بالصفحة العربية فقط؛
# المجهول = اسم المزوّد.
import csv as _csv
import json as _json
from html import escape as _esc
from pathlib import Path as _Path

LIVE_LINEUP_SRC = "https://saffara-live.abujaishamr.workers.dev/lineup"
LIVE_BADGE = {"ar": "التشكيلة الرسمية", "en": "Official lineups"}
_AR_BY_TEAM = None
_COACH_AR = None


def _ar_maps(conn):
    """{team_id: {pid: اسم عربي}} و {coach_en: coach_ar} — تُحسب مرة لكل تشغيل (استعلامان)."""
    global _AR_BY_TEAM, _COACH_AR
    if _AR_BY_TEAM is not None:
        return _AR_BY_TEAM, _COACH_AR
    by_team = defaultdict(dict)
    try:
        csv_path = _Path(__file__).resolve().parent / "players_ar.csv"
        with open(csv_path, encoding="utf-8-sig") as f:
            for r in _csv.DictReader(f):
                pid, tid, ar = (r.get("player_id") or "").strip(), (r.get("team_id") or "").strip(), (r.get("player_ar") or "").strip()
                if pid.isdigit() and tid.isdigit() and ar:
                    by_team[int(tid)][int(pid)] = ar
    except OSError:
        pass
    # lineup_players تغلب players_ar.csv (الاسم الذي تعرضه صفحات المباريات نفسها)، والأحدث يغلب الأقدم
    for tid, pid, ar in conn.execute("""SELECT team_id, player_id, player_ar FROM lineup_players
                                        WHERE player_id > 0 AND COALESCE(player_ar, '') <> '' ORDER BY match_id"""):
        by_team[tid][pid] = ar.strip()
    coach = {}
    for en, ar in conn.execute("""SELECT coach_en, coach_ar FROM lineups
                                  WHERE COALESCE(coach_en, '') <> '' AND COALESCE(coach_ar, '') <> '' ORDER BY match_id"""):
        coach[en.strip()] = ar.strip()
    _AR_BY_TEAM, _COACH_AR = by_team, coach
    return by_team, coach


def live_lineup_slot(conn, m, h, a, lang, T, tname, logo_url):
    """محتوى لوحة «التشكيلات» الحيّة: h2 + عنصر #lulive ببياناته (يملؤه LIVE_LINEUP_SCRIPT). لا يُستدعى إن وُجدت تشكيلة ثابتة."""
    t = T[lang]
    date_parts = str(m["date"] or "").split()
    if len(date_parts) < 2:
        return ""
    ko = f"{date_parts[0]}T{date_parts[1][:5]}:00Z"
    names, coaches = {}, {}
    if lang == "ar":
        by_team, coach = _ar_maps(conn)
        for tid in (m["home_id"], m["away_id"]):
            names.update({str(k): v for k, v in by_team.get(tid, {}).items()})
        coaches = coach
    data = {
        "id": m["match_id"], "ko": ko, "src": LIVE_LINEUP_SRC,
        "home": {"id": m["home_id"], "name": tname(h, lang), "logo": logo_url(h, lang)},
        "away": {"id": m["away_id"], "name": tname(a, lang), "logo": logo_url(a, lang)},
        "t": {"badge": LIVE_BADGE[lang], "formation": t["formation"], "coach": t["coach"], "subs": t["subs"], "nogrid": t["lu_nogrid"]},
        "names": names, "coaches": coaches,
    }
    js = _json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (f'<h2>{t["lineups"]}</h2><div id="lulive" data-svg="{_esc(PITCH_SVG, quote=True)}"></div>'
            f'<script type="application/json" id="lulive-data">{js}</script>')


LIVE_LINEUP_SCRIPT = r"""
<script>
(function(){
  var box=document.getElementById('lulive'),dn=document.getElementById('lulive-data');
  if(!box||!dn)return;
  var D;try{D=JSON.parse(dn.textContent);}catch(e){return;}
  var ko=Date.parse(D.ko),now=Date.now();
  if(!(ko>0)||now<ko-65*60000||now>ko+36*3600000)return;   /* خارج نافذة وجود التشكيلة: بلا طلب */
  var ENT={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'};ENT[String.fromCharCode(39)]='&#39;';
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ENT[c];});}
  function nm(p){var a=p.id!=null&&D.names[String(p.id)];return a||p.name||'—';}
  function grid(g){var m=/^(\d+):(\d+)$/.exec(String(g||''));return m?[+m[1],+m[2]]:null;}
  function ready(t){
    if(!t||!t.formation||!t.xi||t.xi.length!==11)return false;
    var seen={};
    for(var i=0;i<t.xi.length;i++){var g=grid(t.xi[i].grid);if(!g||seen[g])return false;seen[g]=1;}
    return true;
  }
  function chip(p,key,x,y){
    return '<div class="fp" style="left:'+x.toFixed(1)+'%;top:'+y.toFixed(1)+'%">'+
      '<span class="fs '+key+'">'+(p.number!=null?p.number:'—')+'</span><span class="fn">'+esc(nm(p))+'</span></div>';
  }
  /* نفس حساب _full_pitch: المضيف أعلى (أعمدته معكوسة)، الضيف أسفل */
  function full(J){
    var html='';
    [['h',J.home,D.home],['a',J.away,D.away]].forEach(function(z){
      var key=z[0],tm=z[1],meta=z[2],rows={};
      tm.xi.forEach(function(p){var g=grid(p.grid);(rows[g[0]]=rows[g[0]]||[]).push([g[1],p]);});
      var lines=Object.keys(rows).map(Number).sort(function(x,y){return x-y;}),nl=lines.length;
      lines.forEach(function(r,k){
        var cells=rows[r].sort(function(x,y){return x[0]-y[0];}),n=cells.length,fr=nl>1?k/(nl-1):0;
        var y=key==='h'?7+fr*37:93-fr*37;
        cells.forEach(function(c,i){var xi=key==='h'?n-1-i:i;html+=chip(c[1],key,(xi+1)/(n+1)*100,y);});
      });
      html+='<div class="fpt '+(key==='h'?'top':'bot')+'"><img src="'+esc(meta.logo)+'" alt=""><span>'+esc(meta.name)+
        (tm.formation?' <bdi dir="ltr">'+esc(tm.formation)+'</bdi>':'')+'</span></div>';
    });
    return '<div class="fpitch">'+box.getAttribute('data-svg')+html+'</div>';
  }
  function list(arr){
    return arr.map(function(p){return '<span class="sub">'+(p.number!=null?'<span class="num">'+p.number+'</span>':'')+esc(nm(p))+'</span>';}).join('');
  }
  /* نفس _team_block: رأس (شعار + اسم + الخطة) + المدرب + (قائمة الأساسيين إن تعذّر الملعب) + البدلاء */
  function team(tm,meta,pitchOn){
    var coach=tm.coach?(D.coaches[tm.coach]||tm.coach):'',body='';
    if(!pitchOn)body='<div class="lunote">'+esc(D.t.nogrid)+'</div><div class="lulist">'+list(tm.xi)+'</div>';
    return '<div class="luteam"><div class="luhead"><span class="luname"><img src="'+esc(meta.logo)+'" alt="">'+esc(meta.name)+'</span>'+
      (tm.formation?'<span class="luform">'+esc(D.t.formation)+' <bdi dir="ltr">'+esc(tm.formation)+'</bdi></span>':'')+'</div>'+
      (coach?'<div class="lucoach">'+esc(D.t.coach)+': '+esc(coach)+'</div>':'')+body+
      (tm.subs&&tm.subs.length?'<div class="subs"><h4>'+esc(D.t.subs)+'</h4><div class="sublist">'+list(tm.subs)+'</div></div>':'')+'</div>';
  }
  function render(J){
    if(!J||!J.home||!J.away||!J.home.xi||!J.away.xi||!J.home.xi.length||!J.away.xi.length)return false;
    var ok=ready(J.home)&&ready(J.away);
    box.innerHTML='<div class="lubadge">'+esc(D.t.badge)+'</div>'+(ok?full(J):'')+
      '<div class="lu">'+team(J.home,D.home,ok)+team(J.away,D.away,ok)+'</div>';
    var b=document.querySelector('.mtab[data-tab="lineups"]');
    if(b){b.hidden=false;if(location.hash==='#lineups')b.click();}
    else{var sec=box.closest('.mp');if(sec)sec.classList.add('on');}
    return true;
  }
  var tries=0;
  function load(){
    fetch(D.src+'?id='+D.id).then(function(r){return r.ok?r.json():null;}).then(function(J){
      if(render(J))return;
      /* لم تُنشر بعد: إعادة كل دقيقتين حتى 10 دقائق بعد الانطلاق (حدّ 40 محاولة) */
      if(++tries<40&&Date.now()<ko+10*60000)setTimeout(load,120000);
    }).catch(function(){});
  }
  load();
})();
</script>"""
