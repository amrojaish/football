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
DETAILED = ["SAU", "EGY"]
ALL_LEAGUES = ["JOR", "IRQ", "SAU", "EGY"]

S = str(SEASON)

STEPS = [
    # ---- السحب ----
("سحب المباريات المباشرة", ["fetch_live.py"]),
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

STEPS += [
    ("ترتيب المزوّد", ["fetch_standings.py", "--season", S]),

    # ---- المعالجة — الترتيب إجباري ----
    ("دمج الأندية المكررة", ["apply_merges.py"]),
    ("استثناء المباريات", ["apply_exclusions.py"]),
    ("إضافة المباريات اليدوية", ["apply_manual.py"]),
    ("تصحيح النتائج", ["apply_corrections.py"]),
    ("توحيد أسماء اللاعبين", ["apply_player_merges.py"]),
    ("تطبيق الترجمات", ["apply_players_ar.py"]),

    # ---- التوليد ----
    ("توليد الصفحة الرئيسية", ["make_site3.py"]),
    ("توليد صفحة الدوريات", ["make_leagues.py"]),
    ("توليد صفحات الأندية", ["make_clubs.py"]),
    ("توليد صفحات المباريات", ["make_matches.py"]),
    ("توليد الصفحات الثابتة", ["make_pages.py"]),
    ("توليد صفحات اللاعبين", ["make_players.py"]),
    ("توليد فهرس البحث", ["make_search.py"]),
    ("توليد خريطة الموقع", ["make_sitemap.py"]),
]


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
