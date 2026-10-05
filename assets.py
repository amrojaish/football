#!/usr/bin/env python3
"""
روابط ملفات /assets (CSS/JS المشتركة) — مصدر واحد للمولِّدات
==============================================================
كل صفحة مباراة/لاعب/نادٍ كانت تحمل نسختها الكاملة من CSS وJS مضمَّنة
(~60% من حجم HTML، 650 م.ب من 1,081 م.ب). صارت الصفحات تربط ملفات
خارجية مولَّدة بـ`make_assets.py`، بمسارات مطلقة `/assets/...?v=<hash>`
(الـhash = أول 8 رموز من SHA1 للمحتوى، فيتغيّر الرابط عند أي تعديل).

⚠️ **هذا الملف لا يبني شيئاً** — يقرأ `assets/manifest.json` الذي يكتبه
   `make_assets.py`، ويفشل بصوت عالٍ إن غاب (شغّل make_assets.py أولاً —
   موضعه أول خطوة بـ`update_all.py`).

⚠️ **ترتيب CSS محفوظ حرفياً:** `{kind}.css` (VARS + أنماط النوع) ثم
   `site.css` (SEARCH + NAV + LIVE) — نفس تسلسل الكتلة المضمَّنة القديمة.

⚠️ **JS بـdefer:** `site.js` ثم `{kind}.{lang}.js`
   بالترتيب. `THEME_HEAD` يبقى مضمَّناً بالـhead (يمنع وميض الثيم).
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ASSETS_DIR = BASE / "assets"
MANIFEST = ASSETS_DIR / "manifest.json"

_files = None


def _manifest():
    global _files
    if _files is None:
        if not MANIFEST.exists():
            raise RuntimeError(
                "assets/manifest.json غير موجود — شغّل make_assets.py أولاً")
        _files = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    return _files


def url(name):
    """رابط مطلق مُصدَّر بـhash: /assets/<name>?v=<hash>"""
    return f"/assets/{name}?v={_manifest()[name]}"


def css_links(kind):
    """وسما <link> بترتيب الكتلة القديمة: نوع الصفحة ثم المشترك."""
    return (f'<link rel="stylesheet" href="{url(kind + ".css")}">\n'
            f'<link rel="stylesheet" href="{url("site.css")}">\n')


def script_tags(kind, lang):
    """وسوم JS مؤجَّلة بالترتيب: site.js ← حزمة النوع/اللغة."""
    return (f'<script src="{url("site.js")}" defer></script>\n'
            f'<script src="{url(f"{kind}.{lang}.js")}" defer></script>\n')
