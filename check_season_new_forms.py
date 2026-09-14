#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص صيغ الأسماء الجديدة عند بداية الموسم — بند 35
=====================================================
سكربت دائم يبني على توصية بند 35 (موثَّقة بالـREADME، 13 سبتمبر
2026): "نمط سنوي" مؤكَّد إحصائياً — صيغ اسم جديدة لمعرّفات
`player_id` **مؤسَّسة** (لها تاريخ سابق) تتكاثر بنافذة منتصف
أغسطس-منتصف سبتمبر من كل سنة (245/164/396/340 لسنوات
2023-2026)، بسبب تزامن بدايات معظم الدوريات بنفس الفترة.

⚠️ هذا فحص **اكتشاف** لا **حسم** — يخرج قائمة "يستاهل مراجعة
   بشرية فردية"، تماماً مثل فلسفة كل أدوات بند 27 السابقة
   (`check_ar_conflict_queue.py`). صفر قرار تلقائي، صفر كتابة.

اللاعبون فقط بهذه النسخة (بطلب صريح) — **المدربون مؤجَّلون**
(يحتاجون فحصاً مستقلاً على `lineups.coach_en`، لم يُبدَأ — راجع
"فتح 1" ببند 35).

المنهجية
--------
1. **الهوية والتواريخ**: `player_id`↔`player_en`↔تاريخ يُستخرَج
   حصراً من `lineup_players`+`player_stats` (UNION) — لا مصدر
   آخر يحمل `player_id` إطلاقاً (`events`/`goals` نصّ حرّ بلا
   `player_id`). هذا **لا يخالف** توجيه "تجاهل lineup_players/
   player_stats" — ذاك التوجيه يخص استخدامهما **كدليل واقعية**
   (عدّ ظهور، تقاطع بين الجدولين) لأن كل جدول نقطة API مستقلة
   ثابتة الصيغة لحظة السحب (نفس المشكلة الموثَّقة بمحاولة 1 من
   `check_ar_conflict_queue.py`: تقاطعهما يعطي ~100% كاذبة بلا
   علاقة بالحقيقة). هنا يُستخدَمان فقط لموضع "متى ظهرت هذه
   الصيغة أول مرة لهذا المعرّف" — لا بديل عنهما لهذا الغرض،
   وصفر منطق تقاطع/خرق متبادل بينهما بهذا السكربت.

2. **صيغة "جديدة"** لمعرّف `player_id`: أول ظهور لها (`MIN(date)`)
   يقع داخل نافذة الفحص **و** نفس المعرّف له صيغة مختلفة ظهرت
   **قبل** بداية النافذة (= "معرّف مؤسَّس"، لا لاعب يظهر لأول مرة
   بالقاعدة هذا الموسم أصلاً).

3. **دليل السلوك الحقيقي**: يُستعاد **حرفياً** من
   `check_ar_conflict_queue.py` (استيراد مباشر لا نسخ) —
   `behavioral_evidence()` يعدّ صفوف `events`+`goals` بمطابقة
   نصية تامة على `player_en`. هذا هو "نفس منطق الخرق المتبادل"
   المطلوب الاعتماد عليه: دليل استخدام فعلي بالتعليق الحي على
   المباريات، لا مجرد سطر واحد بجدول تشكيلة.
   ⚠️ نفس تحذير الأصل: مطابقة نصية عامة بلا قيد `player_id`، قد
   تحمل ضجيجاً من لاعب آخر بنفس النص بالصدفة — للمراجعة اليدوية.

4. **صفر حسم**: لا "أرجح صيغة"، لا استبعاد تلقائي. القائمة كاملة
   لمراجعة بشرية، مع أعلام مساعدة فقط (دليل=0 يعني صيغة قد تكون
   ضجيجاً/خطأ عابر لا نمطاً حقيقياً — يحتاج فحصاً أدق قبل التجاهل).

القراءة فقط دائماً — صفر كتابة على football.db. `--csv` يكتب
ملف مخرجات فقط (لا يلمس القاعدة).

