#!/usr/bin/env python3
"""
الأدوار الإقصائية للكأس (الموجة 1، 4 نوفمبر 2026 — cups_plan.md 3.3) — دوال صافية بلا HTML، مصدر واحد لـmake_cups.py
(تبويب «شجرة البطولة») وmake_api.py (api/v1/cups/<code>.json) وبطاقة «البطولات» بصفحة النادي.
=====================================================================================================================
بلا جداول جديدة: كل شيء مشتق من matches (round + الفريقين + النتيجة + pen_home/pen_away من match_score).

  ترتيب الأدوار  = أول موعد بكل دور (ترتيب المزوّد)؛ دور بلا موعد ← ROUND_RANK (التمهيدي < 128 < … < النهائي)
  المواجهة (tie) = (الدور، زوج الفريقين بلا ترتيب) — مباراة واحدة أو ذهاب/إياب؛ الملغاة (CANC/ABD) لا تُحسب
  المجموع        = مجموع home_goals/away_goals لكل فريق (فقط إن انتهت كل المباريات)؛ الترجيح من آخر مباراة
  الفائز         = الفريق الظاهر بالدور التالي (يصمد أمام قاعدة الأهداف خارج الأرض/أي اختلاف)، وإلا المجموع ثم الترجيح
  الشجرة        = ترتيب مواجهات كل دور بحيث تتجاور مغذّيات المواجهة التالية (بالفريق، لا بمعرّفات المزوّد)
  الأدوار المقبلة = بالتسلسل القياسي (… ربع النهائي، نصف النهائي، النهائي) بخانات فارغة حتى تظهر بالقائمة
  «المركز الثالث» خارج الشجرة (extra)

⚠️ السوبر بمباراة واحدة: المزوّد يسمّي دورها أحياناً «Group Stage» (السوبر الإماراتي 896) — مسابقة type=super بمواجهة واحدة
   تُعرض «النهائي» (display_round).
"""
FINAL_ST = ("FT", "AET", "PEN", "AWD")
VOID = ("CANC", "ABD")
SEQ = ("Preliminary Round", "1st Preliminary Round", "2nd Preliminary Round", "Round of 128", "Round of 64",
       "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final")
ROUND_RANK = {r: i for i, r in enumerate(SEQ)}
EXTRA = ("3rd place",)
NEXT = {"Round of 128": "Round of 64", "Round of 64": "Round of 32", "Round of 32": "Round of 16",
        "Round of 16": "Quarter-finals", "Quarter-finals": "Semi-finals", "Semi-finals": "Final"}


def _g(m, k):
    try:
        return m[k]
    except (KeyError, IndexError):
        return None


def round_order(rows):
    """أسماء الأدوار بالترتيب: أول موعد بكل دور، ثم ROUND_RANK لما لا موعد له"""
    first = {}
    for m in rows:
        r = _g(m, "round") or ""
        d = str(_g(m, "date") or "")
        if r not in first or (d and (not first[r] or d < first[r])):
            first[r] = d
    return sorted(first, key=lambda r: (first[r] or "9999", ROUND_RANK.get(r, 99), r))


def _tie(rnd, legs):
    legs = sorted(legs, key=lambda m: (str(_g(m, "date") or ""), _g(m, "match_id")))
    a, b = _g(legs[0], "home_id"), _g(legs[0], "away_id")
    done = all(_g(m, "status") in FINAL_ST and _g(m, "home_goals") is not None for m in legs)
    agg = None
    if done:
        ga = sum(_g(m, "home_goals") if _g(m, "home_id") == a else _g(m, "away_goals") for m in legs)
        gb = sum(_g(m, "away_goals") if _g(m, "home_id") == a else _g(m, "home_goals") for m in legs)
        agg = (ga, gb)
    pens = None
    last = legs[-1]
    ph, pa = _g(last, "pen_home"), _g(last, "pen_away")
    if ph is not None and pa is not None:
        pens = (ph, pa) if _g(last, "home_id") == a else (pa, ph)
    return {"round": rnd, "a": a, "b": b, "legs": legs, "done": done, "agg": agg, "pens": pens, "winner": None,
            "placeholder": False}


def _decide(t, next_teams):
    """الفائز: الظاهر بالدور التالي، وإلا المجموع ثم الترجيح (None حتى يُحسم)"""
    ins = [x for x in (t["a"], t["b"]) if x in next_teams]
    if len(ins) == 1:
        return ins[0]
    if not t["done"]:
        return None
    ga, gb = t["agg"]
    if ga != gb:
        return t["a"] if ga > gb else t["b"]
    if t["pens"] and t["pens"][0] != t["pens"][1]:
        return t["a"] if t["pens"][0] > t["pens"][1] else t["b"]
    return None


