#!/usr/bin/env python3
"""
مقارنة أحداث دوري (بطاقات/تبديلات/VAR) المخزَّنة عندنا بما يرجّعه المزوّد الآن
==========================================================================
للقراءة فقط: لا يكتب بالديتابيس إطلاقاً. النتائج تُحفظ بـevents_check_<CODE>.json
(قابلة للاستئناف — أي مباراة فُحصت لا تُعاد).

التشغيل (مسار كامل):
    python C:\\Users\\User\\Projects\\Football\\check_events_vs_provider.py EGY --limit 25
    python C:\\Users\\User\\Projects\\Football\\check_events_vs_provider.py EGY          <- كل الباقي
    python C:\\Users\\User\\Projects\\Football\\check_events_vs_provider.py EGY --report  <- تقرير بلا طلبات

التصنيف لكل مباراة:
    match       مطابقة تامة (نوع/دقيقة/فريق/تفصيل/لاعب)
    names_only  نفس الأحداث لكن أسماء لاعبين مختلفة (مثلاً دمج/تنظيف أسماء)
    db_missing  المزوّد يرجّع أحداثاً ليست عندنا
    db_extra    عندنا أحداث لا يرجّعها المزوّد الآن
    differ      خليط
    error       فشل الطلب
"""

import json
import os
import sqlite3
import sys
import time
from collections import Counter

from config import DB_FILE, LEAGUES, check_key, clean_name
from fetch_events import get, KEEP_TYPES

DELAY = 1.0
HERE = os.path.dirname(os.path.abspath(__file__))


def key4(t, m, ty, d):
    return (t, m, ty, d or "")


def classify(db_rows, api_rows):
    """db_rows/api_rows: قوائم (team, minute, type, detail, player)"""
    c4_db = Counter(key4(*r[:4]) for r in db_rows)
    c4_api = Counter(key4(*r[:4]) for r in api_rows)
    missing = c4_api - c4_db
    extra = c4_db - c4_api
    if not missing and not extra:
        if Counter(db_rows) == Counter(api_rows):
            return "match", {}
        return "names_only", {}
    detail = {"missing": [list(k) for k in missing.elements()][:6],
              "extra": [list(k) for k in extra.elements()][:6]}
    if missing and not extra:
        return "db_missing", detail
    if extra and not missing:
        return "db_extra", detail
    return "differ", detail


def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def report(state, matches):
    by = {}
    for mid, season in matches:
        r = state.get(str(mid))
        cls = r["cls"] if r else "unchecked"
        by.setdefault(season, Counter())[cls] += 1
    print(f"\n{'=' * 60}")
    for s in sorted(by):
        print(f"  موسم {s}: " + "  ".join(f"{k}={v}" for k, v in sorted(by[s].items())))
    tot = Counter()
    for c in by.values():
        tot.update(c)
    print(f"  الإجمالي: " + "  ".join(f"{k}={v}" for k, v in sorted(tot.items())))
    print(f"{'=' * 60}")
    bad = [(mid, state[str(mid)]) for mid, _ in matches
           if str(mid) in state and state[str(mid)]["cls"] not in ("match", "names_only")]
    for mid, r in bad[:25]:
        print(f"  {mid}  [{r['cls']}]  {r.get('detail') or r.get('reason', '')}")
    if len(bad) > 25:
        print(f"  ... و{len(bad) - 25} أخرى")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    code = args[0].upper() if args else None
    if code not in LEAGUES:
        print("حدّد رمز دوري صحيحاً (مثال: EGY)")
        return
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    seasons = (2022, 2023, 2024, 2025)
    if "--season" in sys.argv:
        seasons = (int(sys.argv[sys.argv.index("--season") + 1]),)

    conn = sqlite3.connect(DB_FILE)
    matches = conn.execute(
        f"SELECT match_id, season FROM matches WHERE league_code=? AND season IN "
        f"({','.join('?' * len(seasons))}) AND home_goals IS NOT NULL "
        f"ORDER BY season, date, match_id", (code, *seasons)).fetchall()

    path = os.path.join(HERE, f"events_check_{code}.json")
    state = load_state(path)

    if "--report" in sys.argv:
        report(state, matches)
        return
    if not check_key():
        return

    todo = [(m, s) for m, s in matches if str(m) not in state]
    if limit:
        todo = todo[:limit]
    print(f"مباريات {code} ضمن النطاق: {len(matches)} | مفحوصة سابقاً: "
          f"{len(matches) - len([1 for m, s in matches if str(m) not in state])} | "
          f"سأفحص الآن: {len(todo)}")

    for i, (mid, season) in enumerate(todo, 1):
        ok, events, reason = get("fixtures/events", {"fixture": mid})
        if not ok:
            state[str(mid)] = {"cls": "error", "reason": reason, "season": season}
        else:
            api_rows = []
            for e in events:
                if (e.get("type") or "") not in KEEP_TYPES:
                    continue
                api_rows.append((
                    (e.get("team") or {}).get("id"),
                    (e.get("time") or {}).get("elapsed"),
                    e.get("type"), e.get("detail") or "",
                    clean_name((e.get("player") or {}).get("name") or "")))
            db_rows = [tuple(r) for r in conn.execute(
                "SELECT team_id, minute, type, detail, player_en FROM events "
                "WHERE match_id=? AND type!='none'", (mid,))]
            cls, detail = classify(db_rows, api_rows)
            state[str(mid)] = {"cls": cls, "detail": detail, "season": season,
                               "n_db": len(db_rows), "n_api": len(api_rows)}
        if i % 25 == 0 or i == len(todo):
            save_state(path, state)
            print(f"  [{i}/{len(todo)}] آخر مباراة {mid}", flush=True)
        time.sleep(DELAY)
    save_state(path, state)
    report(state, matches)


if __name__ == "__main__":
    main()
