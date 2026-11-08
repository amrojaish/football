#!/usr/bin/env python3
"""
جداول مرحلة المجموعات / الدوري بالكؤوس (الموجة 3، 6 نوفمبر 2026) — دوال صافية بلا HTML، مصدر واحد لـmake_cups.py
(تبويب «الجدول»)، make_api.py (api/v1/cups/<code>.json → tables) وبطاقة «البطولات» بصفحة النادي.
=====================================================================================================================
المزوّد بلا /standings لهذه الكؤوس (results 0) ولا اسم مجموعة بالجولة («Group Stage - 3»)، فالجدول محسوب من النتائج:
  المباريات   = جولات المرحلة فقط (is_table_round) — أدوار خروج المغلوب بعدها تبقى لشجرة البطولة
  المحسوبة    = المنتهية بنتيجة (FT/AET/PEN/AWD) — النتيجة من matches بعد التصحيحات (apply_corrections)
  النقاط      = 3 فوز / 1 تعادل / 0 خسارة
  الترتيب     = النقاط ← فارق الأهداف ← الأهداف له ← الاسم (الإنجليزي، فيتطابق الترتيب بين اللغتين وبالـAPI) ← المعرّف
  المجموعات  = config.COMPETITIONS[code]["table"] == "groups": مكوّنات متصلة لرسم المواجهات (كل المباريات المجدولة بالمرحلة،
                لا المنتهية فقط) — ترقيمها بأقدم مباراة بكل مجموعة (التاريخ ثم المعرّف). "league" = جدول واحد لكل الفرق.
  الخط        = config.COMPETITIONS[code]["table_line"] (مثلاً 8 = خط تحت الثامن، المتأهلون لربع النهائي) أو None
فريق مجدول بلا مباراة منتهية يظهر بأصفار. لا كتابة على القاعدة، لا طلبات API.

(الموجة 4، 6 نوفمبر 2026 — AFC-CLE / AFC-CL2) خياران بالـconfig لكأس بعينها فقط (tables(..., code=)):
  "groups"    = أسماء رسمية بعضوية الفرق [{"ar","en","teams"}] — كل مكوّن مواجهات يُنسب للمجموعة التي تضمّ فرقه، والعرض بترتيب
                القائمة؛ المدخل يحمل "name": {"ar","en"} و"group" = رقمه بالعرض. مكوّن لا يطابق أي مجموعة يُلحق بعدها برقمه.
  "tiebreak": "h2h" = النقاط ← نقاط المواجهات بين المتعادلين بالنقاط ← فارقها ← أهدافها ← الفارق العام ← الأهداف ← الاسم ← المعرّف
               (AFC-CL2)؛ "league" = النقاط ← الفارق ← الأهداف ← الانتصارات ← المعرّف تصاعدياً (AFC-CLE، مرحلة دوري بلا h2h).
كأس بلا الخيارين (كل كؤوس الموجة 3) = نفس الناتج حرفياً.
"""
from config import COMPETITIONS

TABLE_STAGES = ("Group Stage", "League Phase", "Regular Season", "Regular season", "Caf Confederation Cup")
FINISHED = ("FT", "AET", "PEN", "AWD")
VOID = ("CANC", "ABD")


def _g(m, k):
    try:
        return m[k]
    except (KeyError, IndexError):
        return None


def mode(code):
    """"groups" | "league" | None (كأس بلا جدول — كل الكؤوس الإقصائية)"""
    return (COMPETITIONS.get(code) or {}).get("table")


def line(code):
    return (COMPETITIONS.get(code) or {}).get("table_line")


def tiebreak(code):
    """"h2h" | "league" | None (الترتيب القديم)"""
    return (COMPETITIONS.get(code) or {}).get("tiebreak")


def group_names(code):
    """[{"ar","en","teams"}] أسماء المجموعات الرسمية بعضوية الفرق، أو () (مجموعات مرقّمة)"""
    return (COMPETITIONS.get(code) or {}).get("groups") or ()


def is_table_round(rnd):
    """جولة مرحلة مجموعات/دوري: «Group Stage» أو «Group Stage - 3» (وصيغ المرحلة الأخرى)"""
    r = (rnd or "").strip()
    return any(r == s or r.startswith(s + " - ") for s in TABLE_STAGES)


def stage_rows(rows):
    """مباريات المرحلة (بلا الملغاة)"""
    return [m for m in rows if is_table_round(_g(m, "round")) and _g(m, "status") not in VOID]


def knockout_rows(rows):
    """ما بعد المرحلة (لشجرة البطولة)"""
    return [m for m in rows if not is_table_round(_g(m, "round"))]


def split_groups(rows):
    """قائمة مجموعات (قوائم معرّفات مرتّبة) من رسم المواجهات — مرتّبة بأقدم مباراة بكل مجموعة"""
    adj, first = {}, {}
    for m in rows:
        h, a = _g(m, "home_id"), _g(m, "away_id")
        adj.setdefault(h, set()).add(a)
        adj.setdefault(a, set()).add(h)
        key = (str(_g(m, "date") or "9999"), _g(m, "match_id") or 0)
        for t in (h, a):
            if t not in first or key < first[t]:
                first[t] = key
    seen, groups = set(), []
    for t in sorted(adj):
        if t in seen:
            continue
        comp, stack = set(), [t]
        while stack:
            u = stack.pop()
            if u in comp:
                continue
            comp.add(u)
            stack.extend(adj[u] - comp)
        seen |= comp
        groups.append(comp)
    groups.sort(key=lambda g: min(first[t] for t in g))
    return [sorted(g) for g in groups]


