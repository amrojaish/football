#!/usr/bin/env python3
"""
إحصائيات محسوبة من الديتابيس
==============================
كل شي هون محسوب من الداتا الخام — ما في API بيعطيك إياه جاهز.
هاي القيمة اللي بتملكها إنت.

صفر طلبات API.

التشغيل:
    python stats.py           <- الأردني
    python stats.py IRQ       <- العراقي
    python stats.py SAU       <- السعودي
"""

import sqlite3
import sys
from collections import defaultdict
from config import DB_FILE, LEAGUES

CODE = sys.argv[1].upper() if len(sys.argv) > 1 else "JOR"


def line(title=""):
    print("\n" + "=" * 56)
    if title:
        print(f"  {title}")
        print("=" * 56)


def get_matches(conn, code):
    return conn.execute("""
        SELECT m.date, m.home_id, m.away_id, m.home_goals, m.away_goals,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        JOIN teams h ON h.team_id = m.home_id
        JOIN teams a ON a.team_id = m.away_id
        WHERE m.league_code = ?
        ORDER BY m.date
    """, (code,)).fetchall()


def attack_defence(matches):
    """أقوى هجوم وأقوى دفاع"""
    scored = defaultdict(int)
    conceded = defaultdict(int)
    played = defaultdict(int)

    for m in matches:
        scored[m["home"]] += m["home_goals"]
        conceded[m["home"]] += m["away_goals"]
        scored[m["away"]] += m["away_goals"]
        conceded[m["away"]] += m["home_goals"]
        played[m["home"]] += 1
        played[m["away"]] += 1

    line("أقوى هجوم")
    top = sorted(scored.items(), key=lambda x: -x[1])[:5]
    for i, (team, goals) in enumerate(top, 1):
        avg = goals / played[team]
        print(f"  {i}. {team:<16} {goals:>3} هدف   "
              f"(معدل {avg:.2f} بالماتش)")

    line("أقوى دفاع")
    best = sorted(conceded.items(), key=lambda x: x[1])[:5]
    for i, (team, goals) in enumerate(best, 1):
        avg = goals / played[team]
        print(f"  {i}. {team:<16} {goals:>3} هدف عليه   "
              f"(معدل {avg:.2f})")


def streaks(matches):
    """
    أطول سلسلة انتصارات وأطول سلسلة بدون خسارة.
    الفكرة: نمشي على مباريات كل فريق بالترتيب الزمني،
    ونعد المتتاليات.
    """
    history = defaultdict(list)   # فريق -> ['W','D','L',...]

    for m in matches:
        h, a = m["home"], m["away"]
        gh, ga = m["home_goals"], m["away_goals"]

        if gh > ga:
            history[h].append("W")
            history[a].append("L")
        elif gh < ga:
            history[h].append("L")
            history[a].append("W")
        else:
            history[h].append("D")
            history[a].append("D")

    def longest(seq, allowed):
        best = cur = 0
        for r in seq:
            if r in allowed:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    wins = [(t, longest(s, {"W"})) for t, s in history.items()]
    unbeaten = [(t, longest(s, {"W", "D"})) for t, s in history.items()]

    line("أطول سلسلة انتصارات")
    for i, (team, n) in enumerate(sorted(wins, key=lambda x: -x[1])[:5], 1):
        print(f"  {i}. {team:<16} {n} انتصار متتالي")

    line("أطول سلسلة بدون خسارة")
    for i, (team, n) in enumerate(sorted(unbeaten, key=lambda x: -x[1])[:5], 1):
        print(f"  {i}. {team:<16} {n} ماتش")


