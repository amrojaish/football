#!/usr/bin/env python3
"""
توحيد معرّفات اللاعبين المكررة (نفس الشخص بأكثر من player_id)
================================================================
يقرأ player_id_merges.csv ويحوّل صفوف المعرّف المحذوف (drop_id) إلى المعرّف المحتفَظ به (keep_id) بجدولي
`lineup_players` و`player_stats` (الجدولان الوحيدان الحاملان player_id). **بالمعرّف فقط** — لا علاقة بـplayer_merges.csv
(ذاك يوحّد الأسماء النصية؛ هذا يوحّد المعرّفات): لا يمسّ `player_en` ولا `goals` ولا `events` ولا أي جدول آخر،
فصفحات اللاعبين (المبنية من goals.player_en) لا تتغيّر وتتوحّد إحصائيات/تفاصيل اللاعب على معرّف واحد.

الأعمدة:
    drop_id    المعرّف الذي يُنقَل (0 = لاعب بلا معرّف: يُحدَّد بـplayer_en + team_id)
    keep_id    المعرّف الباقي (الأكثر ظهوراً)
    team_id    النادي المشترك الذي ثبتت عنده الهوية (للتوثيق؛ وللمعرّف 0 شرط إلزامي)
    player_en  للمعرّف 0 فقط: اسم المزوّد الذي يجمع صفوفه
    note       توثيق (أدلة القرار)

⚠️ شروط القرار (8 أكتوبر 2026، بلا مراجعة بشرية — قرار عمرو): صفر مباراة مشتركة (تشكيلات/إحصائيات/أحداث/أهداف) · نفس النادي
   وموسمان مختلفان أو أحدهما يكمل الآخر · اسم متوافق (حرف أول+لقب أو تشابه ≥0.85) · نفس المركز وأرقام قمصان لا تتعارض
   بنفس الموسم · لا صيغة اسم أخرى بلقب مختلف لأي من المعرّفين. الباقي يُترك.

⚠️ حواجز التشغيل (كل تشغيل، لأن CI يعيد سحب صفوف جديدة):
   • صف يُنتج مباراة بها المعرّفان معاً (أي ظهرا فعلاً معاً: شخصان) يُتخطّى بتحذير ولا يُكسَر التشغيل.
   • سلسلة (keep_id هو drop_id لصف آخر) أو دورة أو drop=keep = إيقاف كامل بلا كتابة.
   • إعادة التشغيل آمنة (idempotent): بعد التطبيق لا يبقى صف مطابق.

--check يحاكي على نسخة بالذاكرة (الأصل قراءة فقط). صفر طلبات API.

التشغيل:
    python apply_id_merges.py --check    <- محاكاة، صفر كتابة
    python apply_id_merges.py            <- تنفيذ
"""
import csv
import sqlite3
import sys

from config import BASE_DIR, DB_FILE

SOURCE = BASE_DIR / "player_id_merges.csv"
TABLES = ("lineup_players", "player_stats")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("drop_id") or "").strip():
                continue
            rows.append({
                "drop": int(r["drop_id"]), "keep": int(r["keep_id"]),
                "team": int(r["team_id"]) if (r.get("team_id") or "").strip() else None,
                "en": (r.get("player_en") or "").strip(), "note": (r.get("note") or "").strip(),
            })
    return rows


def validate(rows):
    """سلسلة/دورة/drop=keep/صف ناقص => ValueError (إيقاف كامل بلا كتابة)"""
    keeps = {r["keep"] for r in rows}
    drops_real = {r["drop"] for r in rows if r["drop"] != 0}
    for r in rows:
        if r["drop"] == r["keep"]:
            raise ValueError(f"drop_id = keep_id: {r['drop']}")
        if r["keep"] == 0:
            raise ValueError("keep_id = 0 غير مسموح")
        if r["drop"] == 0 and not (r["en"] and r["team"] is not None):
            raise ValueError(f"المعرّف 0 يحتاج player_en وteam_id: {r}")
    chain = keeps & drops_real
    if chain:
        raise ValueError(f"سلسلة دمج (keep_id هو drop_id لصف آخر): {sorted(chain)}")
    seen = {}
    for r in rows:
        k = (r["drop"], r["en"], r["team"]) if r["drop"] == 0 else (r["drop"],)
        if k in seen and seen[k] != r["keep"]:
            raise ValueError(f"المصدر يُحوَّل لمعرّفين مختلفين: {k}")
        seen[k] = r["keep"]


