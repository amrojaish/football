#!/usr/bin/env python3
"""
صفحة المتابَعة — Following
=============================

⚠️ **إعادة تصميم 12 أكتوبر 2026 (نموذج محلي، قرار عمرو، مرجع FotMob):** أُزيلت شاشة التعديل الطويلة (شرائح الدوريات/الأندية
   + «التالي» + وضع أول زيارة). الآن: «تعديل» يحوّل الكروت لوضع اختيار (دائرة بكل كرت + شريط سفلي «إزالة من المفضلة (n)» / «تم»)،
   و«+» يفتح ورقة بحث سفلية بالأندية فقط (`FBSEARCH.c`، 7 دوريات، `search_data.js` يُحمَّل كسولاً عند أول فتح) بزر «متابعة/متابَع»
   فوري. كله على FBPrefs نفسه (fbClubs/fbPlayers). لا دوريات ولا منتخبات هنا. التفاصيل بالتعليقات أدناه قد تذكر الشاشة القديمة.
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

⚠️ **لا تحويل تلقائي لزائر أول مرة (2 أكتوبر 2026):** الرئيسية تعرض بطاقة
   اختيارية قابلة للإغلاق تربط بهذه الصفحة (`follow_card_html()` بـ`make_site3.py`).
   كان `follow_redirect_script()` يحوّل لهنا فيرى جوجل (زائر أول مرة دائماً) الرئيسية
   تحويلاً لصفحة noindex.

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
                    nav_script, pwa_script, appbar)
from search_view import SEARCH_CSS, search_field
from prefs import prefs_script
from make_site3 import FLAG, load_league_logos, load_overrides
from make_leagues import COUNTRY
from swipe_view import TOUCH_CSS, swipe_script, head_html as swipe_head
from make_players import gather, load_teams
from player_pages import get_plan
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
    # ⚠️ **"قادمة" = بلا نتيجة وتاريخها اليوم أو بعده** (4 أكتوبر 2026). كانت
    #    أي مباراة بلا نتيجة تُعدّ قادمة حتى لو راح تاريخها (مؤجَّلة PST مثل
    #    FAR Rabat–الرجاء 2026-09-24 كانت تظهر «قادمة» بتاريخ ماضٍ). التواريخ
    #    UTC فنقارن بـdate('now') (UTC) على الجزء اليومي. الفريق الذي لا قادمة
    #    له يرجع لآخر نتيجة سابقة كالمعتاد.
    # ⚠️ **المؤجّلة (PST) مرشّحة أيضاً** (5 أكتوبر، دفعة 4): الكرت يكتب «مؤجّلة»
    #    بدل الموعد. المؤجّلة التي تاريخها الأصلي أقدم من 30 يوماً لا تُحسب (لا تحجب
    #    القادمة الفعلية بكرت بلا موعد). الأقدم تاريخاً بين المرشّحات تفوز.
    #    الصف: (opp, match_id, date, is_home, is_upcoming, status, tg, og).
    cond = """home_goals IS NULL AND (
          (substr(date, 1, 10) >= date('now')
             AND COALESCE(status,'') NOT IN ('PST','CANC','ABD'))
          OR (status = 'PST' AND substr(date, 1, 10) >= date('now','-30 day')))"""
    # ⚠️ **القادمة الفعلية أولاً، والمؤجَّلة احتياط** (12 أكتوبر 2026): كانت الأقدم تاريخاً بين الاثنتين تفوز فيظهر كرت الجيش الملكي
    #    «مؤجّلة ضد الرجاء (24 سبتمبر)» بدل مباراة الليلة. الآن: أقرب مباراة غير مؤجَّلة (اليوم أو بعده)، وإلا المؤجَّلة (PST ≤ 30 يوماً)،
    #    وإلا آخر نتيجة. الملغاة/المتروكة (CANC/ABD) مستبعدة كما كانت.
    upcoming = {}
    postponed = {}
    for r in conn.execute(f"""
        SELECT home_id AS tid, away_id AS opp, match_id, date, 1 AS is_home,
               COALESCE(status,'') AS st
        FROM matches WHERE {cond}
        UNION ALL
        SELECT away_id AS tid, home_id AS opp, match_id, date, 0 AS is_home,
               COALESCE(status,'') AS st
        FROM matches WHERE {cond}
        ORDER BY date ASC
    """):
        row = (r["opp"], r["match_id"], r["date"], r["is_home"], True, r["st"], None, None)
        (postponed if r["st"] == "PST" else upcoming).setdefault(r["tid"], row)

    past = {}
    for r in conn.execute("""
        SELECT home_id AS tid, away_id AS opp, match_id, date, 1 AS is_home,
               home_goals AS tg, away_goals AS og
        FROM matches WHERE home_goals IS NOT NULL
        UNION ALL
        SELECT away_id AS tid, home_id AS opp, match_id, date, 0 AS is_home,
               away_goals AS tg, home_goals AS og
        FROM matches WHERE home_goals IS NOT NULL
        ORDER BY date DESC
    """):
        past.setdefault(r["tid"], (r["opp"], r["match_id"], r["date"],
                                    r["is_home"], False, "", r["tg"], r["og"]))

    out = {}
    for tid in set(upcoming) | set(postponed) | set(past):
        out[tid] = upcoming.get(tid) or postponed.get(tid) or past.get(tid)
    return out


def build_follow_data(conn, teams, colors):
    """
    follow_data.js — ملف بيانات خارجي مشترك (نفس نمط search_data.js)
    لكل الفرق واللاعبين المؤهَّلين، بلا حقن HTML كامل بكل صفحة
    (161 فريقاً مقبول، 3,701 لاعباً ليس كذلك — راجع تصميم البند 4
    جزء ب: JS وقت العرض يبني الكروت من هنا حسب FBPrefs فقط).

    صفوف teams: [team_id, ar, en, logo, color_or_null,
                  opp_ar, opp_en, opp_logo, date, is_home, is_upcoming,
                  status ('PST' أو ''), team_goals|null, opp_goals|null]
    صفوف players: [slug, ar, en, team_id, team_ar, team_en, team_logo,
                    team_color_or_null, opp_ar, opp_en, date, is_home,
                    player_id|0 (للصورة), season_apps|null, season_goals]

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
        opp_id, _mid, date, is_home, is_upcoming, st, tg, og = info
        opp = teams.get(opp_id, {})
        teams_rows.append([
            tid, name["ar"], name["en"], name["logo"],
            colors.get(str(tid)),
            opp.get("ar", ""), opp.get("en", ""), opp.get("logo", ""),
            date, bool(is_home), bool(is_upcoming), st, tg, og,
        ])

    goals, bridge, _stats, _seasons = gather(conn)
    season_of = {r["lg"]: r["s"] for r in conn.execute(
        "SELECT league_code AS lg, MAX(season) AS s FROM matches GROUP BY 1")}
    team_lg = {r["team_id"]: r["league_code"]
               for r in conn.execute("SELECT team_id, league_code FROM teams")}
    # مباريات اللاعب بالموسم الحالي لدوريه: اتحاد lineup_players+player_stats
    # (معرّف المزوّد فقط — الأردني/العراقي بلا تشكيلات فتبقى null لا صفراً كاذباً)
    apps = defaultdict(set)
    for r in conn.execute("""
        SELECT x.player_id AS pid, m.match_id AS mid, m.league_code AS lg, m.season AS s
        FROM (SELECT player_id, match_id FROM lineup_players
              UNION SELECT player_id, match_id FROM player_stats) x
        JOIN matches m ON m.match_id = x.match_id
        WHERE x.player_id > 0"""):
        if season_of.get(r["lg"]) == r["s"]:
            apps[r["pid"]].add(r["mid"])
    plan = get_plan()      # صفحة لكل player_id (player_pages.py) — نفس slugs make_players حرفياً

    players_rows = []
    for page in plan["pages"]:
        slug, rows, name = page["slug"], page["goals"], page["display_en"]
        if not slug or not rows:
            continue
        last = rows[0]
        tid = last["team_id"]
        team = teams.get(tid, {})
        opp_id = (last["away_id"] if last["home_id"] == tid
                  else last["home_id"])
        opp = teams.get(opp_id, {})
        lg = team_lg.get(tid)
        cur = season_of.get(lg)
        pid = page["stats_pid"] or 0
        sg = sum(1 for g in rows
                 if g["season"] == cur and g["league_code"] == lg
                 and g["detail"] != "Own Goal" and g["team_id"] == tid)
        players_rows.append([
            slug, page["display_ar"] or last["ar"] or name, name, tid,
            team.get("ar", ""), team.get("en", ""), team.get("logo", ""),
            colors.get(str(tid)),
            opp.get("ar", ""), opp.get("en", ""),
            last["date"], last["home_id"] == tid,
            pid, (len(apps[pid]) if pid else None), sg,
        ])

    js = ("window.FBFollowData = " +
          json.dumps({"teams": teams_rows, "players": players_rows,
                      "pa": plan["stubs"]},   # روابط لاعبين قديمة ← الجديدة (متابعة محفوظة بالمتصفح)
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
  header { text-align:center; margin-bottom:16px; }
  h1 { font-size:20px; }
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
  /* تعديل + إضافة (12 أكتوبر): زر تعديل يحوّل الكروت لوضع اختيار، و«+» يفتح ورقة بحث سفلية (قرار عمرو، مرجع FotMob) */
  .fedit { margin-inline-start:auto; background:var(--card);
           color:var(--text); border:1px solid var(--line);
           padding:0 16px; border-radius:22px; cursor:pointer;
           font-family:inherit; font-size:14px; min-height:44px; }
  .fadd { background:var(--card); color:var(--text);
          border:1px solid var(--line); border-radius:50%;
          width:44px; height:44px; cursor:pointer; font-family:inherit;
          font-size:24px; line-height:1; display:flex;
          align-items:center; justify-content:center; padding:0; }
  .ftab { min-height:44px; }
  /* ثلاثة تبويبات + «تعديل» + «+» (تبويب الدوريات، 27 أكتوبر 2026) بعرض 390px: حشو أصغر والتبويبات تتقلّص قبل أن يُقصّ «+» */
  .ftabs { gap:6px; }
  .ftab { padding:9px 12px; flex:0 1 auto; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .fedit { padding:0 12px; flex:0 0 auto; }
  .fadd { flex:0 0 44px; }

  /* كروت مربعة، اثنان بالصف (دفعة 4، 5 أكتوبر). الخلفية لون النادي الصافي
     (--bg) والكتابة أبيض/أسود (--fg) تُحسب بالجافاسكربت بأعلى تباين WCAG
     (≥4.58 دائماً)، فلا opacity على النص كي لا ينقص التباين. بلا لون
     محفوظ: var(--card) وvar(--text) العاديان. */
  .fgrid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
           gap:10px; }
  .fcard { --bg:var(--card); --fg:var(--text);
           aspect-ratio:1/1; min-width:0; overflow:hidden;
           display:flex; flex-direction:column; align-items:center;
           justify-content:space-between; text-align:center; gap:4px;
           background:var(--bg); color:var(--fg);
           border:1px solid var(--line); border-radius:16px;
           padding:12px 10px; text-decoration:none;
           transition:transform .12s, border-color .15s; }
  .fcard:hover { border-color:var(--accent); }
  .fcard:active { transform:scale(.985); }
  .fcard .flogo { width:50px; height:50px; object-fit:contain;
                  border-radius:50%; background:#fff; padding:4px;
                  flex:0 0 auto; }
  .fcard .fname { font-weight:800; font-size:14.5px; line-height:1.25;
                  max-width:100%; overflow:hidden;
                  display:-webkit-box; -webkit-line-clamp:2;
                  -webkit-box-orient:vertical; }
  .fcard .fmatch { display:flex; flex-direction:column; align-items:center;
                   gap:1px; max-width:100%; font-size:12px; line-height:1.35; }
  .fcard .flbl { font-weight:700; font-size:11px; }
  .fcard .fopp { max-width:100%; overflow:hidden; text-overflow:ellipsis;
                 white-space:nowrap; font-weight:600; }
  .fcard .fwhen { font-variant-numeric:tabular-nums; white-space:nowrap; }
  .fcard .fpst { font-weight:800; }
  /* لاعب: صورة دائرية + شعار النادي بالزاوية */
  .fcard .fph { position:relative; width:62px; height:62px; flex:0 0 auto; }
  .fcard .fph .fimg, .fcard .fph .finit { width:62px; height:62px;
        border-radius:50%; object-fit:cover; display:flex;
        align-items:center; justify-content:center; background:#fff; }
  .fcard .fph .finit { background:var(--fg); color:var(--bg);
        font-weight:800; font-size:26px; }
  .fcard .fph .fbadge { position:absolute; inset-inline-end:-4px; bottom:-2px;
        width:24px; height:24px; border-radius:50%; background:#fff;
        padding:2px; object-fit:contain; border:1px solid var(--bg); }
  .fcard .fpn { display:flex; flex-direction:column; line-height:1.2;
                max-width:100%; }
  .fcard .ffirst { font-weight:400; font-size:13px; white-space:nowrap;
                   overflow:hidden; text-overflow:ellipsis; min-height:1.2em; }
  .fcard .ffam { font-weight:800; font-size:14.5px; white-space:nowrap;
                 overflow:hidden; text-overflow:ellipsis; }
  .fcard .fpills { display:flex; gap:5px; flex-wrap:nowrap;
                   justify-content:center; max-width:100%; }
  .fcard .fpill { border:1.5px solid var(--fg); border-radius:20px;
                  padding:1px 8px; font-size:11px; font-weight:700;
                  white-space:nowrap; font-variant-numeric:tabular-nums; }
  .fempty { color:var(--muted); font-size:14px; text-align:center;
            padding:36px 10px; background:var(--card);
            border-radius:12px; }

  /* وضع الاختيار: دائرة اختيار بكل كرت + شريط سفلي (إزالة من المفضلة / تم) */
  .fcard { position:relative; }
  .fsel { display:none; position:absolute; top:8px; inset-inline-end:8px;
          width:26px; height:26px; border-radius:50%;
          border:2px solid var(--fg); background:rgba(0,0,0,.18); }
  .editing .fsel { display:block; }
  .editing .fcard { cursor:pointer; }
  .fcard.sel { border-color:var(--accent); box-shadow:0 0 0 2px var(--accent) inset; }
  .fcard.sel .fsel { background:var(--accent); border-color:var(--accent); }
  .fcard.sel .fsel::after { content:""; position:absolute; left:7px; top:3px;
          width:6px; height:11px; border:solid #fff; border-width:0 2.5px 2.5px 0;
          transform:rotate(45deg); }
  body.fediting .wrap { padding-bottom:84px; }
  .fbar { display:none; position:fixed; left:0; right:0; bottom:0; z-index:920;
          background:var(--card); border-top:1px solid var(--line);
          padding:10px 16px calc(10px + env(safe-area-inset-bottom)); gap:10px; }
  .fbar.on { display:flex; }
  .fbar button { min-height:44px; border-radius:10px; font-family:inherit;
                 font-size:15px; font-weight:700; cursor:pointer; }
  .fbar .rm { flex:1; background:#e5484d; color:#fff; border:none; }
  .fbar .rm:disabled { opacity:.38; cursor:default; }
  .fbar .dn { background:var(--card2); color:var(--text);
              border:1px solid var(--line); padding:0 22px; }

  /* ورقة «+» السفلية (30 أكتوبر 2026، دفعة 4 بنود 3-7، نمط FotMob): تُفتح بنصف الارتفاع بقائمة ما تتابعه بهذا التبويب (زر متابَع/متابعة)
     وخانة البحث مثبّتة بالأسفل؛ النقر على الخانة يمدّها لكامل الارتفاع، الخانة للأعلى والنتائج تحتها (قائمة المتابَع تختفي خلفها).
     .fsh يتبع visualViewport (top/height بالجافاسكربت) فلا تختبئ الخانة خلف لوحة مفاتيح iOS (بند 5). */
  .fsh { position:fixed; left:0; right:0; top:0; height:100%; z-index:960; display:none; }
  .fsh.on { display:block; }
  .fsh .bd { position:absolute; inset:0; background:rgba(0,0,0,.55); }
  .fsheet { position:absolute; left:0; right:0; bottom:0; margin:0 auto;
            max-width:720px; height:56%; display:flex; flex-direction:column;
            background:var(--card); border-radius:18px 18px 0 0;
            padding:8px 16px calc(10px + env(safe-area-inset-bottom));
            transition:height .28s ease, border-radius .28s ease; }
  .fsh.full .fsheet { height:100%; border-radius:0; padding-top:calc(8px + env(safe-area-inset-top)); }
  .fsheet > .grab { order:0; } .fsheet > .fsh-h { order:1; }
  .fsheet > .ffol { order:2; } .fsheet > .sfield { order:3; } .fsheet > .fres { order:4; display:none; }
  .fsh.full .fsheet > .sfield { order:2; animation:fshIn .22s ease; }
  .fsh.full .fsheet > .fres { order:3; display:block; animation:fshIn .22s ease; }
  .fsh.full .fsheet > .ffol { display:none; }
  .fsh.full .fsheet > .grab { visibility:hidden; height:0; margin:0; }
  @keyframes fshIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
  @media (prefers-reduced-motion: reduce) { .fsheet { transition:none; } .fsh.full .fsheet > .sfield, .fsh.full .fsheet > .fres { animation:none; } }
  .ffol { overflow-y:auto; flex:1; min-height:0; }
  .fr .fph { width:36px; height:36px; border-radius:50%; object-fit:cover; background:#fff; flex:0 0 auto; }
  .fsheet .grab { width:40px; height:4px; border-radius:2px; background:var(--line);
                  margin:0 auto 6px; }
  .fsheet .fsh-h { display:flex; align-items:center; justify-content:space-between; }
  .fsheet .fsh-h h3 { font-size:17px; }
  .fsheet .fx { background:none; border:none; color:var(--muted); font-size:26px;
                width:44px; height:44px; cursor:pointer; font-family:inherit; line-height:1; }
  /* الخانة = search_field المشتركة (.sfield بـSEARCH_CSS، 30 أكتوبر 2026)؛ هنا الهامش فقط */
  .fsheet .sfield { margin:8px 0 4px; flex:0 0 auto; }
  .fsh.full .fsheet .sfield { margin:4px 0 8px; }
  .fres { overflow-y:auto; flex:1; min-height:0; }
  .fr { display:flex; align-items:center; gap:12px; min-height:56px; padding:6px 2px;
        border-bottom:1px solid var(--line); cursor:pointer; }
  .fr:last-child { border-bottom:none; }
  .fr img { width:36px; height:36px; object-fit:contain; flex:0 0 auto; }
  .fr .frt { flex:1; min-width:0; display:flex; flex-direction:column; line-height:1.3; }
  .fr .frn { font-size:15px; font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .fr .frl { font-size:12px; color:var(--muted); }
  .fpillb { min-height:36px; min-width:84px; border-radius:18px; padding:0 14px;
            font-family:inherit; font-size:13px; font-weight:700; cursor:pointer;
            background:var(--accent); color:#fff; border:1px solid var(--accent); }
  .fpillb.on { background:transparent; color:var(--muted); border-color:var(--line); }
  .fhint { color:var(--muted); font-size:13px; text-align:center; padding:26px 10px; }
"""

STYLE = ("<style>" + VARS + FOLLOWING_CSS + NAV_CSS
         + SEARCH_CSS + "</style>")

def following_view_script(t, lang, depth, league_names, league_info=None):
    """
    التبويبان (فرق/لاعبون) + العرض + وضع الاختيار + ورقة «إضافة فرق»، يبني الكروت من follow_data.js حسب FBPrefs
    (12 أكتوبر 2026: أُزيلت شاشة التعديل الطويلة — شرائح الدوريات/الأندية — ودوري/منتخبات لا تُعرض هنا).
    ⚠️ الإضافة تبحث بـ`window.FBSEARCH.c` (الأندية فقط، 7 دوريات) من search_data.js **يُحمَّل كسولاً عند فتح الورقة** فقط.
    ⚠️ متابعة نادٍ من دوري غير مختار بـfbLeagues (لو القائمة غير فارغة) تضيف دوريه كي لا يزيله cleanClubs بصفحة أخرى.
    """
    up = "../" * depth
    upl = up + ("en/" if lang == "en" else "")
    X = {"remove": t["f_remove"], "done": t["f_done"], "follow": t["f_follow"], "following": t["f_followed"],
         "add": t["f_add_teams"], "ph": t["f_search_team"], "hint": t["f_type_hint"], "none": t["no_results"],
         "noteams": t["f_no_teams"], "noleagues": t["f_no_leagues"], "addl": t["f_add_leagues"], "lgs": t["s_leagues"],
         "addp": t["f_add_players"], "php": t["f_search_player"], "phl": t["f_search_league"], "hintp": t["f_type_hint_p"],
         "fnone": t["f_sheet_none"]}

    def esc(k):
        return t[k].replace('"', '\\"')

    js = """
<script src="__UP__follow_data.js" defer></script>
<script>
(function(){
  var FB = window.FBPrefs;
  if (!FB) return;
  var LANG = "__LANG__", UP = "__UP__", UPL = "__UPL__";
  var EDIT = "__EDIT__";
  var F_UP = "__F_UP__", F_LAST = "__F_LAST__", F_GOAL = "__F_GOAL__";
  var F_VS = "__F_VS__", F_B_APPS = "__F_B_APPS__", F_B_GOALS = "__F_B_GOALS__", PST = "__PST__";
  var X = __X__, LGN = __LGN__, LGI = __LGI__;   // LGI: {code: [اسم، دولة، شعار]} — الدوريات العشرة (27 أكتوبر 2026)
  var NO_TEAMS = X.noteams, NO_PLAYERS = "__NO_PLAYERS__";

  var tabTeams = document.getElementById('tab-teams');
  var tabPlayers = document.getElementById('tab-players');
  var tabLeagues = document.getElementById('tab-leagues');
  var viewLeagues = document.getElementById('view-leagues');
  var editBtn = document.getElementById('fedit');
  var addBtn = document.getElementById('fadd');
  var bar = document.getElementById('fbar');
  var rmBtn = document.getElementById('frm');
  var doneBtn = document.getElementById('fdone');
  var viewTeams = document.getElementById('view-teams');
  var viewPlayers = document.getElementById('view-players');
  if (!tabTeams || !editBtn) return;

  var activeTab = 'teams';
  var editMode = false;
  var sel = {};   // العناصر المختارة بوضع التعديل: مفتاح (معرّف النادي / slug اللاعب) → true

  function esc(s){
    return (''+s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                 .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function pad(n){ return (n<10?'0':'')+n; }
  function fmtDate0(d){ return (''+(d||'')).slice(0, 10); }
  // التاريخ/الوقت: UTC مخزَّن → محلي المتصفح (نفس منطق matchtime.py)؛ بلا وقت
  // (نتائج قديمة) يبقى التاريخ كما هو.
  function fmtWhen(d){
    d = (''+(d||''));
    var m = d.match(/^(\\d{4}-\\d{2}-\\d{2})[ T](\\d{2}):(\\d{2})/);
    if (m){
      var dt = new Date(m[1]+'T'+m[2]+':'+m[3]+':00Z');
      if (!isNaN(dt.getTime()))
        return dt.getFullYear()+'-'+pad(dt.getMonth()+1)+'-'+pad(dt.getDate())
               +' · '+pad(dt.getHours())+':'+pad(dt.getMinutes());
    }
    return d.slice(0, 10);
  }
  // لون الكتابة: أبيض أو أسود، الأعلى تبايناً على الخلفية (WCAG)
  function lum(hex){
    var n = parseInt(hex.slice(1), 16), c = [n>>16&255, n>>8&255, n&255];
    c = c.map(function(v){ v/=255; return v<=.03928 ? v/12.92
                                   : Math.pow((v+.055)/1.055, 2.4); });
    return .2126*c[0] + .7152*c[1] + .0722*c[2];
  }
  function fgFor(hex){
    var L = lum(hex);
    return (1.05)/(L+.05) >= (L+.05)/.05 ? '#fff' : '#000';
  }
  function paint(el, hex){
    if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return;
    el.style.setProperty('--bg', hex);
    el.style.setProperty('--fg', fgFor(hex));
  }
  function logoSrc(logo){
    // ⚠️ نفس منطق search_view.py::clubHtml — رابط بعيد كما هو،
    //    مسار محلي (logos/xxx.png) يحتاج UP (الملف بجذر الموقع).
    return (logo && logo.indexOf('http') === 0) ? logo : (UP + (logo || ''));
  }
  function mk(href, cls, html){
    var a = document.createElement('a');
    a.className = 'fcard ' + cls;
    a.href = href;
    a.innerHTML = html;
    return a;
  }
  function logoImg(cls, logo){
    if (!logo) return '';
    return '<img class="'+cls+'" loading="lazy" decoding="async" alt="" src="'
      +esc(logoSrc(logo))+'" onerror="this.style.visibility=\\'hidden\\'">';
  }
  // معرّف اللاعب → صورة المزوّد؛ بلا معرّف/فشل تحميل → دائرة بأول حرف
  var PHOTO = 'https://media.api-sports.io/football/players/';
  function initial(name){
    var c = (''+name).trim().charAt(0);
    return c ? c.toUpperCase() : '?';
  }

  function nSel(){ return Object.keys(sel).length; }
  function updateBar(){
    var n = nSel();
    rmBtn.disabled = !n;
    rmBtn.textContent = X.remove + (n ? ' (' + n + ')' : '');
  }
  // دائرة اختيار + اعتراض النقر بوضع التعديل (الكرت رابط: لا تنقّل أثناء الاختيار)
  function decorate(el, key){
    var c = document.createElement('span');
    c.className = 'fsel';
    el.appendChild(c);
    el.setAttribute('data-key', key);
    if (sel[key]) el.classList.add('sel');
    el.addEventListener('click', function(e){
      if (!editMode) return;
      e.preventDefault();
      var k = el.getAttribute('data-key');
      if (sel[k]) delete sel[k]; else sel[k] = true;
      el.classList.toggle('sel', !!sel[k]);
      updateBar();
    });
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
      return 0;
    }
    box.style.display = ''; empty.style.display = 'none';
    rows.forEach(function(r){
      var tid=r[0], ar=r[1], en=r[2], logo=r[3], color=r[4],
          oppAr=r[5], oppEn=r[6], date=r[8], isUp=r[10],
          st=r[11], tg=r[12], og=r[13];
      var name = LANG==='ar' ? (ar||en) : (en||ar);
      var opp = LANG==='ar' ? (oppAr||oppEn) : (oppEn||oppAr);
      var lbl = isUp ? F_UP : F_LAST;
      var when;
      if (isUp && st === 'PST') when = '<span class="fpst">'+esc(PST)+'</span>';
      else if (isUp || tg == null) when = '<span dir="ltr">'+esc(fmtWhen(date))+'</span>';
      else when = '<span dir="ltr">'+esc(tg+' - '+og+' · '+fmtDate0(date))+'</span>';
      var html = logoImg('flogo', logo)
        +'<div class="fname" dir="auto">'+esc(name)+'</div>'
        +'<div class="fmatch"><span class="flbl">'+esc(lbl)+'</span>'
        +(opp ? '<span class="fopp" dir="auto">'+esc(F_VS)+' '+esc(opp)+'</span>' : '')
        +'<span class="fwhen">'+when+'</span></div>';
      var el = mk(UPL+'clubs/'+tid+'.html', 'fclub', html);
      paint(el, color);
      decorate(el, String(tid));
      box.appendChild(el);
    });
    return rows.length;
  }

  // متابعة محفوظة بـslug قديم (صار stub) ← تُحوَّل للـslug الجديد ويُحفَظ
  function normPlayers(){
    var d = window.FBFollowData;
    if (!d || !d.pa) return;
    var p = FB.getPlayers(), q = [], ch = false;
    p.forEach(function(s){
      var t = d.pa[s] || s;
      if (t !== s) ch = true;
      if (q.indexOf(t) < 0) q.push(t); else ch = true;
    });
    if (ch) FB.setPlayers(q);
  }

  function renderPlayers(){
    normPlayers();
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
      return 0;
    }
    box.style.display = ''; empty.style.display = 'none';
    rows.forEach(function(r){
      var slug=r[0], ar=r[1], en=r[2], tLogo=r[6], color=r[7],
          pid=r[12], apps=r[13], sg=r[14];
      var name = (LANG==='ar' ? (ar||en) : (en||ar)) || '';
      var parts = name.trim().split(' ').filter(Boolean);
      // الأول عادي، والعائلة (آخر كلمة) عريضة؛ اسم من كلمة واحدة = سطر عريض فقط
      var fam = parts.pop() || '';
      var first = parts.join(' ');
      var photo = pid
        ? '<img class="fimg" loading="lazy" decoding="async" alt="" src="'
          +PHOTO+pid+'.png" data-i="'+esc(initial(name))+'">'
        : '<div class="finit">'+esc(initial(name))+'</div>';
      var html = '<div class="fph">'+photo+logoImg('fbadge', tLogo)+'</div>'
        +'<div class="fpn"><span class="ffirst" dir="auto">'+esc(first)+'</span>'
        +'<span class="ffam" dir="auto">'+esc(fam)+'</span></div>'
        +'<div class="fpills">'
        +'<span class="fpill">'+esc(F_B_APPS)+' '+(apps == null ? '—' : apps)+'</span>'
        +'<span class="fpill">'+esc(F_B_GOALS)+' '+(sg == null ? 0 : sg)+'</span></div>';
      var el = mk(UPL+'players/'+slug+'.html', 'fplayer', html);
      var im = el.querySelector('.fimg');
      if (im) im.addEventListener('error', function(){
        var d = document.createElement('div');
        d.className = 'finit'; d.textContent = im.getAttribute('data-i');
        im.replaceWith(d);
      });
      paint(el, color);
      decorate(el, slug);
      box.appendChild(el);
    });
    return rows.length;
  }

  // الدوريات المتابَعة (27 أكتوبر 2026، طلب عمرو #4): fbLeagues — شعار + اسم + دولة، النقر = صفحة الدوري، «تعديل» يزيل. ليست تنبيهات.
  function renderLeagues(){
    var box = document.getElementById('leagueCards');
    var empty = document.getElementById('leaguesEmpty');
    if (!box) return 0;
    box.innerHTML = '';
    var codes = (FB.getLeagues() || []).filter(function(c){ return LGI[c]; });
    if (!codes.length){
      box.style.display = 'none';
      empty.textContent = X.noleagues;
      empty.style.display = '';
      return 0;
    }
    box.style.display = ''; empty.style.display = 'none';
    codes.forEach(function(c){
      var g = LGI[c];
      var html = logoImg('flogo', g[2])
        + '<div class="fname" dir="auto">' + esc(g[0]) + '</div>'
        + '<div class="fmatch"><span class="flbl">' + esc(g[1]) + '</span></div>';
      var el = mk(UPL + 'leagues/' + c.toLowerCase() + '.html', 'fleague', html);
      decorate(el, c);
      box.appendChild(el);
    });
    return codes.length;
  }

  var nTeams = 0, nPlayers = 0, nLeagues = 0;
  function render(){
    tabTeams.classList.toggle('active', activeTab === 'teams');
    tabPlayers.classList.toggle('active', activeTab === 'players');
    tabLeagues.classList.toggle('active', activeTab === 'leagues');
    viewTeams.style.display = activeTab === 'teams' ? '' : 'none';
    viewPlayers.style.display = activeTab === 'players' ? '' : 'none';
    viewLeagues.style.display = activeTab === 'leagues' ? '' : 'none';
    nTeams = renderTeams() || 0;
    nPlayers = renderPlayers() || 0;
    nLeagues = renderLeagues() || 0;
    var cur = activeTab === 'teams' ? nTeams : (activeTab === 'leagues' ? nLeagues : nPlayers);
    if (editMode && !cur) { editMode = false; sel = {}; }   // لا شيء للتعديل: نخرج من وضع الاختيار
    document.getElementById('teamCards').classList.toggle('editing', editMode);
    document.getElementById('playerCards').classList.toggle('editing', editMode);
    document.getElementById('leagueCards').classList.toggle('editing', editMode);
    document.body.classList.toggle('fediting', editMode);
    bar.classList.toggle('on', editMode);
    editBtn.style.display = (!editMode && cur) ? '' : 'none';
    // (30 أكتوبر 2026، دفعة 4 بند 6) «+» بالتبويبات الثلاثة (كان مخفياً بتبويب اللاعبين)
    addBtn.style.display = !editMode ? '' : 'none';
    addBtn.setAttribute('aria-label', activeTab === 'leagues' ? X.addl : (activeTab === 'players' ? X.addp : X.add));
    updateBar();
  }

  tabTeams.addEventListener('click', function(){ activeTab = 'teams'; sel = {}; render(); });
  tabPlayers.addEventListener('click', function(){ activeTab = 'players'; sel = {}; render(); });
  tabLeagues.addEventListener('click', function(){ activeTab = 'leagues'; sel = {}; render(); });
  editBtn.addEventListener('click', function(){ editMode = true; sel = {}; render(); });
  doneBtn.addEventListener('click', function(){ editMode = false; sel = {}; render(); });
  rmBtn.addEventListener('click', function(){
    if (!nSel()) return;
    // نفس التخزين الذي تستعمله أزرار المتابعة (FBPrefs)
    if (activeTab === 'teams') FB.setClubs(FB.getClubs().filter(function(id){ return !sel[String(id)]; }));
    else if (activeTab === 'leagues') FB.setLeagues((FB.getLeagues() || []).filter(function(c){ return !sel[c]; }));
    else FB.setPlayers(FB.getPlayers().filter(function(s){ return !sel[s]; }));
    sel = {};
    render();
  });

  // ── ورقة «+» (30 أكتوبر 2026، دفعة 4 بنود 3-7، نمط FotMob) ──
  //   الفتح = نصف الارتفاع: ما تتابعه بهذا التبويب (زر متابَع/متابعة) والخانة مثبّتة بالأسفل. النقر على الخانة = كامل الارتفاع، الخانة
  //   أعلى والنتائج تحتها (قائمة المتابَع تختفي خلفها). النتائج من نوع التبويب وحده (بند 4 — كانت الدوريات تظهر بتبويب الأندية):
  //   الأندية = FBSEARCH.c (assets/search_top.js كسولاً)، الدوريات = LGI، اللاعبون = FBFollowData.players (نفس slugs المتابعة: اسم +
  //   ناديه، بند 6). .fsh يتبع visualViewport (top/height) فلا تختبئ الخانة خلف لوحة مفاتيح iOS (بند 5).
  var sheet = document.getElementById('fsheet');
  var sq = document.getElementById('fsq');
  var sres = document.getElementById('fres');
  var sfol = document.getElementById('ffol');
  var kind = 'teams', keepFull = false;
  function norm(s){
    s = ('' + s).toLowerCase();
    var o = '';
    for (var i = 0; i < s.length; i++){
      var c = s.charCodeAt(i);
      if (c >= 1611 && c <= 1618) continue;                 // التشكيل
      if (c === 1571 || c === 1573 || c === 1570) c = 1575; // أإآ → ا
      if (c === 1609) c = 1610;                             // ى → ي
      if (c === 1577) c = 1607;                             // ة → ه
      o += String.fromCharCode(c);
    }
    return o;
  }
  function loadSearch(cb){
    if (window.FBSEARCH) { cb(); return; }
    var sc = document.createElement('script');
    sc.src = UP + 'assets/search_top.js?v=__SV__';
    sc.onload = cb;
    document.head.appendChild(sc);
  }
  function pillText(on){ return on ? X.following : X.follow; }
  // صف واحد بالورقة: صورة + اسم + سطر فرعي + زر متابعة؛ النقر بأي مكان بالصف يبدّل، والكروت خلف الورقة تتحدّث فوراً
  function mkRow(img, name, sub, isOn, toggle){
    var row = document.createElement('div');
    row.className = 'fr';
    row.innerHTML = img + '<div class="frt"><span class="frn" dir="auto">' + esc(name) + '</span>'
      + (sub ? '<span class="frl" dir="auto">' + esc(sub) + '</span>' : '') + '</div>'
      + '<button type="button" class="fpillb"></button>';
    var pill = row.querySelector('.fpillb');
    function paintPill(){
      var on = isOn();
      pill.classList.toggle('on', on); pill.textContent = pillText(on); pill.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    paintPill();
    row.addEventListener('click', function(){ toggle(); paintPill(); render(); });
    return row;
  }
  function flip(get, set, key){
    var A = (get() || []).slice(), i = A.indexOf(key);
    if (i >= 0) A.splice(i, 1);
    else { A.push(key); if (FB.markSetupDone) FB.markSetupDone(); }
    set(A);
  }
  // (27 أكتوبر 2026) لا يُضاف دوري النادي لـfbLeagues: متابعة الدوري صريحة (تبويب «الدوريات»/زر صفحة الدوري)
  function clubRow(id, name, lg, logo){
    return mkRow(logoImg('', logo), name, LGN[lg] || lg || '',
      function(){ return FB.getClubs().indexOf(id) >= 0; },
      function(){ flip(FB.getClubs, FB.setClubs, id); });
  }
  function leagueRow(c){
    var g = LGI[c];
    return mkRow(logoImg('', g[2]), g[0], g[1],
      function(){ return (FB.getLeagues() || []).indexOf(c) >= 0; },
      function(){ flip(FB.getLeagues, FB.setLeagues, c); });
  }
  function playerRow(r){
    var slug = r[0], name = (LANG === 'ar' ? (r[1] || r[2]) : (r[2] || r[1])) || '';
    var club = LANG === 'ar' ? (r[4] || r[5]) : (r[5] || r[4]);
    var img = r[12] ? '<img class="fph" loading="lazy" decoding="async" alt="" src="' + PHOTO + r[12] + '.png">' : logoImg('', r[6]);
    var row = mkRow(img, name, club,
      function(){ return FB.getPlayers().indexOf(slug) >= 0; },
      function(){ flip(FB.getPlayers, FB.setPlayers, slug); });
    var im = row.querySelector('img.fph');
    if (im) im.addEventListener('error', function(){ im.className = ''; im.src = logoSrc(r[6] || ''); }, {once: true});
    return row;
  }
  // نصف الارتفاع: ما تتابعه بنوع التبويب
  function showFollowed(){
    sfol.innerHTML = '';
    var n = 0, d = window.FBFollowData;
    if (kind === 'teams'){
      var byId = {}, lgOf = {};
      if (d) d.teams.forEach(function(r){ byId[r[0]] = r; });
      ((window.FBSEARCH && window.FBSEARCH.c) || []).forEach(function(r){ lgOf[r[0]] = r[3]; });
      FB.getClubs().forEach(function(id){
        var r = byId[id]; if (!r) return;
        sfol.appendChild(clubRow(id, LANG === 'ar' ? (r[1] || r[2]) : (r[2] || r[1]), lgOf[id], r[3])); n++;
      });
    } else if (kind === 'leagues'){
      (FB.getLeagues() || []).forEach(function(c){ if (LGI[c]) { sfol.appendChild(leagueRow(c)); n++; } });
    } else {
      var byS = {};
      if (d) d.players.forEach(function(r){ byS[r[0]] = r; });
      FB.getPlayers().forEach(function(s){ var r = byS[s]; if (r) { sfol.appendChild(playerRow(r)); n++; } });
    }
    if (!n) sfol.innerHTML = '<div class="fhint">' + esc(X.fnone) + '</div>';
  }
  // مطابقة: بداية الاسم أو بداية أي كلمة فيه أولاً، ثم احتواء
  function hits(list, keys, q, max){
    var pre = [], mid = [];
    list.forEach(function(r){
      var best = 9;
      keys.forEach(function(k){
        var s = norm(r[k] || ''), i = s.indexOf(q);
        if (i < 0) return;
        best = Math.min(best, (i === 0 || s.indexOf(' ' + q) >= 0) ? 0 : 1);
      });
      if (best === 0) pre.push(r); else if (best === 1) mid.push(r);
    });
    return pre.concat(mid).slice(0, max);
  }
  function showResults(){
    var q = norm(sq.value.trim());
    sres.innerHTML = '';
    var rows = [];
    if (kind === 'leagues'){
      // الدوريات العشرة كلها بلا كتابة؛ بكتابة = المطابقة بالاسم أو الدولة أو الرمز
      rows = Object.keys(LGI).filter(function(c){
        var g = LGI[c];
        return !q || norm(g[0]).indexOf(q) >= 0 || norm(g[1]).indexOf(q) >= 0 || norm(c).indexOf(q) >= 0;
      });
      rows.forEach(function(c){ sres.appendChild(leagueRow(c)); });
    } else if (!q){
      sres.innerHTML = '<div class="fhint">' + esc(kind === 'players' ? X.hintp : X.hint) + '</div>';
      return;
    } else if (kind === 'players'){
      rows = hits((window.FBFollowData && window.FBFollowData.players) || [], [1, 2], q, 40);
      rows.forEach(function(r){ sres.appendChild(playerRow(r)); });
    } else {
      rows = hits((window.FBSEARCH && window.FBSEARCH.c) || [], [1, 2], q, 40);
      rows.forEach(function(r){ sres.appendChild(clubRow(r[0], LANG === 'ar' ? (r[1] || r[2]) : (r[2] || r[1]), r[3], r[4])); });
    }
    if (!rows.length) sres.innerHTML = '<div class="fhint">' + esc(X.none) + '</div>';
  }
  // لوحة مفاتيح iOS: Safari لا يصغّر النافذة الأساسية، فالورقة الثابتة بأسفلها تختفي خلف اللوحة. نلصق .fsh بالجزء الظاهر فعلاً.
  var VV = window.visualViewport;
  function fitVV(){
    if (!VV || !sheet.classList.contains('on')) return;
    sheet.style.top = VV.offsetTop + 'px';
    sheet.style.height = VV.height + 'px';
  }
  if (VV) { VV.addEventListener('resize', fitVV); VV.addEventListener('scroll', fitVV); }
  function expand(){
    if (sheet.classList.contains('full')) return;
    sheet.classList.add('full');
    showResults();
  }
  function collapse(){
    sheet.classList.remove('full');
    sq.value = '';
    sres.innerHTML = '';
    showFollowed();
  }
  function openSheet(){
    kind = activeTab;
    keepFull = false;
    sheet.classList.remove('full');
    sheet.classList.add('on');
    document.body.style.overflow = 'hidden';
    document.getElementById('fshh').textContent = kind === 'leagues' ? X.addl : (kind === 'players' ? X.addp : X.add);
    var ph = kind === 'leagues' ? X.phl : (kind === 'players' ? X.php : X.ph);
    sq.placeholder = ph; sq.setAttribute('aria-label', ph);
    sq.value = ''; sres.innerHTML = '';
    showFollowed();
    fitVV();
    if (kind === 'teams') loadSearch(function(){ showFollowed(); if (sheet.classList.contains('full')) showResults(); });
  }
  function closeSheet(){
    sheet.classList.remove('on', 'full');
    sheet.style.top = ''; sheet.style.height = '';
    document.body.style.overflow = '';
    if (document.activeElement === sq) sq.blur();
  }
  addBtn.addEventListener('click', openSheet);
  document.getElementById('fx').addEventListener('click', closeSheet);
  document.getElementById('fbd').addEventListener('click', closeSheet);
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeSheet(); });
  sq.addEventListener('focus', function(){ keepFull = false; expand(); });
  sq.addEventListener('input', function(){ expand(); showResults(); });
  // نقرة داخل النتائج تُفقد الخانة التركيز: تبقى الورقة ممتدة. فقدان التركيز بلا كتابة ولا نقرة بالنتائج = عودة لنصف الارتفاع.
  sres.addEventListener('pointerdown', function(){ keepFull = true; });
  sq.addEventListener('blur', function(){
    setTimeout(function(){
      if (sheet.classList.contains('on') && !keepFull && !sq.value.trim() && document.activeElement !== sq) collapse();
    }, 120);
  });
  window.addEventListener('load', function(){ if (sheet.classList.contains('on') && !sheet.classList.contains('full')) showFollowed(); });

  window.__ffRenderTeams = render;
  render();
  window.addEventListener('load', render);
  // رابط «ابدأ» من بطاقة الرئيسية: following.html?add=1 يفتح ورقة إضافة فرق مباشرة
  if (/[?&]add=1/.test(location.search)) openSheet();
})();
</script>"""

    from make_search import asset_v, OUT_TOP
    return (js.replace("__UP__", up)
              .replace("__SV__", asset_v(OUT_TOP))
              .replace("__UPL__", upl)
              .replace("__LANG__", lang)
              .replace("__EDIT__", esc("edit"))
              .replace("__F_UP__", esc("f_upcoming"))
              .replace("__F_LAST__", esc("f_last_result"))
              .replace("__F_GOAL__", esc("f_last_goal"))
              .replace("__F_VS__", esc("f_vs"))
              .replace("__F_B_APPS__", esc("f_b_apps"))
              .replace("__F_B_GOALS__", esc("f_b_goals"))
              .replace("__PST__", esc("st_pst"))
              .replace("__NO_PLAYERS__", esc("f_no_players"))
              .replace("__X__", json.dumps(X, ensure_ascii=False))
              .replace("__LGN__", json.dumps(league_names, ensure_ascii=False))
              .replace("__LGI__", json.dumps(league_info or {}, ensure_ascii=False)))


def following_page(conn, lang, leagues, logos):
    t = T[lang]
    depth = 0 if lang == "ar" else 1
    switch = "en/following.html" if lang == "ar" else "../following.html"
    league_names = {c: league_name(c, lang) for c in leagues}
    # الدوريات العشرة لتبويب «الدوريات» وورقة «+» (27 أكتوبر 2026): [اسم، دولة، شعار (المحلي ثم المزوّد ثم العلم؛ مسار من الجذر)]
    lg_logos, lg_local = load_league_logos()
    league_info = {c: [league_name(c, lang), COUNTRY.get(c, ("", ""))[0 if lang == "ar" else 1],
                       lg_local.get(c) or lg_logos.get(c) or f"flags/{FLAG[c]}.svg"] for c in LEAGUES}

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
        + THEME_HEAD + STYLE + "<style>" + TOUCH_CSS + "</style>" + swipe_head() +
        '</head>\n<body>\n<div class="wrap">\n'
        # (25 أكتوبر 2026، دفعة UI 3) عنوان الصف = اسم التبويب؛ h1 مخفي للفهرسة والقارئات
        + appbar(t, lang, switch, title=t["nv_following"]) +
        f'<h1 class="vh">{t["following"]}</h1>\n'

        # تبويبا الأندية/اللاعبين + «تعديل» (وضع اختيار) + «+» (ورقة إضافة فرق) — راجع following_view_script()
        f'<div class="ftabs">'
        f'<button class="ftab active" id="tab-teams">{t["s_clubs"]}</button>'
        f'<button class="ftab" id="tab-leagues">{t["s_leagues"]}</button>'
        f'<button class="ftab" id="tab-players">{t["s_players"]}</button>'
        f'<button class="fedit" id="fedit">{t["edit"]}</button>'
        f'<button class="fadd" id="fadd" aria-label="{t["f_add_teams"]}">+</button>'
        f'</div>\n'

        # الكروت فارغة بالـHTML، تُملأ وقت العرض من follow_data.js حسب FBPrefs
        f'<div class="fview" id="view-teams">'
        f'<div class="fgrid" id="teamCards"></div>'
        f'<div class="fempty" id="teamsEmpty" style="display:none">'
        f'{t["f_no_teams"]}</div></div>\n'
        f'<div class="fview" id="view-leagues" style="display:none">'
        f'<div class="fgrid" id="leagueCards"></div>'
        f'<div class="fempty" id="leaguesEmpty" style="display:none">'
        f'{t["f_no_leagues"]}</div></div>\n'
        f'<div class="fview" id="view-players" style="display:none">'
        f'<div class="fgrid" id="playerCards"></div>'
        f'<div class="fempty" id="playersEmpty" style="display:none">'
        f'{t["f_no_players"]}</div></div>\n'

        # شريط وضع الاختيار (ثابت أسفل الشاشة)
        f'<div class="fbar" id="fbar">'
        f'<button class="rm" id="frm" disabled>{t["f_remove"]}</button>'
        f'<button class="dn" id="fdone">{t["f_done"]}</button></div>\n'

        # ورقة «إضافة فرق» (بحث بالأندية فقط، يُحمَّل search_data.js كسولاً)
        f'<div class="fsh" id="fsheet"><div class="bd" id="fbd"></div>'
        f'<div class="fsheet" role="dialog" aria-modal="true"><div class="grab"></div>'
        f'<div class="fsh-h"><h3 id="fshh">{t["f_add_teams"]}</h3>'
        f'<button class="fx" id="fx" aria-label="x">&times;</button></div>'
        f'<div class="ffol" id="ffol"></div>'   # ما تتابعه بهذا التبويب (نصف الارتفاع، دفعة 4 بند 3)
        + search_field(f'<input type="search" id="fsq" placeholder="{t["f_search_team"]}" aria-label="{t["f_search_team"]}" autocomplete="off">') +
        f'<div class="fres" id="fres"></div></div></div>\n'

        '</div>\n'
        + navbar(t, depth, "following", lang)
        + THEME_SCRIPT
        + prefs_script()
        + following_view_script(t, lang, depth, league_names, league_info) + swipe_script()
        + nav_script(t) + pwa_script(lang)
        +
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
