#!/usr/bin/env python3
"""
استيراد الكؤوس (الموجة 1، 4 نوفمبر 2026 — cups_plan.md 4/6) من ردود المزوّد المخبّأة
=====================================================================================
لكل رمز بـconfig.COMPETITIONS (الموسم الجاري بالسجلّ): قائمة `fixtures?league&season` + تفاصيل `fixtures?ids=` (≤ 20 بالطلب،
تحمل events/lineups/statistics/players بنفس الردّ). يكتب بنفس كتّاب السحب العادي حرفياً (لا SQL منسوخ للصف أو الأهداف):
    منتهية FT/AET/PEN   ← fetch_matches2.save_finished (الصف + الجولة + الملعب + تفصيل النتيجة + الأهداف بلا ركلات الترجيح)
    AWD / WO            ← نفس معاملة fetch_overdue (AWD بنتيجته، WO بلا نتيجة)
    غير ذلك (NS/CANC…)  ← صف بلا نتيجة كـfetch_upcoming (الجولة + الملعب + MS.save)
    events              ← أنواع fetch_events.KEEP_TYPES (Card/subst/Var) — الأهداف بجدول goals وحده كالسحب العادي
    lineups             ← fetch_lineups.build_rows
    match_stats         ← fetch_stats.FIELD_MAP/num
    player_stats        ← fetch_player_stats.extract (+ أعمدة player_stats_extra إن هوجرت)
آمن للتكرار: كل مباراة تُمسح طبقاتها ثم تُكتب من الردّ (نفس النتيجة بكل تشغيل).

⚠️ --db إلزامي (كـmatch_score.py): لا يُفتح football.db افتراضياً. اعمل على نسخة أولاً.
⚠️ الطلبات: صفر إن غطّت الذاكرة المخبّأة كل شيء. «الناقص» = مباراة بالقائمة بلا تفاصيل بالذاكرة، أو فات موعدها (+3 س) بلا
   نهاية بالذاكرة (قد تكون انتهت). يُسحب فقط مع --fetch: /status أولاً، توقّف إن بقي < 2,000 (كـfetch_player_info)، ثم ids=.
   الردود المسحوبة تُحفظ بـ--save <مجلد جديد> (لا تُكتب فوق الذاكرة الأصلية).

التشغيل:
    python import_cups.py --db <نسخة.db> --cache <مجلد> SAU-KC SAU-SC ...        ← من الذاكرة فقط (يطبع الناقص)
    python import_cups.py --db <نسخة.db> --cache <مجلد> --fetch --save <مجلد> SAU-KC ...
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import competitions as CP
import match_score as MS
import match_venue as MV
import player_stats_extra as PX
from config import COMPETITIONS, clean_name
from team_alias import alias_fixture   # (الموجة 4) config.TEAM_ID_ALIASES — قبل أي كتابة بـimport_code (ومنه fetch_cups)
from fetch_events import KEEP_TYPES
from fetch_lineups import build_rows
from fetch_matches2 import save_finished
from fetch_player_stats import COLS as PS_COLS, extract as ps_extract
from fetch_stats import COLS as MS_COLS, FIELD_MAP, num as st_num
from match_round import has_round, round_of

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FINAL = ("FT", "AET", "PEN")
AWARDED = ("AWD", "WO")
NOT_PLAYED = ("CANC", "ABD", "PST", "SUSP", "INT")
MIN_REMAINING = 2000
IDS_MAX = 20


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def load_cache(cache):
    """({provider_id: [fixtures من القائمة]}, {fixture_id: fixture كامل من ids=})"""
    lists, full = {}, {}
    for f in sorted(Path(cache).glob("list_*.json")):
        r = json.loads(f.read_text(encoding="utf-8")).get("response") or []
        if r:
            lists.setdefault(r[0]["league"]["id"], []).extend(r)
    for f in sorted(Path(cache).glob("ids_*.json")):
        for x in json.loads(f.read_text(encoding="utf-8")).get("response") or []:
            full[x["fixture"]["id"]] = x
    return lists, full


def missing(lst, full, now):
    """معرّفات تحتاج ids=: بلا تفاصيل، أو فات موعدها (+3 س) بلا نهاية بالذاكرة"""
    out = []
    for x in lst:
        fid = x["fixture"]["id"]
        fx = full.get(fid)
        st = (fx or x)["fixture"]["status"]["short"]
        ko = datetime.fromisoformat((fx or x)["fixture"]["date"])
        if fx is None or (st not in FINAL + AWARDED + NOT_PLAYED and ko + timedelta(hours=3) < now):
            out.append(fid)
    return out


def fetch_ids(ids, save_dir, tag):
    """fixtures?ids= بدفعات 20 بعد فحص /status — يرجّع ({id: fixture}, طلبات). يتوقّف تحت MIN_REMAINING."""
    import requests
    from config import API_BASE, check_key, headers
    if not check_key():
        raise SystemExit("❌ لا مفتاح API")
    s = requests.get(f"{API_BASE}/status", headers=headers(), timeout=30).json()["response"]["requests"]
    left = s["limit_day"] - s["current"]
    print(f"  /status: {s['current']} / {s['limit_day']} (متبقٍّ {left:,})")
    if left < MIN_REMAINING:
        raise SystemExit(f"❌ متبقٍّ {left} < {MIN_REMAINING} — لا سحب")
    got, calls = {}, 0
    for i in range(0, len(ids), IDS_MAX):
        part = ids[i:i + IDS_MAX]
        r = requests.get(f"{API_BASE}/fixtures", headers=headers(), params={"ids": "-".join(map(str, part))}, timeout=30)
        calls += 1
        rem = r.headers.get("x-ratelimit-requests-remaining")
        d = r.json()
        if save_dir:
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            (Path(save_dir) / f"ids_{tag}_{i // IDS_MAX}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        for x in d.get("response") or []:
            got[x["fixture"]["id"]] = x
        if rem not in (None, "") and int(rem) < MIN_REMAINING:
            print(f"  ⚠️ x-ratelimit-requests-remaining {rem} < {MIN_REMAINING} — توقّف")
            break
        time.sleep(1.0)
    return got, calls


def save_unplayed(conn, code, season, fx):
    """صف بلا نتيجة (NS/TBD/CANC…) — نفس كتابة fetch_upcoming (INSERT OR REPLACE + الجولة + الملعب + MS.save)"""
    mid = fx["fixture"]["id"]
    keep = MV.current(conn, mid)
    vals = (mid, code, season, fx["fixture"]["date"][:16].replace("T", " "),
            fx["teams"]["home"]["id"], fx["teams"]["away"]["id"], fx["fixture"]["status"]["short"])
    if has_round(conn):
        conn.execute("""INSERT OR REPLACE INTO matches (match_id, league_code, season, date, home_id, away_id,
                        home_goals, away_goals, status, round) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                     vals + (round_of(fx),))
    else:
        conn.execute("""INSERT OR REPLACE INTO matches (match_id, league_code, season, date, home_id, away_id,
                        home_goals, away_goals, status) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)""", vals)
    MV.save(conn, fx, keep)
    MS.save(conn, fx)