def _where(r):
    if r["drop"] == 0:
        return "player_id = 0 AND player_en = ? AND team_id = ?", (r["en"], r["team"])
    return "player_id = ?", (r["drop"],)


def shared_match(conn, r):
    """عدد المباريات التي ظهر فيها المصدر والمعرّف الباقي معاً (عبر الجدولين)"""
    w, p = _where(r)
    src = set()
    for t in TABLES:
        src |= {m for (m,) in conn.execute(f"SELECT match_id FROM {t} WHERE {w}", p)}
    if not src:
        return 0
    dst = set()
    for t in TABLES:
        dst |= {m for (m,) in conn.execute(f"SELECT match_id FROM {t} WHERE player_id = ?", (r["keep"],))}
    return len(src & dst)


def appearances(conn, pid):
    return sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE player_id = ?", (pid,)).fetchone()[0] for t in TABLES)


def apply(conn, rows, write=True, out=print):
    """يرجّع (قائمة تقارير بالصفوف, عدد المُنفَّذ, عدد المُتخطّى). write=False: عدّ فقط."""
    report = []
    done = skipped = 0
    for r in rows:
        w, p = _where(r)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {w}", p).fetchone()[0] for t in TABLES}
        n = sum(counts.values())
        entry = {"row": r, "rows": n, "counts": counts, "status": "done",
                 "keep_before": appearances(conn, r["keep"])}
        if n == 0:
            entry["status"] = "nothing"          # طُبِّق سابقاً
        else:
            sm = shared_match(conn, r)
            if sm:
                entry["status"] = "skipped_shared_match"
                entry["shared"] = sm
                out(f"  ⚠️ تخطّي {r['drop']}→{r['keep']}: ظهرا معاً بـ{sm} مباراة (شخصان) — لا دمج")
                skipped += 1
            elif entry["keep_before"] == 0:
                entry["status"] = "skipped_keep_unknown"
                out(f"  ⚠️ تخطّي {r['drop']}→{r['keep']}: المعرّف الباقي بلا أي صف")
                skipped += 1
            elif write:
                for t in TABLES:
                    conn.execute(f"UPDATE {t} SET player_id = ? WHERE {w}", (r["keep"], *p))
                done += 1
            else:
                done += 1
        entry["keep_after"] = appearances(conn, r["keep"]) if write else entry["keep_before"] + (n if entry["status"] == "done" else 0)
        report.append(entry)
    if write:
        conn.commit()
    return report, done, skipped


def main():
    check = "--check" in sys.argv
    if not DB_FILE.exists():
        print("ما لقيت football.db"); return 1
    if not SOURCE.exists():
        print(f"ما لقيت {SOURCE.name}"); return 0
    rows = load_rows(SOURCE)
    try:
        validate(rows)
    except ValueError as e:
        print(f"⛔ {e} — توقّف كامل، صفر كتابة"); return 1
    if check:
        src = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        conn = sqlite3.connect(DB_FILE)
    print(f"\n{'=' * 58}\n  صفوف دمج المعرّفات: {len(rows)}" + ("   [وضع الفحص — صفر كتابة]" if check else "") + f"\n{'=' * 58}")
    report, done, skipped = apply(conn, rows, write=True)
    moved = 0
    for e in report:
        r = e["row"]
        tag = f"{r['drop']}" + (f" ({r['en']}@{r['team']})" if r["drop"] == 0 else "")
        if e["status"] == "done":
            moved += e["rows"]
            print(f"  ✓ {tag} → {r['keep']}: {e['rows']} صفاً (lineup {e['counts']['lineup_players']} · stats {e['counts']['player_stats']})؛ ظهور الباقي {e['keep_before']} → {e['keep_after']}")
    nothing = sum(1 for e in report if e["status"] == "nothing")
    print(f"\n  نُفِّذ: {done} · تُخطّي: {skipped} · مطبَّق سابقاً: {nothing} · صفوف نُقلت: {moved}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
