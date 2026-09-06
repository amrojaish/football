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

import os
import sqlite3

from config import DB_FILE, LEAGUES
from i18n import T, LANGS, DIR, SWITCH_LABEL, league_name
from theme import VARS, THEME_HEAD, THEME_SCRIPT, head_meta
from navbar import NAV_CSS, navbar, settings_overlay, nav_script, pwa_script
from search_view import SEARCH_CSS, search_script, search_overlay
from onboard import CHIP_CSS, league_chips_html, club_chips_html
from prefs import prefs_script, club_map_script
from make_site3 import load_overrides

BASE = DB_FILE.parent

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
    });
  });

  document.querySelectorAll('#clubs .chip').forEach(function(x){
    x.addEventListener('click', function(){
      this.classList.toggle('on');
      var C = [];
      document.querySelectorAll('#clubs .chip.on').forEach(
        function(y){ C.push(+y.dataset.cl); });
      FB.setClubs(C);
    });
  });

  if (search) search.addEventListener('input', filterClubs);

  syncFromStorage();
})();
</script>"""


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
        f'{SWITCH_LABEL[lang]}</a><span></span></div>\n'
        f'<header><h1>{t["following"]}</h1>'
        f'<div class="sub">{t["site_sub"]}</div></header>\n'
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
        f'<footer>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + search_overlay(t)
        + navbar(t, depth, "following", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT
        + prefs_script() + club_map_script(conn)
        + FOLLOWING_SCRIPT
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
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
