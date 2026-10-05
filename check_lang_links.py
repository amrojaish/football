#!/usr/bin/env python3
"""
فحص روابط اللغة: يمرّ على كل صفحة HTML مولَّدة ويكشف روابط داخلية تنتقل بين اللغتين.

  • صفحة /en/... تربط بصفحة خارج /en/  → خطأ
  • صفحة عربية (خارج /en/) تربط بصفحة داخل /en/ → خطأ
  • مستثنى: رابط تبديل اللغة نفسه (anchor بسمة hreflang، أو داخل <span class="seg"> بالإعدادات)
    — لكنه يُفحَص على حدة: يجب أن يشير إلى **نفس الصفحة بالنسخة الأخرى** وأن يكون الملف موجوداً.

التشغيل (من جذر المشروع، بعد التوليد):
    python check_lang_links.py            # ملخص بالأعداد + 3 أمثلة لكل مجموعة
    python check_lang_links.py --all      # كل الأمثلة
الخروج: 0 إن لم توجد روابط عابرة للغة، 1 غير ذلك.
"""
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urljoin, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", ".github", "node_modules", "_site", "_archive", "backups", "dist",
             ".wrangler", "__pycache__", "assets", "icons", "logos", "flags", "migrations"}
# 404.html ثنائية اللغة عمداً (فقرة عربية + فقرة إنجليزية بالصفحة نفسها)
SKIP_FILES = {"google42cb06cb72108c7f.html", "404.html"}

A_TAG = re.compile(r"<a\b([^>]*)>", re.I)
HREF = re.compile(r'\bhref\s*=\s*("([^"]*)"|\'([^\']*)\')', re.I)
SEG = re.compile(r'<span class="seg">.*?</span>', re.S)
HREFLANG = re.compile(r"\bhreflang\s*=", re.I)
OPTION = re.compile(r'<option\s+value="([^"#]*\.html)"', re.I)

# مولِّد كل نوع صفحة (للتجميع)
GEN = [("matches/", "make_matches.py"), ("clubs/", "make_clubs.py"),
       ("players/", "make_players.py"), ("leagues/", "make_leagues.py")]
GEN_FILES = {"index.html": "make_site3.py", "leagues.html": "make_leagues.py",
             "about.html": "make_pages.py", "following.html": "make_following.py",
             "search.html": "make_search_page.py", "404.html": "make_pages.py",
             "offline.html": "make_pages.py"}
TARGET_TYPES = [("matches/", "match"), ("clubs/", "club"), ("players/", "player"),
                ("leagues/", "league-season")]
TARGET_FILES = {"index.html": "home", "leagues.html": "leagues", "about.html": "about",
                "following.html": "following", "search.html": "search"}


def lang_of(path):
    return "en" if path.startswith("en/") else "ar"


def strip_lang(path):
    return path[3:] if path.startswith("en/") else path


def generator(path):
    p = strip_lang(path)
    for pre, g in GEN:
        if p.startswith(pre):
            return g
    return GEN_FILES.get(p, "other:" + p)


def target_type(path):
    p = strip_lang(path)
    for pre, t in TARGET_TYPES:
        if p.startswith(pre):
            return t
    return TARGET_FILES.get(p, "other")


def pages():
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".html") and f not in SKIP_FILES:
                full = os.path.join(root, f)
                yield os.path.relpath(full, BASE).replace(os.sep, "/"), full


SEG_ANCHOR = re.compile(r'<a([^>]*)>', re.I)


def switch_links(html):
    """روابط التبديل: anchors بسمة hreflang + روابط <span class="seg"> غير "#"."""
    out = []
    for m in A_TAG.finditer(html):
        if HREFLANG.search(m.group(1)):
            h = HREF.search(m.group(1))
            if h:
                out.append(h.group(2) if h.group(2) is not None else h.group(3))
    for seg in SEG.findall(html):
        for m in A_TAG.finditer(seg):
            h = HREF.search(m.group(1))
            if h:
                v = h.group(2) if h.group(2) is not None else h.group(3)
                if v.strip() != "#":
                    out.append(v)
    return out


def norm_path(rel, href):
    u = urlparse(urljoin("https://saffara.app/" + rel, href.strip()))
    path = u.path.lstrip("/")
    if path == "" or path.endswith("/"):
        path += "index.html"
    return path


def links(html):
    html = SEG.sub("", html)
    for m in A_TAG.finditer(html):
        attrs = m.group(1)
        if HREFLANG.search(attrs):
            continue
        h = HREF.search(attrs)
        if h:
            yield h.group(2) if h.group(2) is not None else h.group(3)
    # منسدلات المواسم: <option value="x.html"> + onchange=location.href
    for v in OPTION.findall(html):
        yield v


def main():
    show_all = "--all" in sys.argv
    groups = defaultdict(list)   # (dir, generator, target_type) -> [(src, href)]
    bad_switch = defaultdict(list)
    n_pages = n_links = n_switch = 0
    for rel, full in pages():
        n_pages += 1
        src_lang = lang_of(rel)
        with open(full, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        for href in switch_links(html):
            n_switch += 1
            want = ("en/" + rel) if src_lang == "ar" else rel[3:]
            got = norm_path(rel, href)
            if got != want:
                bad_switch[(src_lang, generator(rel), "wrong target")].append((rel, f"{href} -> {got} (want {want})"))
            elif not os.path.exists(os.path.join(BASE, want)):
                bad_switch[(src_lang, generator(rel), "missing file")].append((rel, got))
        for href in links(html):
            href = href.strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            u = urlparse(urljoin("https://saffara.app/" + rel, href))
            if u.netloc not in ("saffara.app", ""):
                continue
            path = u.path.lstrip("/")
            if path == "" or path.endswith("/"):
                path += "index.html"
            if not path.endswith(".html"):
                continue
            n_links += 1
            if lang_of(path) != src_lang:
                groups[(src_lang, generator(rel), target_type(path))].append((rel, href))

    total = sum(len(v) for v in groups.values())
    print(f"صفحات: {n_pages} · روابط داخلية: {n_links} · روابط عابرة للغة: {total}")
    for (lang, gen, tt), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        pages_n = len({s for s, _ in items})
        print(f"\n[{lang} → {'ar' if lang == 'en' else 'en'}] {gen} → {tt}: "
              f"{len(items)} رابطاً في {pages_n} صفحة")
        seen = set()
        shown = 0
        for src, href in items:
            if (src, href) in seen:
                continue
            seen.add((src, href))
            print(f"    {src}  →  {href}")
            shown += 1
            if shown >= 3 and not show_all:
                break
    nbad = sum(len(v) for v in bad_switch.values())
    print()
    print(f"روابط التبديل المفحوصة: {n_switch} · معطوبة: {nbad}")
    for (lang, gen, kind), items in sorted(bad_switch.items(), key=lambda kv: -len(kv[1])):
        print(f"[switch {lang}] {gen} {kind}: {len(items)}")
        for src, info in items[:3]:
            print(f"    {src}  →  {info}")
    return 1 if (total or nbad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
