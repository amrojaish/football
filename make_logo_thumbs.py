#!/usr/bin/env python3
"""
thumbs/<team_id>.webp — شعارات الأندية مصغّرة 64px لبطاقات الرئيسية
====================================================================
شعارات المزوّد (media.api-sports.io) صور كاملة الحجم (متوسط ~40 ك.ب، حتى 124) تُعرض بـ26px،
فكانت الرئيسية تنزّل 117 شعاراً = 4.5 م.ب. هنا نولّد نسخة 64px (ضعف 32px للشاشات 2x) بصيغة WebP
(شفافية محفوظة، ~2 ك.ب).

المصدر لكل نادٍ: ملف `logo_local` إن وُجد (teams_arabic.csv — شعار معتمد يدوياً أو مُنظَّف)، وإلا
رابط المزوّد من جدول teams (لا حصة API: خادم صور مفتوح). **تراكمي**: ما له نسخة موجودة يُتخطّى
(`--force` لإعادة التوليد) فلا يتكرر التنزيل بكل بناء. فشل نادٍ لا يكسر البناء: الصفحة تعود
لرابط الأصل (`make_site3.thumb_of`).

المجلد `thumbs/` مُتتبَّع بـgit عمداً (≈0.4 م.ب بالكل): نتيجة هذا السكربت لا تُمسح بالبناء النظيف
وبالتالي لا يعتمد النشر على شبكة المزوّد. الأصول الأصلية بصفحات النادي/المباراة تبقى كما هي.

التشغيل:
    python make_logo_thumbs.py            # المفقود فقط
    python make_logo_thumbs.py --force    # الكل
    python make_logo_thumbs.py --check    # يسرد النسخ القديمة (مصدرها المحلي تغيّر) بلا توليد؛ خروج 1 إن وُجدت

⚠️ **نسخة قديمة (10 أكتوبر 2026، نادي قطر 2907):** "المتخطّى لأن الملف موجود" أبقى صورة OFFICIAL LOGO SOON بعد استبدال
الشعار. الآن لكل نادٍ له `logo_local` بصمة sha256 لمصدره محفوظة بـ`thumbs/_src_hash.json`؛ اختلاف البصمة (أو غيابها) =
إعادة توليد تلقائية. (البصمة لا mtime: git/CI لا يحفظان أوقات الملفات.) مصادر المزوّد البعيدة لا بصمة لها (تُعاد بـ--force).
"""
import csv
import hashlib
import io
import json
import sqlite3
import sys
import urllib.request

from PIL import Image

from config import BASE_DIR, DB_FILE, TEAMS_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "thumbs"
SIZE = 64
QUALITY = 82
UA = {"User-Agent": "Mozilla/5.0 (saffara thumbs)"}


def local_overrides():
    out = {}
    if TEAMS_FILE.exists():
        with open(TEAMS_FILE, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                tid = (r.get("team_id") or "").strip()
                loc = (r.get("logo_local") or "").strip()
                if tid and loc:
                    out[tid] = BASE_DIR / loc
    return out


HASHES = OUT / "_src_hash.json"


def src_hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_hashes():
    try:
        return json.loads(HASHES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def stale_locals(local, hashes):
    """معرّفات الأندية التي لها مصدر محلي وبصمته تخالف المسجَّلة (أو لا بصمة) أو لا نسخة لها."""
    return sorted(tid for tid, p in local.items()
                  if p.exists() and (not (OUT / f"{tid}.webp").exists() or hashes.get(tid) != src_hash(p)))


def load_source(tid, url, local):
    p = local.get(str(tid))
    if p and p.exists():
        return Image.open(p)
    if not url:
        return None
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return Image.open(io.BytesIO(r.read()))


def main():
    force = "--force" in sys.argv
    OUT.mkdir(exist_ok=True)
    local = local_overrides()
    hashes = load_hashes()
    stale = set(stale_locals(local, hashes))
    if "--check" in sys.argv:
        print("thumbs قديمة:", ", ".join(stale) if stale else "لا شيء")
        return 1 if stale else 0
    con = sqlite3.connect(DB_FILE)
    rows = con.execute("SELECT team_id, logo FROM teams ORDER BY team_id").fetchall()
    con.close()
    made = skipped = failed = 0
    before = after = 0
    for tid, url in rows:
        dest = OUT / f"{tid}.webp"
        if dest.exists() and not force and str(tid) not in stale:
            skipped += 1
            continue
        try:
            im = load_source(tid, url, local)
            if im is None:
                failed += 1
                continue
            im = im.convert("RGBA")
            im.thumbnail((SIZE, SIZE), Image.LANCZOS)   # يحفظ النسبة؛ CSS يعرضها object-fit:contain
            im.save(dest, "WEBP", quality=QUALITY, method=6)
            made += 1
            if str(tid) in local and local[str(tid)].exists():
                hashes[str(tid)] = src_hash(local[str(tid)])
            after += dest.stat().st_size
        except Exception as e:
            failed += 1
            print(f"  ✗ {tid}: {type(e).__name__}: {e}")
    if hashes:
        HASHES.write_text(json.dumps(hashes, sort_keys=True, indent=0), encoding="utf-8")
    print(f"thumbs: {made} جديد · {skipped} موجود · {failed} فشل → {OUT}"
          + (f" ({after // 1024} ك.ب للجديد)" if made else ""))


if __name__ == "__main__":
    sys.exit(main() or 0)
