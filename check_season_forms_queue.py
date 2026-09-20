#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تصنيف طابور "الصيغ الجديدة" (بند 36/44) — أداة دائمة قراءة فقط
================================================================
يبني فوق مخرجات `check_season_new_forms.py` (استيراد مباشر لا نسخ)
ويصنّف كل صيغة جديدة لمعرّف `player_id` مؤسَّس بنفس معايير بند 27/44،
حتى لا يتكرر ما حدث بجلسة 20 سبتمبر 2026: تصنيف بند 44
(28 + 3 + 182) لم يُحفَظ كسكربت فلم يمكن إعادة إنتاجه.

⚠️ هذا فحص **اكتشاف** لا **حسم** — صفر كتابة على football.db، وصفر
   قرار تلقائي. الكتابة الفعلية (إن وُجدت) تمر حصراً عبر
   `players_ar.csv` مقيَّدة بـ`player_id` (بند 44).

التصنيف (لكل صيغة جديدة، أقرب صيغة قديمة مترابطة اسمياً)
---------------------------------------------------------
- `clear_abbr`    اختصار حرف واحد (`M. Ashraf` ↔ `Mohamed Ashraf`)
- `clear_longer`  اسم أطول أو معاد ترتيبه بلا اختصار
- `check`         تحتاج تحقق شخصي، لأي سبب مما يلي:
    · صيغتان غير مترابطتين اسمياً (ضجيج/تشوّه/لاعب آخر)
    · صفر دليل events/goals، أو تعادل تام بالدليل
    · خرق متبادل (كل من lineup_players وplayer_stats يحمل الصيغتين)

أعلام مساعدة (لا تغيّر الفئة):
- ⚠️تصادم(N): النص (إحدى الصيغتين) مشترك بين N من `player_id` —
  **يحتاج فحصاً إضافياً بـplayer_id قبل أي كتابة، لا كتابة نصية
  عامة** (مثال بند 44: `M. Ashraf` مشترك بين 6 معرّفات).
- [ببند 27]: المعرّف أصلاً بطابور `player_ar_conflict_queue.csv`.
- [مكتوبة ببند 44]: كُتبت فعلاً — لا تُكتب مرة أخرى.
- حالة العربي: بالصيغتين (متزامنة أصلاً) / بالقديمة فقط (كتابة
  محتملة) / بلا عربي (ترجمة عامة منفصلة، لا علاقة لها بتوحيد الصيغ).

⚠️ درس بند 44: "دليل قوي" لا يعني وجود شيء لكتابته — الأداة تكشف
   الصيغة بأول ظهور لا بحالة الترجمة، فالحالات المكتوبة سابقاً تظهر
   ثانية. راجع حالة العربي والأعلام قبل أي قرار.

الترتيب: بمجموع دليل events/goals (قديمة+جديدة) تنازلياً، وعند
التساوي بترتيب الاكتشاف (ثابت لنفس القاعدة).

التشغيل
-------
    python C:\\Users\\User\\Projects\\Football\\check_season_forms_queue.py --summary
    python C:\\Users\\User\\Projects\\Football\\check_season_forms_queue.py                 <- أعلى 50 واضحة
    python C:\\Users\\User\\Projects\\Football\\check_season_forms_queue.py --offset 50 --top 32   <- 51-82
    python C:\\Users\\User\\Projects\\Football\\check_season_forms_queue.py --category check      <- فئة التحقق الشخصي
    python C:\\Users\\User\\Projects\\Football\\check_season_forms_queue.py --year 2025 --json OUT.json
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime

from config import DB_FILE
from check_season_new_forms import (
    player_form_history, find_new_forms, load_existing_queue_ids)
from check_ar_conflict_queue import table_breach

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# حالات كُتبت فعلاً ببند 44 (19 سبتمبر 2026) عبر players_ar.csv مقيَّدة
# بـplayer_id — تظهر بمخرجات الأداة لأنها تكشف بأول ظهور لا بحالة الترجمة.
WRITTEN_ITEM_44 = {588694, 44548, 588680, 615979}

REL_RANK = {"abbr": 0, "reordered": 1, "longer": 1, "unrelated": 2}
REL_LABEL = {"abbr": "اختصار", "longer": "أطول", "reordered": "إعادة ترتيب",
             "unrelated": "غير مترابطتين"}


def _toks(s):
    return [t for t in re.sub(r"[.\-]", " ", s.lower()).split() if t]


def relation(a, b):
    """abbr: إحداهما اختصار حرف واحد للأخرى | reordered: نفس الكلمات
    بترتيب مختلف | longer: كلمات إحداهما ⊂ الأخرى | unrelated: غير ذلك."""
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return "unrelated"
    for x, y in ((ta, tb), (tb, ta)):
        if (len(x[0]) == 1 and len(y[0]) > 1 and y[0].startswith(x[0])
                and x[1:] and set(x[1:]) <= set(y[1:])):
            return "abbr"
    if sorted(ta) == sorted(tb):
        return "reordered"
    if set(ta) < set(tb) or set(tb) < set(ta):
        return "longer"
    return "unrelated"


def pids_carrying(conn, form):
    """عدد player_id المميَّزة التي تحمل هذا النص بالضبط (تصادم نصي)."""
    return conn.execute("""SELECT COUNT(DISTINCT player_id) FROM (
        SELECT player_id FROM lineup_players WHERE player_en=? AND player_id!=0
        UNION SELECT player_id FROM player_stats WHERE player_en=? AND player_id!=0)""",
        (form, form)).fetchone()[0]


