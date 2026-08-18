#!/usr/bin/env python3
"""
روابط اللاعبين — وحدة مشتركة
===============================
مصدر واحد لتوليد رابط اللاعب من اسمه. **كل** السكربتات
تستوردها: make_players · make_clubs · make_site3 ·
make_matches · make_search.

    "Mohanad Ali"        → mohanad-ali
    "A. Hamed-Allah"     → a-hamed-allah
    "Rúben Neves"        → ruben-neves
    "M. Dembélé"         → m-dembele

⚠️ **لا تكرّر هذه الدالة في أي ملف آخر.** نسختان تختلفان
   بحرف واحد تعنيان روابط مكسورة بين الصفحات — والكشف صعب
   لأن كل صفحة تبدو سليمة وحدها.

⚠️ الرابط مبني على `player_en` لا العربي: العربي ناقص لـ97%
   من اللاعبين، والرابط لازم يكون مستقراً للغتين.

⚠️ **التصادم:** اسمان مختلفان قد يعطيان نفس الرابط
   (`Al-Ahli` و`Al Ahli`). `build_slug_map` يحلّها بإضافة
   لاحقة رقمية للأقل أهدافاً — والأكثر أهدافاً يحتفظ بالرابط
   النظيف حتى لا تتغيّر روابط النجوم.

الاستخدام:
    from player_slug import slug, build_slug_map
"""

import re
import unicodedata


def slug(name):
    """اسم اللاعب → جزء الرابط"""
    s = (name or "").strip()
    if not s:
        return ""

    # تجريد اللكنات: é → e ، ć → c
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))

    s = s.lower()
    # أي شيء غير حرف أو رقم → شرطة
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")

    return s or "player"


def build_slug_map(names_with_goals):
    """
    names_with_goals: قاموس {اسم: عدد الأهداف}
    يرجع: {اسم: رابط فريد}

    الأكثر أهدافاً يأخذ الرابط النظيف عند التصادم.
    """
    ordered = sorted(names_with_goals.items(),
                     key=lambda x: (-x[1], x[0]))

    used = {}
    out = {}

    for name, _ in ordered:
        base = slug(name)
        if not base:
            continue
        if base not in used:
            used[base] = 1
            out[name] = base
        else:
            used[base] += 1
            out[name] = f"{base}-{used[base]}"

    return out
