#!/usr/bin/env python3
"""
خطة صفحات اللاعبين — صفحة واحدة لكل player_id (8 أكتوبر 2026)
===============================================================
قبل: صفحة لكل نص `goals.player_en` (3,713) — الشخص بصيغ اسم متعددة له صفحات متعددة، ونصّ مشترك بين شخصين صفحة مختلطة.
الآن: كل هدف يُسنَد لـ`player_id` ثم تُبنى صفحة واحدة لكل معرّف؛ ما لا يُسنَد (بلا معرّف/غامض) يبقى بصفحات الأسماء كما هو.

⚠️ **مصدر حقيقة واحد:** make_players · make_clubs · make_site3/leagues · make_search · make_following · clean_orphans تستورد
   `get_plan()` (نفس الحساب بكل عملية، من نفس القاعدة). لا تكرار محلي للمنطق.

إسناد هدف ← معرّف (أول قاعدة تنطبق؛ غير ذلك يبقى بصفحة الاسم — لا تخمين):
    A  تشكيلة/إحصائيات نفس المباراة والنادي فيها نصّ الهدف بمعرّف واحد فقط
    A2 هدف عكسي: اللاعب بتشكيلة الخصم
    B  (نصّ، نادٍ) له معرّف واحد بكل القاعدة
    ✗  «الاسم له معرّف واحد بالمجمل» **غير مستعمل** (قرار عمرو: أسقط 747 هدفاً ولا يُعاد — مثال m-i-hassan صفحة مختلفة)
    ✗  معرّف 0، أو نصّ بمعرّفين بنفس المباراة (X)، أو نصّ بتشكيلة المباراة غير موجود ولا (نصّ، نادٍ) فريد = يبقى باسمه
استثناء (قرار عمرو): زوج (نصّ، معرّف) دليله الوحيد B (اسم+نادٍ) ولا يشارك أي صيغة أخرى للمعرّف لقباً = لا يُسنَد.

الـslug: صفحة المعرّف تحتفظ بـ**رابط الاسم الأكثر أهدافاً** عندها (فلا يتغيّر رابط النجوم)، ورابط كل اسم يبقى لصفحة اسمه إن لم
يُدمج. تعارض رابطين = للأكثر أهدافاً النظيف والآخر `-N` (لا يعيد استعمال أي رابط قديم). الروابط القديمة المحذوفة = stub إعادة توجيه
لصفحة الجزء الأكبر من أهداف ذلك الاسم. اسم العرض = أكثر صيغة استعمالاً (تشكيلات+إحصائيات+أهداف)، والعربي الأكثر استعمالاً بنفس المعرّف.
"""
import collections
import csv
import difflib
import json
import re
import sqlite3
import unicodedata

from config import BASE_DIR, DB_FILE
from player_slug import build_slug_map, slug as _slugify

_CACHE = {}