def arabic_of(conn, form, pid):
    """الترجمة العربية الأكثر تكراراً لهذه الصيغة بهذا player_id (أو None)."""
    r = conn.execute("""SELECT player_ar FROM (
        SELECT player_ar FROM lineup_players WHERE player_id=? AND player_en=?
        UNION ALL SELECT player_ar FROM player_stats WHERE player_id=? AND player_en=?)
        WHERE player_ar IS NOT NULL AND player_ar!='' GROUP BY player_ar
        ORDER BY COUNT(*) DESC LIMIT 1""", (pid, form, pid, form)).fetchone()
    return r[0] if r else None


def classify(conn, candidates):
    out = []
    for c in candidates:
        pid, new = c["player_id"], c["new_form"]
        rel, old = sorted(
            ((relation(o["form"], new), o) for o in c["old_forms"]),
            key=lambda x: REL_RANK[x[0]])[0]
        ev_old, ev_new = old["evidence"], c["evidence_new"]
        tie = ev_old == ev_new
        mutual = (table_breach(conn, "lineup_players", pid, old["form"], new)
                  and table_breach(conn, "player_stats", pid, old["form"], new))

        reasons = []
        if rel == "unrelated":
            reasons.append("صيغتان غير مترابطتين اسمياً (ضجيج/تشوّه/لاعب آخر)")
        if ev_old + ev_new == 0:
            reasons.append("صفر دليل")
        elif tie:
            reasons.append("تعادل تام بالدليل")
        if mutual:
            reasons.append("خرق متبادل")

        if reasons:
            cat = "check"
        else:
            cat = "clear_abbr" if rel == "abbr" else "clear_longer"

        coll_n = max(pids_carrying(conn, new), pids_carrying(conn, old["form"]))
        out.append(dict(
            pid=pid, old=old["form"], new=new, rel=rel,
            ev_old=ev_old, ev_new=ev_new, n_old=old["n"], n_new=c["new_n"],
            new_first=c["new_first"], gap=c["gap_days"],
            n_old_forms=c["n_old_forms_total"], mutual=mutual, tie=tie,
            cat=cat, reasons=reasons, collision=coll_n > 1, coll_n=coll_n,
            ar_old=arabic_of(conn, old["form"], pid),
            ar_new=arabic_of(conn, new, pid),
            in_queue=c["already_in_queue"], written_44=pid in WRITTEN_ITEM_44))
    return out


def ar_status(o):
    if o["ar_old"] and o["ar_new"]:
        return "عربي بالصيغتين"
    if o["ar_old"]:
        return "عربي بالقديمة فقط"
    if o["ar_new"]:
        return "عربي بالجديدة فقط"
    return "بلا عربي"


def format_line(i, o):
    line = (f"{i}. id={o['pid']}: {o['old']!r} ← {o['new']!r} | "
            f"{REL_LABEL[o['rel']]} | دليل {o['ev_old']}/{o['ev_new']} | {ar_status(o)}")
    if o["collision"]:
        line += f" ⚠️تصادم({o['coll_n']} معرّفات)"
    if o["in_queue"]:
        line += " [ببند 27]"
    if o["written_44"]:
        line += " [مكتوبة ببند 44 — لا تُكتب مرة أخرى]"
    if o["cat"] == "check":
        line += " | " + " + ".join(o["reasons"])
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now().year)
    ap.add_argument("--start", default="08-15", help="بداية النافذة MM-DD")
    ap.add_argument("--end", default="09-15", help="نهاية النافذة MM-DD")
    ap.add_argument("--category", choices=("clear", "check", "all"), default="clear",
                    help="الفئة المعروضة (افتراضي: clear = الواضحة)")
    ap.add_argument("--top", type=int, default=50, help="عدد الأسطر المعروضة")
    ap.add_argument("--offset", type=int, default=0, help="تخطّي أول N (للصفحات)")
    ap.add_argument("--summary", action="store_true", help="الأعداد فقط بلا أسطر")
    ap.add_argument("--json", default=None, help="مسار JSON اختياري لكل الحالات المصنَّفة")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)  # قراءة فقط
    history = player_form_history(conn)
    cands = find_new_forms(conn, history, f"{args.year}-{args.start}",
                           f"{args.year}-{args.end}", load_existing_queue_ids())
    rows = classify(conn, cands)

    cats = Counter(o["cat"] for o in rows)
    clear = [o for o in rows if o["cat"] != "check"]
    print(f"سنة {args.year} ({args.start}..{args.end}): {len(rows)} صيغة جديدة — "
          f"واضحة {len(clear)} (اختصار {cats['clear_abbr']} + أطول/ترتيب "
          f"{cats['clear_longer']}) | تحقق شخصي {cats['check']}")
    if clear:
        st = Counter(ar_status(o) for o in clear)
        print("  الواضحة حسب العربي: " + " | ".join(f"{k} {v}" for k, v in st.most_common()))
        print(f"  الواضحة بتصادم: {sum(o['collision'] for o in clear)} | "
              f"مكتوبة ببند 44: {sum(o['written_44'] for o in clear)}")
    if cats["check"]:
        rs = Counter(r for o in rows if o["cat"] == "check" for r in o["reasons"])
        print("  أسباب التحقق الشخصي (متداخلة): " + " | ".join(f"{k} {v}" for k, v in rs.most_common()))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
        print(f"كُتب: {args.json} ({len(rows)} حالة)")

    if args.summary:
        return
    pick = {"clear": clear, "check": [o for o in rows if o["cat"] == "check"],
            "all": rows}[args.category]
    pick = sorted(pick, key=lambda o: -(o["ev_old"] + o["ev_new"]))  # مستقر
    print()
    for i, o in enumerate(pick[args.offset:args.offset + args.top], args.offset + 1):
        print(format_line(i, o))


if __name__ == "__main__":
    main()
