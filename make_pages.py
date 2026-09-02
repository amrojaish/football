#!/usr/bin/env python3
"""
الصفحات الثابتة — عن الموقع + 404
====================================
بيولّد ثلاث صفحات:

    about.html       → "عن الموقع" بالعربي
    en/about.html    → نفسها بالإنجليزي
    404.html         → صفحة الخطأ — **بالجذر فقط**، وبلغتين معاً

⚠️ صفحة 404 واحدة لا اثنتان: GitHub Pages يخدمها لأي مسار ناقص
   تحت الجذر — بما فيها /en/... — ولا يستطيع أن يعرف
   لغة الرابط المكسور. لذلك النصان معروضان فوق بعض.

⚠️ كل روابط 404 **مطلقة** (/...) لا نسبية. الصفحة تُعرض
   من URL خطأ أياً كان عمقه، فأي رابط نسبي ينكسر حتماً. (نسخة أسوأ
   من درس 32)

كل النصوص من i18n.py، وكل الألوان من theme.py.

التشغيل:
    python make_pages.py
"""

import os
from config import BASE_DIR
from i18n import T, LANGS, DIR, SWITCH_LABEL
from theme import VARS, THEME_HEAD, THEME_SCRIPT, THEME_BUTTON, head_meta
from navbar import NAV_CSS, navbar, settings_overlay, nav_script

BASE = BASE_DIR

# ═══════════════════════════════════════════════════════════
#  عبّئ هذين السطرين — لا يُخمَّنان
# ═══════════════════════════════════════════════════════════

# اسمك كما تكتبه أنت — بالعربي وبالإنجليزي
AUTHOR = {
    "ar": "عمرو أبو جيش",
    "en": "Amro Abu Jaish",       
}

# سطر تعريفي قصير
AUTHOR_BIO = {
    "ar": "خريج علوم الذكاء الاصطناعي والبيانات — جامعة مانشستر متروبوليتان",
    "en": "BSc Artificial Intelligence and Data Science — "
          "Manchester Metropolitan University",
}

# التواصل — اتركه فارغاً وسيختفي القسم كاملاً بدل أن يظهر ناقصاً (مبدأ 17)
CONTACT = {
    "email": "abujaishamr@gmail.com",
    "linkedin": "",    # <- الرابط الكامل https://...
    "github": "",      # <- الرابط الكامل https://...
}

# مسار الموقع على GitHub Pages — لروابط 404 المطلقة
# ⚠️ **جذر الموقع** — كان "/football" قبل الدومين المخصص
#    (27 أغسطس). كل روابط صفحة 404 مطلقة وتُبنى منه، فتغييره
#    وحده يصحّحها كلها.
SITE_ROOT = ""

# ═══════════════════════════════════════════════════════════


PAGE_CSS = """
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
  header { text-align:center; margin-bottom:30px; }
  h1 { font-size:26px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  h2 { font-size:16px; margin:26px 0 8px; padding-inline-start:10px;
       border-inline-start:3px solid var(--accent); }
  p { font-size:14px; color:var(--text); }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:11px; padding:16px; margin-top:10px; }
  .who { font-size:15px; font-weight:600; }
  .bio { color:var(--muted); font-size:13px; margin-top:3px; }
  .links { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
  .links a { background:var(--card2); color:var(--accent);
             border:1px solid var(--line); border-radius:8px;
             padding:7px 14px; font-size:13px; text-decoration:none; }
  .links a:hover { border-color:var(--accent); }
  .home { display:inline-block; margin-top:30px; color:var(--accent);
          text-decoration:none; font-size:14px; }
  .home:hover { text-decoration:underline; }
  footer { text-align:center; color:var(--muted); font-size:12px;
           margin-top:36px; line-height:1.9; }

  /* 404 */
  .nf { text-align:center; padding:60px 16px 20px; }
  .nf .code { font-size:64px; font-weight:700; color:var(--accent);
              line-height:1; }
  .nf h1 { font-size:22px; margin-top:14px; }
  .nf p { color:var(--muted); margin-top:6px; }
  .nf .sep { border:none; border-top:1px solid var(--line);
             margin:34px auto; max-width:180px; }
"""

STYLE = "<style>" + VARS + PAGE_CSS + "</style>"
STYLE_NAV = "<style>" + VARS + PAGE_CSS + NAV_CSS + "</style>"


def head(title, desc, lang, prefix="", style=STYLE):
    """رأس الصفحة — نفس بنية make_site3"""
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        # ⚠️ `lang` إجباري — بدونه تأخذ الصفحة الإنجليزية
        #    manifest عربياً فيظهر اسم التطبيق خطأً عند التثبيت.
        + head_meta(title, desc, prefix, lang)
        + THEME_HEAD + style
        + '</head>\n<body>\n'
    )


