#!/usr/bin/env python3
"""
ترتيب الفرق المتساوية — المواجهات المباشرة
=============================================
وحدة مستقلة. لا تشغّلها لحالها — `make_site3.py` بيستوردها.

⚠️ **`STANDINGS_EXCLUDED` هنا أيضاً** — مباريات حقيقية (ملاحق
   صعود/هبوط غالباً) تبقى ظاهرة بصفحتها وصفحتَي الناديين، لكن
   المزوّد نفسه يستبعدها من حساب ترتيبه، فنستبعدها من حسابنا
   بنفس المكان لنطابقه. راجع `standings_exclusions.csv`
   وبند مفتوح 6 بالـREADME (القطري، 4 سبتمبر).

المشكلة اللي بتحلها:
معظم الدوريات ما بترتّب المتساويين بفارق الأهداف الكلي مباشرة،
بل بالمواجهات المباشرة بينهم أولاً. فارق الأهداف الكلي بيجي بعدين.

مثال مؤكد (السعودي 2025-26):
  الفتح  37 نقطة  فارق -14
  الخليج 37 نقطة  فارق -8
الرسمي بيحط الفتح 11 والخليج 12 — رغم إن فارق الخليج أفضل.
السبب: المواجهات المباشرة بينهم.

⚠️ **الأردني معطّل فقط.** نظام 3 مراحل، عدد المواجهات بين الفرق
   قد يختلف — يحتاج تحقق قبل التفعيل.
   لتفعيله: غيّر القيمة في H2H_ENABLED إلى True بعد التحقق.

⚠️ هذا التعليق نفسه كان يقول "السعودي فقط، العراقي معطّل" وهو
   غلط — العراقي مفعّل أصلاً بالقاموس تحت. صُحح 3 سبتمبر (نفس
   درس الملف يتقادم — راجع رأس الـREADME).
"""

# ------------------------------------------------------------------
# أي دوري يطبّق المواجهات المباشرة
# ------------------------------------------------------------------
H2H_ENABLED = {
    # TUN/ALG/KUW (مطفأة، 24 أكتوبر 2026): False حتى يُتحقَّق من نص اللائحة (وTUN 2022-23/2023-24 بنظام مجموعتين ثم مرحلة حاسمة)
    "TUN": False,
    "ALG": False,
    "KUW": False,
    "SAU": True,    # [مؤكد] — تحقق خارجي: الفتح فوق الخليج رغم فارق أسوأ
    "JOR": False,   # نظام 3 مراحل — يحتاج تحقق قبل التفعيل
    "IRQ": True,    # [مؤكد] 2023 و2024 و2025 مكتملة ومتحقَّقة — 38 مباراة لكل نادٍ
    "EGY": True,    # [مؤكد] لائحة الاتحاد المصري 2025-26 صريحة: المواجهات
                    # المباشرة أول معيار كسر تعادل قبل فارق الأهداف
                    # (تحقّق 3 سبتمبر — filgoal.com + مصادر إخبارية مصرية)
    "UAE": True,    # [مرجح] لا [مؤكد] — ما لقيت نص اللائحة الرسمية حرفياً
                    # (PDF رابطة المحترفين رفض يُفتح)، لكن مصادر متعددة
                    # مستقلة تتفق: المواجهة المباشرة أول معيار، ويطابق
                    # نمط بقية دوريات الخليج/آسيا. أعد التحقق لو ظهر
                    # تعادل نقاط فعلي بجدول الإماراتي — راجع النتيجة
                    # وقتها لا قبلها.
    "QAT": False,   # [مرجح خلاف ذلك] — بحث 5 سبتمبر: نص ويكيبيديا
                    # صريح بموسمين (2021-22 و2024-25، نفس الصياغة
                    # حرفياً): "Points; Goal difference; Goals
                    # scored" — H2H غير مذكور إطلاقاً. حالة تعادل
                    # نقاط حية بموسم 2025-26 (قطر SC 32ن +2 فارق
                    # فوق العربي 32ن -4 فارق) تتفق مع "الفارق الكلي
                    # يحسم مباشرة" لا H2H. لم يُلقَ نص لائحة رسمية
                    # (qsl.qa/qfa.qa) حرفي. **البقاء False صحيح على
                    # الأرجح — لا دليل يرجّح تفعيله.** راجع بند
                    # مفتوح 16 بالـREADME.
    "MAR": True,    # [مؤكد] نص ويكيبيديا صريح ومتكرر حرفياً (موسمَي
                    # 2023-24 و2025-26): "1) Points؛ 2a) H2H goal
                    # difference لو فريقان بالضبط متساويان بالنقاط؛
                    # 2b) الفارق الكلي لو أكثر من فريقين؛ 3) عدد
                    # الفوز؛ 4) الأهداف؛ 5) ملحق". يعتمد على
                    # `H2H_TWO_TEAM_ONLY` تحت (راجعه) ليطبّق H2H
                    # لفريقين بالضبط فقط ويتخطاه لـ3+ فرق — أُصلح
                    # 5 سبتمبر بعد اكتشاف أن `sort_table()` القديم
                    # ما كان يفرّق حجم المجموعة. راجع بند مفتوح 16.
}

