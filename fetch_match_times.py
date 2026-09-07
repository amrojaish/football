#!/usr/bin/env python3
"""
سحب أوقات المباريات المنتهية — الوضع الخاص (بند 20/27/28، 7 سبتمبر)
======================================================================
`fetch_matches2.py` يتخطّى أي مباراة عندها نتيجة (`home_goals
IS NOT NULL`) بغضّ النظر عن طول `date` — فلا يمكن استعماله
لسدّ فجوة الوقت بـ6,528 مباراة منتهية بلا وقت (`date` بطول 10،
تاريخ بلا ساعة).

⚠️ **الحل ليس طلباً لكل مباراة.** نقطة `/fixtures?league=X&
   season=Y&status=FT` (نفسها المستعمَلة بـ`fetch_matches2.py`
   لجلب القائمة) **ترجّع `date` كاملاً بالوقت لكل مباريات الموسم
   بطلب واحد** — تُستعمَل حالياً فقط عند إدراج مباراة *جديدة*،
   وأبداً لتحديث مباراة موجودة أصلاً. هذا السكربت يعيد استعمال
   نفس الرد لتحديث `matches.date` للموجودات — لا طلب لكل مباراة.

⚠️ **يمسّ عموداً واحداً بجدول واحد فقط:** `UPDATE matches SET
   date = ? WHERE match_id = ?`. صفر لمس لـ`goals`/`events`/
   `lineup_players`/`player_stats`/أي عمود آخر بـ`matches` نفسها
   (`home_goals`/`status`/إلخ تبقى كما هي).

⚠️ **`00:00` بالضبط = قيمة نائبة لا توقيت حقيقي (قرار 7 سبتمبر).**
   اكتُشف بـIRQ 2024: 7/380 مباراة رجعت `00:00 UTC` حرفياً،
   موزَّعة على يومين متتاليين فقط بلا أي تنوّع — نمط قيمة عنصر
   نائب لا بيانات فعلية. **لا يُكتَب وقت لها إطلاقاً** — تبقى
   (أو تعود، لو كُتبت سابقاً بخطأ) تاريخاً بلا وقت. العدد المتخطَّى
   يُطبَع صراحة دائماً (مبدأ 17 — لا تخطٍّ صامت)، حتى لو صفراً.

⚠️ **مبني على المقارنة لا القائمة الثابتة — يُصلح ذاتياً.** لكل
   مباراة منتهية بالزوج (لا فقط الناقصة وقتاً)، يُحسَب الهدف
   (وقت حقيقي أو تاريخ فقط لو 00:00) ويُقارَن بالمخزَّن فعلياً؛
   `UPDATE` فقط لو اختلفا. هذا يُصلح تلقائياً أي صف كُتب فيه
   `00:00` بخطأ بتشغيل سابق (قبل هذا القرار) — لا حاجة لتنظيف
   يدوي منفصل.

⚠️ **فحص paging إلزامي لكل زوج، لا افتراضاً عاماً.** يُقارَن
   عدد الـfixtures المُرجَعة بعدد كل المباريات المنتهية عندنا
   لنفس الزوج (`home_goals IS NOT NULL`، لا فقط الناقصة وقتاً) —
   لو الرد أقل، **يرفض الكتابة كاملة لهذا الزوج** ويطبع تحذيراً
   واضحاً، بدل كتابة جزئية صامتة.

نسخة احتياطية تلقائية قبل أي كتابة: `football_before_match_times.db`.

التشغيل:
    python fetch_match_times.py IRQ --season 2024 --check
    python fetch_match_times.py IRQ --season 2024
"""

import requests
import shutil
import sqlite3
import sys
import time

from config import API_BASE, SEASON, DB_FILE, LEAGUES, check_key, headers

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3


