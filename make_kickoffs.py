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

from config import BASE_DIR, DB_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = BASE_DIR / "assets" / "next_kickoffs.json"
BACK_SECS = 2 * 3600
AHEAD_SECS = 48 * 3600


def build(con, now):
    ks = set()
    for (d,) in con.execute("SELECT date FROM matches WHERE status = 'NS' AND date IS NOT NULL"):
        try:
            t = int(datetime.strptime(d[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
        if now - BACK_SECS <= t <= now + AHEAD_SECS:
            ks.add(t)
    return {"t": now, "k": sorted(ks)}


def main():
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    out = build(con, int(time.time()))
    con.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"next_kickoffs.json: {len(out['k'])} موعداً خلال 48 ساعة → {OUT}")


if __name__ == "__main__":
    main()