# ⚠️ **لوائح تحصر H2H بتعادل فريقين بالضبط** — أي دوري هنا يتخطى
#    H2H تماماً لو 3+ فرق متساوية بالنقاط، وينتقل مباشرة للفارق
#    الكلي (بند 2b بلائحة المغرب). الدوريات المفعَّلة بـH2H_ENABLED
#    وغير المذكورة هنا (SAU/IRQ/EGY/UAE) تطبّق H2H على أي حجم
#    مجموعة كما كانت دائماً — **لم يتغيّر سلوكها إطلاقاً**، لا
#    دليل حالياً أن لوائحها تحصر H2H بفريقين فقط. أضِف دورياً هنا
#    فقط بعد تأكيد نص اللائحة صراحةً، بنفس معيار MAR.
H2H_TWO_TEAM_ONLY = {"MAR"}


# ------------------------------------------------------------------
# مباريات حقيقية تُستبعَد من حساب الترتيب فقط (لا من العرض)
# ------------------------------------------------------------------
import csv as _csv
from pathlib import Path as _Path

STANDINGS_EXCLUDED = set()
_excl_file = _Path(__file__).parent / "standings_exclusions.csv"
if _excl_file.exists():
    with open(_excl_file, encoding="utf-8-sig") as _f:
        for _r in _csv.DictReader(_f):
            mid = (_r.get("match_id") or "").strip()
            if mid.isdigit():
                STANDINGS_EXCLUDED.add(int(mid))


# ------------------------------------------------------------------
# ترتيب المزوّد (29 أكتوبر 2026، قرار عمرو: ترتيب الجدول = ترتيب المزوّد متى طابقت أرقامه أرقامنا)
# ------------------------------------------------------------------
_MERGES = None


def _team_merges():
    """{معرّف المزوّد القديم: معرّفنا} من team_merges.csv — api_standings يحمل معرّف المزوّد الخام (الشرطة 28571 → 5242)"""
    global _MERGES
    if _MERGES is None:
        _MERGES = {}
        f = _Path(__file__).parent / "team_merges.csv"
        if f.exists():
            with open(f, encoding="utf-8-sig") as fh:
                for r in _csv.DictReader(fh):
                    o, n = (r.get("old_id") or "").strip(), (r.get("new_id") or "").strip()
                    if o.isdigit() and n.isdigit():
                        _MERGES[int(o)] = int(n)
    return _MERGES


def provider_order(conn, code, season, rows):
    """
    صفوف جدولنا مرتّبة بمركز المزوّد، أو None إن لم يصلح ترتيبه:
      • لا صفوف للمزوّد، أو عددها ≠ فرقنا، أو مراكزه ليست 1..N بلا تكرار؛
      • أي فريق لعبه أو نقاطه عند المزوّد ≠ جدولنا (ترتيب قديم أثناء جولة، حسم إداري غير مطبَّق، خصم نقاط…).
    صف مزوّد بلا معرّف صالح (تونس 2026: «Monastir» بمعرّف فارغ) يُطابَق بالإقصاء فقط إن بقي فريق واحد لنا وصف واحد له —
    ولعبه ونقاطه يجب أن تتطابق كالباقين.
    """
    if not rows:
        return None
    try:
        prov = conn.execute("SELECT team_id, rank, played, points FROM api_standings WHERE league_code = ? AND season = ?",
                            (code, season)).fetchall()
    except Exception:   # لا جدول api_standings (قاعدة اختبار مثلاً) = كسر التعادل العادي
        return None
    if len(prov) != len(rows):
        return None
    ours = {r["team_id"]: (r["played"], r["points"]) for r in rows}
    if len(ours) != len(rows):
        return None
    mm = _team_merges()
    got, rest = {}, []
    for tid, rank, pl, pts in prov:
        t = mm.get(tid, tid) if tid is not None else None
        if t in ours and t not in got:
            got[t] = (rank, pl, pts)
        else:
            rest.append((rank, pl, pts))
    left = [t for t in ours if t not in got]
    if len(rest) == 1 and len(left) == 1:
        got[left[0]] = rest[0]
    if len(got) != len(ours):
        return None
    if any(ours[t] != (pl, pts) for t, (_rk, pl, pts) in got.items()):
        return None
    if sorted((rk if isinstance(rk, int) else -1) for rk, _pl, _pts in got.values()) != list(range(1, len(ours) + 1)):
        return None
    return sorted(rows, key=lambda r: got[r["team_id"]][0])


