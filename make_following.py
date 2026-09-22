#!/usr/bin/env python3
"""
صفحة المتابَعة — Following
=============================
following.html / en/following.html — عرض وتعديل الدوريات والأندية
المتابَعة (fbLeagues/fbClubs عبر prefs.py). **صفحة واحدة بوضعين**
لا صفحة أونبوردنغ منفصلة (قرار موثَّق 6 سبتمبر — تجنّباً لتكرار
ثالث لنفس محتوى الشرائح):
    - **أول زيارة** (`!isSetupDone()`): قسم الأندية مطويّ، زر
      "التالي" وحده ظاهر بعد الدوريات. الضغط عليه يكشف الأندية
      ويُعلِّم `markSetupDone()` — من هنا فصاعداً نفس وضع العائد.
    - **زائر عائد**: القسمان ظاهران معاً فوراً، بلا زر "التالي".
كل نقرة شريحة تحفظ فوراً عبر FBPrefs بكلا الوضعين، بلا زر "حفظ"
منفصل. HTML المولَّد **مطابق لكلا الحالتين** — الفرق كله بجافاسكربت
وقت العرض (`FOLLOWING_SCRIPT`)، لا بتفريع بايثون.

⚠️ **التحويل التلقائي لزائر أول مرة يأتي من `make_site3.py`
   وحده** (`follow_redirect_script()`) — الرئيسية فقط، لا كل
   صفحة (قرار موثَّق: تحويل إجباري من كل صفحة أسوأ من عدم
   التحويل أصلاً).

⚠️ **noindex بقصد، ثلاث طبقات لا واحدة:**
   ١. `<meta name="robots" content="noindex">` بالصفحة نفسها
   ٢. مستبعدة من sitemap.xml (`make_sitemap.py::SKIP_FILES`)
   ٣. رابطها الوحيد بالشريط السفلي يحمل `rel="nofollow"` (`navbar.py`)
   السبب: المحتوى 100% من localStorage — تبدو فاضية دائماً لأي
   زحف، والرابط يظهر بكل صفحات الموقع (اكتشاف داخلي مضمون بصرف
   النظر عن الخريطة).

⚠️ **أول مستهلك فعلي لـ`club_map_script(conn)`** — `cleanClubs()`
   تُستدعى هنا عند إلغاء تحديد دوري، فتزيل أي نادٍ يتبعه من
   `fbClubs` **وتُظهر الأثر فوراً بنفس الشاشة** (شرائح الأندية
   المتأثرة تفقد تظليلها لحظياً) — لا حذف صامت (درس 1).

⚠️ **يعيد استخدام `league_chips_html`/`club_chips_html`/`CHIP_CSS`
   من `onboard.py`** — نفس شكل شرائح المعالج بالضبط، بلا كروم
   النافذة المنبثقة (`.ovl`/`.wiz`/الخطوات) التي لا تخصّ صفحة دائمة.

صفر طلبات API.

التشغيل:
    python make_following.py
"""

import csv
import json
import os
import sqlite3
from collections import defaultdict

from config import DB_FILE, LEAGUES
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from theme import VARS, THEME_HEAD, THEME_SCRIPT, head_meta
from navbar import (NAV_CSS, navbar, settings_button, settings_overlay,
                    nav_script, pwa_script)
from search_view import SEARCH_CSS, search_script, search_overlay
from onboard import CHIP_CSS, league_chips_html, club_chips_html
from prefs import prefs_script, club_map_script
from make_site3 import load_overrides
from make_players import gather, load_teams
from player_slug import build_slug_map

BASE = DB_FILE.parent
COLORS_FILE = BASE / "club_colors.csv"
FOLLOW_DATA_FILE = BASE / "follow_data.js"


