"""
assets/team_names.json — {team_id: {"ar": ..., "en": ...}} لأندية الدوريات السبعة (جدول teams).

يقرؤه worker saffara-live (من saffara.app، كاش ساعة) ليكتب أسماء الفرق بإشعارات الأهداف.
القاعدة نفس الموقع (i18n.team_name / make_clubs.tname): عربي = الاسم المختصر، وإن لم يوجد فالكامل،
وإن لم يوجد أي عربي يُحذف المفتاح "ar" فيستعمل الـworker الإنجليزي. إنجليزي = الرسمي ثم اسم المزوّد.
⚠️ assets/ مجلد مولَّد يُمسح بالبناء النظيف: هذا يشتغل بعد make_assets.py.
"""
import json
import sqlite3
import sys

from config import BASE_DIR, COMPETITIONS, DB_FILE, ENABLED_CUPS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "assets" / "team_names.json"
CUP_TEAMS_OUT = BASE_DIR / "assets" / "cup_teams.json"


def cup_teams(con):
    """(9 نوفمبر 2026، مرحلة 2 للكؤوس) {معرّف المزوّد للكأس: [فرقه]} لكل كأس مفعّل — يقرؤه الـworker لقبول متابعة أندية الكؤوس حين يُفعَّل تنبيه كأسها"""
    out = {}
    for code in ENABLED_CUPS:
        ids = sorted(r[0] for r in con.execute("SELECT home_id FROM matches WHERE league_code = ? AND home_id IS NOT NULL UNION "
                                               "SELECT away_id FROM matches WHERE league_code = ? AND away_id IS NOT NULL", (code, code)))
        if ids:
            out[str(COMPETITIONS[code]["id"])] = ids
    return out


def main():
    con = sqlite3.connect(DB_FILE)
    out = {}
    for tid, en_off, en, short, full in con.execute(
            "SELECT team_id, name_en_official, name_en, short_name_ar, name_ar FROM teams ORDER BY team_id"):
        e = {}
        ar = (short or "").strip() or (full or "").strip()
        if ar:
            e["ar"] = ar
        e["en"] = (en_off or "").strip() or (en or "").strip()
        out[str(tid)] = e
    cups = cup_teams(con)
    con.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    no_ar = sum(1 for v in out.values() if "ar" not in v)
    print(f"team_names.json: {len(out)} فريق ({no_ar} بلا عربي) → {OUT}")
    CUP_TEAMS_OUT.write_text(json.dumps(cups, separators=(",", ":")), encoding="utf-8")
    print(f"cup_teams.json: {len(cups)} كأساً → {CUP_TEAMS_OUT}")


if __name__ == "__main__":
    main()
