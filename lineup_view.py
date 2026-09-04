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
  .stsec h4 { font-size:11px; color:var(--muted); font-weight:600;
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
    click = f' data-p="{pid}"' if pid is not None else ""
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
        cl = ' class="sub cl" data-p="%s"' % pid if pid is not None \
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
        cl = ' class="sub cl" data-p="%s"' % pid if pid is not None \
            else ' class="sub"'
        out += (f'<span{cl}>{num_txt}'
                f'{_pname(r, lang)}'
                f'{_rate_badge(ratings.get(pid), "r")}{cap}</span>')

    return (f'<div class="subs"><h4>{t["subs"]}</h4>'
            f'<div class="sublist">{out}</div></div>')


def _team_block(conn, mid, team, team_html_name, logo, lang, t, stats):
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
    for team_row, tid in ((h, m["home_id"]), (a, m["away_id"])):
        blocks += _team_block(conn, mid, tid,
                              tname(team_row, lang),
                              logo_url(team_row, lang),
                              lang, t, stats)

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
        return f'<h2>{t["lineups"]}</h2><div class="lu">{blocks}</div>'

    close = "إغلاق" if lang == "ar" else "Close"
    overlay = (
        f'<div class="stovl" id="stovl"><div class="stbox">'
        f'<div class="sthead"><span class="nm" id="stnm"></span></div>'
        f'<div class="stsub" id="stsub"></div>'
        f'<div id="stbody"></div>'
        f'<button class="stclose" id="stclose">{close}</button>'
        f'</div></div>'
    )
    return (f'<h2>{t["lineups"]}</h2><div class="lu">{blocks}</div>'
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