# ⚠️ استثناءات صريحة بالمعرّف — 7 سبتمبر. فحص paging لكل الـ33
#    زوجاً كشف زوجين "ناقصين" (EGY 2023 · IRQ 2025) — تحقّق مباشر
#    (لا افتراض) أثبت أن السبب ليس paging بل مباريات لن تظهر
#    بقائمة `/fixtures` **أبداً** مهما كانت المعاملات. تُستبعَد من
#    "المتوقَّع" وقت فحص paging فقط (لا تُكتَب، تبقى بتاريخها الحالي
#    كما هي) — استبعاد بالمعرّف الصريح لا بخفض عتبة الأمان العامة،
#    فأي نقص حقيقي آخر بنفس الزوجين مستقبلاً يبقى مرصوداً.
KNOWN_UNLISTED_IDS = {
    1176885: "كلاسيكو الزمالك×الأهلي 2023 — محسوم إدارياً (بند مفتوح "
             "13)، أُضيف يدوياً بمعرّفه الحقيقي 5 سبتمبر، لا يحمل "
             "status=FT عادياً عند المزوّد",
    9000001: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000002: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000003: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000004: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000005: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000006: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
    9000007: "معرّف اصطناعي يدوي (IRQ 2025) — غير موجود عند المزوّد إطلاقاً",
}


def parse_args():
    code, season = "JOR", SEASON
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        code = args[0].upper()

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, season, check_only


