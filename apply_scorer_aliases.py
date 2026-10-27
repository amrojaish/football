#!/usr/bin/env python3
"""
تنظيف أسماء الهدّافين + أسماء بديلة مقيَّدة بالنادي
=====================================================
خطوتان على `player_en` بالترتيب، كل تشغيل (update_all، بعد السحب وقبل `apply_player_merges.py`/`apply_players_ar.py`):

1) **تنظيف التلف** (كل الدوريات): المزوّد يُلصق أحياناً رقماً بالاسم بأهداف الدقيقة 90 — غالباً دقيقة الوقت بدل
   الضائع ("Y. Amri   7" = 90+7، "1          C. Rivas"). يُزال فقط: مسافات/فراغات طرفية، `^\\d+\\s+` و`\\s+\\d+$`.
   الجداول: goals · events · lineup_players. كل نص يتغيّر يُطبع.

2) **أسماء بديلة** من `scorer_name_aliases.csv` (league,team_id,from_en,to_en,note): `(team_id, from_en) → to_en`
   بـgoals وevents فقط. **مقيَّدة بالنادي عمداً** — لا `player_merges.csv` (ذاك عام بالاسم وحده): 5 من أسماء الكويت
   الأولى (H. Khabba · E. Al Rasheedi · A. Khalaf · A. Al Awadi · A. Hussain) موجودة بأندية أخرى لأشخاص آخرين.
   لماذا: الكويت بلا تشكيلات (لا player_id)، وجدول الهدّافين (`make_site3.get_scorers`) يجمع بنص `player_en` +
   النادي — صيغتان لنفس اللاعب = سطران بالجدول (27 أكتوبر 2026: T. Khenissi 17+2 بدل 19 أول هدّافي 2022).

⚠️ سلسلة (to_en هو from_en لصف آخر بنفس النادي) أو from=to = إيقاف كامل بلا كتابة.
إعادة التشغيل آمنة (idempotent): التشغيل الثاني = صفر تغيير.

--check يحاكي على نسخة بالذاكرة (الأصل قراءة فقط). صفر طلبات API.

التشغيل:
    python apply_scorer_aliases.py --check    <- محاكاة، صفر كتابة
    python apply_scorer_aliases.py            <- تنفيذ
"""
import csv
import re
import sqlite3
import sys

from config import BASE_DIR, DB_FILE

SOURCE = BASE_DIR / "scorer_name_aliases.csv"
CLEAN_TABLES = ("goals", "events", "lineup_players")
ALIAS_TABLES = ("goals", "events")
JUNK_RE = re.compile(r"^\d+\s+|\s+\d+$")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def clean_name(name):
    """فراغات طرفية ثم رقم ملتصق بالبداية/النهاية فقط — لا شيء آخر"""
    s = (name or "").strip()
    s = JUNK_RE.sub("", s)
    return s.strip()


def load_aliases(path=SOURCE):
    out = []
    try:
        f = open(path, encoding="utf-8-sig", newline="")
    except OSError:
        return out
    with f:
        for r in csv.DictReader(f):
            fr, to = (r.get("from_en") or "").strip(), (r.get("to_en") or "").strip()
            if not fr and not to:
                continue
            out.append({"team": int(r["team_id"]), "from": fr, "to": to})
    return out


def validate(aliases):
    """صف ناقص/from=to/سلسلة/مصدر بوجهتين => ValueError (إيقاف كامل بلا كتابة)"""
    seen = {}
    for a in aliases:
        if not a["from"] or not a["to"]:
            raise ValueError(f"صف ناقص: {a}")
        if a["from"] == a["to"]:
            raise ValueError(f"from_en = to_en: {a}")
        k = (a["team"], a["from"])
        if k in seen and seen[k] != a["to"]:
            raise ValueError(f"المصدر يُحوَّل لاسمين مختلفين: {k}")
        seen[k] = a["to"]
    chain = {(a["team"], a["to"]) for a in aliases} & set(seen)
    if chain:
        raise ValueError(f"سلسلة (to_en هو from_en لصف آخر): {sorted(chain)}")


def has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def apply(conn, aliases, out=print):
    """ينظّف ثم يطبّق الأسماء البديلة. يرجّع {"clean": {table: n}, "alias": {table: n}, "changed": [...]}."""
    res = {"clean": {}, "alias": {}, "changed": []}
    for t in CLEAN_TABLES:
        if not has_table(conn, t):
            continue
        n = 0
        bad = [r[0] for r in conn.execute(f"SELECT DISTINCT player_en FROM {t} WHERE player_en IS NOT NULL AND player_en != ''")
               if clean_name(r[0]) != r[0]]
        for name in bad:
            new = clean_name(name)
            if not new:
                continue
            k = conn.execute(f"UPDATE {t} SET player_en = ? WHERE player_en = ?", (new, name)).rowcount
            n += k
            res["changed"].append((t, name, new, k))
            out(f"  🧹 {t}: {name!r} → {new!r} ({k})")
        res["clean"][t] = n
    for t in ALIAS_TABLES:
        if not has_table(conn, t):
            continue
        n = 0
        for a in aliases:
            k = conn.execute(f"UPDATE {t} SET player_en = ? WHERE team_id = ? AND player_en = ?",
                             (a["to"], a["team"], a["from"])).rowcount
            if k:
                out(f"  🔗 {t}: [{a['team']}] {a['from']!r} → {a['to']!r} ({k})")
            n += k
        res["alias"][t] = n
    conn.commit()
    return res


def main():
    check = "--check" in sys.argv
    if not DB_FILE.exists():
        print("ما لقيت football.db"); return 1
    aliases = load_aliases()
    try:
        validate(aliases)
    except ValueError as e:
        print(f"⛔ {e} — توقّف كامل، صفر كتابة"); return 1
    if check:
        src = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        conn = sqlite3.connect(DB_FILE)
    print(f"\n{'=' * 58}\n  أسماء بديلة: {len(aliases)}" + ("   [وضع الفحص — صفر كتابة]" if check else "") + f"\n{'=' * 58}")
    res = apply(conn, aliases)
    print(f"\n  تنظيف: " + " · ".join(f"{t} {n}" for t, n in res["clean"].items())
          + "   |   أسماء بديلة: " + " · ".join(f"{t} {n}" for t, n in res["alias"].items()))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