def h2h_stats(conn, code, season, team_ids):
    """
    بيحسب نقاط وأهداف المواجهات بين مجموعة فرق محددة.
    بيرجع: {team_id: {"pts": n, "gf": n, "ga": n}}
    """
    stats = {t: {"pts": 0, "gf": 0, "ga": 0} for t in team_ids}
    ids = set(team_ids)

    rows = conn.execute("""
        SELECT match_id, home_id, away_id, home_goals, away_goals
        FROM matches
        WHERE league_code = ? AND season = ?
    """, (code, season)).fetchall()

    for r in rows:
        if r["match_id"] in STANDINGS_EXCLUDED:
            continue
        h, a = r["home_id"], r["away_id"]
        if h not in ids or a not in ids:
            continue
        hg, ag = r["home_goals"], r["away_goals"]
        if hg is None or ag is None:
            continue

        stats[h]["gf"] += hg
        stats[h]["ga"] += ag
        stats[a]["gf"] += ag
        stats[a]["ga"] += hg

        if hg > ag:
            stats[h]["pts"] += 3
        elif hg < ag:
            stats[a]["pts"] += 3
        else:
            stats[h]["pts"] += 1
            stats[a]["pts"] += 1

    return stats


def sort_table(conn, code, season, rows):
    """
    بياخد صفوف الجدول (من get_data) وبيرجعها مرتّبة.

    المستوى الأول دائماً: النقاط.
    عند التساوي:
      - لو الدوري مفعّل بـH2H: نقاط المواجهات، فارق المواجهات،
        أهداف المواجهات، ثم الفارق الكلي، ثم الأهداف الكلية
      - غير هيك (أو الدوري بـH2H_TWO_TEAM_ONLY ومجموعة التعادل
        3 فرق فأكثر): الفارق الكلي، ثم الأهداف الكلية

    ⚠️ **حجم مجموعة التعادل يُفحص لدوريات `H2H_TWO_TEAM_ONLY`** —
       H2H ينطبق فقط لو فريقان بالضبط متعادلان بالنقاط؛ 3+ فرق
       يتخطّون H2H تماماً لنفس مسار "غير مفعَّل". أُصلح 5 سبتمبر
       (بند مفتوح 16 بالـREADME) — الدوريات غير المذكورة بـ
       `H2H_TWO_TEAM_ONLY` (SAU/IRQ/EGY/UAE) تطبّق H2H على أي حجم
       مجموعة كما كانت دائماً، سلوكها لم يتغيّر إطلاقاً.

    rows لازم تحتوي: team_id, points, diff, scored (وplayed لترتيب المزوّد)

    ⚠️ (29 أكتوبر 2026، قرار عمرو) **ترتيب المزوّد أولاً:** إن وُجد ترتيب المزوّد لهذا الدوري/الموسم (api_standings) وكان
       لعب ونقاط **كل** فريق عنده = جدولنا، يُرتَّب الجدول بمركز المزوّد حرفياً (provider_order). غير ذلك (ترتيب قديم أثناء
       جولة، أو ناقص، أو فرق مختلفة) = كسر التعادل أدناه كما كان. الترتيب المباشر أثناء المباريات (live_table.js) حسابنا.
    """
    po = provider_order(conn, code, season, rows)
    if po:
        return po
    use_h2h = H2H_ENABLED.get(code, False)
    two_only = code in H2H_TWO_TEAM_ONLY

    # نجمّع الصفوف حسب النقاط
    groups = {}
    for r in rows:
        groups.setdefault(r["points"], []).append(r)

    result = []

    for pts in sorted(groups, reverse=True):
        group = groups[pts]
        skip_h2h = (len(group) == 1 or not use_h2h
                    or (two_only and len(group) > 2))

        if skip_h2h:
            # فريق واحد، أو دوري غير مفعّل، أو (دوري يحصر H2H
            # بفريقين بالضبط ومجموعة التعادل 3+ فرق) — الفارق الكلي
            group = sorted(group,
                           key=lambda r: (-r["diff"], -r["scored"]))
            result.extend(group)
            continue

        # مجموعة متساوية بالنقاط ودوري مفعّل (وحجمها مؤهَّل) — نحسب المواجهات
        ids = [r["team_id"] for r in group]
        st = h2h_stats(conn, code, season, ids)

        group = sorted(group, key=lambda r: (
            -st[r["team_id"]]["pts"],                              # 1
            -(st[r["team_id"]]["gf"] - st[r["team_id"]]["ga"]),    # 2
            -st[r["team_id"]]["gf"],                               # 3
            -r["diff"],                                            # 4
            -r["scored"],                                          # 5
        ))
        result.extend(group)

    return result
