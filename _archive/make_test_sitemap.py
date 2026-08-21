#!/usr/bin/env python3
"""
خريطة تشخيصية صغيرة
=====================
`sitemap.xml` الكامل (4.5 ميغابايت · 9,398 رابطاً · ~28,000 عنصر
مع وسوم hreflang) يرفضه Google بـ"Sitemap could not be read"
رغم أن بنيته سليمة تماماً (فُحصت البداية والنهاية).

[مرجّح] السبب الحجم لا البنية. هذا الملف يولّد خريطة صغيرة
تحوي **الرئيسية وصفحات الأندية فقط** (~140 رابطاً) لاختبار
الفرضية:

    قَبِلها Google  → السبب الحجم مؤكَّد، والحل التقسيم
    رفضها أيضاً     → السبب البنية أو hreflang، ونفحص أعمق

⚠️ **لا يمسّ `sitemap.xml` الأصلي** — يكتب ملفاً منفصلاً
   `sitemap-test.xml` بجانبه.

⚠️ يستعمل نفس منطق `make_sitemap.py` (مسح الملفات الفعلية،
   لا استعلام الديتابيس) لضمان أن الفرق الوحيد هو الحجم.

التشغيل:
    python make_test_sitemap.py
"""

import os

from config import DB_FILE

BASE = DB_FILE.parent
SITE = "https://amrojaish.github.io/football"
OUT = BASE / "sitemap-test.xml"


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def url_for(rel):
    if rel == "index.html":
        return SITE + "/"
    if rel.endswith("/index.html"):
        return f"{SITE}/{rel[:-len('index.html')]}"
    return f"{SITE}/{rel}"


def main():
    files = []

    # الرئيسية بلغتيها
    for rel in ("index.html", "en/index.html",
                "about.html", "en/about.html"):
        if (BASE / rel).exists():
            files.append(rel)

    # صفحات الأندية فقط
    for d in ("clubs", "en/clubs"):
        p = BASE / d
        if p.exists():
            for f in sorted(p.glob("*.html")):
                files.append(f"{d}/{f.name}")

    if not files:
        print("ما لقيت ملفات — شغّل make_clubs.py أولاً")
        return

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/'
             'sitemap/0.9">']

    for rel in files:
        lines.append("  <url>")
        lines.append(f"    <loc>{esc(url_for(rel))}</loc>")
        lines.append("  </url>")

    lines.append("</urlset>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    kb = OUT.stat().st_size / 1024

    print(f"\n{'=' * 58}")
    print(f"  sitemap-test.xml — {len(files)} رابط  ({kb:.0f} كيلوبايت)")
    print(f"{'=' * 58}")
    print("""
  ⚠️ بلا وسوم hreflang عمداً — لعزل متغيّر واحد فقط (الحجم).

  الخطوات:
      1. git add . && git commit -m "خريطة تشخيصية" && git push
      2. استنى دقيقتين للنشر
      3. Search Console ← Sitemaps ← أضف:
             sitemap-test.xml
      4. راقب الحالة خلال ساعات

  إن قَبِلها  → السبب الحجم، والحل تقسيم الخريطة الأصلية
  إن رفضها    → السبب أعمق، نفحص الترميز أو الترويسات
    """)


if __name__ == "__main__":
    main()
