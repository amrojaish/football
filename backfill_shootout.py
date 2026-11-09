#!/usr/bin/env python3
"""
تعبئة ركلات الترجيح بأثر رجعي (المرحلة 3 للكؤوس، 9 نوفمبر 2026) — من ذاكرة ردود المزوّد المخبّأة، صفر طلبات
=================================================================================================================
لكل مباراة بحالة PEN بالقاعدة: أحدث ردّ fixtures?ids= مخبّأ يحمل أحداث "Penalty Shootout" ← match_score.save_kicks (نفس التحقق
ونفس الكاتب: رقم الركلة 1..n لكل فريق، وعدد المسجَّلة = score.penalty، وإلا لا يُكتب شيء). مباراة بلا ركلات بالذاكرة = تُترك.
آمن للتكرار. لا يلمس matches/goals/events.

⚠️ --db و--cache إلزاميان (كـimport_cups.py): لا يُفتح football.db افتراضياً. اعمل على نسخة أولاً.
⚠️ يحتاج الجدول (python match_score.py --db <نسخة.db> --migrate) إلا مع --check.

التشغيل:
    python backfill_shootout.py --db <نسخة.db> --cache <مجلد النسخ الاحتياطية> --check   ← تقرير فقط (لا كتابة)
    python backfill_shootout.py --db <نسخة.db> --cache <مجلد النسخ الاحتياطية>
"""
import json
import sqlite3
import sys
from pathlib import Path

import match_score as MS
from team_alias import alias_fixture

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def arg(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def cached_fixtures(root, wanted):
    """{fixture_id: ردّ كامل} من كل ids_*.json تحت cups_cache_* — المتأخر بترتيب الملفات يغلب، والذي يحمل ركلات يغلب الذي لا يحملها"""
    out = {}
    for f in sorted(Path(root).glob("cups_cache_*/**/ids_*.json")):
        for x in json.loads(f.read_text(encoding="utf-8")).get("response") or []:
            fid = (x.get("fixture") or {}).get("id")
            if fid not in wanted:
                continue
            has = any(MS.is_shootout(e) for e in x.get("events") or [])
            if fid not in out or has or not any(MS.is_shootout(e) for e in out[fid].get("events") or []):
                out[fid] = x
    return out


def main():
    db, cache = arg("--db"), arg("--cache")
    known = {"--db", "--cache", "--check"}
    unknown = [a for i, a in enumerate(sys.argv[1:], 1)
               if a.startswith("--") and a not in known]
    if not db or not cache or unknown:
        print("--db <نسخة.db> و--cache <مجلد> إلزاميان (و--check اختياري)")
        return 2
    check = "--check" in sys.argv
    conn = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True) if check else sqlite3.connect(db)
    if not check and not MS.has_kicks(conn):
        print(f"❌ جدول {MS.KICKS_TABLE} غائب — شغّل match_score.py --migrate أولاً")
        return 2
    pen = {r[0]: r[1] for r in conn.execute("SELECT match_id, league_code FROM matches WHERE status = 'PEN'")}
    cached = cached_fixtures(cache, set(pen))
    written, kicks, bad, none, missing = 0, 0, [], 0, sorted(set(pen) - set(cached))
    named = 0
    for mid in sorted(cached):
        fx = alias_fixture(cached[mid])
        ev = fx.get("events") or []
        rows, problem = MS.kicks_of(fx, ev)
        if problem:
            bad.append((mid, problem))
            print(f"  ❌ {mid} {pen[mid]}: {problem}")
            continue
        if not rows:
            none += 1
            continue
        if not check:
            MS.save_kicks(conn, fx, ev)
        written += 1
        kicks += len(rows)
        n_named = sum(1 for r in rows if r[4])
        named += n_named
        h = fx["teams"]["home"]["id"]
        sh = sum(r[2] for r in rows if r[0] == h)
        print(f"  {mid} {pen[mid]:8} kicks {len(rows):2}  scored {sh}-{sum(r[2] for r in rows) - sh}  "
              f"score.penalty {fx['score']['penalty']['home']}-{fx['score']['penalty']['away']}  named {n_named}")
    if not check:
        conn.commit()
    print(f"\n{'--check (no writes)' if check else 'written'}: PEN matches {len(pen)} · cached {len(cached)} · "
          f"with kicks {written} · kicks {kicks} · named kicks {named} · no kicks {none} · not cached {len(missing)} · rejected {len(bad)}")
    if not check:
        print(f"table rows: {conn.execute(f'SELECT COUNT(*) FROM {MS.KICKS_TABLE}').fetchone()[0]}")
    conn.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
