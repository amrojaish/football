# verify_standings.py
# سكربت تشخيص — بيقرأ بس، ما بيعدّل ولا بيمسح أي شي بالداتابيس.
# الاستخدام:  python verify_standings.py JOR 2025

import sqlite3
import sys

# --- إصلاح ترميز العربي بالـPowerShell (بدونه بتطلع رموز غريبة) ---
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LEAGUE = sys.argv[1] if len(sys.argv) > 1 else "JOR"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
DB = "football.db"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

print(f"\n{'='*60}")
print(f"  تشخيص جدول الترتيب — {LEAGUE} / موسم {SEASON}")
print(f"{'='*60}")

# ------------------------------------------------------------------
# 1) حالات المباريات — هل في مباراة مش FT داخلة بالحساب؟
# ------------------------------------------------------------------
print("\n[1] حالات المباريات (status):")
rows = cur.execute(
    """SELECT status, COUNT(*) AS c FROM matches
       WHERE league_code = ? AND season = ?
       GROUP BY status ORDER BY c DESC""",
    (LEAGUE, SEASON),
).fetchall()
total = 0
for r in rows:
    total += r["c"]
    flag = "" if r["status"] in ("FT", "AET", "PEN") else "   <-- انتبه"
    print(f"      {str(r['status']):>12} : {r['c']:>4}{flag}")
print(f"      {'الإجمالي':>12} : {total:>4}")

# ------------------------------------------------------------------
# 2) مباريات بدون نتيجة
# ------------------------------------------------------------------
r = cur.execute(
    """SELECT COUNT(*) AS c FROM matches
       WHERE league_code = ? AND season = ?
         AND (home_goals IS NULL OR away_goals IS NULL)""",
    (LEAGUE, SEASON),
).fetchone()
print(f"\n[2] مباريات بدون نتيجة (NULL): {r['c']}")

# ------------------------------------------------------------------
# 3) مباريات مكررة (نفس الفريقين + نفس التاريخ)
#    ملاحظة: بنظام 3 مراحل تكرار الفريقين طبيعي، فبنفحص مع التاريخ
# ------------------------------------------------------------------
print("\n[3] مباريات مكررة محتملة (نفس الفريقين + نفس اليوم):")
dups = cur.execute(
    """SELECT home_id, away_id, substr(date,1,10) AS d, COUNT(*) AS c
       FROM matches
       WHERE league_code = ? AND season = ?
       GROUP BY home_id, away_id, d
       HAVING c > 1""",
    (LEAGUE, SEASON),
).fetchall()
if not dups:
    print("      ما في تكرار ✅")
else:
    for r in dups:
        print(f"      {r['home_id']} vs {r['away_id']}  بتاريخ {r['d']}  ×{r['c']}  <-- مكررة")

# ------------------------------------------------------------------
# 4) أسماء الأندية — LEFT JOIN يدوي (درس رقم 6: INNER JOIN بيحذف بصمت)
# ------------------------------------------------------------------
teams = {}
for r in cur.execute(
    "SELECT team_id, name_ar, name_en FROM teams WHERE league_code = ?",
    (LEAGUE,),
):
    teams[r["team_id"]] = r["name_ar"] or r["name_en"] or f"?{r['team_id']}"

# ------------------------------------------------------------------
# 5) حساب الجدول
# ------------------------------------------------------------------
tbl = {}


def slot(tid):
    return tbl.setdefault(
        tid, {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0}
    )


counted = 0
for m in cur.execute(
    """SELECT home_id, away_id, home_goals, away_goals FROM matches
       WHERE league_code = ? AND season = ?""",
    (LEAGUE, SEASON),
):
    hg, ag = m["home_goals"], m["away_goals"]
    if hg is None or ag is None:
        continue
    counted += 1
    h, a = slot(m["home_id"]), slot(m["away_id"])
    h["P"] += 1
    a["P"] += 1
    h["GF"] += hg
    h["GA"] += ag
    a["GF"] += ag
    a["GA"] += hg
    if hg > ag:
        h["W"] += 1
        a["L"] += 1
    elif hg < ag:
        h["L"] += 1
        a["W"] += 1
    else:
        h["D"] += 1
        a["D"] += 1

# فرق ظهرت بالمباريات بس مش موجودة بجدول teams
missing = [t for t in tbl if t not in teams]

print(f"\n[4] مباريات محسوبة: {counted}   |   أندية بالجدول: {len(tbl)}")
if missing:
    print(f"      ⚠️ أندية مش موجودة بجدول teams: {missing}")
    print("      (هاد بالضبط الباگ اللي طلّع 8 فرق بدل 10 قبل)")
else:
    print("      كل الأندية موجودة بجدول teams ✅")

# ------------------------------------------------------------------
# 6) الطباعة
# ------------------------------------------------------------------
def pts(s):
    return s["W"] * 3 + s["D"]


order = sorted(
    tbl.items(),
    key=lambda kv: (-pts(kv[1]), -(kv[1]["GF"] - kv[1]["GA"]), -kv[1]["GF"]),
)

print(f"\n[5] الجدول المحسوب محلياً:\n")
print(f"{'#':>2}  {'النادي':<22} {'ل':>3} {'ف':>3} {'ت':>3} {'خ':>3} "
      f"{'له':>4} {'عليه':>4} {'+/-':>5} {'نقاط':>5}")
print("-" * 72)
for i, (tid, s) in enumerate(order, 1):
    name = teams.get(tid, f"⚠️ ID {tid}")
    gd = s["GF"] - s["GA"]
    print(
        f"{i:>2}  {name:<22} {s['P']:>3} {s['W']:>3} {s['D']:>3} {s['L']:>3} "
        f"{s['GF']:>4} {s['GA']:>4} {gd:>+5} {pts(s):>5}"
    )

# ------------------------------------------------------------------
# 7) فحوصات منطقية
# ------------------------------------------------------------------
print("\n[6] فحوصات منطقية:")
p_values = sorted({s["P"] for s in tbl.values()})
if len(p_values) == 1:
    print(f"      كل الفرق لعبت {p_values[0]} مباراة ✅")
else:
    print(f"      ⚠️ عدد المباريات مختلف بين الفرق: {p_values}")
    print("      (طبيعي لو الموسم شغّال، مشكلة لو منتهي)")

gf = sum(s["GF"] for s in tbl.values())
ga = sum(s["GA"] for s in tbl.values())
print(f"      مجموع 'له' = {gf} | مجموع 'عليه' = {ga}"
      f"{'  ✅' if gf == ga else '  ⚠️ لازم يتساووا'}")

sum_p = sum(s["P"] for s in tbl.values())
print(f"      مجموع المباريات ÷ 2 = {sum_p // 2}"
      f"{'  ✅' if sum_p // 2 == counted else f'  ⚠️ المتوقع {counted}'}")

con.close()
print(f"\n{'='*60}\n")