def _toks(n):
    t = "".join(ch for ch in unicodedata.normalize("NFKD", n) if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[-.'’`]", " ", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return [x for x in t.split() if x not in ("al", "el")]


def _surnames(n):
    t = _toks(n)
    if not t:
        return set()
    r = {t[-1]}
    if len(t) >= 3:
        r.add(t[-2] + t[-1])            # Abdel Salam / Abdelsalam
    return r


def shares_surname(a, b):
    return any(difflib.SequenceMatcher(None, x, y).ratio() >= 0.8 for x in _surnames(a) for y in _surnames(b))


HISTORY_FILE = BASE_DIR / "player_url_history.json"          # حالة دائمة بـdb-state المشفَّر (state_sync.STATE_FILES) لا بـgit
HISTORY_SEED = BASE_DIR / "player_url_history.seed.json"     # مزروع بـgit: احتياط أول تشغيل قبل وجود الملف بالحالة (يُدمج، لا يُكتب)
MERGES_FILE = BASE_DIR / "player_id_merges.csv"
SCORER_ALIASES_FILE = BASE_DIR / "scorer_name_aliases.csv"  # (team_id, from_en) -> to_en لأسماء الهدّافين (apply_scorer_aliases.py)
NAME_MERGES_FILE = BASE_DIR / "player_merges.csv"             # old_name -> keep_name العام (apply_player_merges.py)
PINS_FILE = BASE_DIR / "player_name_pins.csv"                 # player_id,name_en,reason — الاسم المثبَّت يغلب صيغة الأكثرية (وslug الصفحة يتبعه)


def _read_history(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d.get("slugs", {}) if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load_history(path=HISTORY_FILE, seed=HISTORY_SEED):
    """{slug: {"pid": int|None, "name": str|None, "to": slug?}} — كل رابط لاعب نُشر يوماً (اللغتان بنفس الـslug).
    = البذرة المزروعة بـgit ثم ملف الحالة فوقها (الحالة تغلب). بغياب الملفين = {}."""
    h = dict(_read_history(seed)) if seed else {}
    h.update(_read_history(path))
    return h


def load_id_merges(path=MERGES_FILE):
    """{drop_id: keep_id} من player_id_merges.csv (المعرّفات الحقيقية فقط؛ drop=0 مجموعات اسم)."""
    out = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if (r.get("drop_id") or "").strip() and int(r["drop_id"]) != 0:
                    out[int(r["drop_id"])] = int(r["keep_id"])
    except (OSError, ValueError):
        pass
    return out


def load_name_aliases(path=SCORER_ALIASES_FILE, merges_path=NAME_MERGES_FILE):
    """{from_en: {to_en, ...}}: scorer_name_aliases.csv (بلا النادي: سجلّ الروابط بلا نادٍ) + player_merges.csv (old_name -> keep_name،
    بلا «تخميني» كما يطبّقه apply_player_merges.py). كل اسم اختفى من القاعدة بأيّ منهما يجد وجهته. بغياب الملفين = {}."""
    from apply_scorer_aliases import load_aliases
    out = collections.defaultdict(set)
    for a in load_aliases(path):
        out[a["from"]].add(a["to"])
    try:
        with open(merges_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                old, keep = (r.get("old_name") or "").strip(), (r.get("keep_name") or "").strip()
                if old and keep and old != keep and (r.get("confidence") or "").strip() != "تخميني":
                    out[old].add(keep)
    except OSError:
        pass
    return dict(out)


def load_pins(path=PINS_FILE):
    """{player_id: name_en} من player_name_pins.csv. معرّف مكرر أو سطر ناقص = ValueError (توقّف كامل، لا تخمين). بغياب الملف = {}.
    وجود الاسم فعلاً للمعرّف يتحقق منه build_plan."""
    out = {}
    try:
        f = open(path, encoding="utf-8-sig", newline="")
    except OSError:
        return out
    with f:
        for r in csv.DictReader(f):
            pid_s, name = (r.get("player_id") or "").strip(), (r.get("name_en") or "").strip()
            if not pid_s and not name:
                continue
            if not pid_s.isdigit() or int(pid_s) <= 0 or not name:
                raise ValueError(f"pin ناقص أو معرّف غير صالح: {r}")
            if int(pid_s) in out:
                raise ValueError(f"pin مكرر لنفس player_id: {pid_s}")
            out[int(pid_s)] = name
    return out


def update_history(plan, path=HISTORY_FILE, seed=HISTORY_SEED):
    """يضيف صفحات الخطة الحالية للسجلّ (لا يحذف شيئاً أبداً) ويكتب ملف الحالة. يرجّع عدد المضاف/المحدَّث.
    أول تشغيل بلا ملف حالة: يُكتب الملف كاملاً (البذرة + الحالية) فيصعد بـdb_push ويكفي بعدها."""
    hist = load_history(path, seed)
    changed = 0 if path.exists() else 1
    for pg in plan["pages"]:
        e = {"pid": pg["pid"], "name": pg["display_en"]}
        old = hist.get(pg["slug"])
        if old is None or any(old.get(k) != v for k, v in e.items()) or old.get("stub"):
            hist[pg["slug"]] = {k: v for k, v in {**(old or {}), **e}.items() if k != "stub"}   # صفحة الآن: بلا علامة stub
            changed += 1
    # روابط إعادة التوجيه (stubs) المنشورة أيضاً (26 أكتوبر 2026): تُسجَّل بلاعب وجهتها فيحجزها build_plan له كالصفحات
    # (m-hamed → 342766 كاد يصير صفحة لاعب تونسي). جديدة فقط: سجلّ موجود (صفحة سابقة صارت stub) لا يُعاد كتابته.
    by_slug = {pg["slug"]: pg for pg in plan["pages"]}
    # صفحة منشورة سابقاً صارت إعادة توجيه الآن: تُعلَّم "stub" فقط (صاحبها pid/name لا يُمسّ) — فيعرف build_plan صفحة صاحبها الحالية
    # (370169: s-bouchama صفحة قديمة → stub، salah-abd-etouab-bouchama الصفحة الحالية)؛ عادت صفحةً = تُزال العلامة أعلاه
    claims = plan.get("name_claims", {})
    for s, dest in sorted(plan.get("stubs", {}).items()):
        pg = by_slug.get(dest)
        if s in hist:
            if not hist[s].get("stub") and not hist[s].get("to"):
                hist[s] = {**hist[s], "stub": True}
                changed += 1
            # (27 أكتوبر 2026) رابط اسم بلا معرّف حوّله build_plan بالاسم لصفحة لاعب (معرّف): يُسجَّل اللاعب مالكاً — فلا يأخذه لاحقاً
            # نادٍ آخر بنفس نصّ الاسم (/m-lahtimi-2: «M. Lahtimi» المغربي ثم هدّاف كاظمة بنفس الاسم بعد استيراد الكويت). صفحة
            # موجودة الآن (ليست stub) لا تُمسّ؛ وجهة صفحة اسم (بلا معرّف) لا تُسجَّل.
            if (s in claims and claims[s] == dest and pg is not None and pg["kind"] == "pid"
                    and hist[s].get("pid") is None and not hist[s].get("to")):
                hist[s] = {**hist[s], "pid": pg["pid"], "stub": True}
                changed += 1
            continue
        if pg is None:
            continue
        hist[s] = {"pid": pg["pid"], "name": pg["display_en"], "stub": True}
        changed += 1
    if changed:
        write_history(hist, path)
    return changed


def write_history(hist, path=HISTORY_FILE):
    doc = ("كل رابط لاعب نُشر يوماً (players/ و en/players/ بنفس الـslug). player_pages.build_plan يحوّل أي slug هنا لم يعد صفحة "
           "إلى stub نحو صفحة صاحب نفس player_id (بعد player_id_merges.csv)؛ بلا معرّف = يُطبع ويُتخطّى إلا إن كُتب to يدوياً. "
           "make_players يضيف الصفحات الجديدة ولا يحذف شيئاً.")
    lines = [json.dumps(k, ensure_ascii=False) + ": " + json.dumps(hist[k], ensure_ascii=False, sort_keys=True) for k in sorted(hist)]
    nl = chr(10)
    body = '{"_doc": ' + json.dumps(doc, ensure_ascii=False) + ',' + nl + '"slugs": {' + nl + (',' + nl).join(lines) + nl + '}}' + nl
    path.write_text(body, encoding="utf-8", newline=nl)


def build_plan(conn, history=None, id_merges=None, pins=None, name_aliases=None):
    """يرجّع {pages, old_slugs, name_slug, nt_slug, stubs, aliases, stats, unresolved}. conn قراءة فقط.
    history/id_merges: سجلّ الروابط المنشورة وخريطة دمج المعرّفات (get_plan يحمّلهما من الملفين).
    pins: {player_id: name_en} من player_name_pins.csv — الاسم المثبَّت يغلب الأكثر استعمالاً بالعرض وبالـslug (يُرفض نصّ غير موجود للمعرّف).
    name_aliases: {from_en: {to_en}} (None = من scorer_name_aliases.csv) — لحلّ روابط الأسماء المنشورة بعد تنظيف/دمج الاسم."""
    pins = pins or {}
    if name_aliases is None:
        name_aliases = load_name_aliases()
    goals = []
    for r in conn.execute("""
            SELECT g.id AS gid, g.player_en AS en, g.player_ar AS ar, g.team_id, g.minute, g.detail,
                   m.match_id, m.date, m.season, m.league_code, m.home_id, m.away_id
            FROM goals g JOIN matches m ON m.match_id = g.match_id
            WHERE g.player_en IS NOT NULL AND g.player_en != ''
            ORDER BY m.date DESC, g.id"""):
        goals.append(dict(zip(("gid", "en", "ar", "team_id", "minute", "detail", "match_id", "date", "season",
                               "league_code", "home_id", "away_id"), tuple(r))))

    # ---- فهارس التشكيلات والإحصائيات (معرّف غير صفري فقط)
    mt = collections.defaultdict(set)          # (match, team, name) -> ids
    nt = collections.defaultdict(set)          # (name, team) -> ids
    names_of = collections.defaultdict(collections.Counter)    # id -> name -> rows
    ar_of = collections.defaultdict(collections.Counter)       # id -> arabic -> rows
    for t in ("lineup_players", "player_stats"):
        for mid, tid, pid, en, ar in conn.execute(
                f"SELECT match_id, team_id, player_id, player_en, player_ar FROM {t} "
                "WHERE player_id > 0 AND player_en IS NOT NULL AND player_en != ''"):
            mt[(mid, tid, en)].add(pid)
            nt[(en, tid)].add(pid)
            names_of[pid][en] += 1
            if ar:
                ar_of[pid][ar] += 1
    home_away = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT match_id, home_id, away_id FROM matches")}

    # ---- إسناد الأهداف
    attr, via = {}, {}
    for g in goals:
        ps = mt.get((g["match_id"], g["team_id"], g["en"]), set())
        if not ps and g["detail"] == "Own Goal":
            h, a = home_away.get(g["match_id"], (None, None))
            other = a if g["team_id"] == h else h
            ps = mt.get((g["match_id"], other, g["en"]), set())
            if len(ps) == 1:
                attr[g["gid"]], via[g["gid"]] = next(iter(ps)), "A2"
                continue
        if len(ps) == 1:
            attr[g["gid"]], via[g["gid"]] = next(iter(ps)), "A"
            continue
        if len(ps) > 1:
            continue                               # نصّ بمعرّفين بنفس المباراة: غامض، يبقى باسمه
        ps2 = nt.get((g["en"], g["team_id"]), set())
        if len(ps2) == 1:
            attr[g["gid"]], via[g["gid"]] = next(iter(ps2)), "B"
    # استثناء: دليله الوحيد B ولا لقب مشترك مع باقي صيغ المعرّف
    ev = collections.defaultdict(set)
    for g in goals:
        if g["gid"] in attr:
            ev[(g["en"], attr[g["gid"]])].add(via[g["gid"]])
    drop_pairs = set()
    for (n, pid), kinds in ev.items():
        if kinds == {"B"}:
            others = [x for x in names_of[pid] if x != n]
            if others and not any(shares_surname(n, x) for x in others):
                drop_pairs.add((n, pid))
    for g in goals:
        if g["gid"] in attr and (g["en"], attr[g["gid"]]) in drop_pairs:
            del attr[g["gid"]]
            del via[g["gid"]]

    # ---- وحدات الصفحات
    by_name = collections.defaultdict(list)
    for g in goals:
        by_name[g["en"]].append(g)
    old_slugs = build_slug_map({n: len(v) for n, v in by_name.items()})
    pid_goals = collections.defaultdict(list)
    name_left = collections.defaultdict(list)
    for g in goals:
        if g["gid"] in attr:
            pid_goals[attr[g["gid"]]].append(g)
        else:
            name_left[g["en"]].append(g)

    for _pid, _n in sorted(pins.items()):
        if _n not in names_of[_pid] and not any(g["en"] == _n for g in pid_goals[_pid]):
            raise ValueError(f"pin {_pid}: {_n!r} ليس اسماً موجوداً لهذا المعرّف بالتشكيلات/الإحصائيات/الأهداف")

    def primary(pid):
        if pid in pins and pins[pid] in old_slugs:
            return pins[pid]
        c = collections.Counter(g["en"] for g in pid_goals[pid])
        return max(c.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0]

    def want_slug(pid):
        if pid in pins and pins[pid] not in old_slugs:
            print(f"  ⚠️ pin {pid}: {pins[pid]!r} بلا أهداف باسمه — الـslug من الاسم نفسه ({_slugify(pins[pid])})")
            return _slugify(pins[pid])
        return old_slugs[primary(pid)]

    def display(pid):
        if pid in pins:
            return pins[pid]
        use = collections.Counter(names_of[pid])
        for g in pid_goals[pid]:
            use[g["en"]] += 1
        return max(use.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0]

    def display_ar(pid):
        use = collections.Counter(ar_of[pid])
        for g in pid_goals[pid]:
            if g["ar"]:
                use[g["ar"]] += 1
        return max(use.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0] if use else ""

    wants = []
    for pid, gs in pid_goals.items():
        wants.append((len(gs), ("pid", pid), want_slug(pid)))
    for n, gs in name_left.items():
        wants.append((len(gs), ("name", n), old_slugs[n]))
    wants.sort(key=lambda w: (-w[0], str(w[1])))
    # ---- ثبات الروابط المنشورة (26 أكتوبر 2026، استيراد TUN): slug بسجلّ الروابط لصاحبه (معرّف بعد id_merges، أو الاسم لصفحة
    #      بلا معرّف) لا يأخذه لاعب آخر ما دام لصاحبه صفحة — كان الأكثر أهدافاً يأخذ الرابط النظيف فيتغيّر معنى m-diop وغيره.
    #      الطالب المحجوب يأخذ رابطه المنشور هو إن وُجد، وإلا لاحقة جديدة.
    present = {key for _c, key, _w in wants}
    owner, owned = {}, collections.defaultdict(list)
    for h_slug, e in (history or {}).items():
        if e.get("to"):
            continue
        if e.get("pid"):
            pid, seen = e["pid"], set()
            while pid in (id_merges or {}) and pid not in seen:
                seen.add(pid)
                pid = id_merges[pid]
            k = ("pid", pid)
        elif e.get("name"):
            k = ("name", e["name"])
        else:
            continue
        owner[h_slug] = k
        if k in present:
            owned[k].append(h_slug)

    def blocked(s, key):
        o = owner.get(s)
        return o is not None and o != key and o in present

    taken, slug_of = {}, {}
    old_all = set(old_slugs.values())
    # (26 أكتوبر 2026، تحضير ALG/KUW) صاحب صفحة منشورة يبقى على رابطها: إن لم يكن الرابط المحسوب (want) إحدى صفحاته المنشورة
    # (سجلّ بلا "stub") يأخذ صفحته المنشورة — المسجَّلة باسمه المعروض الآن أولاً. كان تغيّر الاسم الأكثر أهدافاً (هدّافون جدد بصيغة
    # أخرى للاسم) ينقل الصفحة لرابط جديد ويحوّل القديم لإعادة توجيه (m-bencherifa → m-w-bencherifa).
    def shown(key):
        return display(key[1]) if key[0] == "pid" else key[1]

    def own_pages(key):
        return [s for s in owned[key] if not (history or {})[s].get("stub")]

    for cnt, key, want in wants:
        mine = sorted((s for s in owned[key] if s not in taken), key=lambda s: (not s.startswith(want), len(s), s))
        pages_ = own_pages(key)
        if pages_ and want not in pages_:
            free = [s for s in pages_ if s not in taken]
            if free:
                nm = shown(key)
                best = sorted(free, key=lambda s: ((history or {})[s].get("name") != nm, not s.startswith(want), len(s), s))[0]
                taken[best], slug_of[key] = key, best
                continue
        if want not in taken and not blocked(want, key):
            taken[want], slug_of[key] = key, want
        elif mine:
            taken[mine[0]], slug_of[key] = key, mine[0]
        else:
            i = 2
            while f"{want}-{i}" in taken or f"{want}-{i}" in old_all or f"{want}-{i}" in owner:
                i += 1
            s2 = f"{want}-{i}"
            taken[s2], slug_of[key] = key, s2

    # ---- bridge (للأسماء الباقية): اسم ← معرّف واحد بالتشكيلات كما كان
    name_ids = collections.defaultdict(set)
    for en, pid in conn.execute("SELECT player_en, player_id FROM lineup_players WHERE player_id > 0 "
                                "AND player_en IS NOT NULL AND player_en != ''"):
        name_ids[en].add(pid)
    bridge = {n: next(iter(s)) for n, s in name_ids.items() if len(s) == 1}

    pages = []
    for cnt, key, _w in wants:
        slug = slug_of[key]
        if key[0] == "pid":
            pid = key[1]
            pages.append(dict(slug=slug, kind="pid", pid=pid, stats_pid=pid, display_en=display(pid), display_ar=display_ar(pid),
                              goals=pid_goals[pid]))
        else:
            n = key[1]
            pages.append(dict(slug=slug, kind="name", pid=None, stats_pid=bridge.get(n), display_en=n, display_ar="",
                              goals=name_left[n]))
    # ---- وجهة كل اسم قديم
    dest = {}
    for n, gs in by_name.items():
        c = collections.Counter()
        for g in gs:
            c[slug_of[("pid", attr[g["gid"]])] if g["gid"] in attr else slug_of[("name", n)]] += 1
        dest[n] = c
    new_slugs = set(slug_of.values())
    stubs = {}
    for n, c in dest.items():
        old_s = old_slugs[n]
        if old_s not in new_slugs:
            o = owner.get(old_s)
            # رابط مسجَّل لصاحب ما زالت له صفحة: يبقى نحو صاحبه لا نحو صاحب أغلب أهداف الاسم الآن
            stubs[old_s] = slug_of[o] if o in slug_of else sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    name_slug = {n: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for n, c in dest.items()}
    ntc = collections.defaultdict(collections.Counter)
    for g in goals:
        s = slug_of[("pid", attr[g["gid"]])] if g["gid"] in attr else slug_of[("name", g["en"])]
        ntc[(g["en"], g["team_id"])][s] += 1
    nt_slug = {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in ntc.items()}
    # ---- روابط منشورة سابقاً لم تعد صفحة (دمج معرّفات/تغيّر الخطة): stub نحو الصفحة التي صار فيها نفس player_id
    slug_by_pid = {pg["pid"]: pg["slug"] for pg in pages if pg["kind"] == "pid"}
    unresolved = []
    name_claims = {}   # رابط اسم منشور حُلّ بالاسم/الاسم البديل/الدمج → وجهته (update_history يسجّل لاعبها مالكاً، 27 أكتوبر 2026)
    # مرّتان: أولاً بالمعرّف، ثم `to` اليدوي (قد يشير لـslug صار stub بالمرحلة الأولى فيُحلّ لوجهته: لا stub نحو stub)
    for manual in (False, True):
        for h_slug, e in sorted((history or {}).items()):
            if h_slug in new_slugs or h_slug in stubs or bool(e.get("to")) != manual:
                continue
            dest = None
            if manual:
                dest = e["to"] if e["to"] in new_slugs else stubs.get(e["to"])
            elif e.get("pid"):
                pid, seen = e["pid"], set()
                while pid in (id_merges or {}) and pid not in seen:
                    seen.add(pid)
                    pid = id_merges[pid]
                dest = slug_by_pid.get(pid)
            elif e.get("name"):
                # رابط اسم بلا معرّف (27 أكتوبر 2026): الاسم اختفى بتنظيف رقم المزوّد الملتصق أو باسم بديل بالنادي
                # (apply_scorer_aliases.py) — يُحوَّل لصفحة الاسم الجديد بنفس التنظيف ونفس الخريطة. لا رابط منشور يصير 404.
                from apply_scorer_aliases import clean_name
                # الترتيب: وجهات الاسم البديل/الدمج أولاً (سلسلة بلا دورات، الأقرب أولاً)، ثم الاسم نفسه منظَّفاً — اسم بقي بنادٍ آخر
                # (H. Khabba) لا يجذب رابط صفحة اسم صار لغيره.
                start = [e["name"], clean_name(e["name"])]
                cands, seen, frontier = [], set(start), start
                while frontier:
                    nxt = []
                    for c in frontier:
                        for t in sorted(name_aliases.get(c, ())):
                            if t not in seen:
                                seen.add(t)
                                cands.append(t)
                                nxt.append(t)
                    frontier = nxt
                cands += [clean_name(e["name"])]
                dest = next((name_slug[c] for c in cands if name_slug.get(c) in new_slugs), None)
                if dest:
                    name_claims[h_slug] = dest
            if dest and dest in new_slugs:
                stubs[h_slug] = dest
            else:
                unresolved.append(h_slug)
    aliases = collections.defaultdict(list)
    for o, n in sorted(stubs.items()):
        aliases[n].append(o)
    return dict(pages=pages, old_slugs=old_slugs, name_slug=name_slug, nt_slug=nt_slug, stubs=stubs,
                aliases=dict(aliases), unresolved=unresolved, name_claims=name_claims, attributed=len(attr), total_goals=len(goals),
                via=dict(collections.Counter(via.values())), dropped_pairs=sorted(drop_pairs))


def get_plan(conn=None):
    """نفس الخطة لكل السكربتات بالعملية الواحدة (كاش). بلا conn يفتح القاعدة قراءة فقط."""
    try:
        _ps = PINS_FILE.stat()
        key = (str(DB_FILE), _ps.st_mtime_ns, _ps.st_size)
    except OSError:
        key = (str(DB_FILE), 0, 0)
    if conn is None and key in _CACHE:
        return _CACHE[key]
    own = conn is None
    if own:
        conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
    try:
        plan = build_plan(conn, load_history(), load_id_merges(), load_pins())
    finally:
        if own:
            conn.close()
    if own:
        _CACHE[key] = plan
    return plan


def resolve_slug(player_en, fallback, team_id=None, plan=None):
    """slug الرابط النهائي: صفحة الاسم/المعرّف إن وُجدت، وإلا الـslug المخمَّن (`fallback`) مُمرَّراً بخريطة الـstubs
    (اسم بلا أهداف كـ«A. Kone» يطابق slug صفحة «A. Koné» القديمة التي صارت stub — لا رابط داخلي لـstub)."""
    plan = plan or get_plan()
    s = link_slug(player_en, team_id, plan) or fallback
    return plan["stubs"].get(s, s)


def link_slug(player_en, team_id=None, plan=None):
    """slug صفحة هذا الاسم (اختيارياً بنادٍ محدد) أو None إن لم يكن له أهداف"""
    plan = plan or get_plan()
    if team_id is not None:
        s = plan["nt_slug"].get((player_en, team_id))
        if s:
            return s
    return plan["name_slug"].get(player_en)
