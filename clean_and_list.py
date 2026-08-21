#!/usr/bin/env python3
"""
تنظيف الترجمات المعطوبة + قائمة ما يحتاج ترجمة
=================================================
دفعة `translated_players.txt` أنتجت **569 ترجمة معطوبة** —
نصف عربية نصف إنجليزية:

    Radhi Al Otaibi      →  "Radhi ال العتيبي"
    Mohammed Al Khabrani →  "محمد ال Khabrani"
    Abdullah Al Muaiouf  →  "عبدالله ال Muaiouf"

⚠️ النمط: ترجمة آلية حوّلت `Al` إلى `ال` وتركت الباقي إنجليزياً.
   **هذا أسوأ من الإنجليزي الكامل** — يخالف قاعدة المشروع:
   "الإنجليزي أفضل من العربي الخطأ".

ما يفعله:
    1. يحذف أي ترجمة تحوي حرفاً لاتينياً (تُفرَّغ، فيرتد الاسم
       للإنجليزي الكامل)
    2. يكتب `need_translation.txt` — كل اسم بلا ترجمة صحيحة،
       من **كل** جداول الديتابيس، مرتّباً بعدد الظهور

⚠️ نسخة احتياطية `players_ar_before_clean.csv` قبل أي كتابة.

التشغيل:
    python clean_and_list.py --check    <- عرض فقط
    python clean_and_list.py            <- تنفيذ
"""

import csv
import io
import os
import shutil
import sqlite3
import sys
from collections import defaultdict

CSV_FILE = "players_ar.csv"
DB = "football.db"
OUT = "need_translation.txt"
CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def has_latin(s):
    return any("a" <= c.lower() <= "z" for c in (s or ""))


def main():
    if not os.path.exists(CSV_FILE):
        print("ما لقيت players_ar.csv")
        return

    rows = list(csv.DictReader(
        io.open(CSV_FILE, encoding="utf-8-sig")))

    broken = [r for r in rows
              if (r["player_ar"] or "").strip()
              and has_latin(r["player_ar"])]

    print()
    print("=" * 60)
    print(f"  صفوف الملف        : {len(rows):,}")
    print(f"  ترجمات معطوبة     : {len(broken):,}")
    print("=" * 60)

    if broken:
        print("\n  عيّنة مما سيُحذف:")
        for r in broken[:10]:
            print(f"    {r['player_en']:<28} → {r['player_ar']}")

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    # ── 1. التنظيف ───────────────────────────────────
    if broken:
        shutil.copy(CSV_FILE, "players_ar_before_clean.csv")
        for r in broken:
            r["player_ar"] = ""

        with io.open(CSV_FILE, "w", encoding="utf-8-sig",
                     newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "priority", "goals", "league", "team_ar",
                "player_en", "player_ar"])
            w.writeheader()
            w.writerows(rows)

        print(f"\n  ✅ نُظِّف {len(broken):,} صفاً")
        print("     نسخة احتياطية: players_ar_before_clean.csv")

    # ── 2. جمع كل الأسماء من الديتابيس ───────────────
    good = {r["player_en"] for r in rows
            if (r["player_ar"] or "").strip()}

    counts = defaultdict(int)
    teams_of = defaultdict(set)
    team_names = {}

    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row

        for r in conn.execute(
                "SELECT team_id, short_name_ar FROM teams"):
            team_names[r["team_id"]] = (r["short_name_ar"]
                                        or str(r["team_id"]))

        for tbl in ("goals", "lineup_players", "player_stats",
                    "events"):
            try:
                cols = {c[1] for c in conn.execute(
                    f"PRAGMA table_info({tbl})")}
                if "player_en" not in cols:
                    continue
                sel_tm = ("team_id" if "team_id" in cols
                          else "NULL AS team_id")
                for r in conn.execute(f"""
                        SELECT player_en, {sel_tm} FROM {tbl}
                        WHERE player_en IS NOT NULL
                          AND player_en != ''
                    """):
                    en = r["player_en"]
                    counts[en] += 1
                    if r["team_id"]:
                        teams_of[en].add(r["team_id"])
            except sqlite3.Error:
                pass
        conn.close()

    need = [(en, c) for en, c in counts.items() if en not in good]
    need.sort(key=lambda x: -x[1])

    print()
    print("=" * 60)
    print(f"  أسماء بالديتابيس  : {len(counts):,}")
    print(f"  مترجَمة صحيحاً    : {len(good):,}")
    print(f"  **تحتاج ترجمة**   : {len(need):,}")
    print("=" * 60)

    # ── 3. كتابة الملف ───────────────────────────────
    out = io.StringIO()
    out.write(f"أسماء تحتاج ترجمة — {len(need)} اسماً\n")
    out.write("مرتّبة بعدد الظهور (الأكثر أولاً)\n")
    out.write("=" * 55 + "\n\n")

    for en, c in need:
        tms = sorted(teams_of.get(en) or [])
        tname = team_names.get(tms[0], "") if tms else ""
        extra = f"   [{tname}]" if tname else ""
        out.write(f"{en}{extra}\n")

    io.open(OUT, "w", encoding="utf-8").write(out.getvalue())

    print(f"\n  كُتب {OUT}")
    print("""
  ⚠️ ترجمها **كاملة بالعربي** — لا تترك أي حرف لاتيني.
     "محمد ال Khabrani" مرفوضة؛ إما "محمد الخبراني" أو تُترك
     فارغة تماماً.

  بعد الترجمة:
      ابعت الملف وأطبّقه
    """)


if __name__ == "__main__":
    main()
