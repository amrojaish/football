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
                "season": 2026, "start": "2026-09-19", "end": "2027-06-30", "table": "league"},
    "UAE-SC":  {"id": 896,  "type": "super", "country": "UAE", "name_ar": "كأس السوبر الإماراتي", "name_en": "UAE Super Cup",
                "season": 2026, "start": "2026-11-29", "end": "2026-11-29"},
    "EGY-C":   {"id": 714,  "type": "cup",   "country": "EGY", "name_ar": "كأس مصر", "name_en": "Egypt Cup",
                "season": 2026, "start": "2026-11-04", "end": "2027-06-30"},
    "EGY-LC":  {"id": 895,  "type": "cup",   "country": "EGY", "name_ar": "كأس الرابطة المصرية", "name_en": "Egyptian League Cup",
                "season": 2026, "start": "2026-10-07", "end": "2027-02-16", "table": "groups",
                "groups": (
                    {"ar": "المجموعة الأولى", "en": "Group 1", "teams": (1039, 1040, 1046, 1572, 7520)},
                    {"ar": "المجموعة الثانية", "en": "Group 2", "teams": (1036, 1044, 13822, 15570, 16431)},
                    {"ar": "المجموعة الثالثة", "en": "Group 3", "teams": (1037, 1574, 1575, 1577, 18021)},
                    {"ar": "المجموعة الرابعة", "en": "Group 4", "teams": (1031, 1041, 13819, 14651, 15731)},
                )},
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
                "season": 2025, "start": "2025-08-28", "end": "2025-12-28", "table": "league"},
    "JOR-SC":  {"id": 838,  "type": "super", "country": "JOR", "name_ar": "كأس السوبر الأردني", "name_en": "Jordan Super Cup",
                "season": 2026, "start": "2026-08-21", "end": "2026-08-28"},
    "QAT-EC":  {"id": 824,  "type": "cup",   "country": "QAT", "name_ar": "كأس أمير قطر", "name_en": "Qatar Emir Cup",
                "season": 2026, "start": "2026-01-10", "end": "2026-05-09"},
    "QAT-SLC": {"id": 677,  "type": "cup",   "country": "QAT", "name_ar": "كأس نجوم قطر", "name_en": "QSL Cup",
                "season": 2026, "start": "2026-09-20", "end": "2027-01-07", "table": "league", "table_line": 8},
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
                "name_en": "AFC Champions League Elite", "season": 2026, "start": "2026-08-11", "end": "2027-02-16",
                "table": "groups", "table_line": 8, "tiebreak": "league",
                "groups": (
                    {"ar": "غرب آسيا", "en": "West", "teams": (2733, 2737, 2865, 2870, 2872, 2895, 2903, 2916, 2929, 2932, 2933, 2938, 2939, 4217, 4220, 8009)},
                    {"ar": "شرق آسيا", "en": "East", "teams": (281, 289, 290, 293, 302, 830, 836, 946, 2523, 2750, 2762, 2764, 2776, 2780, 2789, 16400)},
                )},
    "AFC-CL2": {"id": 18,   "type": "continental", "country": None, "region": "AFC", "name_ar": "دوري أبطال آسيا 2",
                "name_en": "AFC Champions League Two", "season": 2026, "start": "2026-08-12", "end": "2027-06-30",
                "table": "groups", "table_line": 2, "tiebreak": "h2h",
                "groups": (
                    {"ar": "المجموعة A", "en": "Group A", "teams": (2875, 3535, 4215, 17666)},
                    {"ar": "المجموعة B", "en": "Group B", "teams": (2714, 2871, 5488, 21232)},
                    {"ar": "المجموعة C", "en": "Group C", "teams": (2897, 2936, 4531, 5327)},
                    {"ar": "المجموعة D", "en": "Group D", "teams": (3463, 4532, 5242, 7504)},
                    {"ar": "المجموعة E", "en": "Group E", "teams": (944, 2445, 2766, 3681)},
                    {"ar": "المجموعة F", "en": "Group F", "teams": (948, 2769, 4204, 4457)},
                    {"ar": "المجموعة G", "en": "Group G", "teams": (303, 833, 4206, 5396)},
                    {"ar": "المجموعة H", "en": "Group H", "teams": (2746, 4453, 5394, 10108)},
                )},
    "CAF-CL":  {"id": 12,   "type": "continental", "country": None, "region": "CAF", "name_ar": "دوري أبطال أفريقيا",
                "name_en": "CAF Champions League", "season": 2026, "start": "2026-09-04", "end": "2027-01-23",
                "table": "groups", "table_line": 2, "tiebreak": "h2h"},
    "CAF-CC":  {"id": 20,   "type": "continental", "country": None, "region": "CAF", "name_ar": "كأس الكونفدرالية الأفريقية",
                "name_en": "CAF Confederation Cup", "season": 2026, "start": "2026-09-04", "end": "2027-01-23",
                "table": "groups", "table_line": 2, "tiebreak": "h2h"},
    "GCC-CL":  {"id": 1162, "type": "continental", "country": None, "region": "GCC", "name_ar": "دوري أبطال الخليج",
                "name_en": "Gulf Champions League", "season": 2026, "start": "2026-10-13", "end": "2027-02-17",
                "table": "groups", "table_line": 2, "tiebreak": "h2h",
                "groups": (
                    {"ar": "المجموعة الأولى", "en": "Group 1", "teams": (2904, 5329, 10513, 23356)},
                    {"ar": "المجموعة الثانية", "en": "Group 2", "teams": (2907, 5482, 8010, 10155)},
                    {"ar": "المجموعة الثالثة", "en": "Group 3", "teams": (2879, 2934, 3540, 11070)},
                )},
}

