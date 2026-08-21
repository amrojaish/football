#!/usr/bin/env python3
"""
اقتراح دمج صيغ أسماء اللاعبين
================================
ينتج player_merges_new.csv من دليل قوي واحد: **نفس الترجمة
العربية لصيغتين إنجليزيتين مختلفتين** — أي أن المترجِم البشري
عرف أنهما لاعب واحد أثناء الترجمة.

ثم يُصنَّف كل ترشيح بثلاثة حَكَمين:

⚠️ **النفي القاطع: الظهور بنفس كشف مباراة واحدة**
   (`lineup_players` لنفس `match_id`). مستحيل أن يكون الشخص
   لاعبَين في نفس اللقاء.
   ولا يصحّ حساب التصادم عبر الجداول مجتمعة: المزوّد يكتب
   الاسم مختصراً في `goals` وكاملاً في `lineup_players` لنفس
   المباراة، فيبدو الاسمان متزامنين وهما واحد.

⚠️ **`player_id` دليل إثبات لا نفي.** المزوّد يمنح اللاعب
   الواحد معرّفين مختلفين بين موسمين:
       G. Hawsawi       id=576151  الأخدود 2025
       Ghassan Hawsawi  id=483963  الأخدود 2024
   فتطابق المعرّف يؤكّد، واختلافه لا ينفي.

⚠️ **تعدّد الأندية ليس نفياً** — اللاعب ينتقل.

التوافق النصي: تطابق اللقب (أو التصاقه: Bani Hani/Banihani،
أو فرق حرف واحد للألقاب الطويلة) + توافق الاسم الأول.

الأسماء المصنّفة [تخميني] **لا تُطبَّق** — يتخطاها
`apply_player_merges.py`. راجعها يدوياً وارفع ما تتأكد منه.

الاسم المُحتفَظ به: الأكثر مقاطع، ثم الأقل اختصاراً، ثم الأطول.

صفر طلبات API.

    python build_merges.py
"""

import sqlite3
import csv
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from config import DB_FILE, BASE_DIR

OUT = BASE_DIR / "player_merges_new.csv"
STOP = ("al", "el", "bin", "ibn", "abu", "de", "da")

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


def surname_ok(ta, tb):
    if ta[-1] == tb[-1]:
        return True
    ja = "".join(ta[1:]) or ta[-1]
    jb = "".join(tb[1:]) or tb[-1]
    if ja == jb:
        return True
    s1, s2 = ta[-1], tb[-1]
    return lev(s1, s2) <= 1 and min(len(s1), len(s2)) >= 5


def first_ok(ta, tb):
    if len(ta) == 1 or len(tb) == 1:
        return True
    fa, fb = ta[0], tb[0]
    if fa == fb:
        return True
    if len(fa) == 1 and fb.startswith(fa):
        return True
    if len(fb) == 1 and fa.startswith(fb):
        return True
    return lev(fa, fb) <= 1 and min(len(fa), len(fb)) >= 4


def compatible(a, b):
    ta, tb = norm(a), norm(b)
    return bool(ta and tb) and surname_ok(ta, tb) and first_ok(ta, tb)


