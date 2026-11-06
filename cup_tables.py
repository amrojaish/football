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
"""
from config import COMPETITIONS

TABLE_STAGES = ("Group Stage", "League Phase", "Regular Season", "Regular season")
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


def table(rows, team_ids, name_of=None):
    """صفوف الجدول لفرق team_ids من المباريات rows (المنتهية فقط تُحسب)"""
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
    out = []
    for r in st.values():
        r["gd"] = r["gf"] - r["ga"]
        r["points"] = 3 * r["won"] + r["drawn"]
        out.append(r)
    nm = name_of or (lambda t: "")
    out.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], (nm(r["team"]) or "").casefold(), r["team"]))
    for i, r in enumerate(out, 1):
        r["pos"] = i
    return out


def tables(rows, how, name_of=None):
    """[{"group": رقم المجموعة | None, "rows": [صفوف]}] — how = "groups" | "league" (أي شيء آخر = [])"""
    sr = stage_rows(rows)
    if not sr or how not in ("groups", "league"):
        return []
    if how == "groups":
        return [{"group": i, "rows": table(sr, g, name_of)} for i, g in enumerate(split_groups(sr), 1)]
    teams = sorted({_g(m, "home_id") for m in sr} | {_g(m, "away_id") for m in sr})
    return [{"group": None, "rows": table(sr, teams, name_of)}]


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
