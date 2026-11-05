#!/usr/bin/env python3
"""
الإعدادات المشتركة
===================
هاد الملف بيقرأ المفتاح من ملف .env
كل السكربتات التانية بتستورد منه، فبتكتب المفتاح مرة وحدة بس.

ما بتشغّل هاد الملف لحاله — هو بس بيخدم الباقيين.
"""

import html
import os
from pathlib import Path

# مسار المجلد اللي فيه هاد الملف
BASE_DIR = Path(__file__).parent

# ثوابت المشروع
API_BASE = "https://v3.football.api-sports.io"
SEASON = 2026   # الموسم الجاري (سنة بدايته بالـAPI) — المصدر الوحيد: update_all.py وافتراضات السكربتات اليدوية تقرؤه (19 أكتوبر 2026)
TEAMS_FILE = BASE_DIR / "teams_arabic.csv"
DB_FILE = BASE_DIR / "football.db"

LEAGUES = {
    "JOR": {"id": 387, "name_ar": "الدوري الأردني"},
    "IRQ": {"id": 542, "name_ar": "الدوري العراقي"},
    "SAU": {"id": 307, "name_ar": "الدوري السعودي"},
    "EGY": {"id": 233, "name_ar": "الدوري المصري"},
    "UAE": {"id": 301, "name_ar": "الدوري الإماراتي"},
    "QAT": {"id": 305, "name_ar": "دوري نجوم قطر"},
    "MAR": {"id": 200, "name_ar": "الدوري المغربي"},
}

# ── دوريات جاهزة بالكود ومطفأة (24 أكتوبر 2026) ──
# لا تدخل LEAGUES (وكل ما يتبعه: السحب، المواعيد، الصفحات، الترتيب الحي) إلا إن كانت بـENABLED_LEAGUES. الدمج وحده لا يغيّر شيئاً حياً.
# التفعيل: أضف الرمز هنا + نفس المعرّف بـPENDING_LEAGUE_IDS بـworker.js (ثم نشر الـworker و m فارغ) + أندية teams_pending.csv إلى
# teams_arabic.csv بأسمائها العربية ثم sync_teams.py. ما ينقص كل دوري عند المزوّد (عيّنة 19 أكتوبر: new_leagues_sample.md):
#   TUN: نتائج، هدّافون بمعرّفات، بطاقات وتبديلات، تشكيلتان بـ11 — بلا خطة/grid (قائمة لا ملعب) ولا إحصائيات مباراة/لاعبين
#   ALG: مثل TUN (بلا خطة/grid ولا إحصائيات)
#   KUW: نتائج وأحداث الردّ الحيّ فقط — بلا تشكيلات ولا بطاقات/تبديلات بالعيّنة، هدّافون ناقصو المعرّف (مثل JOR/IRQ: طبقة أساسية)
PENDING_LEAGUES = {
    "TUN": {"id": 202, "name_ar": "الدوري التونسي"},
    "ALG": {"id": 186, "name_ar": "الدوري الجزائري"},
    "KUW": {"id": 330, "name_ar": "الدوري الكويتي"},
}
ENABLED_LEAGUES = {"TUN", "ALG", "KUW"}   # 26 أكتوبر 2026: تونس، ثم الجزائر والكويت (استيراد ليلة 26 أكتوبر)
LEAGUES.update({c: v for c, v in PENDING_LEAGUES.items() if c in ENABLED_LEAGUES})

