#!/usr/bin/env python3
"""
الترجمات — طبقة اللغة
=======================
كل نص ظاهر بالموقع موجود هنا. لا يُكتب أي نص عربي مباشرة
داخل سكربتات التوليد بعد اليوم.

الاستخدام:
    from i18n import T, LANGS, league_name

    t = T["ar"]          # أو T["en"]
    t["standings"]       # "جدول الترتيب" أو "Standings"

بنية الموقع:
    index.html           → العربي (الجذر)
    en/index.html        → الإنجليزي
    clubs/4532.html      → صفحة نادٍ عربية
    en/clubs/4532.html   → نفسها إنجليزية

⚠️ أسماء الأندية الإنجليزية تأتي من عمود name_en وهو **اسم المزوّد**
   لا الاسم الرسمي (مثال: Baghdad بدل Amanat Baghdad). مراجعتها
   مؤجلة لجلسة الأسماء مع أسماء اللاعبين العربية.
"""

LANGS = ["ar", "en"]

# اتجاه الصفحة ورمز اللغة
DIR = {"ar": "rtl", "en": "ltr"}
LANG_CODE = {"ar": "ar", "en": "en"}

# اسم اللغة الأخرى (للزر)
OTHER = {"ar": "en", "en": "ar"}
SWITCH_LABEL = {"ar": "EN", "en": "ع"}


T = {
    "ar": {
        # الرأس
        "site_title": "الدوريات العربية",
        "site_sub": "نتائج وترتيب الدوريات العربية",
        "season": "موسم",

        # الأقسام
        "standings": "جدول الترتيب",
        "results": "آخر النتائج",
        "scorers": "الهدافون",
        "club_scorers": "هدافو النادي",
        "all_matches": "كل المباريات",
        "match_events": "أحداث المباراة",

        # أعمدة الجدول
        "pos": "#",
        "team": "الفريق",
        "played": "لعب",
        "won": "فاز",
        "drawn": "تعادل",
        "lost": "خسر",
        "gf": "له",
        "ga": "عليه",
        "gd": "+/-",
        "points": "نقاط",

        # صفحة النادي
        "rank": "المركز",
        "back_home": "→ رجوع للصفحة الرئيسية",

        # الأزرار
        "show_all": "▼ عرض الكل",
        "show_all_matches": "▼ عرض كل المباريات",
        "show_all_scorers": "▼ عرض كل الهدافين",
        "show_less": "▲ عرض أقل",
        "view_all_events": "كل الأحداث",
        "view_key_events": "الأحداث المهمة",

        # صفحة المباراة
        "corrected": "⭐ نتيجة مصححة يدوياً",
        "source": "المصدر",
        "goalless": "انتهت بالتعادل السلبي",
        "not_started": "لم تبدأ بعد",
        "upcoming": "مباراة قادمة",
        "no_details": "لا تتوفر تفاصيل هذه المباراة",

        # أنواع الأهداف
        "penalty": "ركلة جزاء",
        "own_goal": "هدف عكسي",

        # رسائل
        "empty_combo": "ما في بيانات لهذا الدوري بهذا الموسم",
        "incomplete": "⚠️ الموسم غير مكتمل",
        "upcoming_matches": "المباريات القادمة",
        "latest_results": "آخر النتائج عبر الدوريات",
        "leagues": "الدوريات",

        # الفوتر
        "footer_1": "الأسماء والشعارات المصححة من إعداد المطوّر",
        "footer_2": "البيانات الأساسية من API-Football",
    },

    "en": {
        # Header
        "site_title": "Arab Leagues",
        "site_sub": "Results & Standings",
        "season": "Season",

        # Sections
        "standings": "Standings",
        "results": "Latest Results",
        "scorers": "Top Scorers",
        "club_scorers": "Club Top Scorers",
        "all_matches": "All Matches",
        "match_events": "Match Events",

        # Table columns
        "pos": "#",
        "team": "Team",
        "played": "P",
        "won": "W",
        "drawn": "D",
        "lost": "L",
        "gf": "GF",
        "ga": "GA",
        "gd": "+/-",
        "points": "Pts",

        # Club page
        "rank": "Position",
        "back_home": "← Back to home",

        # Buttons
        "show_all": "▼ Show all",
        "show_all_matches": "▼ Show all matches",
        "show_all_scorers": "▼ Show all scorers",
        "show_less": "▲ Show less",
        "view_all_events": "All events",
        "view_key_events": "Key events",

        # Match page
        "corrected": "⭐ Manually corrected result",
        "source": "Source",
        "goalless": "Ended goalless",
        "not_started": "Not started yet",
        "upcoming": "Upcoming match",
        "no_details": "No details available for this match",

        # Goal types
        "penalty": "Penalty",
        "own_goal": "Own goal",

        # Messages
        "empty_combo": "No data for this league in this season",
        "incomplete": "⚠️ Season incomplete",
        "upcoming_matches": "Upcoming Matches",
        "latest_results": "Latest Results",
        "leagues": "Leagues",

        # Footer
        "footer_1": "Corrected names and logos by the developer",
        "footer_2": "Base data from API-Football",
    },
}


# أسماء الدوريات — الرسمية بالإنجليزية
LEAGUE_NAMES = {
    "JOR": {"ar": "الدوري الأردني", "en": "Jordan Pro League"},
    "IRQ": {"ar": "الدوري العراقي", "en": "Iraq Stars League"},
    "SAU": {"ar": "الدوري السعودي", "en": "Saudi Pro League"},
}


def league_name(code, lang):
    """اسم الدوري باللغة المطلوبة"""
    return LEAGUE_NAMES.get(code, {}).get(lang, code)


def team_name(row, lang):
    """
    اسم النادي باللغة المطلوبة.
    row: قاموس أو صف فيه short_name_ar و name_en

    ⚠️ name_en هو اسم المزوّد — مراجعته مؤجلة.
    """
    if lang == "ar":
        return (row.get("short") or row.get("short_name_ar")
                or row.get("name_en") or "")
    return (row.get("name_en") or row.get("short")
            or row.get("short_name_ar") or "")


def goal_detail(detail, lang):
    """ترجمة نوع الهدف"""
    t = T[lang]
    return {
        "Normal Goal": "",
        "Penalty": t["penalty"],
        "Own Goal": t["own_goal"],
    }.get(detail, detail or "")


def prefix(lang, depth=0):
    """
    مسار الجذر النسبي حسب اللغة وعمق الصفحة.
    depth=0 للصفحة الرئيسية، depth=1 لصفحات clubs/ و matches/
    """
    return "../" * depth


def other_url(lang, page="index.html", depth=0):
    """
    رابط نفس الصفحة باللغة الأخرى.
    عربي (الجذر) → en/
    إنجليزي (en/) → الجذر
    """
    if lang == "ar":
        return ("../" * depth) + "en/" + page
    return ("../" * depth) + "../" + page
