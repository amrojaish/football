#!/usr/bin/env python3
"""
اختيار دفعة "نسخ آمن" لترجمة أسماء اللاعبين
================================================
يستبدل السكربتات المؤقّتة اللي كُتبت من الصفر كل دفعة (9 سبتمبر،
أربع مرات) بأداة دائمة واحدة بالمستودع — نفس مكانة
`export_to_translate.py`/`merge_batch.py`.

الفكرة: اسم غير مترجَم يُنسَخ له نفس الترجمة العربية الموجودة
أصلاً لصيغة أخرى **مؤكَّد أنها نفس الشخص** — لا ترجمة جديدة، نسخ
فقط. "نفس الشخص" هنا معناه: نفس `player_id`، ثم تحقّق سلوكي
إضافي (تزامن نفس `match_id` بالضبط) قبل القبول، لا تشابه نصي وحده.

⚠️ **كل المعايير هنا "دروس مُتعلَّمة" من أربع دفعات فعلية (9
   سبتمبر) — لا نظرية**:
   - تفرّد `player_id` وحده غير كافٍ (بند 27: أسماء عامة كـ"Ahmad
     Hassan" تتكرر لأشخاص مختلفين تماماً)
   - تشابه الاسم النصي لا يعني الهوية (درس 5) ولا العكس — أسماء
     مختلفة جذرياً قد تكون فعلاً نفس الشخص (`Abdallah Hassan`/
     `Ahmad Hassan`، تزامن 100% مؤكَّد)
   - التزامن بنفس `match_id` هو الدليل الحاسم — **لكن فقط بعيّنة
     كافية**: تزامن 100% بمباراة أو مباراتين قد يكون مصادفة صرفة
     (`Mansoor Al-Harbi` أعطى 100%@1/1 بينما نفس المصدر تقريباً
     بصيغة أخرى `Mansor Al Harbi` أعطى 48.3%@14/29 — تناقض حاسم)
   - تطابق عدد كلمات **الترجمة العربية نفسها** بعدد مكوّنات الاسم
     الهدف (لا الإنجليزي المصدر وحده) يكشف تلقائياً أسماءً أوسط
     ناقصة أو ألقاباً فنية مُحلولة لاسم أطول
   - بعض الحالات (تصادم هوية مؤكَّد يجتاز كل الفلاتر الآلية
     صدفة) تحتاج استبعاداً صريحاً بالاسم — `translation_excluded.csv`

الملفات المقروءة (لا كتابة على أي منها):
    players_ar.csv                  الترجمات الموجودة (المصدر)
    football.db                     غير المترجَم + player_id + match_id
    names_pending_id_review.csv     136+ اسماً مؤجَّلة (بند 27/43)
    translation_excluded.csv        استبعاد دائم صريح بالاسم

المخرَج: طباعة القائمة فقط (`--check`)، أو كتابة ملف دفعة جاهز
للمراجعة البشرية قبل إلحاقه يدوياً بـ`players_ar.csv` — **هذا
السكربت لا يكتب أبداً على `players_ar.csv` ولا `football.db`،
بأي وضع**، القرار النهائي بشري دائماً (مبدأ 6: لا نقل صوتي/تخمين
بلا مراجعة).

الاستخدام:
    python select_translation_batch.py --mode relaxed --check
    python select_translation_batch.py --mode strict  --check
    python select_translation_batch.py --mode relaxed --out batch_next.csv
"""

import argparse
import csv
import re
import sqlite3
from collections import defaultdict
from difflib import SequenceMatcher

from config import BASE_DIR, DB_FILE

PLAYERS_AR = BASE_DIR / "players_ar.csv"
PENDING136 = BASE_DIR / "names_pending_id_review.csv"
EXCLUDED = BASE_DIR / "translation_excluded.csv"