def contact_links(t):
    """روابط التواصل — تختفي كلياً إن كانت فارغة (مبدأ 17)"""
    items = []
    if CONTACT["email"].strip():
        items.append(f'<a href="mailto:{CONTACT["email"].strip()}">'
                     f'{CONTACT["email"].strip()}</a>')
    if CONTACT["linkedin"].strip():
        items.append(f'<a href="{CONTACT["linkedin"].strip()}" '
                     f'target="_blank" rel="noopener">LinkedIn</a>')
    if CONTACT["github"].strip():
        items.append(f'<a href="{CONTACT["github"].strip()}" '
                     f'target="_blank" rel="noopener">GitHub</a>')

    if not items:
        return ""

    return (f'<h2>{t["about_contact"]}</h2>'
            f'<div class="links">{"".join(items)}</div>')


def build_about(lang):
    """صفحة عن الموقع بلغة واحدة"""
    t = T[lang]

    switch = "en/about.html" if lang == "ar" else "../about.html"
    home = "index.html" if lang == "ar" else "index.html"
    prefix = "" if lang == "ar" else "../"
    # ⚠️ عمق الصفحة: about.html بالجذر (0) و en/about.html (1).
    #    navbar يبني الروابط منه ومن اللغة معاً — لا من العمق وحده.
    depth = 0 if lang == "ar" else 1

    name = AUTHOR.get(lang, "").strip() or AUTHOR.get("ar", "").strip()
    bio = AUTHOR_BIO.get(lang, "").strip()

    sections = ""
    for key in ("what", "data", "fix", "verify", "update"):
        sections += (f'<h2>{t["about_" + key]}</h2>'
                     f'<p>{t["about_" + key + "_1"]}</p>')

    who = ""
    if name:
        bio_html = f'<div class="bio">{bio}</div>' if bio else ""
        who = (f'<h2>{t["about_who"]}</h2>'
               f'<div class="card"><div class="who">{name}</div>'
               f'{bio_html}</div>')

    return (
        head(f'{t["about"]} — {t["site_title"]}', t["about_what_1"][:150],
             lang, prefix, STYLE_NAV)
        + '<div class="wrap">\n'
        f'<div class="topbar">'
        f'<span style="display:flex;gap:8px">'
        f'<a class="lang" href="{switch}">{SWITCH_LABEL[lang]}</a>'
        f'{THEME_BUTTON}</span><span></span></div>\n'
        f'<header><h1>{t["about"]}</h1>'
        f'<div class="sub">{t["site_title"]} — {t["site_sub"]}</div>'
        f'</header>\n'
        f'{sections}\n{who}\n{contact_links(t)}\n'
        f'<a class="home" href="{home}">{t["back_home"]}</a>\n'
        f'<footer>{t["footer_1"]}<br>{t["footer_2"]}</footer>\n'
        '</div>\n'
        + navbar(t, depth=depth, active="", lang=lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT
        + nav_script(t)
        + '</body>\n</html>'
    )


def build_404():
    """صفحة واحدة بلغتين — كل الروابط مطلقة"""
    ar, en = T["ar"], T["en"]

    return (
        '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>404 — {ar["site_title"]}</title>\n'
        '<meta name="robots" content="noindex">\n'
        f'<link rel="icon" type="image/svg+xml" '
        f'href="{SITE_ROOT}/favicon.svg">\n'
        + THEME_HEAD + STYLE
        + '</head>\n<body>\n<div class="wrap">\n'
        '<div class="nf">'
        '<div class="code">404</div>'
        f'<h1>{ar["nf_title"]}</h1>'
        f'<p>{ar["nf_msg"]}</p>'
        f'<p><a class="home" href="{SITE_ROOT}/index.html">'
        f'{ar["nf_home"]}</a></p>'
        '<hr class="sep">'
        '<div dir="ltr">'
        f'<h1>{en["nf_title"]}</h1>'
        f'<p>{en["nf_msg"]}</p>'
        f'<p><a class="home" href="{SITE_ROOT}/en/index.html">'
        f'{en["nf_home"]}</a></p>'
        '</div>'
        '</div>\n</div>\n'
        '</body>\n</html>'
    )


def main():
    os.makedirs(BASE / "en", exist_ok=True)

    made = []
    for lang in LANGS:
        html = build_about(lang)
        path = (BASE / "about.html" if lang == "ar"
                else BASE / "en" / "about.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        made.append(path.name if lang == "ar" else "en/about.html")

    with open(BASE / "404.html", "w", encoding="utf-8") as f:
        f.write(build_404())
    made.append("404.html")

    print(f"\n{'=' * 55}")
    print("  تم توليد:")
    for m in made:
        print(f"      {m}")
    print(f"{'=' * 55}")

    if not AUTHOR["en"].strip():
        print("  ⚠️ AUTHOR['en'] فاضي — الاسم الإنجليزي يرتد للعربي")
    if not any(v.strip() for v in CONTACT.values()):
        print("  ⚠️ CONTACT فاضي — قسم التواصل مخفي بالكامل")
    print()


if __name__ == "__main__":
    main()
