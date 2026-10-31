#!/usr/bin/env python3
"""
الأسماء المختصرة للاعبين (31 أكتوبر 2026، دفعة 7 بند 5) — مساعد واحد مشترك للعربي والإنجليزي
==================================================================================================
اسم من 3 كلمات فأكثر يُعرض «الأول + الأخير» بصفحات المباريات والتشكيلات والأحداث وصفوف القوائم؛ الاسم الكامل يبقى بعنوان صفحة
اللاعب وبكل رابط/مفتاح (روابط اللاعب، data-p، مفاتيح المتابعة والتثبيت لا تتغيّر — النص المعروض فقط).

القواعد (نفسها بـ`SHORT_JS` للصفحات الحيّة):
  • الأول مركّب إن بدأ بـ«عبد/أبو/Abd/Abdul/Abu…» فيبقى كلمتين (عبد الله، Abdul Rahman)
  • الأخير يأخذ أداته إن سبقته (Al/El/De/Da/Van/Bin/Ben/Ibn/Abu/بن/أبو…): Mohammed Al Shwirekh يبقى كما هو
  • النتيجة لا تقصر عن الأصل = الاسم كما هو
حارس التصادم (`page_map`): داخل المباراة/القائمة الواحدة، اسمان كاملان مختلفان يصيران نفس المختصر = كلاهما يبقى كاملاً.
`STATS` يعدّ ما اختُصر وما أبقاه الحارس (للتقرير).
"""
import json
import re

PARTICLES = {"al", "el", "de", "da", "do", "dos", "das", "di", "du", "del", "della", "van", "von", "der", "den", "le", "la",
             "bin", "ben", "ibn", "abu", "bou", "ould", "ait", "st", "san", "santa", "dal", "ter",
             "بن", "ابن", "أبو", "ابو", "آل", "ولد", "بو"}
FIRST_COMPOUND = {"abd", "abdel", "abdul", "abdal", "abu", "abou", "el", "al", "عبد", "أبو", "ابو", "ابن"}

STATS = {"shortened": set(), "kept": set()}


def short_name(full):
    """الاسم المختصر بلا حارس (3 كلمات فأكثر → الأول + الأخير)"""
    s = re.sub(r"\s+", " ", (full or "").strip())
    w = s.split(" ")
    if len(w) < 3:
        return s
    i = 1
    if w[0].lower() in FIRST_COMPOUND and len(w) > 3:
        i = 2
    first = w[:i]
    last = [w[-1]]
    if w[-2].lower() in PARTICLES and len(w) - 2 >= i:
        last = [w[-2], w[-1]]
    out = first + last
    return " ".join(out) if len(out) < len(w) else s


def page_map(names):
    """{الاسم الكامل: المعروض} لمجموعة أسماء صفحة/قائمة واحدة، مع حارس التصادم"""
    full = {re.sub(r"\s+", " ", (n or "").strip()) for n in names if n and str(n).strip()}
    by_short = {}
    for n in full:
        by_short.setdefault(short_name(n), set()).add(n)
    out = {}
    for sh, group in by_short.items():
        clash = len(group) > 1 or (sh in full and sh not in group)
        for n in group:
            if sh == n:
                out[n] = n
            elif clash:
                out[n] = n
                STATS["kept"].add(n)
            else:
                out[n] = sh
                STATS["shortened"].add(n)
    return out


def apply(mp, name):
    """المعروض لاسم من خريطة page_map (اسم غير معروف = short_name بلا حارس)"""
    k = re.sub(r"\s+", " ", (name or "").strip())
    return mp.get(k, short_name(k)) if k else name


_MATCH = {}


def match_map(conn, mid):
    """خريطة صفحة المباراة: كل أسماء التشكيلة + الأحداث + الأهداف (العربي والإنجليزي) — حارس التصادم على مستوى المباراة"""
    if mid in _MATCH:
        return _MATCH[mid]
    names = []
    for q in ("SELECT player_en, player_ar FROM lineup_players WHERE match_id = ?",
              "SELECT player_en, player_ar FROM events WHERE match_id = ?",
              "SELECT assist_en, NULL FROM events WHERE match_id = ?",
              "SELECT player_en, player_ar FROM goals WHERE match_id = ?"):
        try:
            for a, b in conn.execute(q, (mid,)):
                names += [a, b]
        except Exception:
            pass
    _MATCH[mid] = page_map(names)
    return _MATCH[mid]


# نفس القواعد للصفحات الحيّة (live_view: الأحداث وأسطر الهدّافين؛ التشكيلة الحيّة)؛ SN.map(list) = حارس التصادم
SHORT_JS = r"""
window.SN=window.SN||(function(){
  var P=%s, F=%s;
  function one(s){s=String(s||'').replace(/\s+/g,' ').trim();var w=s.split(' ');if(w.length<3)return s;
    var i=(F.indexOf(w[0].toLowerCase())>=0&&w.length>3)?2:1,first=w.slice(0,i),last=[w[w.length-1]];
    if(P.indexOf(w[w.length-2].toLowerCase())>=0&&w.length-2>=i)last=[w[w.length-2],w[w.length-1]];
    var o=first.concat(last);return o.length<w.length?o.join(' '):s;}
  function map(list){var full={},by={},out={};(list||[]).forEach(function(n){n=String(n||'').replace(/\s+/g,' ').trim();if(n)full[n]=1;});
    Object.keys(full).forEach(function(n){var s=one(n);(by[s]=by[s]||[]).push(n);});
    Object.keys(by).forEach(function(s){var g=by[s],clash=g.length>1||(full[s]&&g.indexOf(s)<0);
      g.forEach(function(n){out[n]=clash?n:s;});});
    return function(n){var k=String(n||'').replace(/\s+/g,' ').trim();return k?(k in out?out[k]:one(k)):n;};}
  return {one:one,map:map};
})();
""" % (json.dumps(sorted(PARTICLES), ensure_ascii=False), json.dumps(sorted(FIRST_COMPOUND), ensure_ascii=False))