# ── الكؤوس (الموجة 0، 3 نوفمبر 2026 — cups_plan.md 3.1) ──
# سجلّ منفصل: LEAGUES لا يتغيّر (كل ما يفترض جدول ترتيب يبقى على الدوريات فقط). الرمز <بلد>-<كأس> أو AFC/CAF/GCC.
# type: cup | super | continental (الدوريات = "league" عبر competitions.comp_type). country = رمز دوري البلد، None للقارية.
# season/start/end = الموسم الجاري عند المزوّد (league.seasons[current]) بفحص 3 نوفمبر 2026 (cups_check.md) — موسم المزوّد
# ليس SEASON: كأس الملك 2027، كأس تونس 2025... التسمية المعروضة من التاريخين (competitions.season_label). لا تفعيل بعد:
# لا سحب ولا صفحات ولا بثّ لهذه الرموز حتى الموجة 1.
# (4 نوفمبر 2026، قرار عمرو) end لكأس لم يُجدوَل نهائيه بعد = آخر مباراة مجدولة عند المزوّد لا النهائي: SAU-KC → 2027-05-31،
#   و EGY-C / JOR-C / UAE-LC / KUW-EC / MAR-C / AFC-CL2 → 2027-06-30 (التسمية «2026/27»). صحّحه حين يُجدوَل النهائي.
COMPETITIONS = {
    "SAU-KC":  {"id": 504,  "type": "cup",   "country": "SAU", "name_ar": "كأس الملك", "name_en": "King's Cup",
                # end (4 نوفمبر 2026، قرار عمرو): المزوّد يعطي آخر مباراة مجدولة حتى الآن (1 ديسمبر، دور الـ16) لا النهائي —
                # النهائي بموسم 2026/27 = ربيع 2027 → 2027-05-31 فتكون التسمية «2026/27»
                "season": 2027, "start": "2026-08-16", "end": "2027-05-31"},
    "SAU-SC":  {"id": 826,  "type": "super", "country": "SAU", "name_ar": "كأس السوبر السعودي", "name_en": "Saudi Super Cup",
                "season": 2026, "start": "2025-08-19", "end": "2025-08-23"},
    "UAE-PC":  {"id": 560,  "type": "cup",   "country": "UAE", "name_ar": "كأس رئيس الدولة", "name_en": "UAE President's Cup",
                "season": 2026, "start": "2026-09-22", "end": "2027-02-28"},
    "UAE-LC":  {"id": 302,  "type": "cup",   "country": "UAE", "name_ar": "كأس رابطة المحترفين", "name_en": "UAE League Cup",
                "season": 2026, "start": "2026-09-19", "end": "2027-06-30"},
    "UAE-SC":  {"id": 896,  "type": "super", "country": "UAE", "name_ar": "كأس السوبر الإماراتي", "name_en": "UAE Super Cup",
                "season": 2026, "start": "2026-11-29", "end": "2026-11-29"},
    "EGY-C":   {"id": 714,  "type": "cup",   "country": "EGY", "name_ar": "كأس مصر", "name_en": "Egypt Cup",
                "season": 2026, "start": "2026-11-04", "end": "2027-06-30"},
    "EGY-LC":  {"id": 895,  "type": "cup",   "country": "EGY", "name_ar": "كأس الرابطة المصرية", "name_en": "Egyptian League Cup",
                "season": 2026, "start": "2026-10-08", "end": "2027-02-16"},
    "EGY-SC":  {"id": 539,  "type": "super", "country": "EGY", "name_ar": "كأس السوبر المصري", "name_en": "Egyptian Super Cup",
                "season": 2026, "start": "2025-11-06", "end": "2025-11-09"},
    "KUW-EC":  {"id": 720,  "type": "cup",   "country": "KUW", "name_ar": "كأس أمير الكويت", "name_en": "Kuwait Emir Cup",
                "season": 2026, "start": "2026-02-12", "end": "2027-06-30"},
    "KUW-CPC": {"id": 820,  "type": "cup",   "country": "KUW", "name_ar": "كأس ولي العهد الكويتي", "name_en": "Kuwait Crown Prince Cup",
                "season": 2025, "start": "2026-01-04", "end": "2026-02-25"},
    "KUW-SC":  {"id": 719,  "type": "super", "country": "KUW", "name_ar": "كأس السوبر الكويتي", "name_en": "Kuwait Super Cup",
                "season": 2025, "start": "2026-01-28", "end": "2026-02-01"},
    "JOR-C":   {"id": 863,  "type": "cup",   "country": "JOR", "name_ar": "كأس الأردن", "name_en": "Jordan Cup",
                "season": 2026, "start": "2026-10-07", "end": "2027-06-30"},
    "JOR-SH":  {"id": 816,  "type": "cup",   "country": "JOR", "name_ar": "درع الاتحاد الأردني", "name_en": "Jordan Shield Cup",
                "season": 2025, "start": "2025-08-28", "end": "2025-12-20"},
    "JOR-SC":  {"id": 838,  "type": "super", "country": "JOR", "name_ar": "كأس السوبر الأردني", "name_en": "Jordan Super Cup",
                "season": 2026, "start": "2026-08-21", "end": "2026-08-28"},
    "QAT-EC":  {"id": 824,  "type": "cup",   "country": "QAT", "name_ar": "كأس أمير قطر", "name_en": "Qatar Emir Cup",
                "season": 2026, "start": "2026-01-10", "end": "2026-05-09"},
    "QAT-SLC": {"id": 677,  "type": "cup",   "country": "QAT", "name_ar": "كأس نجوم قطر", "name_en": "QSL Cup",
                "season": 2026, "start": "2026-09-20", "end": "2027-01-07"},
    "QAT-QC":  {"id": 825,  "type": "cup",   "country": "QAT", "name_ar": "كأس قطر", "name_en": "Qatar Cup",
                "season": 2025, "start": "2026-09-01", "end": "2026-12-11"},
    "MAR-C":   {"id": 822,  "type": "cup",   "country": "MAR", "name_ar": "كأس العرش", "name_en": "Moroccan Throne Cup",
                "season": 2025, "start": "2026-05-15", "end": "2027-06-30"},
    "TUN-C":   {"id": 511,  "type": "cup",   "country": "TUN", "name_ar": "كأس تونس", "name_en": "Tunisian Cup",
                "season": 2025, "start": "2026-01-10", "end": "2026-05-31"},
    "TUN-SC":  {"id": 1194, "type": "super", "country": "TUN", "name_ar": "كأس السوبر التونسي", "name_en": "Tunisian Super Cup",
                "season": 2026, "start": "2026-08-15", "end": "2027-01-30"},
    "ALG-C":   {"id": 514,  "type": "cup",   "country": "ALG", "name_ar": "كأس الجمهورية الجزائرية", "name_en": "Algerian Cup",
                "season": 2025, "start": "2025-12-03", "end": "2026-05-02"},
    "ALG-SC":  {"id": 516,  "type": "super", "country": "ALG", "name_ar": "كأس السوبر الجزائري", "name_en": "Algerian Super Cup",
                "season": 2025, "start": "2026-01-17", "end": "2026-01-17"},
    "AFC-CLE": {"id": 17,   "type": "continental", "country": None, "region": "AFC", "name_ar": "دوري أبطال آسيا للنخبة",
                "name_en": "AFC Champions League Elite", "season": 2026, "start": "2026-08-11", "end": "2027-02-16"},
    "AFC-CL2": {"id": 18,   "type": "continental", "country": None, "region": "AFC", "name_ar": "دوري أبطال آسيا 2",
                "name_en": "AFC Champions League Two", "season": 2026, "start": "2026-08-12", "end": "2027-06-30"},
    "CAF-CL":  {"id": 12,   "type": "continental", "country": None, "region": "CAF", "name_ar": "دوري أبطال أفريقيا",
                "name_en": "CAF Champions League", "season": 2026, "start": "2026-09-04", "end": "2027-01-23"},
    "CAF-CC":  {"id": 20,   "type": "continental", "country": None, "region": "CAF", "name_ar": "كأس الكونفدرالية الأفريقية",
                "name_en": "CAF Confederation Cup", "season": 2026, "start": "2026-09-04", "end": "2027-01-23"},
    "GCC-CL":  {"id": 1162, "type": "continental", "country": None, "region": "GCC", "name_ar": "دوري أبطال الخليج",
                "name_en": "Gulf Champions League", "season": 2026, "start": "2026-10-13", "end": "2027-02-17"},
}

