#!/usr/bin/env python3
"""
مسح كل المولَّد قبل البناء (بوابة البناء النظيف)
==================================================
يقرأ generated_paths.txt ويمسح مجلدات/ملفات `dir`/`file`/`removed` (ما عدا `keep`
والحالة الدائمة `state`). التشغيل قبل `update_all.py` بالـCI يضمن أن الموقع المنشور
يُبنى بالكامل من الكود والقاعدة، لا من بقايا ملفات قديمة بالشجرة.

    python clean_generated.py          ← يمسح
    python clean_generated.py --dry    ← يعدّ فقط
"""
import os
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_spec():
    spec = {"dir": [], "file": [], "removed": [], "keep": [], "state": []}
    for line in (BASE / "generated_paths.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, path = line.split(None, 1)
        spec[kind].append(path.strip())
    return spec


def main():
    dry = "--dry" in sys.argv
    spec = parse_spec()
    keep = {BASE / k for k in spec["keep"]}
    n_files = 0
    for d in spec["dir"]:
        root = BASE / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*"), reverse=True):
            if p.is_file():
                if p in keep:
                    continue
                n_files += 1
                if not dry:
                    p.unlink()
            elif p.is_dir() and not dry:
                try:
                    p.rmdir()
                except OSError:
                    pass
    for f in spec["file"] + spec["removed"]:
        p = BASE / f
        if p.is_file():
            n_files += 1
            if not dry:
                p.unlink()
    print(f"{'سيُمسح' if dry else 'مُسح'}: {n_files} ملفاً مولَّداً "
          f"(محفوظ: {len(keep)} يتيماً مُتتبَّعاً + الحالة الدائمة)")


if __name__ == "__main__":
    main()
