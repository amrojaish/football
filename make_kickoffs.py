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


def build(con, now):
    ks = set()
    fx = []   # f: [ts, fixture, th, ta, league(مزوّد), اسم المضيف EN, اسم الضيف EN] — لتذكير «قبل 30 دقيقة» (worker، 3E). إضافة فقط؛ k كما هو.
    names = {r[0]: r[1] for r in con.execute("SELECT team_id, COALESCE(NULLIF(name_en_official, ''), name_en) FROM teams")}
    for mid, d, lg, h, a in con.execute("SELECT match_id, date, league_code, home_id, away_id FROM matches WHERE status = 'NS' AND date IS NOT NULL"):
        try:
            t = int(datetime.strptime(d[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
        if now - BACK_SECS <= t <= now + AHEAD_SECS:
            ks.add(t)
            if t >= now - 600:
                fx.append([t, mid, h, a, (LEAGUES.get(lg) or {}).get("id"), names.get(h, ""), names.get(a, "")])
    fx.sort()
    return {"t": now, "k": sorted(ks), "f": fx}


def main():
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    out = build(con, int(time.time()))
    con.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"next_kickoffs.json: {len(out['k'])} موعداً خلال 48 ساعة → {OUT}")


if __name__ == "__main__":
    main()
