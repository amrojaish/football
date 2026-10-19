#!/usr/bin/env python3
"""
التحديث الكامل — سلسلة واحدة
===============================
بيشغّل كل خطوات التحديث بالترتيب الإجباري:

    سحب  →  دمج  →  استثناء  →  إضافة  →  تصحيح  →  توليد

مصمَّم ليعمل على GitHub Actions بلا تدخل، لكن يعمل محلياً
بنفس الطريقة.

⚠️ **الترتيب إجباري** — راجع README:
   وحّد الأندية، ثم احذف الزائد، ثم أضف الناقص، ثم صحّح الباقي.

⚠️ يسحب **المواسم الجارية فقط** — المواسم المنتهية ثابتة ولا
   داعي لاستهلاك الحصة عليها.

منطق الحصة:
    fetch_upcoming   = 1 طلب لكل دوري
    fetch_matches2   = 1 + عدد المباريات الجديدة
    باقي السكربتات   = عدد المباريات الجديدة فقط (تزايدية)
    fetch_standings  = 1 طلب لكل دوري/موسم جارٍ
  المتوسط بلا مباريات جديدة: ~10 طلبات
  في يوم جولة كاملة (10 مباريات): ~60 طلباً

التشغيل:
    python update_all.py
    python update_all.py --season 2026
    python update_all.py --dry     <- عرض الخطوات بلا تنفيذ
    python update_all.py --generate-only   <- التوليد فقط (بلا سحب/apply)
"""

import os
import subprocess
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DRY = "--dry" in sys.argv

SEASON = 2026
if "--season" in sys.argv:
    i = sys.argv.index("--season")
    if i + 1 < len(sys.argv):
        try:
            SEASON = int(sys.argv[i + 1])
        except ValueError:
            pass

# الدوريات التي يوفّر المزوّد تفاصيلها (درس 25)
# ⚠️ EGY أُضيف 3 سبتمبر — تحقّقت فعلياً (لا افتراضاً): أحداث +
#    تشكيلات + إحصائيات مباراة + إحصائيات لاعبين، الأربعة موجودة
#    (عيّنة 29 مباراة، صفر فشل).
# ⚠️ UAE أُضيف 3 سبتمبر — 749 مباراة (2022-2026) بالأربع طبقات،
#    صفر فشل. جدولان قديمان (2022-23، 2023-24) فيهم فرق صغير جداً
#    (1-2 هدف) بين حسابنا وترتيب المزوّد — راجع بند مفتوح بالـREADME.
# ⚠️ QAT أُضيف 4 سبتمبر — 595 مباراة (2022-2026)، الأربع طبقات
#    كاملة من 2023 (2022 بلا match_stats/player_stats — قيد
#    مزوّد حقيقي، راجع بند مفتوح بالـREADME).
# ⚠️ MAR أُضيف 5 سبتمبر (دوري سابع) — events+lineups كاملان،
#    match_stats جزئي (~53%)، player_stats **غائب كلياً** كل
#    المواسم (قيد مزوّد حقيقي مؤكَّد بعيّنة، راجع بند مفتوح 14).
#    مُبقًى بـDETAILED رغم ذلك — الطلبات الفاشلة رخيصة والثلاث
#    طبقات الأخرى تستأهل السحب.
DETAILED = ["SAU", "EGY", "UAE", "QAT", "MAR"]
ALL_LEAGUES = ["JOR", "IRQ", "SAU", "EGY", "UAE", "QAT", "MAR"]

S = str(SEASON)

STEPS = [
    # ---- السحب ----
# ⚠️ fetch_live.py أُزيل من الخطوات (2 أكتوبر 2026): live.json لا تقرؤه أي صفحة —
    #    الواجهة تقرأ من الـworker مباشرة (live_view.py)
    ("سحب المباريات القادمة", ["fetch_upcoming.py", "--season", S]),
]

for lg in ALL_LEAGUES:
    STEPS.append((f"سحب نتائج {lg}",
                  ["fetch_matches2.py", lg, "--season", S, "--budget", "60"]))

for lg in DETAILED:
    STEPS += [
        (f"أحداث {lg}", ["fetch_events.py", lg, "--season", S,
                          "--budget", "30"]),
        (f"إحصائيات {lg}", ["fetch_stats.py", lg, "--season", S,
                             "--budget", "30"]),
        (f"تشكيلات {lg}", ["fetch_lineups.py", lg, "--season", S,
                            "--budget", "30"]),
        (f"إحصائيات لاعبي {lg}", ["fetch_player_stats.py", lg,
                                    "--season", S, "--budget", "30"]),
    ]

# أحداث العراقي والأردني (19 أكتوبر 2026): بلا سحب من المزوّد — نسخة الـworker النهائية ev:<id> (36 ساعة)؛ لا يكتب فوق صفوف موجودة
STEPS.append(("أحداث العراقي والأردني من الـworker", ["import_live_events.py"]))

