#!/usr/bin/env python3
"""
مقارنة سجل كشف الأهداف (D1 goal_log) مع المباريات الحقيقية بـ football.db — قراءة فقط من الاثنين
=============================================================================================
لكل مباراة ظهرت بالسجل، أو لعبت بالفترة المحددة وانتهت وفيها أهداف:
  • النتيجة النهائية بـfootball.db (matches.home_goals/away_goals) مقابل آخر نتيجة بالسجل
  • صافي الأهداف المكتشفة (مجموع زيادات النتيجة − الإلغاءات) يجب أن = أهداف المباراة الفعلية
  • تكرار: صفّان متطابقان تماماً (نوع/نتيجة/سابقة) خلال دقيقتين = كشف مكرر
  • ناقص: مباراة بها أهداف بـDB ولا صف لها بالسجل (أو مجموع أقل)
  • أهداف DB بالدقيقة (goals.minute) مقابل دقيقة الكشف (فرق > 3 دقائق يُبلَّغ كملاحظة لا فشل: السحب كل دقيقة،
    والخمول يبطّئه لـ5 دقائق)

⚠️ يجب تشغيله بعد أن ينزّل deploy-site نتائج المباريات النهائية بـfootball.db (وإلا تظهر "غير منتهية").
⚠️ مباريات المحاكاة (/push/simulate) لا تكتب بـgoal_log أبداً.

التشغيل:
    python compare_goal_log.py 2026-10-08            # يوم واحد (UTC)
    python compare_goal_log.py 2026-10-08 2026-10-09 # من–إلى (شاملة)
"""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

from config import BASE_DIR, DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def d1(sql):
    out = subprocess.run(["npx", "wrangler", "d1", "execute", "saffara-push", "--remote", "--json", "--command", sql],
                         capture_output=True, text=True, encoding="utf-8", cwd=str(BASE_DIR), shell=True)
    data = json.loads(out.stdout[out.stdout.index("["):])
    return data[0]["results"]


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    d0 = a[0]
    d1_ = a[1] if len(a) > 1 else a[0]
    lo = int(datetime.strptime(d0, "%Y-%m-%d").timestamp()) - 86400
    hi = int((datetime.strptime(d1_, "%Y-%m-%d") + timedelta(days=2)).timestamp())
    log = d1(f"SELECT id, ts, kind, fixture, th, ta, h, a, prev_h, prev_a, minute, league FROM goal_log "
             f"WHERE ts >= {lo} AND ts < {hi} ORDER BY fixture, id")
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    matches = con.execute(
        "SELECT match_id, date, league_code, home_id, away_id, home_goals, away_goals, status FROM matches "
        "WHERE date(date) BETWEEN ? AND ? ORDER BY date", (d0, d1_)).fetchall()
    by_fx = {}
    for r in log:
        by_fx.setdefault(r["fixture"], []).append(r)
    ids = {m[0] for m in matches} | set(by_fx)
    bad = 0
    print(f"فترة {d0} → {d1_}: مباريات بـDB {len(matches)} · مباريات بسجل الكشف {len(by_fx)} · صفوف السجل {len(log)}\n")
    for mid in sorted(ids, key=lambda i: next((m[1] for m in matches if m[0] == i), "9999")):
        m = next((x for x in matches if x[0] == mid), None)
        rows = by_fx.get(mid, [])
        net = sum((r["h"] - r["prev_h"]) + (r["a"] - r["prev_a"]) for r in rows)
        notes = []
        if m is None:
            notes.append("مباراة بالسجل غير موجودة بالـDB بالفترة")
            status = "؟"
        elif m[5] is None:
            status, fin = "غير منتهية بالـDB", None
            notes.append("لم تنزل النتيجة النهائية بعد — أعد بعد deploy-site")
        else:
            fin = (m[5], m[6])
            actual = m[5] + m[6]
            last = (rows[-1]["h"], rows[-1]["a"]) if rows else (0, 0)
            ok = True
            if net != actual:
                ok = False
                notes.append(f"صافي الكشف {net} ≠ أهداف المباراة {actual}")
            if rows and last != fin:
                ok = False
                notes.append(f"آخر نتيجة بالسجل {last[0]}-{last[1]} ≠ النهائية {fin[0]}-{fin[1]}")
            if not rows and actual > 0:
                ok = False
                notes.append("أهداف حقيقية بلا أي صف بالسجل (ناقص)")
            # chain consistency + duplicates
            for i, r in enumerate(rows):
                if i and (r["prev_h"], r["prev_a"]) != (rows[i - 1]["h"], rows[i - 1]["a"]):
                    ok = False
                    notes.append(f"سلسلة مقطوعة عند الصف {r['id']}")
                if i and all(r[k] == rows[i - 1][k] for k in ("kind", "h", "a", "prev_h", "prev_a")) and r["ts"] - rows[i - 1]["ts"] < 120:
                    ok = False
                    notes.append(f"تكرار الصف {r['id']} (نفس الحدث خلال دقيقتين)")
            status = "✔" if ok else "✘"
            if not ok:
                bad += 1
            # minutes vs DB goals (informational)
            gm = [g[0] for g in con.execute("SELECT minute FROM goals WHERE match_id = ? ORDER BY minute", (mid,)) if g[0] is not None]
            dm = sorted(r["minute"] for r in rows if r["kind"] == "goal" and r["minute"] is not None)
            if gm and dm and len(gm) == len(dm) and any(abs(x - y) > 3 for x, y in zip(gm, dm)):
                notes.append(f"ملاحظة: دقائق DB {gm} مقابل الكشف {dm}")
        title = f"{mid} {m[1] if m else '':16} {m[2] if m else '':4}" if m else f"{mid}"
        fin_txt = f"{m[5]}-{m[6]}" if m and m[5] is not None else "—"
        print(f"{status} {title} نهائي DB {fin_txt} · صفوف السجل {len(rows)} · صافي {net}" + ("".join(f"\n     - {n}" for n in notes)))
    print(f"\nالنتيجة: {'تطابق كامل' if bad == 0 else str(bad) + ' مباراة بفروق'} (المباريات المنتهية فقط تُحتسب)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
