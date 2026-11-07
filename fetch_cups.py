#!/usr/bin/env python3
"""
سحب الكؤوس المفعّلة بكل تشغيل (الموجة 1، 4 نوفمبر 2026) — خطوة بـupdate_all.py
==================================================================================
لكل رمز بـconfig.ENABLED_CUPS (موسم المزوّد الجاري بالسجلّ):
    شرط أول   كأس بلا أي صف بالقاعدة = لا سحب إطلاقاً (لا شيء على القاعدة الحية قبل الاستيراد اليدوي import_cups.py).
    البوّابة   فقط كأس له مباراة بالقاعدة اليوم/أمس/خلال 7 أيام قادمة (UTC، DATE(date) بين أمس واليوم+7).
              + الاكتشاف اليومي: تشغيل 00:05 UTC (الساعة 0، أول 30 دقيقة) يسحب **كل** الكؤوس المفعّلة مرة — بلا هذا لا تظهر
              مباريات دور جديد (مثلاً ربع نهائي كأس الملك بعد فراغ أسابيع) لأن البوّابة تقرأ القاعدة لا المزوّد.
    الطلب 1   fixtures?league&season — الحالة والنتيجة والموعد لكل مباريات الموسم (بلا أحداث).
    الطلب 2+  fixtures?ids= (≤ 20) فقط لمباراة انتهت عند المزوّد وصفّها عندنا غير منتهٍ أو أهدافه أقل من النتيجة — تفاصيلها كاملة
              (الأهداف بلا ركلات الترجيح، الأحداث، التشكيلات) بنفس كتّاب import_cups.py.
    لا تُكتب مباراة منتهية مكتملة عندنا من جديد (ردّ القائمة بلا أحداث كان سيمسح أهدافها).
⚠️ الحصة: --budget طلبات بالتشغيل (افتراضي 6)، وتوقّف حين x-ratelimit-requests-remaining < 2,000 (كـfetch_player_info).
⚠️ البثّ الحي والتنبيهات للكؤوس: لاحقاً (worker.js بلا معرّفات الكؤوس بعد).

التشغيل:
    python fetch_cups.py --check        ← البوّابة فقط: أيّ كأس سيُسحب الآن (بلا API ولا كتابة)
    python fetch_cups.py --budget 6
"""
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import import_cups as IC
from config import COMPETITIONS, DB_FILE, ENABLED_CUPS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_REMAINING = 2000
DEFAULT_BUDGET = 6
FINAL = IC.FINAL + IC.AWARDED
STALE_DAYS = 3     # منتهية أقدم من هذا بأهداف ناقصة = لا طلب تفاصيل بعدها (needs_details)


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def discovery_run(now):
    """أول تشغيل باليوم (00:05 UTC بجدولة 5,35): كل الكؤوس المفعّلة مرة"""
    return now.hour == 0 and now.minute < 30


def gated(conn, now, codes=None):
    """[(code, سبب)] للكؤوس التي تُسحب الآن"""
    lo = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    hi = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    out = []
    for code in codes or ENABLED_CUPS:
        season = COMPETITIONS[code]["season"]
        # (4 نوفمبر 2026، قرار عمرو) لا شيء قبل الاستيراد اليدوي: كأس بلا أي صف بالقاعدة لا يُسحب أبداً (ولا بالاكتشاف اليومي) —
        #   بلا هذا كان تشغيل 00:05 سيسحب الكؤوس التسعة ويكتبها بالقاعدة الحية = استيراد غير مقصود. بعد import_cups.py يعمل تلقائياً.
        if not conn.execute("SELECT 1 FROM matches WHERE league_code = ? LIMIT 1", (code,)).fetchone():
            continue
        hit = conn.execute("SELECT 1 FROM matches WHERE league_code = ? AND season = ? AND DATE(date) BETWEEN ? AND ? LIMIT 1",
                           (code, season, lo, hi)).fetchone()
        if hit:
            out.append((code, "window"))
        elif discovery_run(now):
            out.append((code, "daily"))
    return out


def http_get(endpoint, params):
    """(ok, response, remaining) — طلب واحد"""
    import requests
    from config import API_BASE, headers
    try:
        r = requests.get(f"{API_BASE}/{endpoint}", headers=headers(), params=params, timeout=30)
    except requests.RequestException as e:
        return False, [], None, type(e).__name__
    rem = r.headers.get("x-ratelimit-requests-remaining")
    rem = int(rem) if rem not in (None, "") else None
    if r.status_code != 200:
        return False, [], rem, f"HTTP {r.status_code}"
    d = r.json()
    if d.get("errors"):
        return False, [], rem, f"API: {d['errors']}"
    return True, d.get("response") or [], rem, ""


