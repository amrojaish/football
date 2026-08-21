#!/usr/bin/env python3
"""
مطابقة الاسم الكامل مع المختصر المترجَم
==========================================
بعد تطبيق 694 ترجمة، بقي 1,107 اسماً "غير مترجَم" — لكن فحص
العيّنة كشف أن **معظمهم مترجَمون فعلاً بصيغة أخرى**:

    Franck Kessié      ← موجود كـ F. Kessié      = فرانك كيسي
    Fashion Sakala     ← موجود كـ F. Sakala      = فاشون ساكالا
    Marcelo Brozović   ← موجود كـ M. Brozović    = مارسيلو بروزوفيتش
    Abdullah Al-Salem  ← موجود كـ Abdullah Al Salem = عبد الله السالم

⚠️ **السبب البنيوي (درس 44):** `goals` يستعمل الاسم المختصر،
   و`player_stats` يستعمل الكامل — نفس اللاعب باسمين.

يطابق بثلاث طرق متدرّجة:
    1. **بصمة مباشرة** — تجريد اللكنات والشرطة والمسافة
    2. **اختصار الاسم الكامل** — Franck Kessie → f kessie
    3. **توسيع المختصر** — لا يُجرَّب (غامض: A. Ali قد يكون
       Ahmed أو Ali أو Abdullah)

⚠️ **لا تخمين إطلاقاً** — كل مطابقة مبنية على ترجمة موجودة
   فعلاً لنفس اللاعب، لا على استنتاج الاسم.

⚠️ نسخة احتياطية قبل الكتابة.

التشغيل:
    python match_fullnames.py --check
    python match_fullnames.py
"""

import csv
import io
import os
import re
import shutil
import sqlite3
import sys
import unicodedata

CSV_FILE = "players_ar.csv"
DB = "football.db"
CHECK = "--check" in sys.argv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def fold(s):
    """بصمة: تجريد اللكنات وتوحيد الشرطة والمسافة"""
    s = unicodedata.normalize("NFKD", (s or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"[-.]", " ", s)
    return " ".join(s.split()).lower()


def to_initial(s):
    """Franck Kessie -> f kessie  (اختصار الاسم الأول)"""
    parts = fold(s).split()
    if len(parts) < 2:
        return None
    return parts[0][0] + " " + " ".join(parts[1:])


def main():
    if not os.path.exists(CSV_FILE):
        print("ما لقيت players_ar.csv")
        return

    rows = list(csv.DictReader(
        io.open(CSV_FILE, encoding="utf-8-sig")))

    # ── خرائط الترجمات الموجودة ──────────────────────
    by_fold = {}
    by_initial = {}
    for r in rows:
        ar = (r["player_ar"] or "").strip()
        if not ar:
            continue
        en = r["player_en"]
        by_fold.setdefault(fold(en), ar)
        ini = to_initial(en)
        if ini:
            by_initial.setdefault(ini, ar)
        # الاسم المختصر نفسه مفتاح: "F. Kessie" -> "f kessie"
        by_initial.setdefault(fold(en), ar)

    # ── كل الأسماء بالديتابيس ────────────────────────
    all_names = set()
    if os.path.exists(DB):
        conn = sqlite3.connect(DB)
        for tbl in ("goals", "lineup_players", "player_stats",
                    "events"):
            try:
                for r in conn.execute(
                        f"SELECT DISTINCT player_en FROM {tbl} "
                        f"WHERE player_en IS NOT NULL "
                        f"AND player_en != ''"):
                    all_names.add(r[0])
            except sqlite3.Error:
                pass
        conn.close()

    csv_names = {r["player_en"] for r in rows}
    translated = {r["player_en"] for r in rows
                  if (r["player_ar"] or "").strip()}

    # ── الأسماء غير المترجَمة ────────────────────────
    untranslated = [n for n in all_names if n not in translated]

    print()
    print("=" * 60)
    print(f"  أسماء بالديتابيس   : {len(all_names):,}")
    print(f"  مترجَمة            : {len(translated):,}")
    print(f"  غير مترجَمة        : {len(untranslated):,}")
    print("=" * 60)

    # ── المطابقة ─────────────────────────────────────
    matched = {}
    for name in untranslated:
        f = fold(name)
        if f in by_fold:
            matched[name] = (by_fold[f], "بصمة")
            continue
        ini = to_initial(name)
        if ini and ini in by_initial:
            matched[name] = (by_initial[ini], "اختصار")

    print(f"\n  طوبقت: {len(matched):,}")
    by_kind = {}
    for _, (_, kind) in matched.items():
        by_kind[kind] = by_kind.get(kind, 0) + 1
    for k, v in by_kind.items():
        print(f"    {k}: {v}")

    print("\n  عيّنة:")
    for name, (ar, kind) in list(matched.items())[:12]:
        print(f"    {name:<30} → {ar}   [{kind}]")

    still = len(untranslated) - len(matched)
    print(f"\n  يبقى بلا مطابقة: {still:,}")

    if CHECK:
        print("\n  [وضع الفحص] — ما انكتب شي\n")
        return

    if not matched:
        print("\n  ما في شي للإضافة\n")
        return

    # ── إضافة الصفوف الجديدة للـCSV ──────────────────
    shutil.copy(CSV_FILE, CSV_FILE + ".before_match")

    added = 0
    filled = 0
    for r in rows:
        en = r["player_en"]
        if en in matched and not (r["player_ar"] or "").strip():
            r["player_ar"] = matched[en][0]
            filled += 1

    existing = {r["player_en"] for r in rows}
    for name, (ar, kind) in matched.items():
        if name in existing:
            continue
        rows.append({
            "priority": "D",
            "goals": 0,
            "league": "",
            "team_ar": "",
            "player_en": name,
            "player_ar": ar,
        })
        added += 1

    with io.open(CSV_FILE, "w", encoding="utf-8-sig",
                 newline="") as f:
        w = csv.DictWriter(f, fieldnames=["priority", "goals",
                                          "league", "team_ar",
                                          "player_en", "player_ar"])
        w.writeheader()
        w.writerows(rows)

    total = sum(1 for r in rows if (r["player_ar"] or "").strip())
    print(f"\n  نسخة احتياطية: {CSV_FILE}.before_match")
    print(f"  عُبِّئت صفوف موجودة : {filled}")
    print(f"  أُضيفت صفوف جديدة  : {added}")
    print(f"  الإجمالي المترجَم  : {total:,} من {len(rows):,}")
    print("""
  الخطوة الجاية:
      python apply_players_ar.py
      python list_untranslated.py
    """)


if __name__ == "__main__":
    main()
