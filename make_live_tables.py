#!/usr/bin/env python3
"""
لقطات الجدول للترتيب المباشر — /assets/table_<CODE>_<season>.json
====================================================================
لكل دوري بموسمه الحالي (بلا JOR: نظام مراحل وقواعد غير مؤكَّدة — الميزة مطفأة له) ملف صغير يقرؤه `live_view.py`
حين يوجد بالدوري مباراة جارية (`m`) أو انتهت للتو (`f`) فيحسب `assets_src/live_table.js::liveTable()` الجدول المباشر فوقه.

المحتوى (نفس أرقام `get_table` بالضبط، من نفس المدخلات):
    league, season, ts
    rules:       {enabled, leagueId, h2h, twoOnly}   ← tiebreak.H2H_ENABLED / H2H_TWO_TEAM_ONLY + config.LEAGUES
    rows:        [{team_id, played, wins, draws, losses, scored, diff, points}]  بترتيب get_table النهائي
    counted_ids: معرّفات المباريات المنتهية المحسوبة بالجدول (لمنع العدّ المزدوج مع `f`)
    matches:     [[id, home, away, hg, ag]] نفس المباريات (لكسر التعادل بالمواجهات المباشرة)
    alias:       {معرّف المزوّد المدموج: معرّفنا} من team_merges.csv (أندية هذا الدوري فقط)

⚠️ يُشغَّل بعد make_assets.py (مجلد /assets موجود) وقبل بناء الصفحات؛ يُعاد بكل تشغيل لـdeploy-site فيتجدّد مع الجدول الثابت.
⚠️ ملفات الدوري/الموسم القديمة تُحذف (موسم جديد = اسم ملف جديد).
صفر طلبات API. التشغيل: python make_live_tables.py
"""
import csv
import json
import sqlite3
import sys
import time

from config import DB_FILE, LEAGUES
from make_site3 import get_table
from tiebreak import H2H_ENABLED, H2H_TWO_TEAM_ONLY, STANDINGS_EXCLUDED

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = DB_FILE.parent
ASSETS = BASE / "assets"
MERGES = BASE / "team_merges.csv"
OFF = {"JOR"}


def load_aliases():
    out = {}
    if MERGES.exists():
        with open(MERGES, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                o, n, lg = (r.get("old_id") or "").strip(), (r.get("new_id") or "").strip(), (r.get("league_code") or "").strip()
                if o.isdigit() and n.isdigit():
                    out.setdefault(lg, {})[o] = int(n)
    return out


def snapshot(conn, code, season, aliases):
    table = get_table(conn, code, season)
    rows = [{k: r[k] for k in ("team_id", "played", "wins", "draws", "losses", "scored", "diff", "points")} for r in table]
    ms = [m for m in conn.execute(
        "SELECT match_id, home_id, away_id, home_goals, away_goals FROM matches WHERE league_code = ? AND season = ?",
        (code, season)) if m["home_goals"] is not None and m["away_goals"] is not None
        and m["match_id"] not in STANDINGS_EXCLUDED]
    team_ids = {r["team_id"] for r in rows}
    return {
        "league": code, "season": season, "ts": int(time.time()),
        "rules": {"enabled": True, "leagueId": LEAGUES[code]["id"], "h2h": bool(H2H_ENABLED.get(code, False)),
                  "twoOnly": code in H2H_TWO_TEAM_ONLY},
        "rows": rows,
        "counted_ids": [m["match_id"] for m in ms],
        "matches": [[m["match_id"], m["home_id"], m["away_id"], m["home_goals"], m["away_goals"]] for m in ms],
        "alias": {o: n for o, n in aliases.get(code, {}).items() if n in team_ids},
    }


def main():
    ASSETS.mkdir(exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    aliases = load_aliases()
    keep, total = set(), 0
    for code in LEAGUES:
        if code in OFF:
            continue
        season = conn.execute("SELECT MAX(season) FROM matches WHERE league_code = ?", (code,)).fetchone()[0]
        if season is None:
            continue
        snap = snapshot(conn, code, season, aliases)
        if not snap["rows"]:
            continue
        name = f"table_{code}_{season}.json"
        data = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
        (ASSETS / name).write_text(data, encoding="utf-8")
        keep.add(name)
        total += len(data.encode("utf-8"))
        print(f"  {name:22} {len(data.encode('utf-8')) / 1000:6.1f} ك.ب  ({len(snap['rows'])} فريقاً، {len(snap['counted_ids'])} مباراة)")
    for p in ASSETS.glob("table_*.json"):
        if p.name not in keep:
            p.unlink()
    conn.close()
    print(f"  المجموع {total / 1000:.1f} ك.ب")


if __name__ == "__main__":
    main()
