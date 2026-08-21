#!/usr/bin/env python3
"""
مراجعة ترشيحات الدمج قبل تطبيقها
===================================
يقرأ player_merges_new.csv ويرتّب صفوفه بالخطورة بدل أن تُقرأ
500 صف بالتساوي.

⚠️ **الإشارة الأساسية (نفس الترجمة العربية) تنكسر في حالة
   واحدة: خطأ ترجمة.** إن أُعطي لاعبان مختلفان نفس الاسم
   العربي، بدَوا لاعباً واحداً. حالات محقَّقة:
       B. Nasser      ≟  Bandar Al Mutairi
       A. Al Duqayl   ≟  Abdulraouf Al Dakheel
   اللقبان مختلفان تماماً — ومرّت لأن player_id تطابق وحده.

التصنيف:
    🔴 خطر   — اللقبان مختلفان جذرياً: راجعها واحدة واحدة
    🟡 انتبه — لقب متقارب إملائياً (فرق حرف)
    🟢 آمن   — نفس اللقب، الفرق اختصار أو تشكيل

صفر طلبات API. لا يكتب شيئاً — عرض فقط.

    python review_merges.py
    python review_merges.py --risky   <- الخطرة فقط
"""

import csv
import re
import sys
import unicodedata
from config import BASE_DIR

SRC = BASE_DIR / "player_merges_new.csv"
STOP = ("al", "el", "bin", "ibn", "abu", "de", "da")
ONLY_RISKY = "--risky" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z ]", " ", s.replace("-", " "))
    return [w for w in s.split() if w not in STOP]


def lev(a, b):
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def risk(old, keep):
    ta, tb = norm(old), norm(keep)
    if not ta or not tb:
        return 0
    if ta[-1] == tb[-1]:
        return 0
    ja = "".join(ta[1:]) or ta[-1]
    jb = "".join(tb[1:]) or tb[-1]
    if ja == jb:
        return 0
    d = lev(ta[-1], tb[-1])
    if d <= 2 and min(len(ta[-1]), len(tb[-1])) >= 4:
        return 1
    return 2


def main():
    if not SRC.exists():
        print(f"ما لقيت {SRC.name} — شغّل build_merges.py أول")
        return

    rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))
            if (r.get("confidence") or "").strip() != "تخميني"]

    buckets = {0: [], 1: [], 2: []}
    for r in rows:
        buckets[risk(r["old_name"], r["keep_name"])].append(r)

    print()
    print("=" * 62)
    print(f"  ترشيحات مؤكدة: {len(rows)}")
    print("=" * 62)
    print(f"  🔴 خطر   (لقبان مختلفان)  : {len(buckets[2])}  <- راجعها")
    print(f"  🟡 انتبه (فرق إملائي)     : {len(buckets[1])}")
    print(f"  🟢 آمن   (نفس اللقب)      : {len(buckets[0])}")
    print("=" * 62)

    print(f"\n🔴 الخطرة — {len(buckets[2])} صفاً:")
    for r in buckets[2]:
        ar = r["note"].split("(")[-1].rstrip(")")
        print(f"   {r['old_name']:30} -> {r['keep_name']:30} | {ar}")

    if ONLY_RISKY:
        return

    print(f"\n🟡 المتقاربة إملائياً — {len(buckets[1])} صفاً:")
    for r in buckets[1][:40]:
        print(f"   {r['old_name']:30} -> {r['keep_name']}")
    if len(buckets[1]) > 40:
        print(f"   ... و{len(buckets[1]) - 40} غيرها")

    print("""
  🟢 الآمنة لا تحتاج مراجعة فردية — الفرق اختصار أو تشكيل.

  بعد المراجعة: احذف أي صف مرفوض من player_merges_new.csv ثم:
      python add_merges.py --check
    """)


if __name__ == "__main__":
    main()
