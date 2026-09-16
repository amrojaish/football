#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص تضارب صيغ أسماء المدربين — lineups.coach_en (بند المدربين)
=================================================================
سكربت دائم قراءة فقط، بنفس فلسفة `check_ar_conflict_queue.py`
(بند 27) لكن معدَّل بنيوياً — راجع الفروق أدناه.

الأصل (فتح 1 ببند 35، 13 سبتمبر): فحص `lineups.coach_en` كشف نفس
نمط "الخرق المتبادل" الموثَّق للاعبين — صيغتا اسم مختلفتان لنفس
المدرب الحقيقي (نقطتا/تنسيقا كتابة مختلفان من نفس المزوّد).

⚠️ **فروق بنيوية عن check_ar_conflict_queue.py (بند 27):**
1. **لا `coach_id`** — `lineups` تحمل نصّاً حرّاً فقط (`coach_en`)
   بلا معرّف ثابت. بديل الهوية هنا: `team_id` + تشابه نصّي (تطابق
   تام بعد إزالة التشكيل، أو اختصار حرف واحد، أو اختصار اسم⊆اسم
   كامل — كل رمز بالاسم الأقصر له مطابق بالأطول).
2. **لا جدول ثانٍ مستقل** يحمل اسم المدرب لنفس المباراة (خلافاً
   لـ`lineup_players`+`player_stats` للاعبين) — لذا "تزامن
   match_id" بتعريف بند 27 الحرفي (X/Y عبر جدولين) **غير قابل
   للحساب هنا**. البديل: عدد "الانتقالات" بين الصيغتين عبر تسلسل
   مباريات نفس النادي مرتّبة بالتاريخ (داخل نفس الجدول). تداخل
   حقيقي (≥2 انتقال) = خلل تهجئة لنفس الشخص لا تغيير مدرب حقيقي؛
   قطع زمني نظيف = غامض (إما تغيير حقيقي أو مجرد تنسيق مصدر مختلف).
3. **التجميع بالتكتلات لا الأزواج**: نادٍ واحد قد يملك أكثر من
   صيغتين لنفس المدرب (مثال: Pyramids FC — 3 صيغ لـKrunoslav
   Jurčić) — تُجمَّع بخوارزمية Union-Find لا تُعرَض كأزواج منفصلة.
4. **الكتابة تُقيَّد بـ"المكوّن القوي" داخل التكتل**: عضو انضمّ
   للتكتل بحافة ضعيفة فقط (اختصار حرف واحد) لا يُدرَج بقائمة
   الكتابة حتى لو التكتل ككل صُنِّف (أ)/(أ*) — لأن بقية التكتل
   مرتبطة بدليل قوي لا يشمله هو تحديداً (اكتُشفت 16 سبتمبر: 3
   حالات — K. Jurčić/Pyramids، D. Buckingham/Al Kholood،
   V. Ivić/Al Ain — استُبعدوا من أول دفعة كتابة لنفس السبب).