# إعادة سحب التشكيلات الناقصة الحديثة (13 أكتوبر 2026): منتهية خلال آخر 26 ساعة وفيها فريق بأقل من 11 أساسياً، مرة واحدة لكل مباراة بالتشغيل،
# ميزانية 20، وسقف 4 محاولات لكل مباراة (جدول lineup_refetch). دمج لا مسح (راجع fetch_lineups.py). يشغَّل بعد سحب التشكيلات العادي.
STEPS.append(("إعادة سحب التشكيلات الناقصة (آخر 26 ساعة)",
              ["fetch_lineups.py", "--refetch", "recent", "--apply", "--budget", "20"]))

STEPS += [
    ("ترتيب المزوّد", ["fetch_standings.py", "--season", S]),

    # ---- أسماء الهدّافين بعد النهاية (17 أكتوبر 2026): المزوّد يملأ اسماً فارغاً لاحقاً أحياناً؛ fetch_matches2 لا يعيد مباراة منتهية ----
    # يعمل قبل apply_players_ar.py (أدناه) فتأخذ الأسماء الجديدة عربيّها. جدولة fetch_backoff (0/1/6/24/72 س) وسقف 10 طلبات بالدورة.
    ("تحديث أسماء الهدّافين الفارغة بعد النهاية", ["refresh_goal_names.py", "--season", S, "--budget", "10"]),
    # ---- بطاقات اللاعبين (18 أكتوبر 2026): تاريخ الميلاد/الجنسية/الطول/المركز/الرقم + علم الصورة، لمعرّفات صفحات اللاعبين فقط ----
    # آخر السحب: 100 طلب بالدورة كحدّ، 3,000 باليوم (player_info_calls)، ولا شيء تحت 2,000 متبقٍّ (الحصة مشتركة مع الـworker الحي؛ قرار عمرو 18 أكتوبر).
    ("بطاقات اللاعبين (player_info)", ["fetch_player_info.py", "--budget", "100", "--daily-cap", "3000", "--min-remaining", "2000"]),
    # هدف بلا اسم بنتيجة 0-0 = شبح من المزوّد: يُؤرشف بـcancelled_goals ويُحذف (make_matches لا يعرضه كهدف ملغى)
    ("إزالة الأهداف الشبحية (بلا اسم بنتيجة 0-0)", ["fix_goals.py", "--ghosts-only"]),

    # ---- المعالجة — الترتيب إجباري ----
    ("دمج الأندية المكررة", ["apply_merges.py"]),
    ("استثناء المباريات", ["apply_exclusions.py"]),
    ("إضافة المباريات اليدوية", ["apply_manual.py"]),
    ("تصحيح النتائج", ["apply_corrections.py"]),
    # ⚠️ **أُعيد تفعيله 7 سبتمبر 2026 — بند 26 مُغلَق.** الكتابة
    #    الكاملة (774 زوجاً player_en + 501 assist_en) طُبِّقت
    #    وتحقَّقنا: صفر أثر على player_slug.py/make_players.py
    #    (يبنيان الصفحات من goals.player_en وحدها، صفر تقاطع مع
    #    الأزواج). أثناء ذلك اكتُشف تلف حقيقي بسطر CSV (مسافة
    #    مزدوجة بـkeep_name، مصدره auto_merge_names.py) استدعى
    #    استرجاعاً كاملاً، وأُصلح بالمصدر + بوّابة دورات جديدة
    #    (check_merge_cycles.py، تُفحَص تلقائياً داخل
    #    apply_player_merges.py قبل أي كتابة). راجع سجل الجلسات.
    ("توحيد أسماء اللاعبين", ["apply_player_merges.py"]),
    # ⚠️ توحيد **معرّفات** اللاعب المكرر (8 أكتوبر 2026، قرار آلي بلا مراجعة): player_id_merges.csv يحوّل صفوف المعرّف
    #    المحذوف للباقي بـlineup_players/player_stats فقط (لا لمس لـplayer_en ولا goals). لا علاقة له بـplayer_merges.csv.
    #    قبل الترجمات: صفوف P3 المقيَّدة بالمعرّف تُطبَّق على المعرّف الباقي.
    ("توحيد معرّفات اللاعبين المكررة", ["apply_id_merges.py"]),
    # تصحيح player_id لصفوف محدّدة (معرّف خاطئ من المزوّد على لاعب آخر): player_id_repoints.csv، idempotent.
    ("تصحيح معرّفات صفوف محدّدة", ["apply_id_repoints.py"]),
    ("تطبيق الترجمات", ["apply_players_ar.py"]),

    # ---- التوليد ----
    # ⚠️ **البناء يجب أن يكتمل من شجرة بلا أي صفحة مولَّدة** (المرحلة B: لا صفحات
    #    مولَّدة بـgit — درس "بوابة البناء النظيف" بالـREADME). لذلك:
    #    • make_players أولاً: make_site3 وmake_clubs وmake_search تقرأ
    #      players/*.html من القرص لتقرر روابط اللاعبين (قبلها كانت تقرأ صفحات
    #      التشغيل السابق).
    #    • make_leagues --all: بدونه تُبنى المواسم الجارية فقط وتختفي صفحات الأرشيف
    #      (27 × لغتين)، وبمرّتين داخلياً لأن منسدلة المواسم تُبنى من القرص.
    #    • make_following: يولّد following.html وfollow_data.js (لم يكن بالسلسلة،
    #      فكان follow_data.js يتقادم بين التشغيلات اليدوية).
    ("بناء ملفات /assets (CSS/JS المشتركة)", ["make_assets.py"]),
    ("لقطات الجدول للترتيب المباشر (/assets/table_*.json)", ["make_live_tables.py"]),
    ("توليد أسماء الفرق للـworker (إشعارات الأهداف)", ["make_team_names.py"]),
    ("توليد مواعيد الانطلاق للـworker (سحب كل دقيقة قبل المباراة)", ["make_kickoffs.py"]),
    ("توليد أسماء اللاعبين للـworker (اسم الهدّاف)", ["make_player_names.py"]),
    ("توليد شعارات الأندية المصغّرة (thumbs/، تراكمي)", ["make_logo_thumbs.py"]),
    ("توليد صفحات اللاعبين", ["make_players.py"]),
    ("توليد الصفحة الرئيسية", ["make_site3.py"]),
    ("توليد صفحة الدوريات (كل المواسم)", ["make_leagues.py", "--all"]),
    ("توليد صفحات الأندية", ["make_clubs.py"]),
    ("توليد صفحات المباريات", ["make_matches.py"]),
    ("توليد الصفحات الثابتة", ["make_pages.py"]),
    ("توليد صفحة المتابعة", ["make_following.py"]),
    ("توليد صفحة الإشعارات", ["make_notifications.py"]),
    ("توليد فهرس البحث", ["make_search.py"]),
    ("توليد صفحة البحث", ["make_search_page.py"]),
    ("توليد خريطة الموقع", ["make_sitemap.py"]),
]