INITIAL_RE = re.compile(r"^[A-Za-z]\.$")
COMPONENT_SPLIT = re.compile(r"[\s\-]+")
AL_PREFIXES = {"al", "el"}
ABDUL_PREFIXES = {"abdul", "abd", "abdel"}  # ⚠️ درس 9 سبتمبر (بند 32) — راجع تحت
ABDUL_FUSED_RE = re.compile(r"^(abdul|abdel|abd)[a-z]", re.IGNORECASE)

MIN_COOCCUR_MATCHES = 3  # ⚠️ درس الدفعة الرابعة — أقل من هذا غير موثوق


def has_initial_token(name):
    """اسم مختصر بحرف واحد + نقطة (A. / S. / K. ...) بأي مكوّن"""
    return any(INITIAL_RE.match(tok) for tok in name.split())


def components(name):
    """يعامل 'Al X'/'El X'/'Abdul X'/'Abd X'/'Abdel X' كمكوّن واحد
    (يطابق اندماج أداة التعريف بالعربي: 'Al Shamrani' <-> 'الشمراني'
    كلمة واحدة لا كلمتين؛ نفس المنطق لـ'Abdul Rahman' <-> شخص واحد
    لا كلمتين منفصلتين — بند 32)."""
    raw = [c for c in COMPONENT_SPLIT.split(name) if c]
    merged = []
    i = 0
    while i < len(raw):
        if raw[i].lower() in (AL_PREFIXES | ABDUL_PREFIXES) and i + 1 < len(raw):
            merged.append(raw[i] + " " + raw[i + 1])
            i += 2
        else:
            merged.append(raw[i])
            i += 1
    return merged


def ar_weight(comp):
    """وزن الكلمات العربية المتوقَّعة لمكوّن واحد — 2 لمركّبات
    'عبد+اسم' (سواء وصلت متصلة 'Abdulrahman' أو مدموجة من نمط
    Al: 'Abdul Rahman')، 1 لأي مكوّن آخر. بلا هذا الوزن، معيار
    تساوي عدد الكلمات يفترض خطأً أن كل مكوّن إنجليزي = كلمة عربية
    واحدة، وهو افتراض ينهار تحديداً مع "Abdul-" (بند 32)."""
    if comp.split()[0].lower() in ABDUL_PREFIXES:
        return 2
    if ABDUL_FUSED_RE.match(comp.replace(" ", "")):
        return 2
    return 1


def sim(a, b):
    """تشابه نصي متماثل الاتجاه — SequenceMatcher وحده غير متماثل
    رياضياً (اكتُشف 9 سبتمبر)، فنأخذ الأعلى من الاتجاهين."""
    x, y = a.lower(), b.lower()
    return max(SequenceMatcher(None, x, y).ratio(), SequenceMatcher(None, y, x).ratio())


