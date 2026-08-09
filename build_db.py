#!/usr/bin/env python3
"""
بناء الديتابيس المحلية
=======================
بيسحب المباريات والأهداف مرة وحدة، وبيخزنهم بملف football.db
على جهازك. بعدها بتشتغل على الداتا بدون ما تلمس الـAPI أبداً.

التشغيل:
    python build_db.py           <- الأردني (افتراضي)
    python build_db.py IRQ       <- العراقي
    python build_db.py SAU       <- السعودي

ملاحظة: بياخد وقت (دقيقتين تقريباً) لأنه بيسحب أهداف كل ماتش.
"""

import requests
import sqlite3
import csv
import time
import sys

from config import (API_BASE, SEASON, TEAMS_FILE, DB_FILE,
                    LEAGUES, check_key, headers)

# كم ماتش نسحب — خليها صغيرة أول مرة عشان الحصة
MATCHES_LIMIT = 25


def create_tables(conn):
    """بيعمل الجداول إذا مش موجودة"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id       INTEGER PRIMARY KEY,
            league_code   TEXT,
            name_en       TEXT,
            name_ar       TEXT,
            short_name_ar TEXT,
            city          TEXT,
            logo          TEXT
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id    INTEGER PRIMARY KEY,
            league_code TEXT,
            season      INTEGER,
            date        TEXT,
            home_id     INTEGER,
            away_id     INTEGER,
            home_goals  INTEGER,
            away_goals  INTEGER,
            status      TEXT
        );

        CREATE TABLE IF NOT EXISTS goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id    INTEGER,
            team_id     INTEGER,
            minute      INTEGER,
            player_en   TEXT,
            player_ar   TEXT,
            detail      TEXT
        );
    """)
    conn.commit()


def import_teams(conn):
    """بيحمّل جدول الأسماء العربي من ملف CSV للديتابيس"""
    if not TEAMS_FILE.exists():
        print("ما لقيت teams_arabic.csv")
        return 0

    rows = []
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r.get("team_id"):
                continue
            rows.append((
                int(r["team_id"]),
                r.get("league_code", ""),
                r.get("name_en", ""),
                r.get("name_ar", ""),
                r.get("short_name_ar", ""),
                r.get("city", ""),
                r.get("logo", ""),
            ))

    conn.executemany("""
        INSERT OR REPLACE INTO teams
        (team_id, league_code, name_en, name_ar, short_name_ar, city, logo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def get(endpoint, params):
    r = requests.get(f"{API_BASE}/{endpoint}",
                     headers=headers(), params=params, timeout=25)
    return r.json().get("response", [])


def main():
    if not check_key():
        return

    code = sys.argv[1].upper() if len(sys.argv) > 1 else "JOR"
    if code not in LEAGUES:
        print(f"دوري غير معروف: {code}  (استخدم JOR أو IRQ أو SAU)")
        return

    league = LEAGUES[code]

    conn = sqlite3.connect(DB_FILE)
    create_tables(conn)

    n = import_teams(conn)
    print(f"\nحمّلت {n} نادي من جدولك للديتابيس")

    print(f"بسحب مباريات {league['name_ar']} ...")
    fixtures = get("fixtures", {"league": league["id"],
                                "season": SEASON, "status": "FT"})
    if not fixtures:
        print("ما رجعت مباريات")
        conn.close()
        return

    selected = fixtures[-MATCHES_LIMIT:]
    print(f"رجع {len(fixtures)} ماتش — رح نخزّن آخر {len(selected)}\n")

    saved_goals = 0

    for i, fx in enumerate(selected, 1):
        mid = fx["fixture"]["id"]

        conn.execute("""
            INSERT OR REPLACE INTO matches
            (match_id, league_code, season, date,
             home_id, away_id, home_goals, away_goals, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mid, code, SEASON, fx["fixture"]["date"][:10],
            fx["teams"]["home"]["id"], fx["teams"]["away"]["id"],
            fx["goals"]["home"], fx["goals"]["away"], "FT"
        ))

        # نمسح أهداف هالماتش القديمة قبل ما نضيف (عشان ما تتكرر)
        conn.execute("DELETE FROM goals WHERE match_id = ?", (mid,))

        time.sleep(1)
        events = get("fixtures/events", {"fixture": mid})

        for e in events:
            if e.get("type") != "Goal":
              continue
            if e.get("detail") == "Missed Penalty":
              continue
                
            conn.execute("""
                INSERT INTO goals
                (match_id, team_id, minute, player_en, player_ar, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                mid, e["team"]["id"], e["time"]["elapsed"],
                e["player"]["name"] or "", "", e.get("detail", "")
            ))
            saved_goals += 1

        conn.commit()
        print(f"  [{i}/{len(selected)}] ماتش {mid} تم")

    print(f"\n{'=' * 55}")
    print(f"  خلص. الملف: {DB_FILE.name}")
    print(f"  مباريات: {len(selected)}   |   أهداف: {saved_goals}")
    print(f"{'=' * 55}")
    print("""
  من هلأ ورايح، الداتا عندك محلياً.
  السكربتات الجاية بتقرأ من الديتابيس — بدون طلبات API.

  لاحظ عمود player_ar بجدول goals — فاضي.
  هاد مكان أسماء اللاعبين العربية، الطبقة الجاية من الشغل.
    """)

    conn.close()


if __name__ == "__main__":
    main()