def build(rows, comp_type=None):
    """{"rounds": [{"round", "ties":[tie]}], "extra": [tie], "champion": team_id|None}
    rows: صفوف مباريات المسابقة بموسم واحد (dict/sqlite Row بالمفاتيح: match_id, date, status, round, home_id, away_id,
    home_goals, away_goals, pen_home, pen_away)."""
    rows = [m for m in rows if _g(m, "status") not in VOID]
    order = round_order(rows)
    by_round = {}
    for m in rows:
        r = _g(m, "round") or ""
        key = frozenset((_g(m, "home_id"), _g(m, "away_id")))
        by_round.setdefault(r, {}).setdefault(key, []).append(m)
    main = [r for r in order if r not in EXTRA]
    ties = {r: [_tie(r, legs) for legs in by_round[r].values()] for r in order}
    for i, r in enumerate(main):
        nxt = set()
        if i + 1 < len(main):
            for t in ties[main[i + 1]]:
                nxt.update((t["a"], t["b"]))
        for t in ties[r]:
            t["winner"] = _decide(t, nxt)
    for r in order:
        if r in EXTRA:
            for t in ties[r]:
                t["winner"] = _decide(t, set())
    # ترتيب الشجرة على الأدوار المعروفة: آخرها بالموعد، ثم نزولاً — مغذّيا المواجهة k بالدور التالي بالموضعين 2k و2k+1
    #   (مواجهة لم يظهر فائزها بالدور التالي بعد = آخر الدور بالموعد)
    def _date(t):
        return str(_g(t["legs"][0], "date") or "") if t["legs"] else "9999"
    if main:
        ties[main[-1]].sort(key=lambda t: (_date(t), t["a"] or 0))
    for i in range(len(main) - 2, -1, -1):
        slot = {}
        for k, t in enumerate(ties[main[i + 1]]):
            for j, x in enumerate((t["a"], t["b"])):
                slot[x] = 2 * k + j

        def key(t, slot=slot):
            s = [slot[x] for x in (t["a"], t["b"]) if x in slot]
            return (min(s) if s else 10 ** 6, _date(t))
        ties[main[i]].sort(key=key)
    # الأدوار المقبلة (بالتسلسل القياسي) — خانات فارغة، مغذّاة من فائزي الدور السابق (المرتَّب) إن عُرفوا
    if main:
        last = main[-1]
        while len(ties[last]) > 1 and last in NEXT and NEXT[last] not in ties:
            prev, nr = ties[last], NEXT[last]
            ties[nr] = [{"round": nr, "a": prev[2 * k]["winner"],
                         "b": prev[2 * k + 1]["winner"] if 2 * k + 1 < len(prev) else None,
                         "legs": [], "done": False, "agg": None, "pens": None, "winner": None, "placeholder": True}
                        for k in range((len(prev) + 1) // 2)]
            main.append(nr)
            last = nr
    rounds = [{"round": r, "ties": ties[r]} for r in main if ties[r]]
    extra = [t for r in order if r in EXTRA for t in ties[r]]
    champ = None
    if rounds and len(rounds[-1]["ties"]) == 1 and not rounds[-1]["ties"][0]["placeholder"]:
        champ = rounds[-1]["ties"][0]["winner"]
    return {"rounds": rounds, "extra": extra, "champion": champ, "type": comp_type}


def display_round(raw, bracket):
    """اسم الدور للعرض: سوبر بمواجهة واحدة = «Final» مهما سمّاه المزوّد (896 = «Group Stage»)"""
    if bracket.get("type") == "super" and len(bracket["rounds"]) == 1 and len(bracket["rounds"][0]["ties"]) == 1:
        return "Final"
    return raw


def team_stage(bracket, tid):
    """(دور، حالة) لنادٍ بالمسابقة: حالة = champion | runner_up | out | alive | None (لم يشارك).
    دور = آخر دور شارك فيه (بلا خانات فارغة ولا المركز الثالث)."""
    last = None
    for rd in bracket["rounds"]:
        for t in rd["ties"]:
            if t["placeholder"]:
                continue
            if tid in (t["a"], t["b"]):
                last = (rd["round"], t)
    if last is None:
        return None, None
    rnd, t = last
    final = rnd == bracket["rounds"][-1]["round"] and len(bracket["rounds"][-1]["ties"]) == 1 \
        and not bracket["rounds"][-1]["ties"][0]["placeholder"]
    if t["winner"] is None:
        return display_round(rnd, bracket), "alive"
    if t["winner"] == tid:
        return display_round(rnd, bracket), ("champion" if final else "alive")
    return display_round(rnd, bracket), ("runner_up" if final else "out")