def needs_details(conn, fx, now=None):
    """مباراة انتهت عند المزوّد: هل صفّها عندنا ناقص (غير منتهٍ، أو أهدافه أقل من النتيجة)؟"""
    if fx["fixture"]["status"]["short"] not in FINAL:
        return False
    r = conn.execute("SELECT status, home_goals, away_goals FROM matches WHERE match_id = ?", (fx["fixture"]["id"],)).fetchone()
    if r is None or r[0] not in FINAL or r[1] is None:
        return True
    # (5 نوفمبر 2026، الموجة 2a) منتهية عندنا بنتيجتها وأقدم من 3 أيام: المزوّد بلا أحداث لها (3 مباريات بكأس العرش) — لا نعيد طلبها للأبد
    ts = fx["fixture"].get("timestamp")
    if now is not None and ts and ts < (now - timedelta(days=STALE_DAYS)).timestamp():
        return False
    n = conn.execute("SELECT COUNT(*) FROM goals WHERE match_id = ?", (fx["fixture"]["id"],)).fetchone()[0]
    return n < (r[1] or 0) + (r[2] or 0)


def run(conn, now, budget, fetch=http_get, codes=None):
    rep = {"gated": gated(conn, now, codes), "calls": 0, "lines": [], "stopped": None}
    left = budget
    for code, why in rep["gated"]:
        if left <= 0 or rep["stopped"]:
            rep["lines"].append(f"{code}: تُخطّي (الميزانية/الحصة)")
            continue
        season = COMPETITIONS[code]["season"]
        ok, lst, rem, reason = fetch("fixtures", {"league": COMPETITIONS[code]["id"], "season": season})
        rep["calls"] += 1
        left -= 1
        if rem is not None and rem < MIN_REMAINING:
            rep["stopped"] = f"متبقٍّ {rem} < {MIN_REMAINING}"
        if not ok:
            rep["lines"].append(f"{code}: فشل القائمة ({reason})")
            continue
        lst = [IC.alias_fixture(fx) for fx in lst]   # (الموجة 4) config.TEAM_ID_ALIASES — المعرّف المكرّر لا يُكتب أبداً
        need = [fx["fixture"]["id"] for fx in lst if needs_details(conn, fx, now)]
        full = {}
        for i in range(0, len(need), IC.IDS_MAX):
            if left <= 0 or rep["stopped"]:
                break
            ok2, got, rem, reason = fetch("fixtures", {"ids": "-".join(map(str, need[i:i + IC.IDS_MAX]))})
            rep["calls"] += 1
            left -= 1
            if rem is not None and rem < MIN_REMAINING:
                rep["stopped"] = f"متبقٍّ {rem} < {MIN_REMAINING}"
            if ok2:
                full.update({x["fixture"]["id"]: IC.alias_fixture(x) for x in got})
        # اكتب: المنتهية الناقصة بتفاصيلها (إن وصلت)، وغير المنتهية كلها؛ المنتهية المكتملة عندنا لا تُلمس
        write = [fx for fx in lst if fx["fixture"]["status"]["short"] not in FINAL or fx["fixture"]["id"] in full]
        r = IC.import_code(conn, code, write, full) if write else {"finished": 0, "unplayed": 0}
        conn.commit()
        rep["lines"].append(f"{code} ({why}): {len(lst)} بالقائمة · تفاصيل {len(full)}/{len(need)} · "
                            f"منتهية كُتبت {r['finished']} · قادمة/أخرى {r['unplayed']}")
        time.sleep(0 if fetch is not http_get else 1.0)
    return rep


def main():
    now = datetime.now(timezone.utc)
    if "--check" in sys.argv:
        conn = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True)
        print(f"  الكؤوس المستحقّة الآن ({now:%Y-%m-%d %H:%M} UTC): {gated(conn, now) or 'لا شيء'}")
        return 0
    from config import check_key
    if not check_key():
        return 0
    conn = sqlite3.connect(DB_FILE)
    rep = run(conn, now, int(arg("--budget", DEFAULT_BUDGET)))
    conn.close()
    print(f"  الكؤوس: مستحقّة {len(rep['gated'])} · طلبات {rep['calls']}" + (f" · توقّف: {rep['stopped']}" if rep["stopped"] else ""))
    for ln in rep["lines"]:
        print("   ", ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
