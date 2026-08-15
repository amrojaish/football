#!/usr/bin/env python3
"""
تصدير أسماء اللاعبين للترجمة
===============================
بيعمل ملف players_ar.csv فيه كل اللاعبين مرتبين **بالأولوية** —
الأكثر ظهوراً بالموقع أولاً.

عمود priority بيقول ليش هذا اللاعب مهم:
    A = من أفضل 10 هدافين بدوري/موسم  (يظهر بالصفحة الرئيسية)
    B = من أفضل 12 هدافاً بنادٍ        (يظهر بصفحة النادي)
    C = مخزّن فقط                      (لا يظهر حالياً)

⚠️ **لا يمحو الترجمات الموجودة** — إعادة التشغيل آمنة.

الاستراتيجية المقترحة:
    ترجم الفئة A أولاً (~200 اسم)، ثم B تدريجياً.
    اترك ما لا تتأكد منه فارغاً — الكود يرتد للإنجليزي.

التشغيل:
    python export_players_ar.py
    python export_players_ar.py JOR    <- دوري محدد
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT = BASE_DIR / "players_ar.csv"
ONLY = sys.argv[1].upper() if len(sys.argv) > 1 else None


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    combos = conn.execute("""
        SELECT DISTINCT league_code, season FROM matches
    """).fetchall()

    if ONLY:
        combos = [c for c in combos if c["league_code"] == ONLY]

    # ---- الفئة A: أفضل 10 بكل دوري/موسم ----
    cat_a = set()
    for c in combos:
        for r in conn.execute("""
            SELECT g.player_en FROM goals g
            JOIN matches m ON m.match_id = g.match_id
            WHERE g.player_en != '' AND m.league_code = ? AND m.season = ?
            GROUP BY g.player_en ORDER BY COUNT(*) DESC LIMIT 10
        """, (c["league_code"], c["season"])):
            cat_a.add(r["player_en"])

    # ---- الفئة B: أفضل 12 بكل نادٍ ----
    cat_b = set()
    for c in combos:
        for r in conn.execute("""
            SELECT g.player_en, g.team_id FROM goals g
            JOIN matches m ON m.match_id = g.match_id
            WHERE g.player_en != ''
              AND m.league_code = ? AND m.season = ?
            GROUP BY g.team_id, g.player_en
        """, (c["league_code"], c["season"])):
            cat_b.add(r["player_en"])

    # ---- كل اللاعبين مع أهدافهم وأنديتهم ----
    q = """
        SELECT g.player_en AS en,
               t.short_name_ar AS team_ar,
               m.league_code AS lg,
               COUNT(*) AS goals,
               MAX(g.player_ar) AS existing_ar
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        LEFT JOIN teams t ON t.team_id = g.team_id
        WHERE g.player_en != ''
    """
    params = []
    if ONLY:
        q += " AND m.league_code = ?"
        params.append(ONLY)
    q += """
        GROUP BY g.player_en
        ORDER BY goals DESC, g.player_en
    """

    rows = conn.execute(q, params).fetchall()

    # ---- الترجمات الموجودة من ملف سابق ----
    existing = {}
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                en = (r.get("player_en") or "").strip()
                ar = (r.get("player_ar") or "").strip()
                if en and ar:
                    existing[en] = ar
        print(f"لقيت {len(existing)} اسم مترجم من قبل — رح أحافظ عليهم")

    out = []
    for r in rows:
        en = r["en"]
        if en in cat_a:
            pri = "A"
        elif en in cat_b:
            pri = "B"
        else:
            pri = "C"

        ar = existing.get(en) or (r["existing_ar"] or "").strip()

        out.append({
            "priority": pri,
            "goals": r["goals"],
            "league": r["lg"],
            "team_ar": r["team_ar"] or "",
            "player_en": en,
            "player_ar": ar,
        })

    # الترتيب: الأولوية ثم الأهداف
    order = {"A": 0, "B": 1, "C": 2}
    out.sort(key=lambda x: (order[x["priority"]], -x["goals"]))

    conn.close()

    if not out:
        print("ما في لاعبين")
        return

    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    n_a = sum(1 for x in out if x["priority"] == "A")
    n_b = sum(1 for x in out if x["priority"] == "B")
    n_c = sum(1 for x in out if x["priority"] == "C")
    done = sum(1 for x in out if x["player_ar"])

    print(f"\n{'=' * 58}")
    print(f"  تم: {OUTPUT.name}   ({len(out)} لاعب)")
    print(f"{'=' * 58}")
    print(f"  A — يظهر بقوائم الدوريات  : {n_a}")
    print(f"  B — يظهر بصفحات الأندية   : {n_b}")
    print(f"  C — مخزّن فقط             : {n_c}")
    print(f"\n  مترجَم: {done}   |   ناقص: {len(out) - done}")
    print(f"""
{'=' * 58}
  المطلوب:
  افتح players_ar.csv وعبّي عمود player_ar

  ابدأ بالفئة A — هي أعلى الملف، وتغطي كل ما يظهر
  بالصفحة الرئيسية وقوائم الهدافين.

  ⚠️ اللي ما بتتأكد منه اتركه فاضي — الكود بيرجع
     للإنجليزي، والاسم المخمّن الخاطئ أسوأ من الإنجليزي.

  بعد التعبئة:
      python apply_players_ar.py
{'=' * 58}
    """)


if __name__ == "__main__":
    main()