# (6 نوفمبر 2026، الموجة 3 — بناء محلي) "table": مرحلة مجموعات/دوري تُعرض جداولها بتبويب «الجدول» (cup_tables.py):
#   "groups" = مجموعات تُستخرج من المواجهات (EGY-LC)، "league" = جدول واحد (UAE-LC، QAT-SLC، JOR-SH)؛ "table_line" = خط تحت المركز N.
#   تواريخ مصحّحة لأول/آخر مباراة فعلية: EGY-LC تبدأ 2026-10-07، JOR-SH تنتهي 2025-12-28.
# (6 نوفمبر 2026، الموجة 4 — بناء محلي) AFC-CLE / AFC-CL2: "groups" = أسماء المجموعات الرسمية بعضوية الفرق (من /standings المخبّأ)
#   تُعرض بترتيب القائمة؛ "tiebreak": "h2h" (AFC-CL2) = النقاط ← نقاط/فارق/أهداف المواجهات بين المتعادلين ← الفارق العام ← الأهداف ← الاسم؛
#   "league" (AFC-CLE، مرحلة دوري: المتعادلون غالباً لم يلتقوا) = النقاط ← الفارق ← الأهداف ← الانتصارات ← المعرّف تصاعدياً (= ترتيب المزوّد).
#   كؤوس الموجة 3 بلا "groups"/"tiebreak" = الترتيب القديم حرفياً (مجموعات مرقّمة بالمواجهات، النقاط ← الفارق ← الأهداف ← الاسم).

# (6 نوفمبر 2026، الموجة 4) معرّفات فرق مكرّرة عند المزوّد ← المعرّف المعتمد عندنا. تُطبَّق على كل ردّ قبل الكتابة
#   (team_alias.alias_fixture: import_cups/fetch_cups، fetch_overdue، fetch_lineups --refetch، refresh_goal_names): الصف والأهداف
#   والأحداث والتشكيلات والإحصاءات. المعرّف القديم لا يدخل القاعدة أبداً.
#   28571 «Al Shorta» (دوري أبطال آسيا 2) = 5242 الشرطة العراقي؛ 21137 «East Bengal II» = 3463 East Bengal.
TEAM_ID_ALIASES = {28571: 5242, 21137: 3463}

# (8 نوفمبر 2026، الموجة 5ب) بلد النادي حين يخطئ المزوّد: هذا الملف هو المرجع، ولا يكتب فوقه أي سحب.
#   19116 «15 أغسطس»: المزوّد يقول Paraguay، والصحيح غينيا الاستوائية.
TEAM_COUNTRY_OVERRIDES = {19116: "Equatorial-Guinea"}

# (4 نوفمبر 2026، الموجة 1) الكؤوس المفعّلة: تُسحب بكل تشغيل (fetch_cups.py، ببوّابة المواعيد) وتُبنى صفحاتها (make_cups.py).
#   بقية السجلّ تبقى بلا سحب. البثّ الحي والتنبيهات للكؤوس لاحقاً (worker.js بلا معرّفاتها).
# (5 نوفمبر 2026، الموجة 2a) +7 كؤوس: UAE-PC، EGY-C، KUW-EC، KUW-CPC، JOR-C، QAT-EC، MAR-C.
# (6 نوفمبر 2026، الموجة 2b) +2: TUN-C، ALG-C (موسم 2025 = نسخة 2025/26 المكتملة؛ نسخة 2026/27 بلا مباريات عند المزوّد بعد).
# (6 نوفمبر 2026، الموجة 3) +4 بمرحلة مجموعات/دوري (تبويب «الجدول»): UAE-LC، EGY-LC، QAT-SLC، JOR-SH (منتهية — الاكتشاف اليومي فقط).
# (6 نوفمبر 2026، الموجة 4) +2 قاريّة بمجموعات مسمّاة: AFC-CLE (غرب/شرق آسيا)، AFC-CL2 (المجموعات A-H).
ENABLED_CUPS = ("SAU-KC", "SAU-SC", "UAE-SC", "EGY-SC", "KUW-SC", "JOR-SC", "QAT-QC", "TUN-SC", "ALG-SC",
                "UAE-PC", "EGY-C", "KUW-EC", "KUW-CPC", "JOR-C", "QAT-EC", "MAR-C", "TUN-C", "ALG-C",
                "UAE-LC", "EGY-LC", "QAT-SLC", "JOR-SH",
                "AFC-CLE", "AFC-CL2",
                "GCC-CL",
                "CAF-CL", "CAF-CC")

# (8 نوفمبر 2026، بثّ الكؤوس مرحلة 1) كؤوس بنتيجة حيّة فقط، بلا أي تنبيه: تطابق LIVE_ONLY_LEAGUE_IDS بـworker.js (معرّفات المزوّد).
#   make_kickoffs يضيف مواعيدها لنافذة السحب (k) فقط — لا تذكير ولا تشكيلات (f) ولا تصويت (v).
LIVE_CUPS = ("UAE-LC",)


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
