#!/usr/bin/env python3
"""
مباريات تجاوزت موعدها بلا نتيجة (26 أكتوبر 2026)
===================================================
المشكلة (IRQ 1628016 غاز الشمال × نفط ميسان): المزوّد أبقى المباراة NS بموعد قديم (24/10) بعد أن لُعبت (25/10)،
ثم وضع FT بعدها بساعات. fetch_upcoming.py يعيد كتابة NS/TBD/PST فقط، وfetch_matches2.py يرى قائمة FT فقط —
فلا شيء يسأل عن **صف بعينه** فات موعده. بالنسخ الاحتياطية 13–26 أكتوبر: 6 مباريات بقيت NS بتاريخ ماضٍ (أطولها
MAR 1636664 من 24/09 لما بعد 19/10).

الأهداف: مباريات الموسم بلا نتيجة (home_goals IS NULL)، غير ملغاة (CANC/ABD)، فات انطلاقها بأكثر من ساعتين.
الطلب: fixtures?ids= (حتى 20 مباراة بالطلب)، سقف --budget طلبات بالتشغيل (افتراضي 3).
الجدولة: fetch_backoff (kind = "overdue") — 0/1/6/24/72 س بعد النهاية التقديرية (الانطلاق + ساعتان) ثم توقف.
    الرد الذي لا يغيّر شيئاً يُسجَّل محاولة؛ فشل الطلب لا يُسجَّل.

ما يُكتب:
    منتهية (FT/AET/PEN)  ← save_finished من fetch_matches2.py نفسه (الصف + الأهداف من events بالرد)
    غير ذلك               ← status وdate فقط إن اختلفا (home_goals تبقى NULL): موعد جديد/مؤجّلة/ملغاة/جارية
    غائبة عن الرد         ← تُسجَّل محاولة وتُطبع
بعدها: مباراة منتهية بأهداف ناقصة (المزوّد بلا أحداث بعد) يكملها refresh_goal_names.py بجدولته.

التشغيل:
    python fetch_overdue.py --season 2026 --check     ← الأهداف المستحقّة فقط (بلا API ولا كتابة)
    python fetch_overdue.py --season 2026 --budget 3
"""
import csv
import sqlite3
import sys
import time
from datetime import datetime, timezone

import fetch_backoff as BO
from config import BASE_DIR, DB_FILE, SEASON, check_key
from fetch_matches2 import get, save_finished

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KIND = "overdue"
GRACE_H = 2          # بعد الانطلاق بساعتين ولا نتيجة = متأخرة
IDS_MAX = 20         # حدّ المزوّد لـfixtures?ids
DELAY = 1.0
FINAL = ("FT", "AET", "PEN")
DEFAULT_BUDGET = 3


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def excluded_ids(path=BASE_DIR / "excluded_matches.csv"):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return {int(r["match_id"]) for r in csv.DictReader(f) if (r.get("match_id") or "").strip().isdigit()}
    except OSError:
        return set()


def overdue_rows(conn, season, now=None, skip=()):
    """صفوف (match_id, league_code, season, date, status) بلا نتيجة فات انطلاقها بأكثر من GRACE_H."""
    now = time.time() if now is None else now
    cut = datetime.fromtimestamp(now - GRACE_H * 3600, timezone.utc).strftime("%Y-%m-%d %H:%M")
    rows = conn.execute("""
        SELECT match_id, league_code, season, date, status FROM matches
        WHERE season = ? AND home_goals IS NULL AND COALESCE(status, 'NS') NOT IN ('CANC', 'ABD')
          AND length(date) >= 16 AND substr(date, 1, 16) < ?
        ORDER BY date""", (season, cut)).fetchall()
    return [r for r in rows if r["match_id"] not in skip]


def apply_fixture(conn, row, fx):
    """-> وصف ما حدث. لا commit."""
    mid = row["match_id"]
    ps = fx["fixture"]["status"]["short"]
    pd = fx["fixture"]["date"][:16].replace("T", " ")
    if ps in FINAL and fx["goals"]["home"] is not None:
        n = save_finished(conn, row["league_code"], row["season"], fx, fx.get("events") or [], status=ps)
        return f"{mid} {row['league_code']}: {row['status']} {row['date']} → {ps} {pd} "\
               f"{fx['goals']['home']}-{fx['goals']['away']} ({n} هدفاً بالأحداث)", True
    if (ps, pd) != (row["status"], str(row["date"])[:16]):
        conn.execute("UPDATE matches SET status = ?, date = ? WHERE match_id = ? AND home_goals IS NULL",
                     (ps, pd, mid))
        return f"{mid} {row['league_code']}: {row['status']} {row['date']} → {ps} {pd}", False
    return f"{mid} {row['league_code']}: بلا تغيير عند المزوّد ({ps} {pd})", False


def run(conn, season, budget, check, fetch=get, now=None):
    rows = overdue_rows(conn, season, now, excluded_ids())
    BO.ensure_table(conn)
    due, skipped = BO.filter_due(conn, KIND, rows, now)
    rep = {"overdue": len(rows), "due": len(due), "skipped": skipped, "calls": 0, "finished": 0, "changed": 0,
           "lines": []}
    if check:
        rep["lines"] = [f"{r['match_id']} {r['league_code']} {r['status']} {r['date']}" for r in due]
        return rep
    for i in range(0, min(len(due), budget * IDS_MAX), IDS_MAX):
        part = due[i:i + IDS_MAX]
        ok, resp, reason = fetch("fixtures", {"ids": "-".join(str(r["match_id"]) for r in part)})
        rep["calls"] += 1
        if not ok:
            rep["lines"].append(f"فشل الطلب ({reason}) — {len(part)} مباراة تُعاد بالتشغيل التالي")
            time.sleep(DELAY)
            continue
        got = {f["fixture"]["id"]: f for f in resp}
        for r in part:
            fx = got.get(r["match_id"])
            if fx is None:
                rep["lines"].append(f"{r['match_id']} {r['league_code']}: غائبة عن رد المزوّد")
                BO.record_empty(conn, KIND, r["match_id"], now)
                continue
            line, done = apply_fixture(conn, r, fx)
            rep["lines"].append(line)
            if done:
                rep["finished"] += 1
            else:
                rep["changed"] += "→" in line
                BO.record_empty(conn, KIND, r["match_id"], now)   # يحفظ (commit) ما سبقه أيضاً
        conn.commit()
        time.sleep(DELAY)
    return rep


def main():
    check = "--check" in sys.argv
    season = int(arg("--season", SEASON))
    budget = int(arg("--budget", DEFAULT_BUDGET))
    if check:
        src = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        if not check_key():
            return 0
        conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rep = run(conn, season, budget, check)
    conn.close()
    print(f"  مباريات فات موعدها بلا نتيجة (موسم {season}){' [فحص: بلا API ولا كتابة]' if check else ''}: "
          f"{rep['overdue']} · مستحقّة {rep['due']} · طلبات {rep['calls']} · انتهت {rep['finished']}"
          f" · تغيّر موعدها/حالتها {rep['changed']} · متخطّاة {rep['skipped']}")
    for ln in rep["lines"]:
        print("   ", ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