def save_layers(conn, fx):
    """events/lineups/match_stats/player_stats من ردّ ids= — يرجّع عدّاد الطبقات المكتوبة"""
    mid = fx["fixture"]["id"]
    hid, aid = fx["teams"]["home"]["id"], fx["teams"]["away"]["id"]
    n = {"events": 0, "lineups": 0, "stats": 0, "pstats": 0}
    for t in ("events", "lineups", "lineup_players", "match_stats", "player_stats"):
        conn.execute(f"DELETE FROM {t} WHERE match_id = ?", (mid,))
    rows = []
    for e in fx.get("events") or []:
        if (e.get("type") or "") not in KEEP_TYPES:
            continue
        rows.append((mid, (e.get("team") or {}).get("id"), (e.get("time") or {}).get("elapsed"), e.get("type"),
                     e.get("detail") or "", clean_name((e.get("player") or {}).get("name") or ""), "",
                     clean_name((e.get("assist") or {}).get("name") or "")))
    conn.executemany("""INSERT INTO events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)
    n["events"] = len(rows)
    lu = fx.get("lineups") or []
    if lu:
        lines, players, _ = build_rows(mid, hid, aid, lu, conn)
        conn.executemany("INSERT OR REPLACE INTO lineups VALUES (?, ?, ?, ?, ?)", lines)
        conn.executemany("""INSERT OR REPLACE INTO lineup_players (match_id, team_id, player_id, player_en, player_ar,
                            number, pos, grid, starter) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", players)
        n["lineups"] = len(players)
    srows = []
    for blk in fx.get("statistics") or []:
        tid = (blk.get("team") or {}).get("id")
        if tid is None:
            continue
        vals = {c: None for c in MS_COLS}
        for item in blk.get("statistics") or []:
            k = FIELD_MAP.get(item.get("type"))
            if k:
                vals[k] = st_num(item.get("value"))
        srows.append([mid, tid] + [vals[c] for c in MS_COLS])
    if srows:
        conn.executemany(f"INSERT OR REPLACE INTO match_stats (match_id, team_id, {', '.join(MS_COLS)}) "
                         f"VALUES ({', '.join('?' * (2 + len(MS_COLS)))})", srows)
        n["stats"] = len(srows)
    cols = PS_COLS + PX.present(conn)
    prows = []
    for blk in fx.get("players") or []:
        tid = (blk.get("team") or {}).get("id")
        if tid is None:
            continue
        for item in blk.get("players") or []:
            p = item.get("player") or {}
            if p.get("id") is None:
                continue
            v = ps_extract(item)
            prows.append([mid, tid, p["id"], clean_name(p.get("name") or ""), ""] + [v[c] for c in cols])
    if prows:
        conn.executemany(f"INSERT OR REPLACE INTO player_stats (match_id, team_id, player_id, player_en, player_ar, "
                         f"{', '.join(cols)}) VALUES ({', '.join('?' * (5 + len(cols)))})", prows)
        n["pstats"] = len(prows)
    return n


def import_code(conn, code, lst, full):
    """يكتب كل مباريات الكأس (موسمه الجاري بالسجلّ). يرجّع تقريراً."""
    season = COMPETITIONS[code]["season"]
    rep = {"code": code, "fixtures": 0, "finished": 0, "unplayed": 0, "goals": 0, "shootout_dropped": 0,
           "events": 0, "lineups": 0, "stats": 0, "pstats": 0, "status": {}}
    for x in lst:
        fx = alias_fixture(full.get(x["fixture"]["id"], x))   # (الموجة 4) معرّفات الفرق المكرّرة ← المعتمدة قبل أي كتابة
        if fx["league"]["season"] != season:
            raise SystemExit(f"❌ {code}: موسم الردّ {fx['league']['season']} ≠ السجلّ {season}")
        ps = fx["fixture"]["status"]["short"]
        rep["status"][ps] = rep["status"].get(ps, 0) + 1
        rep["fixtures"] += 1
        ev = fx.get("events") or []
        if ps in FINAL and fx["goals"]["home"] is not None:
            rep["goals"] += save_finished(conn, code, season, fx, ev, status=ps)
            rep["shootout_dropped"] += sum(1 for e in ev if e.get("type") == "Goal" and MS.is_shootout(e))
            rep["finished"] += 1
        elif ps in AWARDED:
            save_finished(conn, code, season, dict(fx, goals={"home": None, "away": None}) if ps == "WO" else fx, [],
                          status=ps)
            rep["finished"] += 1
        else:
            save_unplayed(conn, code, season, fx)
            rep["unplayed"] += 1
        if x["fixture"]["id"] in full:
            for k, v in save_layers(conn, fx).items():
                rep[k] += v
    return rep


def main():
    db, cache = arg("--db"), arg("--cache")
    if not db or not cache:
        print("--db <نسخة.db> و--cache <مجلد> إلزاميان")
        return 2
    flags = {"--db", "--cache", "--save"}
    codes = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in flags]
    bad = [c for c in codes if not CP.is_cup(c)]
    if bad or not codes:
        print(f"رموز كؤوس من config.COMPETITIONS مطلوبة (غير معروف: {bad})")
        return 2
    lists, full = load_cache(cache)
    now = datetime.now(timezone.utc)
    calls = 0
    todo = {c: missing(lists.get(COMPETITIONS[c]["id"], []), full, now) for c in codes}
    absent = [c for c in codes if COMPETITIONS[c]["id"] not in lists]
    if absent:
        print(f"  ⚠️ بلا قائمة بالذاكرة: {absent} (تحتاج fixtures?league&season — خارج هذه الأداة)")
    need = [i for c in codes for i in todo[c]]
    print(f"  ناقص بالذاكرة: {len(need)} مباراة {({c: v for c, v in todo.items() if v}) or ''}")
    if need:
        if "--fetch" not in sys.argv:
            print("  (بلا --fetch: يُستورد ما بالذاكرة فقط)")
        else:
            got, calls = fetch_ids(need, arg("--save"), "missing")
            full.update(got)
    conn = sqlite3.connect(db)
    if not MS.has_score(conn):
        print("❌ أعمدة match_score غائبة — python match_score.py --db <نسخة> --migrate أولاً")
        return 2
    reps = []
    for c in codes:
        reps.append(import_code(conn, c, lists.get(COMPETITIONS[c]["id"], []), full))
    conn.commit()
    conn.close()
    print(f"\n  {'الرمز':8} {'مباريات':>7} {'منتهية':>6} {'قادمة/ملغاة':>11} {'أهداف':>5} {'ترجيح مستبعد':>12} "
          f"{'أحداث':>5} {'تشكيلة':>6} {'إحصاء':>5} {'لاعبين':>6}  الحالات")
    for r in reps:
        print(f"  {r['code']:8} {r['fixtures']:>7} {r['finished']:>6} {r['unplayed']:>11} {r['goals']:>5} "
              f"{r['shootout_dropped']:>12} {r['events']:>5} {r['lineups']:>6} {r['stats']:>5} {r['pstats']:>6}  {r['status']}")
    print(f"\n  طلبات API: {calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
