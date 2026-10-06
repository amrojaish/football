#!/usr/bin/env python3
"""
assets/player_names.json — {player_id: {"ar": ..., "en": ...}} للاعبي الدوريات السبعة بالموسم الحالي فقط
===========================================================================================================
يقرؤه worker saffara-live (من saffara.app، كاش ساعة) ليكتب اسم الهدّاف بإشعار الهدف.

المصدر: lineup_players ∪ player_stats لمباريات الموسم الحالي (أعلى season بجدول matches)، بمعرّف لاعب صالح.
• الإنجليزي: الأكثر تكراراً بين صيغ اللاعب (714 معرّفاً بصيغ إملائية متعددة) — كما يعرضه الموقع.
• العربي: فقط إن كان **مؤكداً بنفس قاعدة الموقع** — `player_ar` المطبَّق من players_ar.csv (apply_players_ar.py)،
  وبشرط: صيغة عربية واحدة لا غير لذلك المعرّف (31 معرّفاً بأكثر من صيغة = غير مؤكد فيُحذف عربيّه)، وليس ضمن
  translation_excluded.csv (تصادم هوية)، وليس ضمن player_ar_conflict_queue.csv بقرار فارغ (تعارض لم يُحسم).
  بلا عربي مؤكد يُحذف المفتاح "ar" (الـworker لا يضع إنجليزياً داخل نص عربي).
• ⚠️ **الأردن والعراق بلا أي صف بـlineup_players** (لا لاعبين بمعرّفات) — فالمفتاح الاحتياطي "_n": {"<team_id>|<اسم المزوّد>":
  {"ar": ...}} من جدول goals (موسم حالي + السابق، فهدّافو العام الماضي يغطون الفريق): اسم المزوّد المختصر ("A. Ersan")
  هو نفسه ما يرجعه fixtures/events. الـworker يبحث بالمعرّف أولاً ثم بهذا المفتاح. نفس شروط "العربي المؤكد".
⚠️ assets/ مجلد مولَّد يُمسح بالبناء النظيف: يعمل هذا بعد make_assets.py. قراءة فقط من football.db.
"""
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict

from config import BASE_DIR, DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "assets" / "player_names.json"


def read_csv(name):
    p = BASE_DIR / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    excluded_en = {(r.get("player_en") or "").strip() for r in read_csv("translation_excluded.csv")}
    pending = {(r.get("player_id") or "").strip() for r in read_csv("player_ar_conflict_queue.csv")
               if not (r.get("decision") or "").strip()}
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    season = con.execute("SELECT MAX(season) FROM matches").fetchone()[0]
    ens, ars = defaultdict(Counter), defaultdict(Counter)
    for tbl in ("lineup_players", "player_stats"):
        cols = "player_id, player_en, player_ar"
        for pid, en, ar in con.execute(
                f"SELECT {cols} FROM {tbl} t JOIN matches m ON m.match_id = t.match_id "
                f"WHERE m.season = ? AND player_id IS NOT NULL AND player_id != 0", (season,)):
            if (en or "").strip():
                ens[pid][en.strip()] += 1
            if (ar or "").strip():
                ars[pid][ar.strip()] += 1
    # الاحتياط بالاسم: goals (موسم حالي + السابق) — اسم المزوّد كما يرجع fixtures/events
    names_ar = defaultdict(Counter)
    for tid, en, ar in con.execute(
            "SELECT g.team_id, g.player_en, g.player_ar FROM goals g JOIN matches m ON m.match_id = g.match_id "
            "WHERE m.season >= ? AND g.player_en IS NOT NULL AND g.player_en != '' "
            "AND g.player_ar IS NOT NULL AND g.player_ar != ''", (season - 1,)):
        names_ar[(tid, en.strip())][ar.strip()] += 1
    con.close()
    out, n_ar, skipped = {}, 0, Counter()
    for pid in sorted(ens):
        en = ens[pid].most_common(1)[0][0]
        e = {"en": en}
        a = ars.get(pid)
        if a:
            if len(a) > 1:
                skipped["ar متعدد الصيغ"] += 1
            elif str(pid) in pending:
                skipped["ar بتعارض معلّق"] += 1
            elif any(x in excluded_en for x in ens[pid]):
                skipped["ar مستثنى (تصادم هوية)"] += 1
            else:
                e["ar"] = next(iter(a))
                n_ar += 1
        out[str(pid)] = e
    by_name = {}
    for (tid, en), c in sorted(names_ar.items()):
        if len(c) == 1 and en not in excluded_en:
            by_name[f"{tid}|{en}"] = {"ar": next(iter(c))}
        else:
            skipped["_n غير مؤكد (صيغ متعددة/مستثنى)"] += 1
    if by_name:
        out["_n"] = by_name
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"player_names.json: موسم {season} · {len(out) - (1 if by_name else 0)} لاعباً ({n_ar} بعربي مؤكد) + {len(by_name)} اسم احتياطي بالاسم · {size / 1024:.1f} ك.ب"
          + (f" · عربي محذوف: {dict(skipped)}" if skipped else "") + f" → {OUT}")


if __name__ == "__main__":
    main()
