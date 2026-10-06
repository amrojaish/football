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

from config import BASE_DIR, DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "assets" / "team_names.json"


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
    con.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    no_ar = sum(1 for v in out.values() if "ar" not in v)
    print(f"team_names.json: {len(out)} فريق ({no_ar} بلا عربي) → {OUT}")


if __name__ == "__main__":
    main()