def home_away(matches):
    """الفرق بين الأداء بالبيت وبرّا — ظاهرة معروفة بكرة القدم"""
    home_pts = defaultdict(int)
    away_pts = defaultdict(int)
    home_n = defaultdict(int)
    away_n = defaultdict(int)

    for m in matches:
        gh, ga = m["home_goals"], m["away_goals"]
        h, a = m["home"], m["away"]
        home_n[h] += 1
        away_n[a] += 1

        if gh > ga:
            home_pts[h] += 3
        elif gh < ga:
            away_pts[a] += 3
        else:
            home_pts[h] += 1
            away_pts[a] += 1

    line("الفرق بين البيت وبرّا")
    print("  (نقاط بالبيت مقابل نقاط برّا)\n")

    diffs = []
    for team in home_n:
        hp = home_pts[team]
        ap = away_pts[team]
        diffs.append((team, hp, ap, hp - ap))

    for team, hp, ap, d in sorted(diffs, key=lambda x: -x[3])[:6]:
        bar = "█" * min(d, 20) if d > 0 else ""
        print(f"  {team:<16} بيت {hp:>2}  برّا {ap:>2}   {d:+3}  {bar}")


def biggest_wins(matches):
    """أكبر الانتصارات بالموسم"""
    scored = []
    for m in matches:
        diff = abs(m["home_goals"] - m["away_goals"])
        if diff > 0:
            scored.append((diff, m))

    line("أكبر الانتصارات")
    for i, (diff, m) in enumerate(sorted(scored, key=lambda x: -x[0])[:5], 1):
        print(f"  {i}. {m['home']} {m['home_goals']} - "
              f"{m['away_goals']} {m['away']}   ({m['date']})")


def goal_timing(conn, code):
    """
    توزيع الأهداف على فترات المباراة.
    معلومة ما بيعطيك إياها أي API جاهز — لازم تحسبها.
    """
    rows = conn.execute("""
        SELECT g.minute
        FROM goals g
        JOIN matches m ON m.match_id = g.match_id
        WHERE m.league_code = ? AND g.minute IS NOT NULL
    """, (code,)).fetchall()

    if not rows:
        return

    buckets = defaultdict(int)
    for r in rows:
        minute = r["minute"]
        bucket = min(minute // 15, 5)   # كل 15 دقيقة
        buckets[bucket] += 1

    labels = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90+"]
    total = sum(buckets.values())
    peak = max(buckets.values()) if buckets else 1

    line("متى تُسجَّل الأهداف")
    for i, label in enumerate(labels):
        n = buckets.get(i, 0)
        pct = n / total * 100 if total else 0
        bar = "█" * int(n / peak * 24)
        print(f"  {label:>7}  {bar} {n} ({pct:.0f}%)")

    # الشوط الأول مقابل الثاني
    first = sum(buckets.get(i, 0) for i in (0, 1, 2))
    second = total - first
    print(f"\n  الشوط الأول: {first}  |  الشوط الثاني: {second}")
    if first:
        print(f"  نسبة الثاني للأول: {second / first:.2f}")


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    if CODE not in LEAGUES:
        print(f"دوري غير معروف: {CODE}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    matches = get_matches(conn, CODE)
    if not matches:
        print(f"ما في مباريات مخزنة لـ {CODE}")
        conn.close()
        return

    goals_total = sum(m["home_goals"] + m["away_goals"] for m in matches)

    print(f"\n{'#' * 56}")
    print(f"#  {LEAGUES[CODE]['name_ar']} — إحصائيات محسوبة")
    print(f"{'#' * 56}")
    print(f"\n  {len(matches)} ماتش  |  {goals_total} هدف  |  "
          f"معدل {goals_total/len(matches):.2f} بالماتش")

    attack_defence(matches)
    streaks(matches)
    home_away(matches)
    biggest_wins(matches)
    goal_timing(conn, CODE)

    print(f"""
{'=' * 56}
  كل رقم فوق محسوب من الداتا الخام.
  ما في API بيعطيك سلاسل الانتصارات ولا توزيع الأهداف.
  هاد منطق تملكه إنت.
{'=' * 56}
    """)

    conn.close()


if __name__ == "__main__":
    main()
