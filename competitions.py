#!/usr/bin/env python3
"""
سجلّ المسابقات (الموجة 0 للكؤوس، 3 نوفمبر 2026 — cups_plan.md 3.1)
=====================================================================
مصدر واحد للسؤال «هل هذا الرمز دوري أم كأس؟» لكل السكربتات:
    config.LEAGUES        الدوريات (بلا تغيير) ← comp_type = "league"
    config.COMPETITIONS   الكؤوس والسوبر والقارية (27 رمزاً) ← cup | super | continental
رمز غير معروف (لا هنا ولا هناك) يُعامَل كما كان قبل الموجة 0 (دوري) فلا يتغيّر سلوك أي اختبار/أداة قديمة.

⚠️ القاعدة: كل ما يفترض جدول ترتيب (get_table، الترتيب المباشر، المركز، نقاط الفورمة) يُطفأ لـis_cup(code) فقط.
⚠️ موسم المزوّد للكأس ليس config.SEASON (كأس الملك 2027 يُلعب 2026) — التسمية المعروضة من تاريخي الموسم (season_label).
"""
from config import COMPETITIONS, LEAGUES, PUSH_CUPS

TYPES = ("league", "cup", "super", "continental")


def comp(code):
    """مدخل السجلّ (dict) لكأس، أو None (دوري/غير معروف)"""
    return COMPETITIONS.get(code)


def is_cup(code):
    """True لأي رمز بـCOMPETITIONS (كأس/سوبر/قارية) — كل ما عداه يبقى بسلوك الدوري"""
    return code in COMPETITIONS


def push_on(code):
    """(مرحلة 2 للكؤوس) تنبيهات هذا الكأس مفعّلة (config.PUSH_CUPS)؟"""
    return code in PUSH_CUPS


PUSH_CUP_CLUBS = set()   # أندية الكؤوس المفعّلة التنبيهات: يملؤها make_clubs.main (فارغ والمفتاح مطفأ)


def push_cup_clubs(conn):
    """{team_id} لمن يلعب بكأس تنبيهاته مفعّلة — بلا استعلام والمفتاح مطفأ"""
    if not PUSH_CUPS:
        return set()
    q = ", ".join("?" * len(PUSH_CUPS))
    return {r[0] for r in conn.execute(f"SELECT home_id FROM matches WHERE league_code IN ({q}) UNION "
                                       f"SELECT away_id FROM matches WHERE league_code IN ({q})", tuple(PUSH_CUPS) * 2)}


def is_league(code):
    return code in LEAGUES


def comp_type(code):
    """league | cup | super | continental | None (غير معروف)"""
    if code in LEAGUES:
        return "league"
    c = COMPETITIONS.get(code)
    return c["type"] if c else None


def provider_id(code):
    """معرّف المزوّد للدوري أو الكأس، أو None"""
    c = LEAGUES.get(code) or COMPETITIONS.get(code)
    return c["id"] if c else None


def code_of(provider_league_id):
    """الرمز من معرّف المزوّد (دوري أولاً)، أو None"""
    for reg in (LEAGUES, COMPETITIONS):
        for k, v in reg.items():
            if v["id"] == provider_league_id:
                return k
    return None


def country_of(code):
    """رمز دوري البلد (للعلم/اسم البلد): الدوري نفسه، أو بلد الكأس، أو None (قارية/غير معروف)"""
    if code in LEAGUES:
        return code
    c = COMPETITIONS.get(code)
    return c.get("country") if c else None


def name(code, lang):
    """اسم الكأس بالسجلّ، أو None (الدوريات: i18n.LEAGUE_NAMES)"""
    c = COMPETITIONS.get(code)
    if not c:
        return None
    return c["name_ar"] if lang == "ar" else c["name_en"]


def label_from_dates(start, end):
    """«2026» إن بدأ الموسم وانتهى بنفس السنة الميلادية، وإلا «2026/27». start/end نص ISO أو date."""
    ys, ye = (int(str(x)[:4]) for x in (start, end))
    return str(ys) if ye <= ys else f"{ys}/{str(ys + 1)[-2:]}"


