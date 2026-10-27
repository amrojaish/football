"""
assets/next_kickoffs.json — {"t": توليد (ثوانٍ UTC), "k": [مواعيد انطلاق UTC بالثواني، تصاعدياً بلا تكرار]}

يقرؤه worker saffara-live (من saffara.app، كاش 10 دقائق) ليسحب كل دقيقة من 10 دقائق قبل أي موعد بدل خمول الـ5 دقائق
(هدف الدقيقة 3 بالمباراة 1627995 ضاع بنافذة الخمول). مباريات الدوريات السبعة (جدول matches) غير المنتهية فقط،
من ساعتين مضت (ليغطي ملفاً قديماً حتى 3-6 ساعات بين النشرات) وحتى 48 ساعة قادمة. matches.date بتوقيت UTC.
⚠️ assets/ مجلد مولَّد يُمسح بالبناء النظيف: هذا يشتغل بعد make_assets.py. صفر طلبات API.
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from config import BASE_DIR, DB_FILE, LEAGUES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "assets" / "next_kickoffs.json"
BACK_SECS = 2 * 3600
AHEAD_SECS = 48 * 3600
# v (27 أكتوبر 2026، تصويت «مين رح يفوز؟»): {fixture: موعد الانطلاق} لكل مباراة غير منتهية من ساعتين مضتا حتى 14 يوماً — الـworker يقبل
# الصوت قبل الموعد فقط ويرفض المباراة الغائبة (unknown). أوسع من k/f (48 ساعة) لأن صفحة المباراة تُفتح قبلها بأيام.
VOTE_AHEAD_SECS = 14 * 86400
# NS + الجارية/الموقوفة: fetch_upcoming.py يكتب حالة المزوّد الجارية منذ 26 أكتوبر، فـNS وحدها كانت ستُسقط مباراة جارية من النافذة
PENDING = ("NS", "1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT")


def build(con, now):
    ks = set()
    votes = {}
    fx = []   # f: [ts, fixture, th, ta, league(مزوّد), اسم المضيف EN, اسم الضيف EN] — لتذكير «قبل 30 دقيقة» (worker، 3E). إضافة فقط؛ k كما هو.
    names = {r[0]: r[1] for r in con.execute("SELECT team_id, COALESCE(NULLIF(name_en_official, ''), name_en) FROM teams")}
    q = ",".join("?" * len(PENDING))
    for mid, d, lg, h, a in con.execute(f"SELECT match_id, date, league_code, home_id, away_id FROM matches "
                                        f"WHERE status IN ({q}) AND home_goals IS NULL AND date IS NOT NULL", PENDING):
        try:
            t = int(datetime.strptime(d[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
        if now - BACK_SECS <= t <= now + VOTE_AHEAD_SECS:
            votes[str(mid)] = t
        if now - BACK_SECS <= t <= now + AHEAD_SECS:
            ks.add(t)
            if t >= now - 600:
                fx.append([t, mid, h, a, (LEAGUES.get(lg) or {}).get("id"), names.get(h, ""), names.get(a, "")])
    fx.sort()
    return {"t": now, "k": sorted(ks), "f": fx, "v": votes}


def main():
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    out = build(con, int(time.time()))
    con.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"next_kickoffs.json: {len(out['k'])} موعداً خلال 48 ساعة → {OUT}")


if __name__ == "__main__":
    main()
