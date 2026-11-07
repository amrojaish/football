#!/usr/bin/env python3
"""
معرّفات فرق مكرّرة عند المزوّد ← المعرّف المعتمد (الموجة 4، 6 نوفمبر 2026)
=========================================================================
config.TEAM_ID_ALIASES = {28571: 5242, 21137: 3463}: نفس النادي بمعرّفين عند المزوّد (دوري أبطال آسيا 2). كل ردّ fixtures يمرّ
بـalias_fixture قبل أي كتابة فالمعرّف القديم لا يدخل القاعدة أبداً. نقاط التطبيق:
    import_cups.import_code      (ومنه fetch_cups — وfetch_cups يطبّقها أيضاً على القائمة وردود ids= فور وصولها)
    fetch_overdue                (مباراة كأس فات موعدها تُكتب بـsave_finished)
    fetch_lineups --refetch      (تشكيلة ناقصة لمباراة كأس حديثة)
    refresh_goal_names           (أهداف ناقصة/بلا اسم لمباراة كأس منتهية)
وحدة مستقلة (تستورد config فقط) لتجنّب الاستيراد الدائري (import_cups ← fetch_lineups). صفر طلبات، بلا كتابة.
"""
from config import TEAM_ID_ALIASES


def alias_id(tid, aliases=None):
    al = TEAM_ID_ALIASES if aliases is None else aliases
    return al.get(tid, tid)


def alias_fixture(fx, aliases=None):
    """نسخة من ردّ المزوّد بكل معرّف فريق مكرّر ← المعتمد: teams.home/away، وكل {"team": {"id"}} بالأحداث والتشكيلات
    والإحصاءات واللاعبين. آمنة للتكرار؛ ردّ بلا معرّف مكرّر يرجع مساوياً للأصل."""
    al = TEAM_ID_ALIASES if aliases is None else aliases
    if not al or fx is None:
        return fx

    def walk(o, key=None, parent=None):
        if isinstance(o, dict):
            out = {k: walk(v, k, key) for k, v in o.items()}
            if (key == "team" or (parent == "teams" and key in ("home", "away"))) and out.get("id") in al:
                out["id"] = al[out["id"]]
            return out
        if isinstance(o, list):
            return [walk(v, key, parent) for v in o]
        return o
    return walk(fx)
