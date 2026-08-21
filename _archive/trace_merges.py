"""
تتبّع مراحل build_merges.py لمعرفة أين يتوقّف
================================================
يطبع كل مرحلة مع زمنها فوراً (flush=True) — فآخر سطر يظهر
يحدّد نقطة التوقّف بالضبط.
"""

import sys
import time

T0 = time.time()


def step(msg):
    print(f"[{time.time() - T0:6.2f}s] {msg}", flush=True)


step("بدأ التشغيل")

import sqlite3
from collections import defaultdict
step("استيراد sqlite3")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    step("إعادة ضبط الترميز")
except Exception as e:
    step(f"فشل ضبط الترميز: {type(e).__name__}")

try:
    from config import DB_FILE, BASE_DIR
    step(f"استيراد config — DB={DB_FILE}")
except Exception as e:
    step(f"فشل استيراد config: {type(e).__name__}: {e}")
    sys.exit(1)

step(f"الديتابيس موجود؟ {DB_FILE.exists()}")

conn = sqlite3.connect(DB_FILE)
step("فتح الاتصال")

rev = defaultdict(set)
for t in ("goals", "lineup_players", "player_stats", "events"):
    try:
        rows = conn.execute(f"""
            SELECT DISTINCT player_en, player_ar FROM {t}
            WHERE player_en != ''
              AND player_ar IS NOT NULL AND player_ar != ''
        """).fetchall()
        step(f"قراءة {t}: {len(rows)} صف")
    except sqlite3.OperationalError as e:
        step(f"تعذّر {t}: {e}")
        continue
    for en, ar in rows:
        rev[ar].add(en)

groups = {k: sorted(v) for k, v in rev.items() if len(v) > 1}
step(f"بناء المجموعات: {len(groups)}")

wanted = {e for ens in groups.values() for e in ens}
step(f"الصيغ قيد الفحص: {len(wanted)}")

lp = defaultdict(set)
n = 0
for en, mid in conn.execute(
        "SELECT player_en, match_id FROM lineup_players WHERE player_en != ''"):
    n += 1
    if en in wanted:
        lp[en].add(mid)
step(f"مسح lineup_players: {n} صف")

pid = defaultdict(set)
for t in ("lineup_players", "player_stats"):
    try:
        cur = conn.execute(
            f"SELECT player_en, player_id FROM {t} "
            f"WHERE player_en != '' AND player_id IS NOT NULL")
    except sqlite3.OperationalError as e:
        step(f"تعذّر {t}: {e}")
        continue
    k = 0
    for en, i in cur:
        k += 1
        if en in wanted:
            pid[en].add(i)
    step(f"مسح معرّفات {t}: {k} صف")

step("اكتملت كل مراحل القراءة — البطء ليس هنا")

out = BASE_DIR / "trace_write_test.csv"
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    f.write("test\n")
step(f"اختبار الكتابة نجح: {out.name}")
out.unlink()
step("تم — كل شيء سليم")
