#!/usr/bin/env python3
"""
مناطق جدول الترتيب (تأهّل/هبوط) — شريط ملوَّن بجانب المركز + مفتاح ألوان تحت الجدول (27 أكتوبر 2026، طلب عمرو #6)
===================================================================================================================
المصدر الوحيد: وصف المزوّد لكل مركز (`api_standings.description`، يحفظه fetch_standings.py مع كل تحديث للترتيب — لا طلب إضافي،
لا تغيير بالقاعدة). لا مناطق مُخترَعة: مركز بلا وصف = بلا شريط، ودوري/موسم بلا أوصاف = بلا أشرطة ولا مفتاح (ويبقى تلوين
المركز القديم top/bottom).

⚠️ المنطقة صفة **المركز** لا الفريق: جدولنا محسوب من النتائج (get_table) فيُطابَق المركز N بوصف المركز N عند المزوّد، والترتيب
   المباشر (live_view.ltRender) يعيد التلوين بالمركز بعد إعادة الفرز من `data-zones` على الجدول.

فئات ثابتة بنفس اللون بكل الدوريات (الترتيب = ترتيب المفتاح):
    cl    الدرجة القارية الأولى مباشرة        AFC Champions League (League phase)
    clq   تصفيات/ملحق الدرجة القارية الأولى  AFC/CAF Champions League (Qualification)
    cl2   الدرجة القارية الثانية              AFC Champions League 2 [(Qualification)] · CAF Confederation Cup [(Qualification)]
    reg   بطولة إقليمية                       Gulf Club Champions League · Arab Club Champions Cup
    grp1  مجموعة البطولة (الدوري المقسوم)      Premier League (Championship Group)
    grp2  مجموعة الهبوط (الدوري المقسوم)       Premier League (Relegation Group)   ← مخفية (قرار عمرو 27 أكتوبر: لا شريط ولا مفتاح)
    rpo   ملحق الهبوط                         <الدوري> (Relegation)
    rel   الهبوط                              Relegation[ - <الدرجة الأدنى>]
وصف غير معروف = بلا منطقة + تحذير بالطباعة (يُضاف هنا يدوياً لا تخمين).
"""
import re
import sys

ORDER = ("cl", "clq", "cl2", "reg", "grp1", "grp2", "rpo", "rel")
# فئات تُعرَف (فلا تُطبع «غير معروف») لكن لا تُعرض: مجموعة الهبوط بالدوري المقسوم (14 صفاً رمادياً بالمصري — قرار عمرو 27 أكتوبر 2026)
HIDDEN = {"grp2"}

COLORS = {"cl": "#2f81f7", "clq": "#39c5cf", "cl2": "#f0883e", "reg": "#a371f7",
          "grp1": "#3fb950", "grp2": "#8b949e", "rpo": "#d29922", "rel": "#f85149"}

# اسم البطولة بلغتين + الدرجة (1 = القارية الأولى، 2 = القارية الثانية، r = إقليمية). المزوّد غيّر الصياغة عبر المواسم
# («AFC Champions League Elite» 2023-24، «Champions League Elite»/«Champions League 2» 2024-25، «… (League phase)» 2026)
COMP = {
    "AFC Champions League": ("دوري أبطال آسيا", "AFC Champions League", 1),
    "AFC Champions League Elite": ("دوري أبطال آسيا للنخبة", "AFC Champions League Elite", 1),
    "Champions League Elite": ("دوري أبطال آسيا للنخبة", "AFC Champions League Elite", 1),
    "AFC Champions League 2": ("دوري أبطال آسيا 2", "AFC Champions League Two", 2),
    "Champions League 2": ("دوري أبطال آسيا 2", "AFC Champions League Two", 2),
    "AFC Cup": ("كأس الاتحاد الآسيوي", "AFC Cup", 2),
    "CAF Champions League": ("دوري أبطال أفريقيا", "CAF Champions League", 1),
    "CAF CL": ("دوري أبطال أفريقيا", "CAF Champions League", 1),
    "CAF Confederation Cup": ("كأس الكونفدرالية الأفريقية", "CAF Confederation Cup", 2),
    "Gulf Club Champions League": ("دوري أبطال الخليج للأندية", "Gulf Club Champions League", "r"),
    "Arab Club Champions Cup": ("كأس العرب للأندية الأبطال", "Arab Club Champions Cup", "r"),
}
# مرحلة بنهاية الوصف → (عربي، إنجليزي، تصفيات؟)
STAGES = (
    (r" \(League phase\)$", ("مرحلة الدوري", "league phase", False)),
    (r" group stage$", ("دور المجموعات", "group stage", False)),
    (r" \(Qualification\)$", ("التصفيات", "qualification", True)),
    (r" Qualifiers$", ("التصفيات", "qualification", True)),
    (r" Play-offs$", ("الملحق", "play-off", True)),
)

