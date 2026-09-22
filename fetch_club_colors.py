#!/usr/bin/env python3
"""
استخراج لون مهيمن لكل نادٍ — من شعاره
=========================================
يبني/يحدّث club_colors.csv (team_id, color_hex) — يقرأها
make_following.py وقت التوليد لتلوين خلفية كارت كل فريق/لاعب
بكارته الموحَّد (الجزء ب، 22 سبتمبر). **صفر طلب شبكة وقت
التوليد نفسه** — نفس مبدأ league_logos.csv بالضبط: استخراج يدوي
هنا مرة واحدة (أو عند إضافة نادٍ جديد فقط)، وقراءة الملف المحفوظ
فقط بسكربتات التوليد.

⚠️ **المصدر teams_arabic.csv وحده** — نفس ملف load_overrides()
   بـmake_site3.py، لا اتصال بقاعدة البيانات هنا. logo_local
   (استثناء محلي، مسار نسبي بـlogos/) له الأولوية، وإلا logo
   (رابط خام من المزوّد).

⚠️ **خوارزمية الاستخراج** — لا متوسط بسيط لكل البكسلات (ينتج
   لوناً رمادياً موحلاً حين يختلط أبيض/أسود/لون بشعار واحد، كما
   تأكّد فعلياً بفحص شعارات الدوريات السبعة). بدلاً منه:
   1. استبعاد بكسلات شبه شفافة (alpha<30) وشبه بيضاء/سوداء
      (كلا الحالتين عادة خلفية/حدود الشعار لا هويته البصرية).
   2. تصنيف الباقي بصناديق خشنة (تقريب كل قناة لأقرب 24) —
      تبسيط لـ"تقليل الألوان" بلا الاعتماد على Image.quantize().
   3. أكثر صندوق تكراراً → متوسط ألوانه الفعلية (لا لون الصندوق
      نفسه) → اللون النهائي.
   شعار أبيض/أسود بالكامل (نادر) يرجع None — سقوط آمن،
   make_following.py يستخدم var(--card) العادية وقتها.

⚠️ **تراكمي بقصد** — لا يعيد استخراج نادٍ موجود أصلاً بـ
   club_colors.csv إلا بـ--all صريحة (نفس نمط --all بـ
   make_leagues.py: تشغيل عادي = تحديثي رخيص، --all = إعادة بناء
   كاملة يدوية).

التشغيل:
    python fetch_club_colors.py        الأندية الجديدة فقط
    python fetch_club_colors.py --all  إعادة استخراج الجميع
"""

import colorsys
import csv
import sys
import time
from collections import Counter, defaultdict
from io import BytesIO

import requests
from PIL import Image

from config import TEAMS_FILE, BASE_DIR

COLORS_FILE = BASE_DIR / "club_colors.csv"
DELAY = 0.3
TIMEOUT = 20
ALL_MODE = "--all" in sys.argv

# ⚠️ **فحص بصري فعلي كشف خللاً بالنسخة الأولى** (استبعاد أبيض/
#    أسود بعتبة RGB خام فقط): حواف بيضاء مائلة للكريمي (off-white
#    antialiasing) كانت تفلت من العتبة وتهيمن عدداً، وشعارات بلا
#    فن حقيقي (بطاقات "OFFICIAL LOGO SOON"/"image not available"
#    من المزوّد نفسه، 3 من أصل 10 بالعيّنة) كانت تُنتج رمادياً
#    مسطَّحاً بدل تخطّيها. **الإصلاح: تصفية بالتشبّع (HSL) لا
#    بعتبة RGB خام** — أي بكسل تشبّعه منخفض (رمادي/أبيض/أسود
#    بصرف النظر عن السطوع الدقيق) يُستبعد، فيبقى فقط لون الهوية
#    الحقيقي. شعار بلا تشبّع كافٍ بأي بكسل (رمادي بالكامل، أو
#    بطاقة "قريباً" من المزوّد) يرجع None بأمان.
SAT_MIN = 0.15
LIGHT_LO = 0.08
LIGHT_HI = 0.92
BUCKET = 24
ALPHA_MIN = 30