def load_club_colors():
    """team_id (نص) → hex — من club_colors.csv (fetch_club_colors.py).
    سقوط آمن: نادٍ غائب = بلا لون، خلفية عادية بالكارت (بند 4)."""
    colors = {}
    if not COLORS_FILE.exists():
        return colors
    with open(COLORS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = (row.get("team_id") or "").strip()
            hexcolor = (row.get("color_hex") or "").strip()
            if tid and hexcolor:
                colors[tid] = hexcolor
    return colors


def team_match_info(conn):
    """
    لكل فريق: أقرب مباراة قادمة، وإلا آخر نتيجة سابقة.
    يرجع {team_id: (opp_id, match_id, date, is_home, is_upcoming)}.

    ⚠️ استعلامان لا استعلام واحد بفرز شرطي — أوضح، ولا حاجة
       لـCASE معقّد على عمودين (home_id/away_id) بجهتي المباراة.
    """
    upcoming = {}
    for r in conn.execute("""
        SELECT home_id AS tid, away_id AS opp, match_id, date, 1 AS is_home
        FROM matches WHERE home_goals IS NULL
        UNION ALL
        SELECT away_id AS tid, home_id AS opp, match_id, date, 0 AS is_home
        FROM matches WHERE home_goals IS NULL
        ORDER BY date ASC
    """):
        upcoming.setdefault(r["tid"], (r["opp"], r["match_id"], r["date"],
                                        r["is_home"], True))

    past = {}
    for r in conn.execute("""
        SELECT home_id AS tid, away_id AS opp, match_id, date, 1 AS is_home
        FROM matches WHERE home_goals IS NOT NULL
        UNION ALL
        SELECT away_id AS tid, home_id AS opp, match_id, date, 0 AS is_home
        FROM matches WHERE home_goals IS NOT NULL
        ORDER BY date DESC
    """):
        past.setdefault(r["tid"], (r["opp"], r["match_id"], r["date"],
                                    r["is_home"], False))

    out = {}
    for tid in set(upcoming) | set(past):
        out[tid] = upcoming.get(tid) or past.get(tid)
    return out


def build_follow_data(conn, teams, colors):
    """
    follow_data.js — ملف بيانات خارجي مشترك (نفس نمط search_data.js)
    لكل الفرق واللاعبين المؤهَّلين، بلا حقن HTML كامل بكل صفحة
    (161 فريقاً مقبول، 3,701 لاعباً ليس كذلك — راجع تصميم البند 4
    جزء ب: JS وقت العرض يبني الكروت من هنا حسب FBPrefs فقط).

    صفوف teams: [team_id, ar, en, logo, color_or_null,
                  opp_ar, opp_en, opp_logo, date, is_home, is_upcoming]
    صفوف players: [slug, ar, en, team_id, team_ar, team_en, team_logo,
                    team_color_or_null, opp_ar, opp_en, date, is_home]

    ⚠️ **الـslug من نفس مصدر make_players.py حرفياً** (gather() +
       build_slug_map() بنفس آلية عدّ الأهداف) — لا إعادة تنفيذ
       محلي، أي انحراف بسيط بترتيب العدّ يُنتج slugs مختلفة عمّا
       يخزّنه زر المتابعة بصفحة اللاعب نفسها فتصير المطابقة معطوبة
       بصمت. راجع player_slug.py::build_slug_map.

    ⚠️ **التقييم غير مُضمَّن عمداً** — بيانات "آخر مباراة" هنا
       تعتمد الأهداف فقط (متاحة لكل الدوريات دائماً)، لا التقييم
       (شبه غائب بالأردني/العراقي، وحتى بالسعودي يحتاج استعلاماً
       إضافياً per-match لا per-season). بند مُقَرّ كتبسيط — راجع
       التصميم الموافَق عليه (الجزء ب، بند 4).
    """
    matches = team_match_info(conn)

    teams_rows = []
    for tid, name in sorted(teams.items()):
        info = matches.get(tid)
        if not info:
            continue
        opp_id, _mid, date, is_home, is_upcoming = info
        opp = teams.get(opp_id, {})
        teams_rows.append([
            tid, name["ar"], name["en"], name["logo"],
            colors.get(str(tid)),
            opp.get("ar", ""), opp.get("en", ""), opp.get("logo", ""),
            date, bool(is_home), bool(is_upcoming),
        ])

    goals, _bridge, _stats, _seasons = gather(conn)
    counts = {n: len(rows) for n, rows in goals.items()}
    slugs = build_slug_map(counts)

    players_rows = []
    for name, rows in goals.items():
        slug = slugs.get(name)
        if not slug or not rows:
            continue
        last = rows[0]
        tid = last["team_id"]
        team = teams.get(tid, {})
        opp_id = (last["away_id"] if last["home_id"] == tid
                  else last["home_id"])
        opp = teams.get(opp_id, {})
        players_rows.append([
            slug, last["ar"] or name, name, tid,
            team.get("ar", ""), team.get("en", ""), team.get("logo", ""),
            colors.get(str(tid)),
            opp.get("ar", ""), opp.get("en", ""),
            last["date"], last["home_id"] == tid,
        ])

    js = ("window.FBFollowData = " +
          json.dumps({"teams": teams_rows, "players": players_rows},
                     ensure_ascii=False, separators=(",", ":")) + ";")
    with open(FOLLOW_DATA_FILE, "w", encoding="utf-8") as f:
        f.write(js)
    return len(teams_rows), len(players_rows)

FOLLOWING_CSS = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg);
         color:var(--text); padding:24px 16px; line-height:1.7; }
  .wrap { max-width:720px; margin:0 auto; }
  .topbar { display:flex; align-items:center;
            justify-content:space-between; margin-bottom:6px; }
  .lang { background:var(--card); color:var(--muted);
          border:1px solid var(--line); padding:6px 14px;
          border-radius:8px; font-size:13px; text-decoration:none;
          font-family:inherit; }
  .lang:hover { background:var(--card2); color:var(--text); }
  header { text-align:center; margin-bottom:24px; }
  h1 { font-size:26px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  h2 { font-size:16px; margin:26px 0 8px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }

  /* زر "التالي" — وضع أول زيارة فقط (راجع FOLLOWING_SCRIPT) */
  .fnext { display:block; width:100%; background:var(--accent);
           color:#fff; border:none; border-radius:9px; padding:14px;
           font-size:16px; cursor:pointer; font-family:inherit;
           margin:18px 0; }
  .fnext:hover { filter:brightness(1.1); }

  /* الكروت الموحَّدة + التبويبان (بند 4، جزء ب، 22 سبتمبر) */
  .ftabs { display:flex; gap:8px; align-items:center; margin-bottom:14px; }
  .ftab { background:var(--card); color:var(--muted);
          border:1px solid var(--line); padding:9px 18px;
          border-radius:9px; cursor:pointer; font-family:inherit;
          font-size:14px; transition:.15s; }
  .ftab:hover { background:var(--card2); color:var(--text); }
  .ftab.active { background:var(--accent); color:#fff;
                 border-color:var(--accent); }
  .fedit { margin-inline-start:auto; background:var(--card);
           color:var(--muted); border:1px solid var(--line);
           padding:9px 18px; border-radius:9px; cursor:pointer;
           font-family:inherit; font-size:14px; }
  .fedit.on { background:var(--accent); color:#fff;
              border-color:var(--accent); }

  .fgrid { display:flex; flex-direction:column; gap:10px; }
  /* ⚠️ اللون خلفية كل كارت (--ct) يُضبط سطراً بسطر بالجافاسكربت
     وقت البناء (club_colors.csv عبر follow_data.js) — لا CSS
     ثابت هنا. الافتراضي var(--card) العادية لو بلا لون محفوظ. */
  .fcard { display:flex; align-items:center; gap:12px;
           background:var(--card); border:1px solid var(--line);
           border-radius:14px; padding:14px 16px; text-decoration:none;
           color:var(--text); transition:border-color .15s; }
  .fcard:hover { border-color:var(--accent); }
  .fcard img { width:44px; height:44px; object-fit:contain;
               border-radius:50%; background:#fff; flex:0 0 auto; }
  .fcard .fbody { min-width:0; flex:1; }
  .fcard .fname { font-weight:700; font-size:15px; }
  .fcard .fmeta { color:var(--muted); font-size:12.5px; margin-top:4px;
                  display:flex; align-items:center; gap:5px; }
  .fcard .fmeta .flbl { color:var(--text); font-weight:600; }
  .fcard .fmeta img { width:16px; height:16px; border-radius:50%;
                       background:none; }
  .fempty { color:var(--muted); font-size:14px; text-align:center;
            padding:36px 10px; background:var(--card);
            border-radius:12px; }

  /* وضع تعديل اللاعبين — قائمة بسيطة بزر إزالة فقط، لا شاشة
     اختيار (3,701 عنصر غير قابل للتصفّح كشرائح، راجع تصميم
     البند 4 المُقَرّ). الإضافة حصراً من زر صفحة اللاعب نفسها. */
  .fplist { display:flex; flex-direction:column; gap:8px; }
  .fprow { display:flex; align-items:center; gap:10px;
           background:var(--card); border:1px solid var(--line);
           border-radius:10px; padding:10px 14px; }
  .fprow .fpname { flex:1; font-size:14px; min-width:0;
                    overflow:hidden; text-overflow:ellipsis;
                    white-space:nowrap; }
  .fpremove { background:none; border:none; color:var(--muted);
              font-size:20px; cursor:pointer; line-height:1;
              padding:2px 8px; font-family:inherit; }
  .fpremove:hover { color:#e5484d; }
  .fphint { color:var(--muted); font-size:12.5px; margin-bottom:10px;
            line-height:1.7; }
"""

STYLE = ("<style>" + VARS + FOLLOWING_CSS + CHIP_CSS + NAV_CSS
         + SEARCH_CSS + "</style>")

# ⚠️ بلا فلترة "أشهر 4" افتراضية على نمط المعالج — صفحة تصفّح
#    وتعديل دائمة، كل الأندية ظاهرة مجمَّعة بدوريها، والبحث
#    يفلتر فوق ذلك فقط. راجع النقاش قبل التنفيذ (بند 2).
FOLLOWING_SCRIPT = """
<script>
(function(){
  var FB = window.FBPrefs;
  if (!FB) return;

  var search = document.getElementById('fsearch');
  var clubsSection = document.getElementById('clubs-section');
  var nextBtn = document.getElementById('fnext');

  // ⚠️ وضع أول زيارة (!isSetupDone): قسم الأندية مطويّ، "التالي"
  //    ظاهر بدلاً منه. الضغط عليه يكشف القسم ويعلّم الإعداد مكتملاً
  //    — من هذه اللحظة الصفحة تتصرّف كزائر عائد لبقية الجلسة.
  //    زائر عائد فعلياً: القسمان ظاهران معاً من التحميل، بلا زر.
  if (FB.isSetupDone()) {
    if (nextBtn) nextBtn.style.display = 'none';
  } else {
    if (clubsSection) clubsSection.style.display = 'none';
    if (nextBtn) nextBtn.style.display = '';
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function(){
      if (clubsSection) clubsSection.style.display = '';
      nextBtn.style.display = 'none';
      FB.markSetupDone();
    });
  }

  function syncFromStorage(){
    var L = FB.getLeagues(), C = FB.getClubs();
    document.querySelectorAll('#leagues .chip').forEach(function(x){
      x.classList.toggle('on', L.indexOf(x.dataset.lg) >= 0);
    });
    document.querySelectorAll('#clubs .chip').forEach(function(x){
      x.classList.toggle('on', C.indexOf(+x.dataset.cl) >= 0);
    });
  }

  function filterClubs(){
    var q = (search.value || '').trim().toLowerCase();
    var shown = 0;
    document.querySelectorAll('#clubs .chip').forEach(function(x){
      var ok = !q || x.dataset.nm.indexOf(q) >= 0;
      x.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    document.querySelectorAll('#clubs .lgroup').forEach(function(g){
      var any = false, n = g.nextElementSibling;
      while (n && n.classList.contains('chip')) {
        if (n.style.display !== 'none') { any = true; break; }
        n = n.nextElementSibling;
      }
      g.style.display = any ? '' : 'none';
    });
    document.getElementById('nores').style.display = shown ? 'none' : '';
  }

  document.querySelectorAll('#leagues .chip').forEach(function(x){
    x.addEventListener('click', function(){
      this.classList.toggle('on');
      var L = [];
      document.querySelectorAll('#leagues .chip.on').forEach(
        function(y){ L.push(y.dataset.lg); });
      FB.setLeagues(L);
      // ⚠️ الأثر يجب أن يكون مرئياً فوراً — لا حذف صامت (درس 1)
      var kept = FB.cleanClubs();
      document.querySelectorAll('#clubs .chip.on').forEach(function(c){
        if (kept.indexOf(+c.dataset.cl) < 0) c.classList.remove('on');
      });
      if (window.__ffRenderTeams) window.__ffRenderTeams();
    });
  });

  document.querySelectorAll('#clubs .chip').forEach(function(x){
    x.addEventListener('click', function(){
      this.classList.toggle('on');
      var C = [];
      document.querySelectorAll('#clubs .chip.on').forEach(
        function(y){ C.push(+y.dataset.cl); });
      FB.setClubs(C);
      if (window.__ffRenderTeams) window.__ffRenderTeams();
    });
  });

  if (search) search.addEventListener('input', filterClubs);

  syncFromStorage();
})();
</script>"""


def following_view_script(t, lang, depth):
    """
    التبويبان (فرق/لاعبون) + وضعا العرض/التعديل + بناء الكروت من
    follow_data.js (بند 4، جزء ب، 22 سبتمبر). منفصلة عن
    FOLLOWING_SCRIPT (منتقاة الدوريات/الأندية القديمة، بلا تغيير)
    لوضوح المسؤولية — كلاهما يعملان على نفس الصفحة معاً.

    ⚠️ **follow_data.js UP/UPL بنفس صيغة search_script() حرفياً**
       (راجع "مصيدة 8" بـsearch_view.py) — لا إعادة اشتقاق.
    """
    up = "../" * depth
    upl = up + ("en/" if lang == "en" else "")

    def esc(k):
        return t[k].replace('"', '\\"')

    js = """
<script src="__UP__follow_data.js" defer></script>
<script>
(function(){
  var FB = window.FBPrefs;
  if (!FB) return;
  var LANG = "__LANG__", UP = "__UP__", UPL = "__UPL__";
  var EDIT = "__EDIT__", DONE = "__DONE__";
  var F_UP = "__F_UP__", F_LAST = "__F_LAST__", F_GOAL = "__F_GOAL__";
  var NO_TEAMS = "__NO_TEAMS__", NO_PLAYERS = "__NO_PLAYERS__";

  var tabTeams = document.getElementById('tab-teams');
  var tabPlayers = document.getElementById('tab-players');
  var editBtn = document.getElementById('fedit');
  var viewTeams = document.getElementById('view-teams');
  var viewPlayers = document.getElementById('view-players');
  var editTeams = document.getElementById('edit-teams');
  var editPlayers = document.getElementById('edit-players');
  if (!tabTeams || !editBtn) return;

  var activeTab = 'teams';
  var editMode = !FB.isSetupDone();

  function esc(s){
    return (''+s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                 .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function fmtDate(d){ return (''+(d||'')).slice(0, 10); }
  function tint(el, hex){
    if (hex) el.style.background =
      'color-mix(in srgb, var(--card) 78%, '+hex+' 22%)';
  }
  function logoSrc(logo){
    // ⚠️ نفس منطق search_view.py::clubHtml — رابط بعيد كما هو،
    //    مسار محلي (logos/xxx.png) يحتاج UP (الملف بجذر الموقع).
    return (logo && logo.indexOf('http') === 0) ? logo : (UP + (logo || ''));
  }
  function card(href, logo, name, lbl, oppTxt, date){
    var a = document.createElement('a');
    a.className = 'fcard';
    a.href = href;
    // ⚠️ التاريخ بـspan dir="ltr" منفصل — بلا هذا، بيدي RTL يعكس
    //    ترتيب مقاطع "٢٠٢٦-٠٩-٢٧" المفصولة بشرطات داخل سياق عربي
    //    فيظهر "27-09-2026" رغم أن textContent الفعلي صحيح دائماً
    //    (اكتُشف بفحص بصري فعلي بمتصفح حقيقي — راجع سجل الجلسات).
    var meta = oppTxt
      ? '<div class="fmeta"><span class="flbl">'+esc(lbl)+':</span> '
        +esc(oppTxt)+' · <span dir="ltr">'+esc(fmtDate(date))+'</span></div>'
      : '';
    a.innerHTML = '<img src="'+esc(logoSrc(logo))+'" alt="" '
      +'onerror="this.style.visibility=\\'hidden\\'">'
      +'<div class="fbody"><div class="fname">'+esc(name)+'</div>'
      +meta+'</div>';
    return a;
  }

  function renderTeams(){
    var box = document.getElementById('teamCards');
    var empty = document.getElementById('teamsEmpty');
    if (!box) return;
    box.innerHTML = '';
    var data = window.FBFollowData;
    var followed = FB.getClubs();
    var rows = (data && followed.length)
      ? data.teams.filter(function(r){ return followed.indexOf(r[0]) >= 0; })
      : [];
    if (!rows.length){
      box.style.display = 'none';
      empty.textContent = NO_TEAMS;
      empty.style.display = '';
      return;
    }
    box.style.display = ''; empty.style.display = 'none';
    rows.forEach(function(r){
      var tid=r[0], ar=r[1], en=r[2], logo=r[3], color=r[4],
          oppAr=r[5], oppEn=r[6], date=r[8], isUp=r[10];
      var name = LANG==='ar' ? (ar||en) : (en||ar);
      var opp = LANG==='ar' ? (oppAr||oppEn) : (oppEn||oppAr);
      var el = card(UPL+'clubs/'+tid+'.html', logo, name,
                    isUp ? F_UP : F_LAST, opp, date);
      tint(el, color);
      box.appendChild(el);
    });
  }

  function renderPlayers(){
    var box = document.getElementById('playerCards');
    var empty = document.getElementById('playersEmpty');
    if (!box) return;
    box.innerHTML = '';
    var data = window.FBFollowData;
    var followed = FB.getPlayers();
    var byId = {};
    if (data) data.players.forEach(function(r){ byId[r[0]] = r; });
    var rows = followed.map(function(s){ return byId[s]; }).filter(Boolean);
    if (!rows.length){
      box.style.display = 'none';
      empty.textContent = NO_PLAYERS;
      empty.style.display = '';
      return;
    }
    box.style.display = ''; empty.style.display = 'none';
    rows.forEach(function(r){
      var slug=r[0], ar=r[1], en=r[2], tLogo=r[6], color=r[7],
          oppAr=r[8], oppEn=r[9], date=r[10];
      var name = LANG==='ar' ? (ar||en) : (en||ar);
      var opp = LANG==='ar' ? (oppAr||oppEn) : (oppEn||oppAr);
      var el = card(UPL+'players/'+slug+'.html', tLogo, name,
                    F_GOAL, opp, date);
      tint(el, color);
      box.appendChild(el);
    });
  }

  // ⚠️ وضع تعديل اللاعبين — إزالة فقط، لا إضافة (راجع تعليق CSS
  //    .fplist أعلاه). البيانات نفسها المستخدَمة بالكروت.
  function renderPlayerEdit(){
    var box = document.getElementById('playerEditList');
    if (!box) return;
    box.innerHTML = '';
    var data = window.FBFollowData;
    var followed = FB.getPlayers();
    var byId = {};
    if (data) data.players.forEach(function(r){ byId[r[0]] = r; });
    if (!followed.length){
      box.innerHTML = '<div class="fempty">'+NO_PLAYERS+'</div>';
      return;
    }
    followed.forEach(function(slug){
      var r = byId[slug];
      var name = r ? (LANG==='ar' ? (r[1]||r[2]) : (r[2]||r[1])) : slug;
      var row = document.createElement('div');
      row.className = 'fprow';
      row.innerHTML = '<span class="fpname"></span>'
        +'<button class="fpremove" type="button">×</button>';
      row.querySelector('.fpname').textContent = name;
      row.querySelector('.fpremove').addEventListener('click', function(){
        var p = FB.getPlayers();
        var i = p.indexOf(slug);
        if (i >= 0) p.splice(i, 1);
        FB.setPlayers(p);
        renderPlayerEdit();
        renderPlayers();
      });
      box.appendChild(row);
    });
  }

  function render(){
    tabTeams.classList.toggle('active', activeTab === 'teams');
    tabPlayers.classList.toggle('active', activeTab === 'players');
    editBtn.classList.toggle('on', editMode);
    editBtn.textContent = editMode ? DONE : EDIT;

    viewTeams.style.display =
      (activeTab === 'teams' && !editMode) ? '' : 'none';
    viewPlayers.style.display =
      (activeTab === 'players' && !editMode) ? '' : 'none';
    editTeams.style.display =
      (activeTab === 'teams' && editMode) ? '' : 'none';
    editPlayers.style.display =
      (activeTab === 'players' && editMode) ? '' : 'none';

    renderTeams();
    renderPlayers();
    if (activeTab === 'players' && editMode) renderPlayerEdit();
  }

  tabTeams.addEventListener('click', function(){
    activeTab = 'teams'; render();
  });
  tabPlayers.addEventListener('click', function(){
    activeTab = 'players'; render();
  });
  editBtn.addEventListener('click', function(){
    editMode = !editMode; render();
  });

  window.__ffRenderTeams = render;
  render();
  window.addEventListener('load', render);
})();
</script>"""

    return (js.replace("__UP__", up)
              .replace("__UPL__", upl)
              .replace("__LANG__", lang)
              .replace("__EDIT__", esc("edit"))
              .replace("__DONE__", esc("done"))
              .replace("__F_UP__", esc("f_upcoming"))
              .replace("__F_LAST__", esc("f_last_result"))
              .replace("__F_GOAL__", esc("f_last_goal"))
              .replace("__NO_TEAMS__", esc("f_no_teams"))
              .replace("__NO_PLAYERS__", esc("f_no_players")))


def following_page(conn, lang, leagues, logos):
    t = T[lang]
    depth = 0 if lang == "ar" else 1
    switch = "en/following.html" if lang == "ar" else "../following.html"

    wiz_leagues = [(c, league_name(c, lang)) for c in leagues]

    rows = conn.execute("""
        SELECT DISTINCT t.team_id, t.short_name_ar AS name,
               COALESCE(NULLIF(t.name_en_official,''), t.name_en) AS name_en,
               t.logo, t.league_code AS lg
        FROM teams t
        WHERE EXISTS (
            SELECT 1 FROM matches m
            WHERE m.home_id = t.team_id OR m.away_id = t.team_id
        )
        ORDER BY t.league_code, t.short_name_ar
    """).fetchall()
    wiz_clubs = []
    for r in rows:
        nm = (r["name"] or r["name_en"]) if lang == "ar" \
            else (r["name_en"] or r["name"])
        logo = logos.get(str(r["team_id"]), r["logo"])
        wiz_clubs.append((r["team_id"], nm, logo, r["lg"], 0))

    lg_html = league_chips_html(wiz_leagues)
    cl_html = club_chips_html(wiz_leagues, wiz_clubs)

    title = f'{t["following"]} — {t["site_title"]}'

    html = (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        '<meta name="robots" content="noindex">\n'
        + head_meta(title, t["site_sub"], "" if lang == "ar" else "../",
                    lang,
                    "following.html" if lang == "ar" else "en/following.html")
        + THEME_HEAD + STYLE +
        '</head>\n<body>\n<div class="wrap">\n'
        f'<div class="topbar"><a class="lang" href="{switch}">'
        f'{SWITCH_LABEL[lang]}</a><span>{settings_button(t)}</span></div>\n'
        f'<header><h1>{t["following"]}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'

        # ⚠️ تبويبا Teams/Players + زر Edit (بند 4، جزء ب، 22 سبتمبر)
        #    — راجع following_view_script() للمنطق الكامل.
        f'<div class="ftabs">'
        f'<button class="ftab active" id="tab-teams">{t["s_clubs"]}</button>'
        f'<button class="ftab" id="tab-players">{t["s_players"]}</button>'
        f'<button class="fedit" id="fedit">{t["edit"]}</button>'
        f'</div>\n'

        # وضع العرض — الكروت الموحَّدة، فارغة بالـHTML، تُملأ وقت
        # العرض من follow_data.js حسب FBPrefs (following_view_script)
        f'<div class="fview" id="view-teams">'
        f'<div class="fgrid" id="teamCards"></div>'
        f'<div class="fempty" id="teamsEmpty" style="display:none">'
        f'{t["f_no_teams"]}</div></div>\n'
        f'<div class="fview" id="view-players" style="display:none">'
        f'<div class="fgrid" id="playerCards"></div>'
        f'<div class="fempty" id="playersEmpty" style="display:none">'
        f'{t["f_no_players"]}</div></div>\n'

        # وضع تعديل الفِرَق — شاشة الاختيار القديمة بالضبط (شرائح
        # الدوريات/الأندية)، الآن داخل لوحة يُتحكَّم بظهورها بدل
        # ظهور دائم بأعلى الصفحة.
        f'<div class="fedit-panel" id="edit-teams" style="display:none">\n'
        f'<h2>{t["w_leagues"]}</h2>\n'
        f'<div class="pick" id="leagues">{lg_html}</div>\n'
        # ⚠️ **وضع أول زيارة فقط** — JS يُظهره ويطوي قسم الأندية
        # (راجع FOLLOWING_SCRIPT). زائر عائد لا يرى هذا الزر إطلاقاً،
        # القسمان ظاهران معاً فوراً. نفس HTML لكلا الحالتين بلا فرق.
        f'<button class="fnext" id="fnext" style="display:none">'
        f'{t["next"]}</button>\n'
        f'<div id="clubs-section">\n'
        f'<h2>{t["w_clubs"]}</h2>\n'
        f'<input type="text" id="fsearch" class="wsearch" '
        f'placeholder="{t["search_club"]}">\n'
        f'<div id="clubs">{cl_html}</div>\n'
        f'<div class="nores" id="nores" style="display:none">'
        f'{t["no_results"]}</div>\n'
        f'</div>\n'
        f'</div>\n'

        # وضع تعديل اللاعبين — إزالة فقط، لا شاشة اختيار (3,701 غير
        # قابلة للتصفّح، راجع تصميم البند 4 المُقَرّ). الإضافة من
        # زر صفحة اللاعب نفسها.
        f'<div class="fedit-panel" id="edit-players" style="display:none">\n'
        f'<div class="fphint">{t["f_add_player_hint"]}</div>\n'
        f'<div class="fplist" id="playerEditList"></div>\n'
        f'</div>\n'

        f'<footer>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + navbar(t, depth, "following", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT
        + prefs_script() + club_map_script(conn)
        + FOLLOWING_SCRIPT
        + following_view_script(t, lang, depth)
        + nav_script(t) + pwa_script(lang)
        + search_script(t, depth, lang) +
        '</body>\n</html>'
    )
    if lang == "en":
        html = html.replace('src="logos/', 'src="../logos/')
    return html


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    logos = load_overrides()

    leagues = [c for c in LEAGUES if conn.execute(
        "SELECT 1 FROM matches WHERE league_code=? LIMIT 1", (c,)
    ).fetchone()]

    os.makedirs(BASE / "en", exist_ok=True)

    # ⚠️ follow_data.js ملف واحد مشترك بكلا اللغتين (نفس نمط
    #    search_data.js) — يُبنى مرة، لا لكل لغة.
    teams = load_teams()
    colors = load_club_colors()
    n_teams, n_players = build_follow_data(conn, teams, colors)

    made = []
    for lang in LANGS:
        html = following_page(conn, lang, leagues, logos)
        path = (BASE / "following.html" if lang == "ar"
                else BASE / "en" / "following.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        made.append(path.name if lang == "ar" else "en/following.html")

    conn.close()

    print(f"\n{'=' * 55}")
    print("  تم توليد:")
    for m in made:
        print(f"      {m}")
    print(f"  follow_data.js: {n_teams} فريقاً · {n_players} لاعباً")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
