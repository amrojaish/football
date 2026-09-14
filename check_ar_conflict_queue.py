#!/usr/bin/env python3
"""
فحص طابور بند 27 — player_ar_conflict_queue.csv
===================================================
يفحص كل صف بالطابور (نفس `player_id`، صيغتا اسم إنجليزي مختلفتان
لنفس اللاعب) ويحدّد هل تراكم دليل كافٍ لحسم أيّ صيغة الأرجح
لتحديد الترجمة العربية الصحيحة.

⚠️ **السكربت الأصلي لهذا الفحص لم يُحفَظ بالمستودع قط بالدفعات
   السابقة (بند 27) — أداة مؤقتة فُقدت. هذا الملف يحلّ تلك
   المشكلة نهائياً**، بعد إعادة بناء المعايير الأربعة من الصفر
   (13 سبتمبر) بمحاولتين فاشلتين موثَّقتين أدناه قبل الوصول
   لتعريف يطابق مثالاً تاريخياً حقيقياً بدقة تكاد تكون تامة.

المعايير الأربعة (كما استُخدمت ببند 27 دفعة سادسة، 10 سبتمبر):

1. **تزامن match_id >= 90%** — ⚠️ **محاولتان فاشلتان قبل الوصول
   للتعريف الصحيح**:
   - المحاولة الأولى: تقاطع كل مباريات `lineup_players`×
     `player_stats` لكامل تاريخ اللاعب. **فاشلة**: كل جدول يحمل
     صيغة واحدة حصراً بحكم مصدره (نقطتا API)، فالنتيجة ~100%
     بمجرد البناء لأي زوج تقريباً (39 من 42 حالة فحصتها أعطت
     تطابقاً تاماً) — لا علاقة بكون الصيغتين لنفس الشخص أم لا.
   - **التعريف الصحيح** (تحقَّق بمطابقة تامة تقريباً مع مثال
     تاريخي موثَّق بالـREADME: `id=369413` أعطى 7/9=77.8%،
     مطابق لما وثَّقته الدفعة السادسة حرفياً): يُحصر الفحص
     بـ**نافذة التداخل الزمني** بين `period_a`/`period_b` (تقاطع
     الفترتين، عادةً فترة الصيغة الأقل شيوعاً كاملة). **Y** = عدد
     المباريات المنفصلة (`lineup_players`+`player_stats`،
     مقيَّدة بـ`player_id`) الواقعة بهذه النافذة. **X** = منها كم
     مباراة تُظهر **الصيغتين معاً** (بجدول مختلف لكل صيغة، لنفس
     `match_id`) — دليل مباشر أن نفس المباراة الحقيقية سُجِّلت
     بصيغتين، لا مجرد صدفة توقيت. النسبة = X/Y.
2. **دليل سلوكي حقيقي**: `events`+`goals` > 0 لطرف واحد على
   الأقل (مطابقة نصية على `player_en` — نفس منهجية كل الدفعات
   السابقة؛ ⚠️ تقاطع نصي عام بلا قيد `player_id`، قد يحمل ضجيجاً
   من لاعب آخر مختلف يشارك نفس النص بالصدفة — نفس ظاهرة بند
   27/فئة أ-1. لا يُعتمَد كحسم نهائي بلا مراجعة يدوية فردية)
3. **صفر تعادل تام** بين الدليل السلوكي للطرفين
4. **عيّنة تزامن كافية**: حدّ أدنى **3 مباريات** بنافذة التداخل
   (Y>=3) — درس موثَّق (بند 27، دفعة رابعة): تزامن 100% بعيّنة
   1-2 مباراة قد يكون تطابقاً عشوائياً صرفاً (مثال حي موثَّق:
   نفس الزوج تقريباً أعطى 100% بعيّنة 1/1 و48.3% بعيّنة 14/29
   بنفس الجلسة). أقل من 3 = **عيّنة صغيرة، يحتاج دليلاً إضافياً**
   قبل القبول، لا رفضاً تلقائياً.
5. **صفر "خرق متبادل"** — ⚠️ **محاولة أولى خاطئة أيضاً**: دمج كل
   تواريخ الصيغتين من الجدولين معاً بتسلسل واحد وعدّ "الانقلابات"
   يعطي رقماً كاذباً ضخماً (مثال: `id=328451` أعطى 59) لأن كل
   مباراة تُسجَّل بصيغة أ بجدول وصيغة ب بالجدول الآخر بنفس
   التاريخ تقريباً — نفس تصادم #1 غير التشخيصي، لا خرقاً حقيقياً.
   **التعريف الصحيح**: الفحص داخل **كل جدول لوحده** لا بينهما —
   هل `lineup_players` (وحده) يحمل الصيغتين معاً بتاريخه (خرق
   داخلي)؟ وهل `player_stats` (وحده) كذلك؟ "الخرق المتبادل" =
   **الجدولان معاً** مخروقان داخلياً (كل جدول اخترقته الصيغة
   الأخرى) — لا مصدر ثابت يُعتمَد عليه إطلاقاً. خرق بجدول واحد
   فقط (انتقال تسمية حقيقي بنقطة واحدة داخل ذلك الجدول تحديداً)
   مقبول، لا يُرفَض. (تطابق تعريف حالة `409613` الموثَّقة: "كل
   صيغة اخترقت جدول الأخرى").

⚠️ **كل هذه المعايير مؤهِّلة لا حاسمة** — نفس مبدأ كل دفعات بند
   27 السابقة: قائمة "مؤهَّل" تعني "تستاهل مراجعة بشرية فردية"،
   لا "قرار جاهز للكتابة تلقائياً". صفر كتابة تلقائية بأي حال.

عمود `decision` بالملف: فارغ = لم يُحسَم بعد. أي قيمة غير فارغة
= استبعاد نهائي مؤكَّد (تصادم هوية أشخاص حقيقيين مختلفين، لا
توحيد إملاء) — يُتجاهَل تلقائياً بكل تشغيل (14 سبتمبر).

التشغيل:
    python check_ar_conflict_queue.py             <- كل الطابور بالتفصيل
    python check_ar_conflict_queue.py --qualify   <- الحالات المؤهَّلة فقط

قراءة فقط دائماً — صفر كتابة على `football.db` أو أي CSV.
"""
import csv
import sys
import sqlite3
from datetime import date as _date
from config import DB_FILE, BASE_DIR