التصنيف:
    (أ)  واضحة وآمنة — كل الأدلة القوية بالتكتل (بلا اختصار حرف
         واحد ولا رمز نصي وحيد) إما فرق ديكريتكس بحت، أو تداخل
         تواريخ حقيقي (≥2 انتقال).
    (أ*) نفس معايير (أ) لكن أقل الصيغتين ظهرت بعيّنة <3 مباريات —
         نفس حدّ MIN_SAMPLE ببند 27 (عيّنة صغيرة تحتاج حذراً إضافياً
         لا رفضاً تلقائياً).
    (ب) تحتاج تحقق المستخدم — اختصار حرف واحد، أو رمز نصي وحيد
        (اسم بلا لقب مقابل اسم كامل)، أو قطع زمني نظيف بلا فرق
        ديكريتكس (لا دليل بنيوي كافٍ لتمييز "تغيير مدرب" عن "خلل
        تهجئة").

⚠️ كل هذه المعايير مؤهِّلة لا حاسمة — قائمة (أ)/(أ*) تعني "تستاهل
   كتابة مباشرة بثقة عالية"، لا "صحيحة 100% بلا مراجعة". صفر كتابة
   تلقائية من هذا السكربت نفسه بأي حال.

⚠️ **تحذير ضجيج معروف**: بعض أزواج (ب) تعتمد فقط على تطابق أول
   حرف + اختصار بادئة قصيرة (مثال: `M. Benchrifa`/`B. El Moubarki`
   — لقبان مختلفان تماماً بالفعل، تطابقا آلياً بالصدفة). هذه على
   الأرجح **أشخاص مختلفون حقيقيون** لا خطأ تهجئة — يُنصَح باستبعادها
   بسرعة عند المراجعة اليدوية بلا تحقيق معمّق.

التشغيل:
    python check_coach_conflict_queue.py             <- كل التكتلات بالتفصيل
    python check_coach_conflict_queue.py --write-csv coach_merges_candidates.csv
        <- يكتب أيضاً ملف CSV بصفوف الكتابة المرشَّحة (أ/أ* فقط،
           بعد استبعاد الحواف الضعيفة) — مراجعة بشرية قبل أي استخدام
           فعلي بـapply_coach_merges.py، لا اعتماد آلي.

قراءة فقط دائماً — صفر كتابة على football.db.
"""
import argparse
import csv as csv_module
import sqlite3
import sys
import unicodedata
from config import DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_SAMPLE = 3  # نفس حدّ بند 27 (check_ar_conflict_queue.py)


def strip_diacritics(s):
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm(s):
    return " ".join(strip_diacritics(s).lower().split())


def tokens(s):
    return set(norm(s).split())


def has_diacritics(s):
    return any(unicodedata.combining(c) for c in unicodedata.normalize("NFKD", s))


def token_match(t1, t2):
    if t1 == t2:
        return True
    if len(t1) == 2 and t1.endswith(".") and t2.startswith(t1[0]):
        return True
    if len(t2) == 2 and t2.endswith(".") and t1.startswith(t2[0]):
        return True
    if len(t1) >= 3 and len(t2) >= 3 and (t1.startswith(t2) or t2.startswith(t1)):
        return True
    return False


def full_token_match(shorter, longer):
    """كل رمز بالقائمة الأقصر له مطابق بالأطول (تطابق تام/اختصار
    بحرف واحد/اختصار اسم). يرجّع (تطابق_كامل، فيه_اختصار_حرف_واحد)."""
    used = set()
    has_initial_match = False
    for t in shorter:
        matched = False
        for u in longer:
            if u in used:
                continue
            if t == u:
                matched = True
                used.add(u)
                break
        if not matched:
            for u in longer:
                if u in used:
                    continue
                if token_match(t, u):
                    matched = True
                    used.add(u)
                    if (len(t) == 2 and t.endswith(".")) or (len(u) == 2 and u.endswith(".")):
                        has_initial_match = True
                    break
        if not matched:
            return False, False
    return True, has_initial_match


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0, False, False, False, ta, tb
    inter = ta & tb
    union = ta | tb
    jacc = len(inter) / len(union)
    pure_diacritic = norm(a) == norm(b)
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    full_match, initial_only = full_token_match(shorter, longer)
    return jacc, pure_diacritic, full_match, initial_only, ta, tb


class DSU:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_clusters(conn):
    rows = conn.execute("""
        SELECT l.team_id, l.coach_en, m.date, l.match_id, t.name_ar, t.name_en
        FROM lineups l
        JOIN matches m ON m.match_id = l.match_id
        JOIN teams t ON t.team_id = l.team_id
        WHERE l.coach_en IS NOT NULL AND TRIM(l.coach_en) != ''
    """).fetchall()

    by_team = {}
    for team_id, coach, date, match_id, name_ar, name_en in rows:
        d = date.split(" ")[0]
        info = by_team.setdefault(team_id, {"name_ar": name_ar, "name_en": name_en, "matches": []})
        info["matches"].append((d, match_id, coach))

    clusters = []
    for team_id, info in by_team.items():
        forms = {}
        for d, mid, coach in info["matches"]:
            forms.setdefault(coach, []).append((d, mid))
        distinct = list(forms.keys())
        if len(distinct) < 2:
            continue

        dsu = DSU()
        edges = {}
        for i in range(len(distinct)):
            for j in range(i + 1, len(distinct)):
                a, b = distinct[i], distinct[j]
                jacc, pure_diacritic, full_match, initial_only, ta, tb = similarity(a, b)
                if not full_match:
                    continue
                matches_a = sorted(forms[a])
                matches_b = sorted(forms[b])
                all_dated = sorted([(d, "A", mid) for d, mid in matches_a] +
                                    [(d, "B", mid) for d, mid in matches_b])
                switches = sum(1 for k in range(1, len(all_dated))
                               if all_dated[k][1] != all_dated[k - 1][1])
                first_a, last_a = matches_a[0][0], matches_a[-1][0]
                first_b, last_b = matches_b[0][0], matches_b[-1][0]
                overlap = max(first_a, first_b) <= min(last_a, last_b)
                single_token_side = (len(ta) == 1 and len(tb) > 1) or (len(tb) == 1 and len(ta) > 1)
                edges[(a, b)] = dict(
                    jacc=round(jacc, 2), pure_diacritic=pure_diacritic,
                    switches=switches, overlap=overlap, initial_only=initial_only,
                    single_token_side=single_token_side,
                )
                dsu.union(a, b)

        if not edges:
            continue

        groups = {}
        for f in distinct:
            groups.setdefault(dsu.find(f), []).append(f)
        for root, members in groups.items():
            if len(members) < 2:
                continue
            member_edges = {k: v for k, v in edges.items() if k[0] in members and k[1] in members}
            clusters.append(dict(
                team_id=team_id, name_ar=info["name_ar"], name_en=info["name_en"],
                members=members, forms=forms, edges=member_edges,
            ))
    return clusters


def classify(cluster):
    edges = cluster["edges"].values()
    if all((e["initial_only"] or e["single_token_side"]) for e in edges):
        return "ب"
    strong = [e for e in edges if not e["initial_only"] and not e["single_token_side"]]
    if all((e["overlap"] and e["switches"] >= 2) or (e["pure_diacritic"] and not e["overlap"])
           for e in strong):
        return "أ"
    return "ب"


def member_sort_key(cluster, m):
    return (len(norm(m)), has_diacritics(m))


def strong_component(cluster, start):
    """أعضاء التكتل المتّصلون بـ`start` عبر حواف قوية فقط (بلا
    اختصار حرف واحد/رمز وحيد) — هذه فقط تُعتبَر جاهزة للكتابة."""
    strong_edges = {k for k, e in cluster["edges"].items()
                     if not e["initial_only"] and not e["single_token_side"]}
    adj = {}
    for a, b in strong_edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen = {start}
    stack = [start]
    while stack:
        x = stack.pop()
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-csv", default=None,
                     help="يكتب صفوف الكتابة المرشَّحة (أ/أ* بعد استبعاد الحواف الضعيفة) "
                          "لملف CSV — مراجعة بشرية قبل أي استخدام، لا اعتماد آلي")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
    clusters = build_clusters(conn)

    print(f"إجمالي التكتلات (كل تكتل = صيغ يُرجَّح أنها لنفس المدرب): {len(clusters)}")
    print(f"عدد الأندية (team_id) المتأثرة: {len(set(c['team_id'] for c in clusters))}\n")

    def sort_key(cluster):
        return -max(len(cluster["forms"][m]) for m in cluster["members"])

    n_a = n_b = n_a_small = 0
    write_rows = []
    deferred_rows = []

    for i, c in enumerate(sorted(clusters, key=sort_key), 1):
        members_sorted = sorted(c["members"], key=lambda m: member_sort_key(c, m))
        short_form = members_sorted[0]
        full_form = members_sorted[-1]
        cls = classify(c)
        min_n = min(len(c["forms"][m]) for m in c["members"])
        if cls == "أ" and min_n < MIN_SAMPLE:
            cls = "أ*"
            n_a_small += 1
        elif cls == "أ":
            n_a += 1
        else:
            n_b += 1

        print(f"[{i}] team_id={c['team_id']} | مختصر: {short_form!r} | كامل: {full_form!r} "
              f"| النادي: {c['name_en']} / {c['name_ar']}  — تصنيف ({cls})")
        for m in members_sorted:
            dates = sorted(c["forms"][m])
            print(f"      - {m!r}  (n={len(dates)}, {dates[0][0]}..{dates[-1][0]})")
        ev_notes = []
        for (a, b), e in c["edges"].items():
            note = []
            if e["pure_diacritic"]:
                note.append("ديكريتكس فقط")
            if e["initial_only"]:
                note.append("⚠️اختصار حرف واحد")
            if e["single_token_side"]:
                note.append("⚠️رمز وحيد")
            if e["overlap"]:
                note.append(f"تداخل+{e['switches']}انتقال")
            else:
                note.append("قطع نظيف")
            ev_notes.append(f"({a[:20]}../{b[:20]}..: {','.join(note)})")
        print(f"      أدلة: {' '.join(ev_notes)}")

        if cls in ("أ", "أ*"):
            comp = strong_component(c, full_form)
            weak_riders = [m for m in c["members"] if m not in comp]
            for m in comp:
                if m == full_form:
                    continue
                write_rows.append((c["team_id"], m, full_form, c["name_en"]))
            for m in weak_riders:
                deferred_rows.append((c["team_id"], m, full_form, c["name_en"]))
                print(f"      ⚠️ مؤجَّل من الكتابة رغم تصنيف التكتل: {m!r} "
                      f"(متّصل بـ{full_form!r} بحافة ضعيفة فقط)")
        print()

    print(f"الإجمالي: {len(clusters)} حالة — (أ) واضحة وآمنة: {n_a} | "
          f"(أ*) واضحة لكن عيّنة صغيرة (<{MIN_SAMPLE}): {n_a_small} | "
          f"(ب) تحتاج تحقق المستخدم: {n_b}")

    print(f"\n{'=' * 62}\nصفوف مرشَّحة للكتابة (بعد استبعاد الحواف الضعيفة): {len(write_rows)}\n{'=' * 62}")
    for team_id, old, keep, club in write_rows:
        print(f"  team_id={team_id} ({club}): {old!r} → {keep!r}")

    if deferred_rows:
        print(f"\n{'=' * 62}\nأعضاء داخل تكتلات (أ)/(أ*) لكن مؤجَّلون (حافة ضعيفة فقط): "
              f"{len(deferred_rows)}\n{'=' * 62}")
        for team_id, old, keep, club in deferred_rows:
            print(f"  team_id={team_id} ({club}): {old!r} ~ {keep!r}")

    if args.write_csv:
        with open(args.write_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv_module.writer(f)
            w.writerow(["team_id", "old_name", "keep_name", "confidence", "note"])
            for team_id, old, keep, club in write_rows:
                w.writerow([team_id, old, keep, "مؤكد", f"{club} — بند المدربين"])
        print(f"\nكُتب: {args.write_csv} — مراجعة بشرية قبل أي استخدام بـapply_coach_merges.py")


if __name__ == "__main__":
    main()
