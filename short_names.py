#!/usr/bin/env python3
"""
الأسماء المختصرة للاعبين (31 أكتوبر 2026، دفعة 7 بند 5) — مساعد واحد مشترك للعربي والإنجليزي
==================================================================================================
اسم من 3 كلمات فأكثر يُعرض «الأول + الأخير» بصفحات المباريات والتشكيلات والأحداث وصفوف القوائم؛ الاسم الكامل يبقى بعنوان صفحة
اللاعب وبكل رابط/مفتاح (روابط اللاعب، data-p، مفاتيح المتابعة والتثبيت لا تتغيّر — النص المعروض فقط).

القواعد (نفسها بـ`SHORT_JS` للصفحات الحيّة):
  • المركّبات كلمة واحدة أولاً (1 نوفمبر 2026): عبد/أبو/Abdel/Abu/Sid + التالية · أداة اللقب Al/El/Ben/Bin/Ait/Ould/Bou/بن/آيت/آل…
    + التالية (سلسلة) · X الدين/الله/Eddine/Allah · ثانٍ بـ«ال»/El/Al يلتصق بالأول — ثم الأول + الأخير
  • نتيجة من اسمين مركّبين (عز الدين دوخة، Mohamed Abdel Ghani) = الاسم كما هو؛ لا أداة وحيدة بالآخر ولا لاحقة وحيدة بالأول
  • النتيجة لا تقصر عن الأصل = الاسم كما هو
حارس التصادم (`page_map`): داخل المباراة/القائمة الواحدة، اسمان كاملان مختلفان يصيران نفس المختصر = كلاهما يبقى كاملاً.
`STATS` يعدّ ما اختُصر وما أبقاه الحارس (للتقرير).
"""
import json
import re

PARTICLES = {"al", "el", "de", "da", "do", "dos", "das", "di", "du", "del", "della", "van", "von", "der", "den", "le", "la",
             "bin", "ben", "ibn", "abu", "bou", "ould", "ait", "aït", "st", "san", "santa", "dal", "ter",
             "بن", "ابن", "أبو", "ابو", "آل", "ولد", "بو", "آيت"}
FIRST_COMPOUND = {"abd", "abdel", "abdul", "abdal", "abu", "abou", "sid", "عبد", "أبو", "ابو", "ابن"}
# (1 نوفمبر 2026) مركّبات تُعامَل ككلمة واحدة قبل «الأول + الأخير»:
#   JOIN = سابقة/أداة تلتصق بالكلمة التالية (سلسلة: Abou El Fotouh، بن سعد الله، Ben Al Arbi)
#   SUF  = لاحقة تلتصق بالكلمة السابقة (عز الدين، حمد الله، Ala Eddine، Attiat Allah)
#   ثانٍ يبدأ بـ«ال» (أو El/Al) يلتصق بالاسم الأول (محمد الأمين، Mohamed El Amine)
JOIN = PARTICLES | FIRST_COMPOUND
SUF = {"الدين", "الإسلام", "الاسلام", "الله", "الحق", "eddine", "edine", "eddin", "ed-dine", "allah", "ellah"}

STATS = {"shortened": set(), "kept": set()}


def _groups(w):
    """الكلمات → مجموعات مركّبة (كل مجموعة = اسم واحد)"""
    g, i, n = [], 0, len(w)
    while i < n:
        t = [w[i]]
        while t[-1].lower() in JOIN and i + 1 < n:
            i += 1
            t.append(w[i])
        while i + 1 < n and w[i + 1].lower() in SUF:
            i += 1
            t.append(w[i])
        g.append(t)
        i += 1
    if len(g) >= 3 and len(g[0]) == 1:
        x = g[1][0]
        if (len(g[1]) == 1 and x.startswith("ال") and x not in SUF) or x.lower() in ("el", "al"):
            g = [g[0] + g[1]] + g[2:]
    return g


def short_name(full):
    """الاسم المختصر بلا حارس (3 أسماء فأكثر بعد ضمّ المركّبات → الأول + الأخير)"""
    s = re.sub(r"\s+", " ", (full or "").strip())
    w = s.split(" ")
    if len(w) < 3 or w[0].lower() in SUF:
        return s
    g = _groups(w)
    last = g[-1]
    if len(g) < 3 or (len(last) == 1 and last[0].lower() in JOIN):
        return s
    out = g[0] + last
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
  var J=%s, X=%s;
  function grp(w){var g=[],i=0,n=w.length;
    while(i<n){var t=[w[i]];while(J.indexOf(t[t.length-1].toLowerCase())>=0&&i+1<n){i++;t.push(w[i]);}
      while(i+1<n&&X.indexOf(w[i+1].toLowerCase())>=0){i++;t.push(w[i]);}
      g.push(t);i++;}
    if(g.length>=3&&g[0].length==1){var x=g[1][0];
      if((g[1].length==1&&x.indexOf('ال')==0&&X.indexOf(x)<0)||x.toLowerCase()=='el'||x.toLowerCase()=='al')g=[g[0].concat(g[1])].concat(g.slice(2));}
    return g;}
  function one(s){s=String(s||'').replace(/\s+/g,' ').trim();var w=s.split(' ');if(w.length<3||X.indexOf(w[0].toLowerCase())>=0)return s;
    var g=grp(w),L=g[g.length-1];if(g.length<3||(L.length==1&&J.indexOf(L[0].toLowerCase())>=0))return s;
    var o=g[0].concat(L);return o.length<w.length?o.join(' '):s;}
  function map(list){var full={},by={},out={};(list||[]).forEach(function(n){n=String(n||'').replace(/\s+/g,' ').trim();if(n)full[n]=1;});
    Object.keys(full).forEach(function(n){var s=one(n);(by[s]=by[s]||[]).push(n);});
    Object.keys(by).forEach(function(s){var g=by[s],clash=g.length>1||(full[s]&&g.indexOf(s)<0);
      g.forEach(function(n){out[n]=clash?n:s;});});
    return function(n){var k=String(n||'').replace(/\s+/g,' ').trim();return k?(k in out?out[k]:one(k)):n;};}
  return {one:one,map:map};
})();
""" % (json.dumps(sorted(JOIN), ensure_ascii=False), json.dumps(sorted(SUF), ensure_ascii=False))
