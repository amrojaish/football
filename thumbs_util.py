#!/usr/bin/env python3
"""
مساعد مشترك لشعارات الأندية المصغّرة (thumbs/) — تستعمله صفحات المباراة والنادي والدوري واللاعب
==========================================================================================
يولّدها make_logo_thumbs.py: `thumbs/<id>.webp` (64px للقوائم) و`thumbs/<id>-128.webp` (رؤوس الصفحات؛ كانت `@128` حتى 21 أكتوبر 2026).
بلا نسخة لنادٍ ما (فشل التوليد / نادٍ جديد قبل أول بناء) => يعود لرابط الأصل `fallback` فلا شعار مكسور.

up: بادئة المسار النسبي لجذر الموقع ("" / "../" / "../../").
"""
from config import BASE_DIR

THUMBS_DIR = BASE_DIR / "thumbs"
_have = None


def _names():
    global _have
    if _have is None:
        _have = {p.name for p in THUMBS_DIR.glob("*.webp")} if THUMBS_DIR.exists() else set()
    return _have


def thumb_src(tid, up, big=False):
    """مسار النسخة المصغّرة أو None إن لم توجد."""
    name = f"{tid}-128.webp" if big else f"{tid}.webp"
    return f"{up}thumbs/{name}" if name in _names() else None


def logo_img(tid, fallback, up, px, big=False, eager=False, cls=""):
    """
    وسم <img> للشعار بأبعاد ثابتة (بلا قفزة تخطيط). eager=True لشعارات رأس الصفحة (تُحمَّل فوراً
    وبأولوية عالية)؛ غير ذلك lazy + decoding=async.
    """
    src = thumb_src(tid, up, big) or fallback or ""
    if not src:
        return ""
    c = f' class="{cls}"' if cls else ""
    if eager:
        return f'<img{c} src="{src}" alt="" width="{px}" height="{px}" fetchpriority="high">'
    return f'<img{c} src="{src}" alt="" width="{px}" height="{px}" loading="lazy" decoding="async">'
