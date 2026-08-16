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
        "site_title": "صافرة",
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
        "stats": "إحصائيات المباراة",
        "possession": "الاستحواذ",
        "shots": "التسديدات",
        "shots_on": "على المرمى",
        "corners": "الركنيات",
        "fouls": "الأخطاء",
        "offsides": "التسلل",
        "saves": "تصديات",
        "passes": "التمريرات",
        "pass_acc": "دقة التمرير",
        "xg": "الأهداف المتوقعة",
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
        "welcome": "أهلاً بك",
        "w_name": "شو اسمك؟",
        "w_name_ph": "اكتب اسمك",
        "w_leagues": "أي دوريات تتابع؟",
        "w_clubs": "أي أندية تشجّع؟",
        "skip": "تخطي",
        "next": "التالي",
        "done": "خلّصت",
        "my_clubs": "أنديتي",
        "settings": "الإعدادات",
        "change_prefs": "تغيير التفضيلات",
        "hi": "أهلاً",
        "back": "رجوع",
        "search_club": "ابحث عن نادٍ",
        "no_results": "ما في نتائج",
        # صفحة "عن الموقع"
        "about": "عن الموقع",
        "about_what": "ما هو صافرة",
        "about_what_1": "موقع نتائج وترتيب للدوري الأردني والعراقي والسعودي، بالعربية والإنجليزية. الفكرة بسيطة: الدوريات العربية تغطّيها التطبيقات الكبرى بشكل ناقص أو خاطئ، وهذا الموقع يحاول تغطيتها بدقة.",
        "about_data": "من أين البيانات",
        "about_data_1": "البيانات الأساسية — المباريات والنتائج والأهداف — من API-Football. أما أسماء الأندية بالعربية والإنجليزية، ومدنها، وشعاراتها، فمراجَعة ومصححة يدوياً.",
        "about_fix": "لماذا التصحيح اليدوي",
        "about_fix_1": "المزوّد يخطئ في الدوريات العربية بشكل منهجي: أسماء مختصرة أو خاطئة، شعار نادٍ يظهر لنادٍ آخر، مباريات من خارج الدوري تُحسب ضمنه، وأحياناً نتيجة نهائية خاطئة. كل تصحيح مسجَّل مع مصدره في ملف منفصل، ويُعاد تطبيقه تلقائياً بعد كل تحديث — لا تعديل مباشر على البيانات.",
        "about_verify": "التحقق",
        "about_verify_1": "جداول الترتيب تُقارَن صفاً بصف مع مصادر خارجية قبل النشر، لا بالنقاط وحدها. الموسم الأردني تم التحقق منه من موقع الاتحاد الأردني لكرة القدم.",
        "about_update": "التحديث",
        "about_update_1": "الموقع يحدّث نفسه آلياً كل 30 دقيقة.",
        "about_who": "من وراء الموقع",
        "about_contact": "للتواصل أو الإبلاغ عن خطأ",

        # صفحة 404
        "nf_title": "الصفحة غير موجودة",
        "nf_msg": "الرابط خطأ، أو الصفحة لم تعد موجودة.",
        "nf_home": "الصفحة الرئيسية",

        # الفوتر
        "footer_1": "الأسماء والشعارات المصححة من إعداد المطوّر",
        "footer_2": "البيانات الأساسية من API-Football",
    },

    "en": {
        # Header
        "site_title": "Whistle",
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
        "stats": "Match Stats",
        "possession": "Possession",
        "shots": "Shots",
        "shots_on": "On target",
        "corners": "Corners",
        "fouls": "Fouls",
        "offsides": "Offsides",
        "saves": "Saves",
        "passes": "Passes",
        "pass_acc": "Pass accuracy",
        "xg": "Expected goals",
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
        "welcome": "Welcome",
        "w_name": "What's your name?",
        "w_name_ph": "Type your name",
        "w_leagues": "Which leagues do you follow?",
        "w_clubs": "Which clubs do you support?",
        "skip": "Skip",
        "next": "Next",
        "done": "Done",
        "my_clubs": "My Clubs",
        "settings": "Settings",
        "change_prefs": "Change preferences",
        "hi": "Hi",
        "back": "Back",
        "search_club": "Search for a club",
        "no_results": "No results",
        # About page
        "about": "About",
        "about_what": "What is Whistle",
        "about_what_1": "Results and standings for the Jordanian, Iraqi and Saudi leagues, in Arabic and English. The idea is simple: major apps cover Arab leagues poorly or incorrectly, and this site tries to cover them accurately.",
        "about_data": "Where the data comes from",
        "about_data_1": "Core data — fixtures, results and goals — comes from API-Football. Club names in Arabic and English, their cities and their crests are reviewed and corrected by hand.",
        "about_fix": "Why manual correction",
        "about_fix_1": "The provider gets Arab leagues wrong in systematic ways: shortened or incorrect club names, one club's crest shown for another, matches from outside the league counted inside it, and occasionally a wrong final score. Every correction is recorded with its source in a separate file and reapplied automatically after each update — the data itself is never edited directly.",
        "about_verify": "Verification",
        "about_verify_1": "Standings are compared row by row against external sources before publishing, not by points alone. The Jordanian season was verified against the Jordan Football Association website.",
        "about_update": "Updates",
        "about_update_1": "The site updates itself automatically every 30 minutes.",
        "about_who": "Who is behind it",
        "about_contact": "Contact or report an error",

        # 404 page
        "nf_title": "Page not found",
        "nf_msg": "The link is wrong, or the page no longer exists.",
        "nf_home": "Home",

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
