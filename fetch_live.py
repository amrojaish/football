#!/usr/bin/env python3
"""
سحب المباريات المباشرة
========================
يكتب `live.json` — ملف خفيف (~1 كيلوبايت) فيه المباريات
الجارية الآن بنتيجتها ودقيقتها.

⚠️ **لماذا ملف منفصل لا أعمدة في `matches`؟**
   الحالة المباشرة تتغيّر كل دقيقة. لو حُفظت في الديتابيس،
   كل تحديث يعني إعادة توليد 9,000 صفحة ورفع 12 ميغابايت —
   مستحيل كل 3 دقائق. الملف المنفصل يُكتب في ثانية، والصفحات
   الموجودة تقرأه بالمتصفح وتحدّث نفسها بلا إعادة توليد.

⚠️ **الكلفة: طلب واحد فقط** — `live=387-542-307` يجلب كل
   مباريات دورياتنا الجارية دفعة واحدة. حتى كل 3 دقائق طوال
   اليوم = 480 طلباً (6% من حصة 7,500).

⚠️ **يُكتب دائماً حتى لو صفر مباريات** — الملف الفارغ يخبر
   الصفحة "لا شيء يُلعب الآن"، وغيابه يعني عطلاً.

بنية الملف:
    {
      "t": 1755712345,            ← وقت السحب (epoch)
      "m": {
        "1627042": {
          "h": 0, "a": 0,          ← النتيجة
          "e": 45,                 ← الدقيقة
          "s": "1H"                ← الحالة
        }
      }
    }

التشغيل:
    python fetch_live.py
    python fetch_live.py --check   <- عرض بلا كتابة
"""

import json
import sys
import time
import urllib.request

from config import API_BASE, DB_FILE, LEAGUES, check_key, headers

OUT = DB_FILE.parent / "live.json"
CHECK = "--check" in sys.argv

# الحالات التي تعني "المباراة جارية الآن"
LIVE_STATUS = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def league_ids():
    ids = []
    for code, cfg in LEAGUES.items():
        lid = cfg.get("id") if isinstance(cfg, dict) else cfg
        if lid:
            ids.append(str(lid))
    return ids


def main():
    if not check_key():
        return

    ids = league_ids()
    if not ids:
        print("ما قدرت أقرأ معرّفات الدوريات من config")
        return

    url = f"{API_BASE}/fixtures?live={'-'.join(ids)}"
    req = urllib.request.Request(url, headers=headers())

    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ❌ فشل الطلب: {type(e).__name__}")
        return

    # درس: المزوّد يرجع 200 مع أخطاء داخل errors
    errs = data.get("errors")
    if errs:
        print(f"  ❌ خطأ من المزوّد: {errs}")
        return

    resp = data.get("response") or []

    live = {}
    for f in resp:
        fx = f.get("fixture", {})
        st = (fx.get("status") or {})
        short = st.get("short")

        if short not in LIVE_STATUS:
            continue

        mid = fx.get("id")
        if mid is None:
            continue

        gl = f.get("goals", {})
        live[str(mid)] = {
            "h": gl.get("home"),
            "a": gl.get("away"),
            "e": st.get("elapsed"),
            "s": short,
        }

    payload = {"t": int(time.time()), "m": live}

    print()
    print("=" * 55)
    print(f"  مباريات جارية: {len(live)}")
    print("=" * 55)

    if resp and not live:
        print("  ⚠️ رجّع مباريات لكن لا واحدة بحالة جارية")

    names = {}
    for f in resp:
        fx = f.get("fixture", {})
        tm = f.get("teams", {})
        mid = str(fx.get("id"))
        if mid in live:
            h = (tm.get("home") or {}).get("name", "?")
            a = (tm.get("away") or {}).get("name", "?")
            d = live[mid]
            print(f"    {h} {d['h']}-{d['a']} {a}   "
                  f"د.{d['e']}  [{d['s']}]")

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False,
                  separators=(",", ":"))

    kb = OUT.stat().st_size / 1024
    print(f"\n  كُتب live.json  ({kb:.1f} كيلوبايت)")
    print("  استُهلك: طلب واحد\n")


if __name__ == "__main__":
    main()