# --generate-only: التوليد فقط (بلا سحب ولا apply) — لفحص البناء النظيف بلا طلبات API
if "--generate-only" in sys.argv:
    STEPS = STEPS[next(i for i, (_l, a) in enumerate(STEPS)
                       if a[0] == "make_assets.py"):]


def run(label, args):
    cmd = [sys.executable] + args
    print(f"\n{'─' * 62}")
    print(f"▶  {label}")
    print(f"{'─' * 62}")

    if DRY:
        print(f"   [عرض فقط] {' '.join(args)}")
        return True

    # ⚠️ **PYTHONUTF8 إجباري للعمليات الفرعية.** `capture_output`
    #    ينشئ أنبوباً، وبايثون يختار له ترميز النظام (cp1252 على
    #    ويندوز) لا ترميز الطرفية — فينهار السكربت الابن عند أول
    #    `print` بحرف عربي، **بعد أن يكون أنجز عمله**. الخطأ يبدو
    #    فشلاً في المهمة وهو فشل في الطباعة فقط.
    #    `encoding="utf-8"` هنا يحكم القراءة عندنا لا الكتابة عندهم.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=env, timeout=1800)
    except subprocess.TimeoutExpired:
        print("   ❌ تجاوز المهلة (30 دقيقة)")
        return False
    except Exception as e:
        print(f"   ❌ فشل التشغيل: {type(e).__name__}")
        return False

    out = (r.stdout or "").strip()
    if out:
        # آخر 12 سطراً تكفي — الملخص عادةً بالنهاية
        lines = out.split("\n")
        for line in lines[-12:]:
            print(f"   {line}")

    if r.returncode != 0:
        err = (r.stderr or "").strip()
        print(f"   ❌ رمز الخروج {r.returncode}")
        if err:
            for line in err.split("\n")[-8:]:
                print(f"   {line}")
        return False

    return True


def main():
    start = time.time()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'═' * 62}")
    print(f"  التحديث الكامل — موسم {SEASON}")
    print(f"  {stamp}")
    print(f"{'═' * 62}")

    if DRY:
        print("\n  ⚠️ وضع العرض — ما رح ينفّذ شي\n")

    failed = []
    for label, args in STEPS:
        if not run(label, args):
            failed.append(label)

    mins = (time.time() - start) / 60

    print(f"\n{'═' * 62}")
    print(f"  خلص خلال {mins:.1f} دقيقة")
    print(f"{'═' * 62}")

    if failed:
        print(f"\n  ⚠️ فشل {len(failed)} خطوة:")
        for f in failed:
            print(f"      {f}")
        print("""
  ⚠️ الخطوات التالية تابعت رغم الفشل — قد تكون الصفحات
     مولّدة من داتا ناقصة. راجع السبب قبل الاعتماد عليها.
        """)
        sys.exit(1)

    print("\n  ✅ كل الخطوات نجحت\n")


if __name__ == "__main__":
    main()
