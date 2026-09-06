#!/usr/bin/env python3
"""
فحص حافة منتصف ليل UTC — مباريات قريبة من تغيّر التاريخ محلياً
==================================================================
`matches.date` مخزَّن UTC (راجع matchtime.py + بند مفتوح
بالـREADME). تحويل الوقت المعروض لتوقيت الزائر المحلي (بند "أ"،
مطبَّق) لا يعيد تجميع "شريط اليوم/أمس/غداً" بالرئيسية — ذاك
مبني وقت التوليد على `DATE(m.date)` UTC (`day_view()`،
`make_site3.py`). مباراة بنطاق 20:00-02:00 UTC قد تُعرض بوقتها
المحلي الصحيح لكن تحت تبويب اليوم الخطأ لزائر بمنطقة زمنية
موجبة (شرق UTC) أو سالبة.

⚠️ **هذا الفحص هو الفيصل، لا رأياً.** لو رجع أي عدد غير صفر —
   البند "ب" (إعادة تجميع الأيام بجافاسكربت، لا تحويل نص فقط)
   **لم يعد نظرياً ويجب تنفيذه**. راجع القرار الموثَّق بالـREADME
   (6 سبتمبر): اختير "أ" لأن العدّ وقتها كان صفراً بالضبط.

صفر تعديل، صفر طلبات API — فحص محلي فقط.

التشغيل:
    python check_utc_edge.py
"""

import sqlite3

from config import DB_FILE, LEAGUES

# نطاق الخطر: مباراة الساعة 20:00-23:59 UTC قد تصير اليوم التالي
# محلياً لأي منطقة زمنية موجبة (شرق UTC، كل الدوريات السبعة
# بهذا النطاق أصلاً). 00:00-02:59 UTC قد تصير اليوم السابق
# لمنطقة سالبة (غرب UTC) — نادرة الحدوث هنا لكن مُدرَجة للاكتمال.
RISK_START = "20:00"
RISK_END = "02:00"


def main():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT league_code, match_id, date FROM matches
        WHERE status = 'NS' AND date LIKE '%:%'
          AND (substr(date, 12, 5) >= ? OR substr(date, 12, 5) <= ?)
        ORDER BY league_code, date
    """, (RISK_START, RISK_END))
    rows = cur.fetchall()
    conn.close()

    print(f"\n{'=' * 58}")
    print(f"  مباريات قادمة بنطاق الخطر ({RISK_START}-{RISK_END} UTC): "
          f"{len(rows)}")
    print(f"{'=' * 58}")

    if not rows:
        print("\n  صفر — البند (ب) لا يزال نظرياً اليوم.")
        print("  ⚠️ أعد هذا الفحص دورياً (كل تدوير موسم على الأقل) —")
        print("     مباراة خليجية متأخرة واحدة تكفي لتغيير النتيجة.\n")
        return

    by_league = {}
    for lg, mid, date in rows:
        by_league.setdefault(lg, []).append((mid, date))

    for lg, matches in sorted(by_league.items()):
        name = LEAGUES.get(lg, {}).get("name_ar", lg)
        print(f"\n  {name} ({lg}) — {len(matches)}:")
        for mid, date in matches[:10]:
            print(f"      {mid}  {date}")
        if len(matches) > 10:
            print(f"      ... و{len(matches) - 10} غيرها")

    print(f"\n  ⚠️ العدد غير صفري — البند (ب) لم يعد نظرياً.")
    print("     راجع بند مفتوح matchtime.py بالـREADME.\n")


if __name__ == "__main__":
    main()