def dominant_color(img):
    """أكثر لون مهيمن **بتشبّع حقيقي** (لا رمادي/أبيض/أسود/شفاف).
    None لو الشعار بلا تشبّع كافٍ بأي بكسل — سقوط آمن، لا استثناء."""
    img = img.convert("RGBA")
    img.thumbnail((80, 80))

    buckets = Counter()
    bucket_px = defaultdict(list)

    for r, g, b, a in img.getdata():
        if a < ALPHA_MIN:
            continue
        _, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < SAT_MIN or l < LIGHT_LO or l > LIGHT_HI:
            continue
        key = (r // BUCKET, g // BUCKET, b // BUCKET)
        buckets[key] += 1
        bucket_px[key].append((r, g, b))

    if not buckets:
        return None

    best = buckets.most_common(1)[0][0]
    px = bucket_px[best]
    avg = tuple(sum(c[i] for c in px) // len(px) for i in range(3))
    return "#%02x%02x%02x" % avg


def load_teams():
    """[(team_id, logo_url_or_path, is_local)] من teams_arabic.csv"""
    rows = []
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = (row.get("team_id") or "").strip()
            if not tid:
                continue
            local = (row.get("logo_local") or "").strip()
            remote = (row.get("logo") or "").strip()
            if local:
                rows.append((tid, local, True))
            elif remote:
                rows.append((tid, remote, False))
    return rows


def load_existing():
    if not COLORS_FILE.exists():
        return {}
    with open(COLORS_FILE, encoding="utf-8-sig") as f:
        return {row["team_id"]: row["color_hex"]
                for row in csv.DictReader(f) if row.get("team_id")}


def save(colors):
    with open(COLORS_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["team_id", "color_hex"])
        w.writeheader()
        for tid in sorted(colors, key=int):
            w.writerow({"team_id": tid, "color_hex": colors[tid]})


def get_image(source, is_local):
    if is_local:
        path = BASE_DIR / source
        if not path.exists():
            return None
        return Image.open(path)
    r = requests.get(source, timeout=TIMEOUT)
    r.raise_for_status()
    return Image.open(BytesIO(r.content))


def main():
    if not TEAMS_FILE.exists():
        print("ما لقيت teams_arabic.csv")
        return

    teams = load_teams()
    existing = {} if ALL_MODE else load_existing()
    todo = [t for t in teams if t[0] not in existing]

    print(f"\n{'=' * 55}")
    print(f"  {len(teams)} نادٍ — {len(todo)} يحتاج استخراج"
          + ("  [--all]" if ALL_MODE else ""))
    print(f"{'=' * 55}\n")

    if not todo:
        print("  لا جديد — club_colors.csv محدَّث أصلاً\n")
        return

    colors = dict(existing)
    ok = skipped = failed = 0

    for tid, source, is_local in todo:
        try:
            img = get_image(source, is_local)
            if img is None:
                print(f"  {tid}: الملف المحلي غير موجود — تخطي")
                skipped += 1
                continue

            hexcolor = dominant_color(img)
            if hexcolor is None:
                print(f"  {tid}: شعار أبيض/أسود بالكامل — تخطي "
                      f"(سيستخدم خلفية عادية)")
                skipped += 1
                continue

            colors[tid] = hexcolor
            print(f"  {tid}: {hexcolor}")
            ok += 1

        except Exception as e:
            print(f"  {tid}: فشل — {type(e).__name__}: {e}")
            failed += 1

        if not is_local:
            time.sleep(DELAY)

    save(colors)

    print(f"\n{'=' * 55}")
    print(f"  استُخرج: {ok}  |  تخطي: {skipped}  |  فشل: {failed}")
    print(f"  club_colors.csv: {len(colors)} نادٍ إجمالاً")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