# (4 نوفمبر 2026، الموجة 1) الكؤوس المفعّلة: تُسحب بكل تشغيل (fetch_cups.py، ببوّابة المواعيد) وتُبنى صفحاتها (make_cups.py).
#   بقية السجلّ تبقى بلا سحب. البثّ الحي والتنبيهات للكؤوس لاحقاً (worker.js بلا معرّفاتها).
ENABLED_CUPS = ("SAU-KC", "SAU-SC", "UAE-SC", "EGY-SC", "KUW-SC", "JOR-SC", "QAT-QC", "TUN-SC", "ALG-SC")


def load_env():
    """بيقرأ ملف .env ويحوله لقاموس"""
    env_path = BASE_DIR / ".env"

    if not env_path.exists():
        return {}

    values = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # نتجاهل السطور الفاضية والتعليقات
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values


_env = load_env()
API_KEY = _env.get("API_FOOTBALL_KEY", "")


def check_key():
    """بيتأكد إنو المفتاح موجود، وبيطبع رسالة واضحة إذا لأ"""
    if not API_KEY or API_KEY == "ضع_مفتاحك_هنا":
        print("=" * 55)
        print("  ما في مفتاح")
        print("=" * 55)
        print("""
  اعمل ملف اسمه .env بنفس المجلد، وحط فيه سطر واحد:

      API_FOOTBALL_KEY=مفتاحك_هون

  بدون علامات تنصيص، وبدون مسافات حوالين =
        """)
        return False
    return True


def headers():
    """الهيدرز الجاهزة لطلبات الـAPI"""
    return {"x-apisports-key": API_KEY}


def clean_name(name):
    """يصفّي اسماً خاماً من المزوّد قبل التخزين — تلوّث نادر لكن
    موثَّق فعلياً (بند 44 بالـREADME): تاب حقيقي بنهاية النص،
    نمط باكسلاش-تي/إن حرفي (لا بايت تحكّم فعلي)، وكيانات HTML
    غير مفكوكة (`&apos;` بدل `'`). لا يصلح تشوّهاً أعمق بالاسم
    نفسه (تلك تحتاج مراجعة يدوية لا فلترة عامة)."""
    if not name:
        return name
    name = html.unescape(name)
    name = name.replace("\\t", "").replace("\\n", "")
    return name.strip()