def fullness(e):
    t = norm(e)
    return (len(t), -sum(1 for x in t if len(x) == 1), len(e))


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return

    conn = sqlite3.connect(DB_FILE)
    tables = ("goals", "lineup_players", "player_stats", "events")

    rev = defaultdict(set)
    for t in tables:
        try:
            rows = conn.execute(f"""
                SELECT DISTINCT player_en, player_ar FROM {t}
                WHERE player_en != ''
                  AND player_ar IS NOT NULL AND player_ar != ''
            """).fetchall()
        except sqlite3.OperationalError:
            continue
        for en, ar in rows:
            rev[ar].add(en)

    groups = {k: sorted(v) for k, v in rev.items() if len(v) > 1}

    def lineup_matches(en):
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT match_id FROM lineup_players WHERE player_en = ?",
            (en,))}

    def ids_of(en):
        s = set()
        for t in ("lineup_players", "player_stats"):
            for r in conn.execute(
                    f"""SELECT DISTINCT player_id FROM {t}
                        WHERE player_en = ? AND player_id IS NOT NULL""",
                    (en,)):
                s.add(r[0])
        return s

    # ⚠️ **التحليل زوجي لا جماعي.** المجموعة الواحدة قد تضمّ
    #    لاعبَين مختلفَين وثالثاً يطابق أحدهما: الرفض الجماعي
    #    يضيّع دمجاً صحيحاً. مثال محقَّق:
    #        Mohammed Al Aqel  id=326655
    #        Mohammed Al Aqal  id=326655   <- نفسه
    #        Mohamed Al Oqil   id=432634   <- لاعب آخر
    #    فنقيس كل زوج على حدة ثم نجمع الأزواج المقبولة بعناقيد.
    rows, veto = [], []
    for ar, ens in groups.items():
        lp = {e: lineup_matches(e) for e in ens}
        ids = {e: ids_of(e) for e in ens}

        parent = {e: e for e in ens}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        pair_note = {}
        rejected = []
        for i, a in enumerate(ens):
            for b in ens[i + 1:]:
                if lp[a] & lp[b]:
                    rejected.append((a, b))
                    continue
                shared = bool(ids[a] and ids[b] and (ids[a] & ids[b]))
                text_ok = compatible(a, b)
                if shared and text_ok:
                    note = "نفس player_id + الصيغ متوافقة"
                elif shared:
                    note = "نفس player_id"
                elif text_ok:
                    note = "الصيغ متوافقة نصياً + نفس الترجمة"
                else:
                    note = None
                if note:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
                    pair_note[(a, b)] = note

        if rejected:
            veto.append((ar, rejected))

        clusters = defaultdict(list)
        for e in ens:
            clusters[find(e)].append(e)

        for members in clusters.values():
            if len(members) < 2:
                continue
            keep = max(members, key=fullness)
            for e in members:
                if e == keep:
                    continue
                note = (pair_note.get((e, keep)) or pair_note.get((keep, e))
                        or "متصل عبر صيغة وسيطة")
                rows.append({"old_name": e, "keep_name": keep,
                             "confidence": "مؤكد",
                             "note": f"{note} ({ar})"})

        # صيغ لم تُقبل مع أي أخرى -> ترشيح تخميني للمراجعة
        singles = [m[0] for m in clusters.values() if len(m) == 1]
        if singles and len(clusters) > 1:
            biggest = max(clusters.values(), key=len)
            if len(biggest) > 1:
                keep = max(biggest, key=fullness)
                for e in singles:
                    rows.append({"old_name": e, "keep_name": keep,
                                 "confidence": "تخميني",
                                 "note": f"نفس الترجمة فقط — لم يثبت ({ar})"})

    conn.close()
    rows.sort(key=lambda r: (r["confidence"], r["keep_name"]))

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["old_name", "keep_name",
                                          "confidence", "note"])
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["confidence"] for r in rows)
    print(f"\n{'=' * 58}")
    print(f"  مجموعات (نفس الترجمة لصيغ متعددة): {len(groups)}")
    print(f"{'=' * 58}")
    print(f"  ✅ مؤكد    : {c['مؤكد']} صيغة")
    print(f"  ⚠️ تخميني  : {c['تخميني']} صيغة — لن تُطبَّق")
    print(f"  ⛔ أزواج مرفوضة (بنفس كشف مباراة): {len(veto)} مجموعة")
    for ar, pairs in veto:
        for a, b in pairs:
            print(f"       {ar}: {a}  ≠  {b}")
    print(f"\n  تم إنشاء {OUT.name}")
    print("""
  الخطوة الجاية:
      راجع الملف، ثم ادمج صفوفه في player_merges.csv
      python apply_player_merges.py --check
    """)


if __name__ == "__main__":
    main()