QUEUE_FILE = BASE_DIR / "player_ar_conflict_queue.csv"
QUALIFY_ONLY = "--qualify" in sys.argv
COOCCUR_THRESHOLD = 90.0
MIN_SAMPLE = 3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def behavioral_evidence(conn, form):
    """events+goals — تقاطع نصي عام، بلا قيد player_id (نفس
    منهجية كل الدفعات السابقة، بنفس تحذيرها)."""
    n = 0
    for table in ("events", "goals"):
        n += conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE player_en=?", (form,)
        ).fetchone()[0]
    return n


def parse_date(period_str):
    """'YYYY-MM-DD..YYYY-MM-DD' -> (start, end) نصّياً، قابلة
    للمقارنة المعجمية مباشرة (تنسيق ISO)."""
    a, b = period_str.split("..")
    return a.strip(), b.strip()


def match_cooccur(conn, player_id, fa, fb, period_a, period_b):
    """X/Y ضمن نافذة تداخل period_a/period_b — راجع الشرح المفصَّل
    برأس الملف. يرجّع (X, Y, نسبة%)."""
    lo = max(period_a[0], period_b[0])
    hi = min(period_a[1], period_b[1])
    if lo > hi:
        return 0, 0, 0.0

    rows = conn.execute("""
        SELECT DISTINCT t.match_id, m.date, t.player_en
        FROM (SELECT match_id, player_id, player_en FROM lineup_players
              UNION ALL
              SELECT match_id, player_id, player_en FROM player_stats) t
        JOIN matches m ON m.match_id = t.match_id
        WHERE t.player_id=? AND t.player_en IN (?, ?)
    """, (player_id, fa, fb)).fetchall()

    by_match = {}
    for mid, mdate, en in rows:
        d = mdate.split(" ")[0]
        if lo <= d <= hi:
            by_match.setdefault(mid, set()).add(en)

    y = len(by_match)
    x = sum(1 for forms in by_match.values() if fa in forms and fb in forms)
    return x, y, (round(100 * x / y, 1) if y else 0.0)


def table_breach(conn, table, player_id, fa, fb):
    """يفحص جدولاً واحداً بمفرده: هل يحمل الصيغتين معاً (خرق
    داخلي) أم صيغة واحدة ثابتة طوال تاريخ هذا player_id فيه؟"""
    rows = conn.execute(f"""
        SELECT DISTINCT t.player_en FROM {table} t
        WHERE t.player_id=? AND t.player_en IN (?, ?)
    """, (player_id, fa, fb)).fetchall()
    return len(rows) > 1


