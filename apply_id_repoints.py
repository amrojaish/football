#!/usr/bin/env python3
"""
تصحيح player_id الخاطئ بصفوف محدّدة (لا دمج معرّفين كاملين)
=============================================================
حين يكتب المزوّد معرّف لاعب آخر على صفوف قليلة (مثال: «M. I. Hassan» بالقميص 52 مربوطاً بمعرّف الونش 16858 بدل 477137)
لا يصلح apply_id_merges.py لأن المعرّف الأصلي لاعب حقيقي آخر يبقى. هنا نصحّح **الصفوف المطابقة فقط**.

player_id_repoints.csv — الأعمدة:
    table      lineup_players أو player_stats
    from_id    المعرّف الخاطئ
    to_id      المعرّف الصحيح (يجب أن له صفوف أصلاً)
    number     القميص (شرط، اختياري لـplayer_stats لأنه بلا عمود قميص — يُترك فارغاً)
    player_en  الاسم النصي كما كتبه المزوّد بالصف (شرط)
    expect     عدد الصفوف وقت القرار (للتوثيق: يُطبع عند الاختلاف، لا يوقف — نفس الخطأ قد يتكرر بصفوف جديدة)
    note       الأدلة

⚠️ كل تشغيل (CI يعيد سحب صفوف جديدة)؛ idempotent: بعد التطبيق لا يبقى صف مطابق. صف سيُنتج مباراة فيها المعرّف
   الصحيح أصلاً بنفس الفريق يُتخطّى بتحذير (تكرار). لا يمسّ إلا عمود player_id. صفر طلبات API.

--check يحاكي على نسخة بالذاكرة (الأصل قراءة فقط).
    python apply_id_repoints.py --check
    python apply_id_repoints.py
"""
import csv
import sqlite3
import sys

from config import BASE_DIR, DB_FILE

SOURCE = BASE_DIR / "player_id_repoints.csv"
TABLES = ("lineup_players", "player_stats")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("from_id") or "").strip():
                continue
            rows.append({
                "table": r["table"].strip(), "from": int(r["from_id"]), "to": int(r["to_id"]),
                "number": int(r["number"]) if (r.get("number") or "").strip() else None,
                "en": (r.get("player_en") or "").strip(),
                "expect": int(r["expect"]) if (r.get("expect") or "").strip() else None,
            })
    return rows


def validate(rows):
    for r in rows:
        if r["table"] not in TABLES:
            raise ValueError(f"جدول غير مسموح: {r['table']}")
        if r["from"] == r["to"] or r["to"] == 0 or r["from"] == 0:
            raise ValueError(f"معرّف غير صالح: {r['from']}→{r['to']}")
        if not r["en"]:
            raise ValueError(f"player_en شرط إلزامي: {r}")
        if r["number"] is not None and r["table"] != "lineup_players":
            raise ValueError("number خاص بـlineup_players")
    froms = {r["from"] for r in rows}
    chain = froms & {r["to"] for r in rows}
    if chain:
        raise ValueError(f"سلسلة: {sorted(chain)}")


def _where(r):
    w, p = "player_id = ? AND player_en = ?", [r["from"], r["en"]]
    if r["number"] is not None:
        w += " AND number = ?"
        p.append(r["number"])
    return w, p


def apply(conn, rows, out=print):
    """يرجّع قائمة تقارير [{row, matched, moved, skipped_dup}]"""
    report = []
    for r in rows:
        w, p = _where(r)
        t = r["table"]
        found = conn.execute(f"SELECT match_id, team_id FROM {t} WHERE {w}", p).fetchall()
        e = {"row": r, "matched": len(found), "moved": 0, "skipped_dup": 0,
             "to_before": conn.execute(f"SELECT COUNT(*) FROM {t} WHERE player_id = ?", (r["to"],)).fetchone()[0]}
        if found and e["to_before"] == 0:
            out(f"  ⚠️ تخطّي {r['from']}→{r['to']}: المعرّف الصحيح بلا أي صف بـ{t}")
            e["skipped_dup"] = len(found)
            report.append(e)
            continue
        for mid, tid in found:
            if conn.execute(f"SELECT 1 FROM {t} WHERE match_id = ? AND team_id = ? AND player_id = ?", (mid, tid, r["to"])).fetchone():
                out(f"  ⚠️ تخطّي صف مباراة {mid}: المعرّف {r['to']} موجود بنفس المباراة والفريق")
                e["skipped_dup"] += 1
                continue
            conn.execute(f"UPDATE {t} SET player_id = ? WHERE match_id = ? AND team_id = ? AND {w}", (r["to"], mid, tid, *p))
            e["moved"] += 1
        report.append(e)
    conn.commit()
    return report


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
    print(f"\n{'=' * 58}\n  تصحيحات معرّف بصفوف محدّدة: {len(rows)}" + ("   [وضع الفحص — صفر كتابة]" if check else "") + f"\n{'=' * 58}")
    report = apply(conn, rows)
    for e in report:
        r = e["row"]
        exp = "" if r["expect"] is None or r["expect"] == e["matched"] or e["matched"] == 0 else f" (المتوقع وقت القرار {r['expect']})"
        print(f"  {r['table']} {r['from']}→{r['to']} «{r['en']}»" + (f" #{r['number']}" if r["number"] is not None else "")
              + f": مطابق {e['matched']} · نُقل {e['moved']} · تُخطّي {e['skipped_dup']}{exp}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