def load_translated(conn):
    translated = {}
    with open(PLAYERS_AR, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            en = (row.get("player_en") or "").strip()
            ar = (row.get("player_ar") or "").strip()
            if en and ar:
                translated[en] = ar
    return translated


def load_untranslated(conn):
    """مباشرة من الديتابيس — لا من ملف ساكن قد يكون قديماً."""
    untranslated = set()
    for table in ("goals", "lineup_players", "events", "player_stats"):
        for r in conn.execute(f"""
            SELECT DISTINCT player_en FROM {table}
            WHERE (player_ar IS NULL OR player_ar = '')
              AND player_en IS NOT NULL AND player_en != ''
        """):
            untranslated.add(r[0])
    return untranslated


def load_pending136():
    pending = set()
    if PENDING136.exists():
        with open(PENDING136, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                pending.add(row["player_en"])
    return pending


def load_excluded():
    excluded = {}
    if EXCLUDED.exists():
        with open(EXCLUDED, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                excluded[row["player_en"]] = row.get("reason", "")
    return excluded


def build_name_ids(conn):
    """اسم -> مجموعة player_id (من lineup_players/player_stats فقط
    — الجدولان الوحيدان الحاملان player_id، goals بلا معرّفات
    بنيوياً — درس 26)."""
    name_ids = defaultdict(set)
    for table in ("lineup_players", "player_stats"):
        for r in conn.execute(f"""
            SELECT player_id AS pid, player_en AS name FROM {table}
            WHERE player_id IS NOT NULL AND player_id != 0
              AND player_en IS NOT NULL AND player_en != ''
        """):
            name_ids[r["name"]].add(r["pid"])
    return name_ids


def build_appearance_counts(conn):
    counts = defaultdict(int)
    for table in ("goals", "lineup_players", "events", "player_stats"):
        for r in conn.execute(f"""
            SELECT x.player_en AS name, COUNT(*) AS n
            FROM {table} x JOIN matches m ON m.match_id = x.match_id
            WHERE x.player_en IS NOT NULL AND x.player_en != ''
            GROUP BY x.player_en
        """):
            counts[r["name"]] += r["n"]
    return counts


def match_id_cooccurrence(conn, pid, name_a, name_b):
    """كم مباراة لكل صيغة بنفس player_id، وكم منها متزامنة بالضبط."""
    ma, mb = set(), set()
    for t in ("lineup_players", "player_stats"):
        for r in conn.execute(
            f"SELECT DISTINCT match_id FROM {t} WHERE player_id=? AND player_en=?", (pid, name_a)
        ):
            ma.add(r[0])
        for r in conn.execute(
            f"SELECT DISTINCT match_id FROM {t} WHERE player_id=? AND player_en=?", (pid, name_b)
        ):
            mb.add(r[0])
    both = ma & mb
    smaller = min(len(ma), len(mb)) if ma and mb else 0
    rate = (len(both) / smaller * 100) if smaller else 0.0
    return len(ma), len(mb), len(both), rate


def find_candidates(conn, mode):
    """mode='strict': تفرّد player_id لطرفَي الزوج معاً ومطابقتهما.
    mode='relaxed': الهدف فريد إلزامياً، المصدر قد يحمل عدّة
    معرّفات بشرط أن يكون معرّف الهدف أحدها — يحتاج فحص تزامن
    match_id إلزامياً بكل الحالتين (لا استثناء)."""
    name_ids = build_name_ids(conn)
    translated = load_translated(conn)
    untranslated = load_untranslated(conn)
    pending136 = load_pending136()
    excluded = load_excluded()
    appearances = build_appearance_counts(conn)

    rejected_excluded = []
    rejected_pending = []
    rejected_initial = []
    rejected_no_unique_target = []
    rejected_component_count = []
    rejected_completeness = []
    rejected_no_source = []
    checked = []

    for name in untranslated:
        if name in excluded:
            rejected_excluded.append(name)
            continue
        if name in pending136:
            rejected_pending.append(name)
            continue
        if has_initial_token(name):
            rejected_initial.append(name)
            continue

        ids_name = name_ids.get(name, set())
        if len(ids_name) != 1:
            rejected_no_unique_target.append(name)
            continue
        pid = next(iter(ids_name))

        found_source = False
        for other, oids in name_ids.items():
            if other == name or other not in translated or other in excluded:
                continue
            if has_initial_token(other):
                continue

            if mode == "strict":
                if oids != {pid}:
                    continue
            else:  # relaxed
                if pid not in oids:
                    continue

            t_comp = components(name)
            s_comp = components(other)
            if len(t_comp) != len(s_comp):
                rejected_component_count.append((name, other))
                continue

            ar = translated[other]
            if len(ar.split()) != sum(ar_weight(c) for c in t_comp):
                rejected_completeness.append((name, other, ar))
                continue

            found_source = True
            na, nb, both, rate = match_id_cooccurrence(conn, pid, name, other)
            accepted = rate == 100.0 and min(na, nb) >= MIN_COOCCUR_MATCHES
            checked.append({
                "player_en": name,
                "player_id": pid,
                "other_name_translated": other,
                "other_total_ids": len(oids),
                "player_ar": ar,
                "similarity": round(sim(name, other), 2),
                "appearances": appearances.get(name, 0),
                "matches_a": na, "matches_b": nb, "matches_both": both,
                "cooccur_rate": round(rate, 1),
                "accepted": accepted,
            })
            break  # أول مصدر صالح بنيوياً يكفي لفحص التزامن عليه

        if not found_source:
            rejected_no_source.append(name)

    stats = {
        "untranslated_total": len(untranslated),
        "rejected_excluded": len(rejected_excluded),
        "rejected_pending136": len(rejected_pending),
        "rejected_initial": len(rejected_initial),
        "rejected_no_unique_target": len(rejected_no_unique_target),
        "rejected_component_count": len(rejected_component_count),
        "rejected_completeness": len(rejected_completeness),
        "rejected_no_source": len(rejected_no_source),
        "checked_total": len(checked),
    }
    return checked, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["strict", "relaxed"], default="relaxed",
                     help="strict: تفرّد player_id لطرفَي الزوج معاً. relaxed: الهدف فريد فقط (افتراضي)")
    ap.add_argument("--check", action="store_true", help="عرض فقط — لا كتابة أي ملف")
    ap.add_argument("--out", default=None, help="اسم ملف الدفعة الناتج (بدون --check)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    checked, stats = find_candidates(conn, args.mode)
    conn.close()

    accepted = [c for c in checked if c["accepted"]]
    rejected = [c for c in checked if not c["accepted"]]

    print("=" * 62)
    print(f"  الوضع: {args.mode}")
    print("=" * 62)
    print(f"  غير مترجَم إجمالاً (حيّ من الديتابيس)     : {stats['untranslated_total']}")
    print(f"  مستبعَد (translation_excluded.csv)         : {stats['rejected_excluded']}")
    print(f"  مؤجَّل (names_pending_id_review.csv)        : {stats['rejected_pending136']}")
    print(f"  مستبعَد (اختصار حرف واحد)                  : {stats['rejected_initial']}")
    print(f"  مستبعَد (الهدف غير فريد المعرّف)            : {stats['rejected_no_unique_target']}")
    print(f"  مستبعَد (فرق عدد مكوّنات الاسم)             : {stats['rejected_component_count']}")
    print(f"  مستبعَد (ترجمة ناقصة/زائدة طولاً)           : {stats['rejected_completeness']}")
    print(f"  صفر مصدر صالح بنيوياً                      : {stats['rejected_no_source']}")
    print("-" * 62)
    print(f"  فُحص بتزامن match_id                       : {stats['checked_total']}")
    print(f"  ✅ مقبول (تزامن 100% + عيّنة >= {MIN_COOCCUR_MATCHES} مباريات) : {len(accepted)}")
    print(f"  ⛔ مرفوض (تزامن ناقص أو عيّنة صغيرة)        : {len(rejected)}")
    print("=" * 62)

    accepted.sort(key=lambda c: -c["appearances"])
    print()
    print(f"القائمة المقبولة ({len(accepted)}):")
    for i, c in enumerate(accepted, 1):
        print(f"  {i}. {c['player_en']!r:28} id={c['player_id']:<8} <- {c['other_name_translated']!r:28} "
              f"= {c['player_ar']:<20} تزامن={c['matches_both']}/{min(c['matches_a'],c['matches_b'])} "
              f"({c['cooccur_rate']}%) ظهور={c['appearances']}")

    if not args.check:
        out_name = args.out or "next_translation_batch.csv"
        out_path = BASE_DIR / out_name
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["priority", "goals", "league", "team_ar", "player_en", "player_ar"])
            w.writeheader()
            for c in accepted:
                w.writerow({
                    "priority": "D", "goals": c["appearances"], "league": "", "team_ar": "",
                    "player_en": c["player_en"], "player_ar": c["player_ar"],
                })
        print()
        print(f"  كُتب: {out_path.name} ({len(accepted)} صفاً)")
        print("  ⚠️ راجعه يدوياً قبل إلحاقه بـplayers_ar.csv — هذا الملف لا يكتب")
        print("     على players_ar.csv أو football.db مطلقاً بأي وضع.")


if __name__ == "__main__":
    main()
