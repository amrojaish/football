#!/usr/bin/env python3
"""
فحص الناديين المفقودين — 17472 و 22188
=========================================
ظهرا في مباريات موسم 2026 لكنهما غير موجودين في teams_arabic.csv،
يعني make_clubs.py يتخطاهما (سطر 478) وما إلهم صفحات،
و make_matches.py يتخطى كل مباراة إلهم.

بيطبع: أي دوري، أي موسم، كم مباراة، ومع مين لعبوا.

صفر طلبات API. للقراءة فقط — ما بيعدّل شي.

التشغيل:
    python check.py
"""

import sqlite3
import csv
import os

DB = "football.db"
CSV_FILE = "teams_arabic.csv"
MISSING = [17472, 22188]


def main():
    if not os.path.exists(DB):
        print("ما لقيت football.db — تأكد إنك بمجلد Football")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    ids = ",".join(str(i) for i in MISSING)

    print("=" * 55)
    print("  أين يظهران")
    print("=" * 55)

    q1 = f"""
        SELECT league_code, season, COUNT(match_id) AS n
        FROM matches
        WHERE home_id IN ({ids}) OR away_id IN ({ids})
        GROUP BY league_code, season
        ORDER BY season DESC
    """
    rows = list(conn.execute(q1))
    if not rows:
        print("  لا مباريات — الأرجح أنهما من fetch_upcoming فقط")
    for r in rows:
        print(f"  {r['league_code']}  موسم {r['season']}  "
              f"{r['n']} مباراة")

    # كل نادٍ لحاله
    for tid in MISSING:
        print()
        print("=" * 55)
        print(f"  النادي {tid}")
        print("=" * 55)

        q2 = """
            SELECT league_code, season, date, home_id, away_id,
                   home_goals, away_goals
            FROM matches
            WHERE home_id = ? OR away_id = ?
            ORDER BY date
            LIMIT 8
        """
        ms = list(conn.execute(q2, (tid, tid)))
        if not ms:
            print("  ما ظهر بأي مباراة")
            continue

        print(f"  عدد المباريات: "
              f"{conn.execute('SELECT COUNT(match_id) FROM matches WHERE home_id=? OR away_id=?', (tid, tid)).fetchone()[0]}")
        print("  أول المباريات:")
        for m in ms:
            print(f"    {m['date'][:10]}  {m['league_code']} "
                  f"{m['season']}  {m['home_id']} vs {m['away_id']}  "
                  f"{m['home_goals']}-{m['away_goals']}")

    # هل لهما اسم في أي مكان بالديتابيس؟
    print()
    print("=" * 55)
    print("  هل يوجد اسم لهما في الديتابيس")
    print("=" * 55)

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    found = False
    for t in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})")]
        id_col = next((c for c in cols
                       if c in ("team_id", "id", "home_id")), None)
        name_col = next((c for c in cols
                         if "name" in c.lower()), None)
        if not id_col or not name_col:
            continue
        try:
            for r in conn.execute(
                    f"SELECT DISTINCT {id_col}, {name_col} FROM {t} "
                    f"WHERE {id_col} IN ({ids})"):
                print(f"  جدول {t}: {r[0]} → {r[1]}")
                found = True
        except sqlite3.Error:
            continue

    if not found:
        print("  لا اسم في أي جدول — يحتاجان إضافة يدوية")

    # تأكيد أنهما فعلاً خارج CSV
    print()
    print("=" * 55)
    print("  التأكد من teams_arabic.csv")
    print("=" * 55)

    if not os.path.exists(CSV_FILE):
        print("  ما لقيت teams_arabic.csv")
    else:
        with open(CSV_FILE, encoding="utf-8-sig") as f:
            csv_ids = {str(r.get("team_id", "")).strip()
                       for r in csv.DictReader(f)}
        for tid in MISSING:
            state = "موجود" if str(tid) in csv_ids else "مفقود ❌"
            print(f"  {tid}: {state}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
