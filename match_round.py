#!/usr/bin/env python3
"""
رقم الجولة (27 أكتوبر 2026، طلب عمرو) — `matches.round` من `league.round` بردّ المزوّد (fixtures يرجعه أصلاً، صفر طلبات إضافية)
==========================================================================================================================
⚠️ العمود يُضاف بهجرة يدوية واحدة (`migrate()`، راجع خطة الهجرة بالتقرير/README) — **الكود لا يضيفه بنفسه**: كل السكربتات تفحص
   وجوده (`has_round`) وتكتبه فقط إن وُجد، فقبل الهجرة يبقى السلوك القديم حرفياً (لا كسر للسحب الآلي بـCI).
⚠️ `INSERT OR REPLACE` يستبدل الصف كله: كل مكان يكتب صف مباراة من ردّ المزوّد يمرّر الجولة (وإلا تُمسح) — fetch_matches2.save_finished
   (ومعه fetch_overdue) وfetch_upcoming؛ وfetch_upcoming يملأ جولة كل مباريات الموسم الجاري من نفس الردّ (منتهية وقادمة) = تعبئة
   الموسم الجاري كاملة بأول تشغيل بعد الهجرة. المواسم القديمة: لا مصدر خام محفوظ → تبقى بلا جولة (لا سحب إضافي).

العرض (`label`): «Regular Season - 8» → «الجولة 8» / "Round 8"؛ مراحل معروفة مترجمة («Championship Round - 3» → «مرحلة البطولة - الجولة 3»)؛
غير المعروف كما هو.
"""
import re

COL = "round"

STAGES = {   # بادئة المزوّد → (عربي، إنجليزي)؛ «Regular Season» = بلا اسم مرحلة
    "Regular Season": ("", ""),
    "Championship Round": ("مرحلة البطولة", "Championship round"),
    "Championship Group": ("مجموعة البطولة", "Championship group"),
    "Relegation Round": ("مرحلة الهبوط", "Relegation round"),
    "Relegation Group": ("مجموعة الهبوط", "Relegation group"),
    "1st Phase": ("المرحلة الأولى", "1st phase"),
    "2nd Phase": ("المرحلة الثانية", "2nd phase"),
    "Group Stage": ("دور المجموعات", "Group stage"),
    # الكؤوس (الموجة 0، 3 نوفمبر 2026 — كل الجولات بمرشّحي cups_plan.md؛ المزوّد يسمّي مرحلة المجموعات بثلاث صيغ)
    "League Phase": ("مرحلة الدوري", "League phase"),               # دوري أبطال آسيا للنخبة
    "Regular season": ("دور المجموعات", "Group stage"),             # دوري أبطال أفريقيا (s صغيرة ≠ «Regular Season» الدوري)
    "Caf Confederation Cup": ("دور المجموعات", "Group stage"),      # كأس الكونفدرالية الأفريقية
}
WHOLE = {   # جولات بلا رقم
    "Relegation Play-offs": ("ملحق الهبوط", "Relegation play-offs"),
    "Relegation Round": ("مرحلة الهبوط", "Relegation round"),
    "Play-offs": ("الملحق", "Play-offs"),
    "Final": ("النهائي", "Final"),
    "Semi-finals": ("نصف النهائي", "Semi-finals"),
    "Quarter-finals": ("ربع النهائي", "Quarter-finals"),
    "Round of 16": ("دور الـ16", "Round of 16"),
    # الكؤوس (الموجة 0، 3 نوفمبر 2026)
    "Preliminary Round": ("الدور التمهيدي", "Preliminary round"),
    "1st Preliminary Round": ("الدور التمهيدي الأول", "1st preliminary round"),
    "2nd Preliminary Round": ("الدور التمهيدي الثاني", "2nd preliminary round"),
    "Round of 128": ("دور الـ128", "Round of 128"),
    "Round of 64": ("دور الـ64", "Round of 64"),
    "Round of 32": ("دور الـ32", "Round of 32"),
    "3rd place": ("مباراة المركز الثالث", "Third-place match"),
    # (6 نوفمبر 2026، الموجة 3) كأس رابطة المحترفين الإماراتية 2025/26 — دورا خروج المغلوب الأولان
    "1st Round": ("الدور الأول", "1st round"),
    "2nd Round": ("الدور الثاني", "2nd round"),
    "Group Stage": ("دور المجموعات", "Group stage"),                # مباراة واحدة بلا رقم (السوبر الإماراتي)
}


def has_round(conn):
    return any(r[1] == COL for r in conn.execute("PRAGMA table_info(matches)"))


def migrate(conn):
    """الهجرة الوحيدة: يضيف العمود إن غاب (آمن للتكرار). يرجّع True إن أضافه."""
    if has_round(conn):
        return False
    conn.execute(f"ALTER TABLE matches ADD COLUMN {COL} TEXT")
    conn.commit()
    return True


def round_of(fx):
    """league.round من عنصر fixtures (نص أو None)"""
    r = ((fx or {}).get("league") or {}).get("round")
    r = (r or "").strip()
    return r or None


def label(rnd, lang):
    """نص العرض أو "" — «الجولة 8» / "Round 8"، أو اسم المرحلة مع الجولة، أو النص كما هو"""
    r = (rnd or "").strip()
    if not r:
        return ""
    ar = lang == "ar"
    if r in WHOLE:
        return WHOLE[r][0 if ar else 1]
    m = re.fullmatch(r"(.+?)\s*-\s*(\d+)", r)
    if m:
        stage, n = m.group(1).strip(), m.group(2)
        word = f"الجولة {n}" if ar else f"Round {n}"
        if stage in STAGES:
            name = STAGES[stage][0 if ar else 1]
            return f"{name} - {word}" if name else word
        return f"{stage} - {word}" if not ar else f"{stage} - {word}"
    return r
