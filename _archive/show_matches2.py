#!/usr/bin/env python3
"""
عرض المباريات بالأسماء العربية — نسخة 2
=========================================
نفس السكربت القديم، بس المفتاح صار بيجي من ملف .env
عن طريق config.py — ما في مفتاح مكتوب هون.

التشغيل:
    python show_matches2.py
"""

import requests
import csv
import time

# بنستورد الإعدادات من config.py
from config import (API_BASE, SEASON, TEAMS_FILE, LEAGUES,
                    check_key, headers)

# غيّر هون لتشوف دوري تاني: "JOR" أو "IRQ" أو "SAU"
LEAGUE_CODE = "JOR"

HOW_MANY_MATCHES = 5


def load_team_names():
    if not TEAMS_FILE.exists():
        print(f"ما لقيت الملف {TEAMS_FILE.name}")
        return None

    names = {}
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tid = row.get("team_id", "").strip()
            short = row.get("short_name_ar", "").strip()
            full = row.get("name_ar", "").strip()
            if tid:
                names[tid] = short or full

    print(f"قرأت {len(names)} اسم من جدولك\n")
    return names


def get(endpoint, params):
    r = requests.get(f"{API_BASE}/{endpoint}",
                     headers=headers(), params=params, timeout=25)
    return r.json().get("response", [])


def arabic_name(team, names):
    tid = str(team["id"])
    return names.get(tid) or f"{team['name']} (؟)"


def main():
    # الفحص صار بسطر واحد
    if not check_key():
        return

    league = LEAGUES[LEAGUE_CODE]
    print(f"\n{league['name_ar']} — موسم {SEASON}\n")

    names = load_team_names()
    if names is None:
        return

    fixtures = get("fixtures", {"league": league["id"],
                                "season": SEASON, "status": "FT"})
    if not fixtures:
        print("ما رجعت مباريات")
        return

    print("=" * 50)

    for fx in fixtures[-HOW_MANY_MATCHES:]:
        home = arabic_name(fx["teams"]["home"], names)
        away = arabic_name(fx["teams"]["away"], names)
        gh, ga = fx["goals"]["home"], fx["goals"]["away"]
        date = fx["fixture"]["date"][:10]

        print(f"\n  {home}  {gh} - {ga}  {away}")
        print(f"  {date}")

        time.sleep(1)
        events = get("fixtures/events", {"fixture": fx["fixture"]["id"]})
        goals = [e for e in events if e.get("type") == "Goal"]

        for g in goals:
            scorer = g["player"]["name"] or "؟"
            team_ar = arabic_name(g["team"], names)
            print(f"      د.{g['time']['elapsed']}'  {scorer}  —  {team_ar}")

        if not goals:
            print("      (ما في تفاصيل)")

    print("\n" + "=" * 50)
    print("""
  المفتاح هالمرة إجا من ملف .env — مش مكتوب بهاد الملف.
  جرّب: غيّر LEAGUE_CODE فوق لـ "IRQ" أو "SAU"
    """)


if __name__ == "__main__":
    main()
