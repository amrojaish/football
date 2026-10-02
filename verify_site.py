#!/usr/bin/env python3
"""
بوابة البناء النظيف: قائمة ملفات `_site/` مقابل الموقع الحي (git ref)
=======================================================================
الموقع الحي (قبل التحويل) = ملفات الفرع المنشورة بقواعد build_site.is_published.
البوابة: **صفر ملفات ناقصة** (موجودة بالحي وغائبة من البناء) — وإلا يفشل الخروج.
الزائد (بالبناء وغائب عن الحي) والمختلف المحتوى يُعرَضان للعلم لا للفشل.

    python verify_site.py [--site _site] [--ref HEAD] [--content] [--accept path ...]

--content يقارن بصمة git للمحتوى (على ويندوز مع autocrlf غير موثوق — للـCI/لينكس).
--accept مسارات ناقصة مقبولة صراحةً (حذف مقصود، مثل live.json).
"""
import subprocess
import sys
from pathlib import Path

import build_site

BASE = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    site = Path(arg("--site", "_site"))
    if not site.is_absolute():
        site = BASE / site
    ref = arg("--ref", "HEAD")
    accept = set()
    if "--accept" in sys.argv:
        i = sys.argv.index("--accept") + 1
        while i < len(sys.argv) and not sys.argv[i].startswith("--"):
            accept.add(sys.argv[i])
            i += 1

    out = subprocess.check_output(["git", "-C", str(BASE), "ls-tree", "-r", ref],
                                  text=True, encoding="utf-8")
    live = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        path = path.strip('"')
        if build_site.is_published(path):
            live[path] = meta.split()[2]
    built = set(build_site.walk_publishable(site))

    missing = sorted(p for p in live if p not in built and p not in accept)
    accepted = sorted(p for p in live if p not in built and p in accept)
    extra = sorted(p for p in built if p not in live)
    print(f"الحي ({ref}): {len(live):,} ملفاً · البناء: {len(built):,}")
    print(f"ناقص: {len(missing)} · زائد: {len(extra)} · ناقص مقبول: {accepted}")
    for lbl, lst in (("ناقص", missing), ("زائد", extra)):
        for p in lst[:60]:
            print(f"  {lbl}: {p}")
        if len(lst) > 60:
            print(f"  … و{len(lst) - 60} غيرها")

    if "--content" in sys.argv:
        both = [p for p in built if p in live]
        inp = "\n".join(str(site / p) for p in both) + "\n"
        res = subprocess.run(["git", "hash-object", "--stdin-paths"], input=inp,
                             capture_output=True, text=True, encoding="utf-8")
        hashes = res.stdout.split()
        diff = [p for p, h in zip(both, hashes) if live[p] != h]
        print(f"محتوى: متطابق {len(both) - len(diff):,} · مختلف {len(diff):,}")
        by = {}
        for p in diff:
            top = p.split("/")[0] if "/" in p else "(root)"
            if top == "en" and p.count("/") > 1:
                top = "en/" + p.split("/")[1]
            by[top] = by.get(top, 0) + 1
        print(f"  المختلف بالمجلد: {by}")
        for p in diff[:15]:
            print(f"  مختلف: {p}")

    if missing:
        print("❌ البوابة فشلت: ملفات ناقصة")
        sys.exit(1)
    print("✅ البوابة: صفر ملفات ناقصة")


if __name__ == "__main__":
    main()