def get(endpoint, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{API_BASE}/{endpoint}", headers=headers(),
                             params=params, timeout=TIMEOUT)

            if r.status_code == 429:
                wait = attempt * 10
                print(f"      تجاوز المعدل — انتظار {wait}ث")
                time.sleep(wait)
                continue

            if r.status_code != 200:
                return False, [], f"HTTP {r.status_code}"

            data = r.json()
            errors = data.get("errors")
            if errors and isinstance(errors, dict) and errors:
                return False, [], f"API: {errors}"

            return True, data.get("response", []), ""

        except requests.exceptions.Timeout:
            wait = attempt * 3
            if attempt < MAX_RETRIES:
                print(f"      مهلة انتهت — إعادة محاولة بعد {wait}ث "
                      f"({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                return False, [], "مهلة انتهت"
        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def run(code, season, check_only):
    """يرجع dict بملخّص النتيجة — يُستعمَل يدوياً أو بحلقة تعميم."""
    result = {"code": code, "season": season, "ok": False}

    if code not in LEAGUES:
        print(f"دوري غير معروف: {code}")
        return result

    league = LEAGUES[code]
    conn = sqlite3.connect(DB_FILE)

    print(f"\n{'=' * 55}")
    print(f"  {league['name_ar']} — موسم {season} — سحب الأوقات")
    print(f"{'=' * 55}")

    ok, fixtures, reason = get("fixtures", {"league": league["id"],
                                            "season": season,
                                            "status": "FT"})
    if not ok:
        print(f"  فشل جلب القائمة: {reason}")
        conn.close()
        result["error"] = reason
        return result

    # ⚠️ فحص paging إلزامي — المتوقَّع = كل المنتهية عندنا لهذا
    #    الزوج (لا فقط الناقصة وقتاً)، لا رقماً ثابتاً مفترَضاً.
    #    KNOWN_UNLISTED_IDS تُطرَح من المتوقَّع فقط لو موجودة فعلاً
    #    بهذا الزوج تحديداً — استثناء بالمعرّف الصريح، والفحص يبقى
    #    صارماً 1:1 لما عداها.
    db_ids = {r[0] for r in conn.execute("""
        SELECT match_id FROM matches
        WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL
    """, (code, season))}
    expected_total_raw = len(db_ids)
    excluded_present = sorted(db_ids & set(KNOWN_UNLISTED_IDS))
    expected_total = expected_total_raw - len(excluded_present)

    print(f"  متوقَّع (كل المنتهية عندنا): {expected_total_raw}")
    print(f"  مستثنى (معرّفات معروفة غير مُدرَجة عند المزوّد): "
          f"{len(excluded_present)}")
    for mid in excluded_present:
        print(f"      {mid}  —  {KNOWN_UNLISTED_IDS[mid]}")
    print(f"  متوقَّع بعد الاستثناء: {expected_total}")
    print(f"  المُرجَع فعلياً من المزوّد : {len(fixtures)}")

    if len(fixtures) < expected_total:
        print(f"  ❌ الرد أقصر من المتوقَّع حتى بعد الاستثناءات "
              f"المعروفة — احتمال paging أو نقص بالمزوّد. الكتابة "
              f"مرفوضة لهذا الزوج كاملاً.")
        conn.close()
        result["paging_issue"] = True
        return result

    result["excluded"] = len(excluded_present)

    if not fixtures:
        print("  ما رجعت مباريات")
        conn.close()
        result["ok"] = True
        return result

    fx_by_id = {fx["fixture"]["id"]: fx["fixture"]["date"][:16].replace("T", " ")
                for fx in fixtures}

    rows = conn.execute("""
        SELECT match_id, date FROM matches
        WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL
    """, (code, season)).fetchall()

    to_write = []      # (mid, old, new)      وقت حقيقي جديد/مصحَّح
    to_revert = []      # (mid, old, new)      00:00 مكتوب سابقاً بخطأ → يعود لتاريخ فقط
    skipped_midnight = []  # (mid)             00:00 بالرد، ولا شيء مكتوب أصلاً — يبقى كما هو
    not_in_response = []
    unchanged = 0

    for mid, cur_date in rows:
        new_full = fx_by_id.get(mid)
        if new_full is None:
            not_in_response.append(mid)
            continue

        is_midnight = new_full.endswith(" 00:00")
        target = new_full[:10] if is_midnight else new_full

        if target == cur_date:
            unchanged += 1
            if is_midnight and len(cur_date) == 10:
                pass  # كان صحيحاً أصلاً (تاريخ فقط)، بلا تغيير
            continue

        if is_midnight:
            to_revert.append((mid, cur_date, target))
        elif len(cur_date) == 10:
            to_write.append((mid, cur_date, target))
        else:
            # كان له وقت مختلف أصلاً وتغيّر — نادر، لكن نتعامل معه
            to_write.append((mid, cur_date, target))

    # ⚠️ لا تخطٍّ صامت — يُطبَع دائماً حتى لو صفراً
    print(f"  سيُكتَب (وقت حقيقي جديد): {len(to_write)}")
    print(f"  سيُصحَّح (00:00 مكتوب بخطأ سابقاً → يعود تاريخاً فقط): "
          f"{len(to_revert)}")
    print(f"  بلا تغيير (مطابق أصلاً): {unchanged}")
    if not_in_response:
        print(f"  ⚠️ غائبة عن هذا الرد رغم وجودها عندنا منتهية: "
              f"{len(not_in_response)}  {sorted(not_in_response)[:5]}")

    changes = to_write + to_revert
    result["to_write"] = len(to_write)
    result["to_revert"] = len(to_revert)
    result["unchanged"] = unchanged
    result["not_in_response"] = len(not_in_response)

    if check_only or not changes:
        print("\n  [وضع الفحص] — ما انكتب شي\n" if check_only else
              "\n  لا شيء ليُحدَّث\n")
        conn.close()
        result["ok"] = True
        return result

    backup = DB_FILE.parent / "football_before_match_times.db"
    shutil.copy(DB_FILE, backup)
    print(f"\n  نسخة احتياطية: {backup.name}")

    for mid, old_date, new_date in changes:
        conn.execute("UPDATE matches SET date = ? WHERE match_id = ?",
                     (new_date, mid))
    conn.commit()

    print(f"\n  حُدِّث: {len(changes)} صفاً "
          f"({len(to_write)} وقت جديد + {len(to_revert)} تصحيح)")

    if to_write:
        print("\n  عيّنة كتابة (match_id · قبل · بعد):")
        for mid, old_date, new_date in to_write[:5]:
            print(f"    {mid}  {old_date}  →  {new_date}")
    if to_revert:
        print("\n  عيّنة تصحيح (match_id · قبل · بعد):")
        for mid, old_date, new_date in to_revert[:5]:
            print(f"    {mid}  {old_date}  →  {new_date}")

    conn.close()
    result["ok"] = True
    return result


def main():
    if not check_key():
        return
    code, season, check_only = parse_args()
    run(code, season, check_only)


if __name__ == "__main__":
    main()