def _stats(rows, team_ids):
    """{team: {played, won, drawn, lost, gf, ga, gd, points}} من المنتهية بين فرق team_ids فقط"""
    st = {t: {"team": t, "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0} for t in team_ids}
    for m in rows:
        if _g(m, "status") not in FINISHED or _g(m, "home_goals") is None or _g(m, "away_goals") is None:
            continue
        h, a, hg, ag = _g(m, "home_id"), _g(m, "away_id"), _g(m, "home_goals"), _g(m, "away_goals")
        if h not in st or a not in st:
            continue
        for t, gf, ga in ((h, hg, ag), (a, ag, hg)):
            r = st[t]
            r["played"] += 1
            r["gf"] += gf
            r["ga"] += ga
            r["won" if gf > ga else "drawn" if gf == ga else "lost"] += 1
    for r in st.values():
        r["gd"] = r["gf"] - r["ga"]
        r["points"] = 3 * r["won"] + r["drawn"]
    return st


def table(rows, team_ids, name_of=None, h2h=False, rule=None):
    """صفوف الجدول لفرق team_ids من المباريات rows (المنتهية فقط تُحسب).
    h2h=True (الموجة 4): بين المتعادلين بالنقاط تُقارن نقاط/فارق/أهداف مواجهاتهم المباشرة قبل الفارق العام.
    rule="league" (الموجة 4، AFC-CLE — مرحلة دوري لا يلتقي فيها كل المتعادلين): النقاط ← الفارق ← الأهداف ← الانتصارات ← المعرّف
    (تصاعدياً) — يطابق ترتيب المزوّد (كيوتو 302 قبل جوهور 2523 بتعادل كامل)."""
    out = list(_stats(rows, team_ids).values())
    nm = name_of or (lambda t: "")
    if rule == "league":
        out.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], -r["won"], r["team"]))
    elif not h2h:
        out.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], (nm(r["team"]) or "").casefold(), r["team"]))
    else:
        tied = {}
        for r in out:
            tied.setdefault(r["points"], []).append(r["team"])
        mini = {}
        for ids in tied.values():
            mini.update(_stats(rows, ids) if len(ids) > 1 else {})
        z = {"points": 0, "gd": 0, "gf": 0}
        out.sort(key=lambda r: (-r["points"], -mini.get(r["team"], z)["points"], -mini.get(r["team"], z)["gd"],
                                -mini.get(r["team"], z)["gf"], -r["gd"], -r["gf"], (nm(r["team"]) or "").casefold(), r["team"]))
    for i, r in enumerate(out, 1):
        r["pos"] = i
    return out


def _named(sr, comps, names, name_of, tb):
    """مكوّنات المواجهات ← المجموعات المسمّاة (بعضوية الفرق، بترتيب الـconfig)؛ ما لا يطابق يُلحق بعدها"""
    out, left = [], list(comps)
    for g in names:
        members = set(g["teams"])
        mine = [c for c in left if set(c) <= members]
        if not mine:
            continue
        left = [c for c in left if c not in mine]
        out.append({"name": {"ar": g["ar"], "en": g["en"]}, "teams": sorted(set().union(*map(set, mine)))})
    out += [{"teams": c} for c in left]
    res = []
    for i, g in enumerate(out, 1):
        e = {"group": i, "rows": table(sr, g["teams"], name_of, **tb)}
        if "name" in g:
            e["name"] = g["name"]
        res.append(e)
    return res


def tables(rows, how, name_of=None, code=None):
    """[{"group": رقم المجموعة | None, "name"?: {"ar","en"}, "rows": [صفوف]}] — how = "groups" | "league" (أي شيء آخر = []).
    code (الموجة 4): يقرأ "groups" (أسماء بعضوية الفرق) و"tiebreak" من الـconfig — كأس بلاهما = الناتج القديم حرفياً."""
    sr = stage_rows(rows)
    if not sr or how not in ("groups", "league"):
        return []
    tb = {"h2h": tiebreak(code) == "h2h", "rule": tiebreak(code)}
    if how == "groups":
        names = group_names(code)
        if names:
            return _named(sr, split_groups(sr), names, name_of, tb)
        return [{"group": i, "rows": table(sr, g, name_of, **tb)} for i, g in enumerate(split_groups(sr), 1)]
    teams = sorted({_g(m, "home_id") for m in sr} | {_g(m, "away_id") for m in sr})
    return [{"group": None, "rows": table(sr, teams, name_of, **tb)}]


def group_title(entry, lang):
    """اسم المجموعة الرسمي بلغة العرض، أو None (مجموعة مرقّمة/جدول واحد)"""
    n = entry.get("name") if entry else None
    return n[lang] if n else None


def position_entry(tbls, tid):
    """(مدخل المجموعة، المركز) أو (None, None) — لعنوان المجموعة المسمّاة ببطاقة النادي"""
    for g in tbls:
        for r in g["rows"]:
            if r["team"] == tid:
                return g, r["pos"]
    return None, None


def position(tbls, tid):
    """(رقم المجموعة | None، المركز) أو (None, None)"""
    for g in tbls:
        for r in g["rows"]:
            if r["team"] == tid:
                return g["group"], r["pos"]
    return None, None


def en_names(conn):
    """{team_id: الاسم الإنجليزي المعروض} — لكسر التعادل الأخير بالاسم"""
    return {r[0]: r[1] or "" for r in conn.execute(
        "SELECT team_id, COALESCE(NULLIF(name_en_official, ''), name_en) FROM teams")}
