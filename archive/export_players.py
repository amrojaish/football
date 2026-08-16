#!/usr/bin/env python3
"""
استخراج أسماء اللاعبين للترجمة
================================
بيطلع كل اللاعبين اللي سجّلوا أهداف من الديتابيس،
وبيعمل ملف players_arabic.csv عشان تعبّي الأسماء العربية.

صفر طلبات API — كله من الديتابيس المحلية.

التشغيل:
    python export_players.py           <- كل الدوريات
    python export_players.py JOR       <- الأردني بس
"""

import sqlite3
import csv
import sys
from config import DB_FILE, BASE_DIR, LEAGUES

OUTPUT = BASE_DIR / "players_arabic.csv"


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    code = sys.argv[1].upper() if len(sys.argv) > 1 else None

    if code and code not in LEAGUES:
        print(f"دوري غير معروف: {code}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # نجيب كل لاعب مع فريقه ودوريه وعدد أهدافه
    query = """
        SELECT
            g.player_en,
            m.league_code,
            t.short_name_ar AS team_ar,
            t.team_id,
            COUNT(*) AS goals
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        JOIN teams t   ON t.team_id  = g.team_id
        WHERE g.player_en != ''
    """
    params = []

    if code:
        query += " AND m.league_code = ?"
        params.append(code)

    query += """
        GROUP BY g.player_en, m.league_code, t.short_name_ar, t.team_id
        ORDER BY m.league_code, goals DESC, g.player_en
    """

    rows = conn.execute(query, params).fetchall()

    # نقرأ الترجمات الموجودة مسبقاً عشان ما نضيّع شغلك
    existing = {}
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (r.get("player_en", "").strip(),
                       r.get("league_code", "").strip())
                name_ar = (r.get("player_ar") or "").strip()
                if name_ar:
                    existing[key] = name_ar
        print(f"لقيت {len(existing)} اسم مترجم من قبل — رح أحافظ عليهم")

    out_rows = []
    for r in rows:
        key = (r["player_en"], r["league_code"])
        out_rows.append({
            "league_code": r["league_code"],
            "team_id": r["team_id"],
            "team_ar": r["team_ar"],
            "player_en": r["player_en"],
            "player_ar": existing.get(key, ""),
            "goals": r["goals"],
        })

    conn.close()

    if not out_rows:
        print("ما في لاعبين — شغّل build_db أول")
        return

    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    # إحصائيات حسب الدوري
    by_league = {}
    filled = 0
    for r in out_rows:
        by_league[r["league_code"]] = by_league.get(r["league_code"], 0) + 1
        if r["player_ar"]:
            filled += 1

    print(f"\n{'=' * 55}")
    print(f"  تم: {OUTPUT.name}")
    print(f"{'=' * 55}")
    for lg, n in by_league.items():
        print(f"  {LEAGUES[lg]['name_ar']}: {n} لاعب")
    print(f"\n  المجموع: {len(out_rows)}  |  مترجم: {filled}  "
          f"|  ناقص: {len(out_rows) - filled}")
    print(f"""
{'=' * 55}
  المطلوب:
  افتح players_arabic.csv بالإكسل وعبّي عمود player_ar

  مثال:
    R. Bani Hani   -->  ربيع بني هاني
    M. Al Attar    -->  محمد العطار

  ملاحظات مهمة:
  - عمود team_ar موجود ليساعدك تعرف اللاعب من ناديه
  - الأجانب (Cesar, Ronaldo) اكتبهم بالنطق العربي المتداول
  - اللي ما بتعرفه، اتركه فاضي — الكود بيرجع للإنجليزي
  - إعادة تشغيل هذا السكربت ما بتمحي شغلك
    """)


if __name__ == "__main__":
    main()
