# check_h2h.py
# بيطلّع المواجهات المباشرة بين فريقين + تفاصيل أهداف كل مباراة.
# بيقرأ بس — ما بيعدّل ولا بيمسح أي شي.
#
# الاستخدام:
#   python check_h2h.py
#   python check_h2h.py الحسين الفيصلي JOR 2025

import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

A = sys.argv[1] if len(sys.argv) > 1 else "الحسين"
B = sys.argv[2] if len(sys.argv) > 2 else "الفيصلي"
LEAGUE = sys.argv[3] if len(sys.argv) > 3 else "JOR"
SEASON = int(sys.argv[4]) if len(sys.argv) > 4 else 2025

con = sqlite3.connect("football.db")
con.row_factory = sqlite3.Row
cur = con.cursor()


def find_team(fragment):
    rows = cur.execute(
        """SELECT team_id, name_ar, name_en FROM teams
           WHERE league_code = ? AND (name_ar LIKE ? OR name_en LIKE ?)""",
        (LEAGUE, f"%{fragment}%", f"%{fragment}%"),
    ).fetchall()
    if len(rows) == 0:
        print(f"❌ ما لقيت نادي اسمه فيه '{fragment}' بدوري {LEAGUE}")
        sys.exit(1)
    if len(rows) > 1:
        print(f"⚠️ '{fragment}' طابق أكثر من نادي:")
        for r in rows:
            print(f"      {r['team_id']}  {r['name_ar']}")
        print("   شغّل السكربت مرة تانية باسم أدق.")
        sys.exit(1)
    return rows[0]["team_id"], rows[0]["name_ar"]


a_id, a_name = find_team(A)
b_id, b_name = find_team(B)

print(f"\n{'='*66}")
print(f"  {a_name}  (ID {a_id})   ضد   {b_name}  (ID {b_id})")
print(f"  {LEAGUE} / موسم {SEASON}")
print(f"{'='*66}")

matches = cur.execute(
    """SELECT match_id, date, home_id, away_id, home_goals, away_goals, status
       FROM matches
       WHERE league_code = ? AND season = ?
         AND ((home_id = ? AND away_id = ?) OR (home_id = ? AND away_id = ?))
       ORDER BY date""",
    (LEAGUE, SEASON, a_id, b_id, b_id, a_id),
).fetchall()

print(f"\nعدد المواجهات الموجودة: {len(matches)}")
if len(matches) != 3:
    print("⚠️ المتوقع 3 مواجهات بنظام 3 مراحل — راجع هالنقطة.")

names = {a_id: a_name, b_id: b_name}

for m in matches:
    hg, ag = m["home_goals"], m["away_goals"]
    h_name = names.get(m["home_id"], str(m["home_id"]))
    a_nm = names.get(m["away_id"], str(m["away_id"]))

    if hg is None or ag is None:
        result = "بدون نتيجة"
    elif hg > ag:
        result = f"فوز {h_name}"
    elif ag > hg:
        result = f"فوز {a_nm}"
    else:
        result = "تعادل"

    print(f"\n{'-'*66}")
    print(f"  match_id : {m['match_id']}")
    print(f"  التاريخ  : {m['date']}")
    print(f"  status   : {m['status']}")
    print(f"  النتيجة  : {h_name} {hg} - {ag} {a_nm}   →  {result}")

    # الأهداف المسجلة بجدول goals لهالمباراة
    gs = cur.execute(
        """SELECT team_id, minute, player_en, detail FROM goals
           WHERE match_id = ? ORDER BY minute""",
        (m["match_id"],),
    ).fetchall()

    print(f"  أهداف بجدول goals: {len(gs)}")
    for g in gs:
        who = names.get(g["team_id"], f"ID {g['team_id']}")
        player = g["player_en"] or "(بلا اسم لاعب ⚠️)"
        detail = g["detail"] or ""
        warn = "  <-- انتبه" if detail in ("Missed Penalty",) else ""
        print(f"      {str(g['minute']):>3}'  {who:<20} {player:<28} {detail}{warn}")

    # مقارنة: مجموع الأهداف بالجدول مقابل نتيجة المباراة
    if hg is not None and ag is not None:
        g_home = sum(1 for g in gs if g["team_id"] == m["home_id"])
        g_away = sum(1 for g in gs if g["team_id"] == m["away_id"])
        if (g_home, g_away) != (hg, ag):
            print(f"  ⚠️ تعارض: النتيجة {hg}-{ag} بس جدول goals فيه {g_home}-{g_away}")
        else:
            print("  ✅ النتيجة متطابقة مع جدول goals")

print(f"\n{'='*66}\n")
con.close()