def check_row(conn, r):
    pid = int(r["player_id"])
    fa, fb = r["form_a"], r["form_b"]
    period_a = parse_date(r["period_a"])
    period_b = parse_date(r["period_b"])

    beh_a = behavioral_evidence(conn, fa)
    beh_b = behavioral_evidence(conn, fb)
    has_evidence = beh_a > 0 or beh_b > 0
    is_tie = beh_a == beh_b

    x, y, cooccur_pct = match_cooccur(conn, pid, fa, fb, period_a, period_b)
    cooccur_ok = cooccur_pct >= COOCCUR_THRESHOLD
    small_sample = y < MIN_SAMPLE

    breach_lineup = table_breach(conn, "lineup_players", pid, fa, fb)
    breach_stats = table_breach(conn, "player_stats", pid, fa, fb)
    mutual_violation = breach_lineup and breach_stats

    winner = None
    if has_evidence and not is_tie:
        winner = fa if beh_a > beh_b else fb

    return dict(
        player_id=pid, form_a=fa, form_b=fb,
        beh_a=beh_a, beh_b=beh_b,
        cooccur=f"{x}/{y}", cooccur_pct=cooccur_pct, cooccur_ok=cooccur_ok,
        small_sample=small_sample,
        breach_lineup=breach_lineup, breach_stats=breach_stats,
        mutual_violation=mutual_violation,
        winner=winner,
        qualifies=(cooccur_ok and has_evidence and not is_tie
                   and not mutual_violation and not small_sample),
        qualifies_but_small_sample=(cooccur_ok and has_evidence and not is_tie
                                     and not mutual_violation and small_sample),
    )


def main():
    conn = sqlite3.connect(DB_FILE)

    with open(QUEUE_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # صفوف باستبعاد نهائي مؤكَّد بعمود decision (تصادم هوية أشخاص
    # حقيقيين مختلفين، لا توحيد إملاء) — تُستبعَد من كل فحص لاحق،
    # لا تُعاد كمرشَّحة أبداً (14 سبتمبر، أول استخدام فعلي للعمود).
    excluded = [r for r in rows if r["decision"].strip()]
    rows = [r for r in rows if not r["decision"].strip()]
    if excluded:
        print(f"مستبعَدة نهائياً (عمود decision مملوء، تُتجاهَل): {len(excluded)}")

    print(f"إجمالي صفوف الطابور القابلة للفحص: {len(rows)}\n")

    all_results = [check_row(conn, r) for r in rows]
    qualified = [r for r in all_results if r["qualifies"]]
    small_sample = [r for r in all_results if r["qualifies_but_small_sample"]]

    if not QUALIFY_ONLY:
        for res in all_results:
            print(res)

    print(f"\n{'=' * 58}")
    print(f"حالات مؤهَّلة لمراجعة بشرية فردية (تزامن>={COOCCUR_THRESHOLD:.0f}% + "
          f"عيّنة>={MIN_SAMPLE} + دليل سلوكي + بلا تعادل تام + بلا خرق متبادل): "
          f"{len(qualified)}")
    print(f"{'=' * 58}")
    for q in sorted(qualified, key=lambda x: -x["cooccur_pct"]):
        print(f"  id={q['player_id']}: {q['form_a']} ({q['beh_a']}) مقابل "
              f"{q['form_b']} ({q['beh_b']}) -> الأرجح: {q['winner']} "
              f"[تزامن={q['cooccur']}={q['cooccur_pct']}%]")

    print(f"\n⚠️ نفس المعايير لكن بعيّنة تزامن صغيرة (<{MIN_SAMPLE} مباريات — "
          f"يحتاج دليلاً إضافياً قبل القبول، درس الدفعة الرابعة): {len(small_sample)}")
    for q in sorted(small_sample, key=lambda x: -x["cooccur_pct"]):
        print(f"  id={q['player_id']}: {q['form_a']} ({q['beh_a']}) مقابل "
              f"{q['form_b']} ({q['beh_b']}) -> الأرجح: {q['winner']} "
              f"[تزامن={q['cooccur']}={q['cooccur_pct']}%]")


if __name__ == "__main__":
    main()