_WARNED = set()


def classify(desc):
    """وصف المزوّد → (فئة، عربي، إنجليزي) أو None"""
    d = (desc or "").strip()
    if not d:
        return None
    if re.fullmatch(r"Relegation(?: - .+)?", d):
        return "rel", "الهبوط", "Relegation"
    if re.fullmatch(r".+ \(Relegation\)", d) or re.fullmatch(r"Relegation Play-?offs?", d, re.I):
        return "rpo", "ملحق الهبوط", "Relegation play-off"
    if re.fullmatch(r"(?:Promotion - .+ \(Championship Group\)|Championship Round)", d):
        return "grp1", "مجموعة البطولة", "Championship group"
    if re.fullmatch(r"(?:Promotion - .+ \(Relegation Group\)|Relegation Round)", d):
        return "grp2", "مجموعة الهبوط", "Relegation group"
    base = re.sub(r"^Promotion - ", "", d)
    stage = None
    for pat, st in STAGES:
        if re.search(pat, base):
            base, stage = re.sub(pat, "", base), st
            break
    if base in COMP:
        ar, en, tier = COMP[base]
        cat = {1: "clq" if stage and stage[2] else "cl", 2: "cl2", "r": "reg"}[tier]
        if stage:
            ar, en = f"{ar} – {stage[0]}", f"{en} – {stage[1]}"
        return cat, ar, en
    if d not in _WARNED:
        _WARNED.add(d)
        print(f"  ⚠️ zones: وصف ترتيب غير معروف (بلا منطقة): {d!r}", file=sys.stderr)
    return None


def zone_list(conn, code, season):
    """{مركز: (فئة، عربي، إنجليزي)} من أوصاف المزوّد لهذا الدوري/الموسم ({} = بلا مناطق)"""
    out = {}
    for rank, desc in conn.execute(
            "SELECT rank, description FROM api_standings WHERE league_code = ? AND season = ? AND description IS NOT NULL",
            (code, season)):
        z = classify(desc)
        if z and rank and z[0] not in HIDDEN:
            out[int(rank)] = z
    return out


def row_class(zones, pos):
    z = zones.get(pos)
    return f"z-{z[0]}" if z else ""


def data_attr(zones, n):
    """data-zones="cl,cl,,..." بطول الجدول — يقرؤه ltRender بعد إعادة الفرز المباشر"""
    if not zones:
        return ""
    return ' data-zones="' + ",".join((zones.get(i) or ("",))[0] for i in range(1, n + 1)) + '"'


def legend(zones, lang, n=None):
    """مفتاح الألوان: نقطة + اسم لكل فئة موجودة بالجدول (بترتيب ORDER)؛ فئة بأكثر من بطولة/مرحلة = الأسماء بـ « · »"""
    if not zones:
        return ""
    labels = {}
    for pos in sorted(zones):
        if n is not None and pos > n:
            continue
        cat = zones[pos][0]
        lab = zones[pos][2 if lang == "en" else 1]
        labels.setdefault(cat, [])
        if lab not in labels[cat]:
            labels[cat].append(lab)
    items = "".join(f'<span class="zli"><i class="zd z-{c}"></i>{" · ".join(labels[c])}</span>'
                    for c in ORDER if c in labels)
    return f'<div class="zleg">{items}</div>' if items else ""


# الشريط بجهة البداية من خلية المركز (يمين بالعربي، يسار بالإنجليزي — خصائص منطقية)؛ اللون من --zc لكل فئة
ZONE_CSS = "\n".join(f"  .z-{c} {{ --zc:{COLORS[c]}; }}" for c in ORDER) + """
  tr[class*="z-"] > td:first-child { position:relative; }
  tr[class*="z-"] > td:first-child::before { content:""; position:absolute; inset-inline-start:0; top:3px; bottom:3px; width:3px;
                                            border-radius:2px; background:var(--zc); }
  .zleg { display:flex; flex-wrap:wrap; gap:6px 14px; margin:10px 2px 4px; font-size:12px; color:var(--muted); line-height:1.4; }
  .zli { display:inline-flex; align-items:center; gap:6px; }
  .zd { width:9px; height:9px; border-radius:50%; background:var(--zc); flex:0 0 9px; }
"""
