#!/usr/bin/env python3
"""
تجميع الموقع المنشور في `_site/` (يستعمله سير عمل النشر محلياً وبالـCI)
=========================================================================
Pages بمصدر "GitHub Actions" ينشر مجلداً نبنيه نحن (لا الفرع). القواعد نفسها
التي كان `_config.yml` يطبّقها (Jekyll):

  يُستبعد: .git/.github وأي ملف/مجلد يبدأ بنقطة (ما عدا `.well-known`)، `_archive/`،
           `__pycache__/`، `_site/`، `*.py`، `*.csv`، `*.md`، `_config.yml`،
           `generated_paths.txt`، `live.json` (لم يعد مولَّداً)، والملفات الخاصة بأي مسار
           (`PRIVATE_PATTERNS`: `*.db` و`*.db-*` و`*.sqlite*` و`*.bak` و`sitemap_state.json`).
  يُنشر: كل ما عداها — بالمسارات نفسها (فالروابط لا تتغيّر).

⚠️ **حاجز الحجم:** يفشل إن تجاوز `_site/` 800 م.ب (حد Pages 1 غ.ب).
⚠️ **حواجز النشر (21 أكتوبر 2026):** يفشل إن وُجد بـ`_site/` ملف أكبر من 25 MiB (حد Cloudflare
   للملف) أو أكثر من 90,000 ملف أو أي ملف خاص (`PRIVATE_PATTERNS`) — نسخة
   `football_before_merges.db` كانت تُنشر للعموم من جذر المشروع.

    python build_site.py [--out _site] [--max-mb 800]
"""
import fnmatch
import os
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXCLUDE_DIRS = {"_archive", "__pycache__", "_site", "backups", "node_modules", "migrations",
                # مصادر JS (تُنسخ لـ/assets بـmake_assets.py) — لا تُنشر نسخة ثانية
                "assets_src"}
EXCLUDE_FILES = {"_config.yml", "generated_paths.txt", "live.json",
                 # أدوات الـworker/الاختبار — لا صفحة تجلبها (دفعة 3 تنبيهات الأهداف)
                 "package.json", "package-lock.json", "wrangler.toml", "worker.js",
                 # إعداد/كود استضافة الموقع على Cloudflare (saffara-site) — ليس ملفاً بالموقع
                 "wrangler.site.toml", "site_worker.js",
                 # سجلّ روابط اللاعبين (حالة دائمة + بذرتها): داخلي، لا يُنشر
                 "player_url_history.json", "player_url_history.seed.json"}
EXCLUDE_SUFFIX = (".py", ".csv", ".md", ".pyc", ".mjs")
# ملفات خاصة لا تُنشر أبداً، بأي مجلد (قواعد الديتابيس ونسخها، حالة الـsitemap)
PRIVATE_PATTERNS = ("*.db", "*.db-*", "*.sqlite*", "*.bak", "sitemap_state.json")
MAX_FILE_MIB = 25        # حد Cloudflare للملف الواحد
MAX_FILES = 90_000       # هامش تحت حد Workers Paid (100,000 ملف)
REQUIRED = ["index.html", "en/index.html", "404.html", "sw.js", "sitemap.xml",
            "assets/manifest.json", "CNAME", "robots.txt", "offline.html",
            "en/offline.html"]


def is_private(name):
    return any(fnmatch.fnmatch(name.lower(), p) for p in PRIVATE_PATTERNS)


def is_published(rel):
    """rel: مسار نسبي بشرطات مائلة للأمام."""
    parts = rel.split("/")
    for part in parts[:-1]:
        if part in EXCLUDE_DIRS:
            return False
        if part.startswith(".") and part != ".well-known":
            return False
    name = parts[-1]
    if is_private(name):
        return False
    if name.startswith(".") and parts[0] != ".well-known":
        return False
    if name in EXCLUDE_FILES and len(parts) == 1:
        return False
    return not name.endswith(EXCLUDE_SUFFIX)


def walk_publishable(root):
    for r, ds, fs in os.walk(root):
        rel_dir = os.path.relpath(r, root).replace(os.sep, "/")
        ds[:] = [d for d in ds if d not in EXCLUDE_DIRS
                 and (not d.startswith(".") or d == ".well-known")
                 and not (rel_dir == "." and d == ".git")]
        for f in fs:
            rel = f if rel_dir == "." else f"{rel_dir}/{f}"
            if is_published(rel):
                yield rel


def main():
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else BASE / "_site"
    limit = float(sys.argv[sys.argv.index("--max-mb") + 1]) if "--max-mb" in sys.argv else 800
    if not out.is_absolute():
        out = BASE / out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n = total = 0
    for rel in walk_publishable(BASE):
        src = BASE / rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        total += src.stat().st_size
        n += 1
    missing = [r for r in REQUIRED if not (out / r).exists()]
    print(f"_site: {n:,} ملفاً، {total / 1e6:.1f} م.ب (الحد {limit:.0f})")
    if missing:
        print(f"❌ ملفات أساسية غائبة: {missing}")
        sys.exit(1)
    if total / 1e6 > limit:
        print(f"❌ تجاوز الحد {limit:.0f} م.ب — لا نشر")
        sys.exit(1)
    # الحواجز على ما بـ_site فعلاً (لا على قائمة النسخ): يلتقط أي ملف وصل بطريق آخر
    built = [p for p in out.rglob("*") if p.is_file()]
    private = [p.relative_to(out).as_posix() for p in built if is_private(p.name)]
    big = [(p.relative_to(out).as_posix(), p.stat().st_size) for p in built
           if p.stat().st_size > MAX_FILE_MIB * 1024 * 1024]
    if private:
        print(f"❌ ملفات خاصة داخل _site: {private[:10]} — لا نشر")
        sys.exit(1)
    if big:
        print(f"❌ ملفات أكبر من {MAX_FILE_MIB} MiB: "
              + ", ".join(f"{r} ({s / 1048576:.1f} MiB)" for r, s in big[:10]) + " — لا نشر")
        sys.exit(1)
    if len(built) > MAX_FILES:
        print(f"❌ {len(built):,} ملفاً بـ_site (الحد {MAX_FILES:,}) — لا نشر")
        sys.exit(1)


if __name__ == "__main__":
    main()