التشغيل
-------
    python check_season_new_forms.py                        <- السنة الحالية، نافذة 08-15..09-15
    python check_season_new_forms.py --year 2025             <- سنة محددة
    python check_season_new_forms.py --year 2023 2024 2025 2026  <- عدة سنوات دفعة وحدة (إعادة إنتاج أرقام بند 35)
    python check_season_new_forms.py --start 08-01 --end 09-15   <- نافذة مخصَّصة
    python check_season_new_forms.py --csv OUT.csv           <- يكتب أيضاً ملف CSV للمراجعة
    python check_season_new_forms.py --summary               <- عدد الحالات فقط لكل سنة، بلا تفصيل
"""

import argparse
import csv as csv_module
import sqlite3
import sys
from datetime import datetime

from config import DB_FILE, BASE_DIR
from check_ar_conflict_queue import behavioral_evidence

QUEUE_FILE = BASE_DIR / "player_ar_conflict_queue.csv"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_existing_queue_ids():
    """player_id الموجودة أصلاً بطابور بند 27 — لتمييز الحالات
    المعروفة سلفاً عن الحالات الجديدة فعلاً بمخرجات هذا السكربت."""
    if not QUEUE_FILE.exists():
        return set()
    with open(QUEUE_FILE, encoding="utf-8-sig") as f:
        return {int(r["player_id"]) for r in csv_module.DictReader(f)}


def player_form_history(conn):
    """لكل player_id: كل الصيغ (player_en) المميَّزة مع أول/آخر
    ظهور وعدد المباريات — من lineup_players+player_stats فقط
    (المصدر الوحيد الذي يربط player_id بتاريخ فعلي). راجع تحذير
    رأس الملف: يُستخدَم هنا للموضع الزمني فقط، لا كدليل واقعية."""
    rows = conn.execute("""
        SELECT t.player_id, t.player_en, m.date
        FROM (
            SELECT match_id, player_id, player_en FROM lineup_players
            UNION ALL
            SELECT match_id, player_id, player_en FROM player_stats
        ) t
        JOIN matches m ON m.match_id = t.match_id
        WHERE t.player_id IS NOT NULL AND t.player_en IS NOT NULL
          -- ⚠️ player_id=0 قيمة حارسة لـ"لاعب غير مطابَق" بـplayer_stats
          -- (174 صف/148 صيغة مختلفة، اكتُشفت 14 سبتمبر 2026 أثناء أول
          -- تشغيل فعلي لهذا السكربت) — ليست معرّفاً حقيقياً واحداً،
          -- استبعادها إلزامي وإلا تلوّث النتائج بضجيج ضخم كاذب.
          AND t.player_id != 0
    """).fetchall()

    history = {}  # player_id -> {form: {"first": d, "last": d, "n": count}}
    for pid, form, date in rows:
        d = date.split(" ")[0]
        by_form = history.setdefault(pid, {})
        info = by_form.setdefault(form, {"first": d, "last": d, "n": 0})
        info["n"] += 1
        if d < info["first"]:
            info["first"] = d
        if d > info["last"]:
            info["last"] = d
    return history


def find_new_forms(conn, history, window_start, window_end, existing_queue_ids):
    """يفحص كل player_id: صيغ ظهرت أول مرة داخل النافذة، بشرط
    وجود صيغة مختلفة سابقة (معرّف مؤسَّس). يرجّع قائمة مرشَّحين."""
    candidates = []

    for pid, by_form in history.items():
        pre_window = {f: i for f, i in by_form.items() if i["first"] < window_start}
        in_window = {f: i for f, i in by_form.items()
                     if window_start <= i["first"] <= window_end}

        if not pre_window or not in_window:
            continue

        # ⚠️ كل الصيغ السابقة تُعرَض — لا اختصار لصيغة واحدة "الأفضل".
        # حالات فعلية بثلاث صيغ قديمة أو أكثر لنفس player_id موجودة
        # (مثال: 28339) — القرار البشري يحتاج الصورة الكاملة.
        old_forms = sorted(
            (
                dict(form=f, first=i["first"], last=i["last"], n=i["n"],
                     evidence=behavioral_evidence(conn, f))
                for f, i in pre_window.items()
            ),
            key=lambda o: o["first"],
        )
        old_last_overall = max(o["last"] for o in old_forms)

        for new_form, new_info in in_window.items():
            evidence_new = behavioral_evidence(conn, new_form)
            gap_days = (
                datetime.strptime(window_start, "%Y-%m-%d")
                - datetime.strptime(old_last_overall, "%Y-%m-%d")
            ).days

            candidates.append(dict(
                player_id=pid,
                old_forms=old_forms,
                new_form=new_form, new_first=new_info["first"],
                new_n=new_info["n"], evidence_new=evidence_new,
                gap_days=gap_days,
                n_old_forms_total=len(old_forms),
                already_in_queue=pid in existing_queue_ids,
                has_evidence=(evidence_new > 0
                              or any(o["evidence"] > 0 for o in old_forms)),
            ))

    return candidates


def run_for_year(conn, history, year, start_md, end_md, existing_queue_ids):
    window_start = f"{year}-{start_md}"
    window_end = f"{year}-{end_md}"
    return window_start, window_end, find_new_forms(
        conn, history, window_start, window_end, existing_queue_ids)


def format_old_forms(old_forms):
    return " | ".join(
        f"{o['form']!r} ({o['first']}..{o['last']}, n={o['n']}, دليل={o['evidence']})"
        for o in old_forms
    )


def print_candidates(candidates, year):
    print(f"\n{'=' * 70}")
    print(f"سنة {year} — {len(candidates)} صيغة جديدة لمعرّفات مؤسَّسة")
    print(f"{'=' * 70}")

    def total_evidence(c):
        return c["evidence_new"] + sum(o["evidence"] for o in c["old_forms"])

    for c in sorted(candidates, key=lambda x: -total_evidence(x)):
        flag = "" if c["has_evidence"] else "  ⚠️ صفر دليل events/goals لأي صيغة"
        queue_flag = "  [بطابور بند 27 أصلاً]" if c["already_in_queue"] else ""
        multi_flag = f"  [{c['n_old_forms_total']} صيغ قديمة]" if c["n_old_forms_total"] > 1 else ""
        print(
            f"  id={c['player_id']}: صيغ قديمة: {format_old_forms(c['old_forms'])}\n"
            f"      -> جديدة: {c['new_form']!r} (من {c['new_first']}, "
            f"دليل={c['evidence_new']}, n_مباريات={c['new_n']}, فجوة={c['gap_days']}يوم)"
            f"{flag}{queue_flag}{multi_flag}"
        )


def write_csv(path, all_candidates):
    fields = ["year", "player_id", "old_forms", "n_old_forms_total",
              "new_form", "new_first", "new_n", "evidence_new",
              "gap_days", "already_in_queue", "has_evidence"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv_module.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for year, rows in all_candidates:
            for r in rows:
                row = {k: v for k, v in r.items() if k != "old_forms"}
                row["old_forms"] = format_old_forms(r["old_forms"])
                w.writerow({"year": year, **row})
    print(f"\nكُتب: {path} ({sum(len(r) for _, r in all_candidates)} صف)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, nargs="+", default=[datetime.now().year],
                     help="سنة أو عدة سنوات (افتراضي: السنة الحالية)")
    ap.add_argument("--start", default="08-15", help="بداية النافذة MM-DD (افتراضي 08-15)")
    ap.add_argument("--end", default="09-15", help="نهاية النافذة MM-DD (افتراضي 09-15)")
    ap.add_argument("--csv", default=None, help="مسار ملف CSV اختياري للمخرجات")
    ap.add_argument("--summary", action="store_true", help="عدد الحالات فقط، بلا تفصيل")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)  # قراءة فقط على مستوى الاتصال
    existing_queue_ids = load_existing_queue_ids()
    history = player_form_history(conn)

    all_candidates = []
    for year in args.year:
        window_start, window_end, candidates = run_for_year(
            conn, history, year, args.start, args.end, existing_queue_ids)
        all_candidates.append((year, candidates))
        if args.summary:
            print(f"{year} ({window_start}..{window_end}): {len(candidates)} صيغة جديدة "
                  f"({sum(1 for c in candidates if c['has_evidence'])} بدليل events/goals، "
                  f"{sum(1 for c in candidates if c['already_in_queue'])} بطابور بند 27 أصلاً)")
        else:
            print_candidates(candidates, year)

    if args.csv:
        write_csv(args.csv, all_candidates)


if __name__ == "__main__":
    main()