def season_label(code, season):
    """تسمية موسم الكأس للعرض (للرموز غير الدورية فقط؛ None للدوري/غير المعروف — يبقى «2026/27» الخاص به).
    الموسم الجاري بالسجلّ: من تاريخيه. موسم آخر: بنفس الإزاحة والشكل (سنة البداية = الموسم + (سنة بداية الجاري − الجاري))."""
    c = COMPETITIONS.get(code)
    if not c:
        return None
    s = int(season)
    if s == c["season"]:
        return label_from_dates(c["start"], c["end"])
    off = int(c["start"][:4]) - c["season"]
    span = int(c["end"][:4]) > int(c["start"][:4])
    y = s + off
    return f"{y}/{str(y + 1)[-2:]}" if span else str(y)


def current_season(code):
    """موسم المزوّد الجاري للكأس (السجلّ)، أو None"""
    c = COMPETITIONS.get(code)
    return c["season"] if c else None


def no_cup_sql(col="league_code"):
    """(4 نوفمبر 2026، الموجة 1 — بوّابة اللاعبين) جزء SQL بلا معاملات: «col ليس رمز كأس» — الرموز ثابتة من السجلّ (أحرف/شرطة)
    فتُضمَّن نصّاً فلا تتغيّر معاملات أي استعلام قائم. لصفحات اللاعبين وروابطها وملفاتها: الكؤوس خارجها حتى موجة لاحقة."""
    return f"{col} NOT IN ({_cup_list()})"


def no_cup_except_push_sql(col="league_code"):
    """مثل no_cup_sql لكن كؤوس التنبيهات المفعّلة تُحسب (أسماء الهدّافين). المفتاح مطفأ = النص نفسه حرفياً."""
    return f"{col} NOT IN ({', '.join(repr(c) for c in sorted(COMPETITIONS) if c not in PUSH_CUPS)})" if PUSH_CUPS else no_cup_sql(col)


def _cup_list():
    return ", ".join(repr(c) for c in sorted(COMPETITIONS))


def career_season(code, season):
    """(8 نوفمبر 2026) موسم الدوري المقابل لنسخة الكأس بتبويب المسيرة: سنة بداية النسخة، وناقص 1 إن بدأت بنصف السنة الأول
    (كأس يناير-مايو 2026 ينتمي لموسم 2025/26). موسم المزوّد لا يصلح: كأس الملك 2026/27 موسمه 2027. غير الكؤوس = كما هو."""
    c = COMPETITIONS.get(code)
    if not c:
        return season
    y = int(c["start"][:4]) + int(season) - c["season"]
    return y - 1 if int(c["start"][5:7]) < 7 else y


def only_cup_match_sql(col="match_id"):
    """عكس no_cup_match_sql: مباريات الكؤوس وحدها (لفهرس أدلة الكؤوس بـplayer_pages)"""
    return f"{col} IN (SELECT match_id FROM matches WHERE league_code IN ({_cup_list()}))"


def no_cup_match_sql(col="match_id"):
    """مثل no_cup_sql لجداول بلا league_code (goals/lineup_players/player_stats): «المباراة ليست مباراة كأس»"""
    return f"{col} NOT IN (SELECT match_id FROM matches WHERE league_code IN ({_cup_list()}))"


def league_codes_sql():
    """(جزء SQL، معاملات) يستثني رموز الكؤوس — لاستعلامات «أحدث موسم» العامة (MAX(season)) فلا يرفعها موسم كأس 2027"""
    codes = sorted(COMPETITIONS)
    return f"league_code NOT IN ({', '.join('?' * len(codes))})", codes


if __name__ == "__main__":
    for k, v in COMPETITIONS.items():
        print(f"{k:8} {v['id']:>5} {v['type']:12} {v.get('country') or v.get('region'):4} "
              f"{v['season']} → {season_label(k, v['season'])}  {v['name_en']}")
