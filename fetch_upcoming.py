#!/usr/bin/env python3
"""
سحب المباريات القادمة
=======================
بيسحب المباريات **غير المنتهية** (المجدولة والمؤجلة) ويخزّنها
بجدول matches بنتيجة NULL.

ليش منفصل عن fetch_matches2.py:
ذاك السكربت يسحب FT فقط ويجلب أحداث كل مباراة (طلب لكل واحدة).
المباريات القادمة بلا أحداث، فطلب واحد لكل دوري يكفي —
أرخص بمئات المرات.

الحالات المسحوبة:
    NS   = لم تبدأ
    TBD  = الموعد غير محدد
    PST  = مؤجلة

⚠️ عمودا home_goals و away_goals يُخزَّنان NULL — كل استعلامات
   الجدول تتخطى الصفوف الفارغة أصلاً، فلا تؤثر على الترتيب.

⚠️ المباريات المسحوبة سابقاً كـFT لا تُلمس.

التشغيل:
    python fetch_upcoming.py --check       <- عرض بس
    python fetch_upcoming.py               <- الموسم الحالي
    python fetch_upcoming.py --season 2026
    python fetch_upcoming.py SAU
"""

import requests
import sqlite3
import sys
import time
from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UPCOMING = ("NS", "TBD", "PST")
DELAY = 1.0


def parse_args():
    code = None
    season = 2026
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].upper() in LEAGUES:
        code = args[0].upper()

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, season, check_only


def get_fixtures(league_id, season):
    """بيرجع (نجح؟, المباريات, سبب الفشل)"""
    try:
        r = requests.get(
            f"{API_BASE}/fixtures",
            headers=headers(),
            params={"league": league_id, "season": season},
            timeout=30,
        )
    except Exception as e:
        return False, [], f"شبكة: {type(e).__name__}"

    if r.status_code != 200:
        return False, [], f"HTTP {r.status_code}"

    try:
        data = r.json()
    except Exception:
        return False, [], "رد غير صالح"

    errors = data.get("errors")
    if errors and isinstance(errors, dict) and errors:
        return False, [], f"API: {errors}"

    return True, data.get("response", []), ""


def main():
    if not check_key():
        return

    code, season, check_only = parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    codes = [code] if code else list(LEAGUES.keys())

    print(f"\n{'=' * 62}")
    print(f"  سحب المباريات القادمة — موسم {season}")
    print(f"{'=' * 62}")

    total_new = total_upd = total_skip = 0

    for c in codes:
        info = LEAGUES[c]
        ok, fx, reason = get_fixtures(info["id"], season)

        if not ok:
            print(f"\n  {info['name_ar']}: فشل — {reason}")
            continue

        if not fx:
            print(f"\n  {info['name_ar']}: ما في مباريات بهالموسم")
            continue

        upcoming = [f for f in fx
                    if f["fixture"]["status"]["short"] in UPCOMING]

        print(f"\n  {'-' * 58}")
        print(f"  {info['name_ar']}")
        print(f"  {'-' * 58}")
        print(f"      إجمالي عند المزوّد : {len(fx)}")
        print(f"      قادمة              : {len(upcoming)}")

        if not upcoming:
            continue

        new = upd = skip = 0

        for f in upcoming:
            mid = f["fixture"]["id"]
            status = f["fixture"]["status"]["short"]
            # التاريخ والوقت — مفيد للعرض
            dt = f["fixture"]["date"][:16].replace("T", " ")

            row = conn.execute(
                "SELECT status FROM matches WHERE match_id = ?",
                (mid,)).fetchone()

            # المباريات المنتهية المخزّنة لا تُلمس
            if row and row["status"] in ("FT", "AET", "PEN"):
                skip += 1
                continue

            if check_only:
                if row:
                    upd += 1
                else:
                    new += 1
                continue

            conn.execute("""
                INSERT OR REPLACE INTO matches
                (match_id, league_code, season, date,
                 home_id, away_id, home_goals, away_goals, status)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """, (mid, c, season, dt,
                  f["teams"]["home"]["id"],
                  f["teams"]["away"]["id"],
                  status))

            if row:
                upd += 1
            else:
                new += 1

        if not check_only:
            conn.commit()

        print(f"      جديدة              : {new}")
        print(f"      محدّثة             : {upd}")
        if skip:
            print(f"      متخطاة (منتهية)    : {skip}")

        total_new += new
        total_upd += upd
        total_skip += skip

        time.sleep(DELAY)

    # فحص الأندية المفقودة
    missing = conn.execute("""
        SELECT DISTINCT t FROM (
            SELECT home_id t FROM matches WHERE season = ?
            UNION SELECT away_id FROM matches WHERE season = ?
        ) WHERE t NOT IN (SELECT team_id FROM teams)
    """, (season, season)).fetchall()

    conn.close()

    print(f"\n{'=' * 62}")
    if check_only:
        print(f"  [وضع الفحص] — ما انكتب شي")
    print(f"  جديدة: {total_new}  |  محدّثة: {total_upd}"
          f"  |  متخطاة: {total_skip}")
    print(f"{'=' * 62}")

    if missing:
        print(f"\n  ⚠️ {len(missing)} نادٍ غير موجود بجدول teams:")
        for r in missing:
            print(f"      {r['t']}")
        print("""
  هذه الأندية ستختفي من الجداول (درس 6).
  شغّل:  python update_teams.py {} SAU
         python update_teams.py {} IRQ
  ثم عبّئ أسماءها بـteams_arabic.csv
        """.format(season, season))

    if total_new and not check_only:
        print("""
  الخطوة الجاية:
      python make_site3.py
        """)


if __name__ == "__main__":
    main()
