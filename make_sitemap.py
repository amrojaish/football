#!/usr/bin/env python3
"""
توليد sitemap.xml
==================
بيمسح كل ملفات .html الموجودة فعلاً ويولّد خريطة موقع واحدة،
مع وسوم hreflang تربط كل صفحة عربية بنظيرتها الإنجليزية.

    sitemap.xml            → الناتج
    sitemap_state.json     → كاش البصمات (لا تحذفه، لا تعدّله يدوياً)

⚠️ **يمسح الملفات، لا يستعلم من الديتابيس.** السبب:
   make_clubs.py يتخطى أي نادٍ غير موجود بجدول teams،
   و make_matches.py يتخطى أي مباراة أحد نادييها مفقود.
   يعني في الديتابيس سجلات بلا ملفات HTML — وتقديمها لـGoogle
   يعني روابط 404 في الخريطة، وهي تُحسَب أخطاءً في Search Console.

⚠️ **lastmod من بصمة المحتوى لا من تاريخ الملف.** الأتمتة تعيد
   توليد كل الصفحات كل 30 دقيقة، فتاريخ التعديل يصير "اليوم"
   لكل صفحة دائماً. Google يتعلّم أن lastmod عندنا بلا معنى
   ويتجاهله. الكاش يجعل التاريخ يتغير فقط عند تغيّر المحتوى فعلاً.

⚠️ **robots.txt لا يعمل هنا.** الموقع project page، والزواحف
   تقرأ robots.txt من جذر الدومين (amrojaish.github.io) لا من
   /football/. تقديم الخريطة يتم عبر Google Search Console.

⚠️ 404.html مستثناة — لا تُفهرس صفحة خطأ.

صفر طلبات API.

التشغيل:
    python make_sitemap.py
"""

import hashlib
import json
import os
from datetime import date

from config import BASE_DIR

BASE = BASE_DIR

# عنوان الموقع — بلا / في النهاية
SITE = "https://amrojaish.github.io/football"

OUT = BASE / "sitemap.xml"
STATE = BASE / "sitemap_state.json"

# مجلدات لا تُمسح
SKIP_DIRS = {".git", ".github", "logos", "__pycache__", ".vscode", "venv"}

# ملفات لا تُفهرس
SKIP_FILES = {"404.html", "google42cb06cb72108c7f.html"}

# حد Google: 50,000 رابط للخريطة الواحدة
MAX_URLS = 50000


def file_hash(path):
    """بصمة محتوى الملف"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state():
    """كاش البصمات — path → {hash, lastmod}"""
    if not STATE.exists():
        return {}
    try:
        with open(STATE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        print("  ⚠️ sitemap_state.json تالف — سيُبنى من جديد")
        return {}


def scan():
    """كل ملفات .html الموجودة، كمسارات نسبية بفواصل /"""
    found = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".html"):
                continue
            if name in SKIP_FILES:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, BASE).replace(os.sep, "/")
            found.append(rel)
    return sorted(found)


def lang_of(rel):
    """عربي إن كان خارج en/، إنجليزي إن كان داخلها"""
    return "en" if rel == "en" or rel.startswith("en/") else "ar"


def pair_key(rel):
    """
    المفتاح المشترك بين النسختين.
    clubs/4532.html      → clubs/4532.html
    en/clubs/4532.html   → clubs/4532.html
    """
    return rel[3:] if rel.startswith("en/") else rel


def url_for(rel):
    """
    الرابط الكامل. index.html يُحوَّل لمسار المجلد — الشكل
    الأنظف والذي يعرضه GitHub Pages أصلاً على /football/
    """
    if rel == "index.html":
        return SITE + "/"
    if rel.endswith("/index.html"):
        return f"{SITE}/{rel[:-len('index.html')]}"
    return f"{SITE}/{rel}"


def esc(s):
    """ترميز XML — & أولاً وإلا ضاعفنا الترميز"""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def main():
    files = scan()

    if not files:
        print("  ❌ ما لقيت ولا ملف .html — شغّل make_site3.py أول")
        return

    if len(files) > MAX_URLS:
        print(f"  ❌ {len(files)} رابط — فوق حد Google ({MAX_URLS})")
        print("     تحتاج تقسيم الخريطة وملف sitemap index")
        return

    old = load_state()
    today = date.today().isoformat()
    new_state = {}
    changed = 0

    # البصمة والتاريخ لكل ملف
    for rel in files:
        h = file_hash(BASE / rel)
        prev = old.get(rel)

        if prev and prev.get("hash") == h and prev.get("lastmod"):
            lastmod = prev["lastmod"]
        else:
            lastmod = today
            changed += 1

        new_state[rel] = {"hash": h, "lastmod": lastmod}

    # ربط النسختين لوسوم hreflang
    pairs = {}
    for rel in files:
        pairs.setdefault(pair_key(rel), {})[lang_of(rel)] = rel

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
             '        xmlns:xhtml="http://www.w3.org/1999/xhtml">']

    for rel in files:
        group = pairs.get(pair_key(rel), {})

        lines.append("  <url>")
        lines.append(f"    <loc>{esc(url_for(rel))}</loc>")
        lines.append(f"    <lastmod>{new_state[rel]['lastmod']}</lastmod>")

        # hreflang — فقط إن وُجدت النسختان
        if len(group) == 2:
            for code in ("ar", "en"):
                other = group[code]
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="{code}" '
                    f'href="{esc(url_for(other))}"/>'
                )
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" '
                f'href="{esc(url_for(group["ar"]))}"/>'
            )

        lines.append("  </url>")

    lines.append("</urlset>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=1, sort_keys=True)

    # إحصاء
    paired = sum(1 for g in pairs.values() if len(g) == 2)
    orphans = [rel for rel in files if len(pairs[pair_key(rel)]) == 1]
    size_kb = OUT.stat().st_size / 1024

    print(f"\n{'=' * 55}")
    print(f"  sitemap.xml — {len(files)} رابط  ({size_kb:.0f} كيلوبايت)")
    print(f"{'=' * 55}")
    print(f"  أزواج ar/en مرتبطة بـhreflang: {paired}")
    print(f"  تغيّر تاريخها هذه المرة: {changed}")

    if orphans:
        print(f"\n  ⚠️ {len(orphans)} صفحة بلا نظير بالغة الأخرى:")
        for rel in orphans[:10]:
            print(f"      {rel}")
        if len(orphans) > 10:
            print(f"      ... و{len(orphans) - 10} غيرها")

    print(f"""
  التقديم لـGoogle (مرة واحدة فقط):
      Search Console ← Sitemaps ← أضف: sitemap.xml
    """)


if __name__ == "__main__":
    main()
