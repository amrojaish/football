#!/usr/bin/env python3
"""
سحب التشكيلات
================
بيسحب من fixtures/lineups: الخطة، المدرب، التشكيلة الأساسية
والاحتياط لكل فريق.

طلب واحد لكل مباراة.

⚠️ **لا يلمس** matches ولا goals ولا events ولا match_stats.

تزايدي: المباريات اللي عندها تشكيلات بينتخطاها.
المباريات القادمة (بلا نتيجة) بتنتخطى — التشكيلة تُعلَن قبل
المباراة بساعة، فلا فائدة من سحبها مبكراً.

⚠️ نفس نمط الأحداث والإحصائيات: **المزوّد يوفّرها للسعودي فقط**
   على الأرجح. اختبر بعيّنة صغيرة قبل السحب الكامل.

⚠️ **لاعب بلا معرّف من المزوّد (`player.id = null`) يُخزَّن بمعرّف سالب اصطناعي** (12 أكتوبر 2026) بدل تخطّيه بصمت — كان
   التخطّي يُسقط أساسياً من التشكيلة (مثال: 1634291، «Mohamed Nasser» #12 مدافع 2:4 → الفريق 10 أساسيين). المعرّف =
   `-(match_id*1000 + team_slot*100 + number)` (slot 1 = المضيف، 2 = الضيف؛ بلا رقم: 99 − ترتيبه بالفريق). فريد بالمباراة، سالب فلا
   يتصادم مع معرّف المزوّد، ويُستبعد من كل تجميع بالمعرّف (`player_id > 0` بمستهلكي الداتا). الاسم/المركز/الـgrid كما رجعت من المزوّد.

إعادة سحب مباريات ناقصة (للأساسيين < 11):
    python fetch_lineups.py --refetch auto --check          <- فحص فقط: يطلب من المزوّد ويحفظ JSON خام بـFootballBackups، **بلا أي كتابة**
    python fetch_lineups.py --refetch 1634291,1612252 --check
    python fetch_lineups.py --refetch auto --apply          <- التنفيذ (بعد db_pull مقفول وموافقة): **دمج لا مسح** (13 أكتوبر): يضيف/يحدّث الصفوف
                                                               ولا يحذف صفاً مخزَّناً غاب عن الرد، ولا يمسح player_ar/coach_ar موجوداً
    python fetch_lineups.py --refetch auto --apply --db copy.db --from-json DIR   <- تجربة على نسخة بـJSON محفوظ (صفر طلبات)

التشغيل:
    python fetch_lineups.py --check
    python fetch_lineups.py SAU --budget 5      <- اختبار
    python fetch_lineups.py SAU --budget 700
"""

import json
import os
import requests
import sqlite3
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import API_BASE, DB_FILE, LEAGUES, check_key, clean_name, headers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3


def parse_args():
    code, budget = None, 100
    season = None
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].upper() in LEAGUES:
        code = args[0].upper()

    if "--budget" in sys.argv:
        i = sys.argv.index("--budget")
        if i + 1 < len(sys.argv):
            try:
                budget = int(sys.argv[i + 1])
            except ValueError:
                pass

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, budget, check_only, season


def argv_val(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            return sys.argv[i + 1]
    return None


def parse_refetch():
    """(ids_arg|None, apply, out_dir)"""
    ids_arg = None
    if "--refetch" in sys.argv:
        i = sys.argv.index("--refetch")
        ids_arg = sys.argv[i + 1] if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--") else "auto"
    out = os.path.join(os.path.expanduser("~"), "FootballBackups",
                       "lineups-refetch-" + datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if "--out" in sys.argv:
        j = sys.argv.index("--out")
        if j + 1 < len(sys.argv):
            out = sys.argv[j + 1]
    return ids_arg, "--apply" in sys.argv, out


def get(endpoint, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{API_BASE}/{endpoint}",
                             headers=headers(), params=params,
                             timeout=TIMEOUT)

            if r.status_code == 429:
                wait = attempt * 10
                print(f"      تجاوز المعدل — انتظار {wait}ث")
                time.sleep(wait)
                continue

            if r.status_code != 200:
                return False, [], f"HTTP {r.status_code}"

            data = r.json()
            errors = data.get("errors")
            if errors and isinstance(errors, dict) and errors:
                return False, [], f"API: {errors}"

            return True, data.get("response", []), ""

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                print(f"      مهلة — إعادة ({attempt}/{MAX_RETRIES})")
                time.sleep(attempt * 3)
            else:
                return False, [], "مهلة انتهت"

        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                print(f"      انقطاع — إعادة ({attempt}/{MAX_RETRIES})")
                time.sleep(attempt * 5)
            else:
                return False, [], "انقطاع اتصال"

        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def synth_id(mid, slot, number, idx, used):
    """معرّف سالب اصطناعي فريد بالمباراة للاعب بلا معرّف مزوّد."""
    num = number if isinstance(number, int) and 0 <= number <= 99 else 99 - idx
    pid = -(mid * 1000 + slot * 100 + num)
    while pid in used:
        pid -= 1
    used.add(pid)
    return pid


DUP_LOG = []   # كل حالة معرّف مكرّر داخل المباراة (يطبعها refetch): (match_id, team_id, id, الاسم المُبقى، الاسم الذي أخذ معرّفاً اصطناعياً)


def _tokens(name):
    import re as _re
    import unicodedata as _ud
    s = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return {t for t in _re.sub(r"[^a-z0-9 ]", " ", s).split() if len(t) > 1}


def known_names(conn, pid, exclude_mid):
    """أسماء معروفة لهذا المعرّف بمباريات أخرى (lineup_players + player_stats) مرتّبة بالأكثر تكراراً أولاً — لتحديد صاحب المعرّف الحقيقي
    عند التكرار. الأكثر تكراراً أولاً لأن صفوفاً قديمة تلوّثت بالتصادم نفسه (اسم الدخيل يظهر بضع مرات فقط)."""
    cnt = {}
    for tbl in ("lineup_players", "player_stats"):
        try:
            for name, n in conn.execute(
                    f"SELECT player_en, COUNT(*) FROM {tbl} WHERE player_id = ? AND match_id != ? AND player_en != '' GROUP BY player_en",
                    (pid, exclude_mid)):
                cnt[name] = cnt.get(name, 0) + n
        except Exception:
            pass
    return [n for n, _ in sorted(cnt.items(), key=lambda kv: -kv[1])]


def build_rows(mid, home_id, away_id, data, conn=None):
    """
    صفوف lineups + lineup_players من ردّ المزوّد. يرجع (lines, players, n_null).
    اللاعب بلا معرّف يأخذ معرّفاً سالباً اصطناعياً (راجع رأس الملف) بدل أن يُهمَل.
    ⚠️ معرّف مكرّر بالمباراة (13 أكتوبر 2026): المزوّد يعطي أحياناً نفس `player.id` للاعبَين مختلفين (PK الجدول (match_id, player_id)
    فكان الثاني يمحو الأول). يحتفظ بالمعرّف الحقيقي اللاعبُ الذي يطابق اسمه الأسماء المعروفة لهذا المعرّف (conn)، وإلا الأول المذكور؛
    الآخر يأخذ معرّفاً سالباً اصطناعياً من نفس عائلة بلا المعرّف (يُسجَّل بـ DUP_LOG).
    """
    lines, entries = [], []
    used = set()
    for blk in data:
        tid = (blk.get("team") or {}).get("id")
        if tid is None:
            continue
        slot = 1 if tid == home_id else 2
        coach = clean_name((blk.get("coach") or {}).get("name") or "")
        formation = blk.get("formation") or ""
        lines.append((mid, tid, formation, coach, ""))
        idx = 0
        for grp, starter in (("startXI", 1), ("substitutes", 0)):
            for item in blk.get(grp) or []:
                p = item.get("player") or {}
                entries.append({"tid": tid, "slot": slot, "idx": idx, "p": p, "starter": starter, "pid": p.get("id")})
                idx += 1
    # حلّ التكرار: لكل معرّف حقيقي مكرّر يبقى لمالكه فقط
    by_id = {}
    for e in entries:
        if e["pid"] is not None:
            by_id.setdefault(e["pid"], []).append(e)
    for pid, es in by_id.items():
        if len(es) < 2:
            continue
        keep = 0   # لا اسم معروف يطابق: الأول المذكور
        for kn in (known_names(conn, pid, mid) if conn is not None else []):   # الأكثر تكراراً أولاً؛ أول اسم معروف يطابق أحدهم يحسم
            hit = [i for i, e in enumerate(es) if _tokens(clean_name(e["p"].get("name") or "")) & _tokens(kn)]
            if hit:
                keep = hit[0]
                break
        for i, e in enumerate(es):
            if i != keep:
                e["dup"] = True
                DUP_LOG.append((mid, e["tid"], pid, clean_name(es[keep]["p"].get("name") or ""), clean_name(e["p"].get("name") or "")))
    players, n_null = [], 0
    for e in entries:
        p, pid = e["p"], e["pid"]
        if pid is None or e.get("dup"):
            pid = synth_id(mid, e["slot"], p.get("number"), e["idx"], used)
            n_null += 1 if e["pid"] is None else 0
        players.append((
            mid, e["tid"], pid,
            clean_name(p.get("name") or ""), "",
            p.get("number"),
            p.get("pos") or "",
            p.get("grid") or "",
            e["starter"],
        ))
    return lines, players, n_null


def short_fixtures(conn):
    """مباريات فيها فريق بخطة وأساسيون مخزَّنون < 11 (مرشّحة لإعادة السحب)."""
    return [r[0] for r in conn.execute("""
        SELECT DISTINCT l.match_id FROM lineups l
        WHERE l.formation IS NOT NULL AND l.formation != ''
          AND (SELECT COUNT(*) FROM lineup_players p
               WHERE p.match_id = l.match_id AND p.team_id = l.team_id AND p.starter = 1) < 11
        ORDER BY l.match_id DESC""")]


STALE_LOG = []   # (match, team, number, name, starter, player_ar, matched_to_id|None)


def _last_token(name):
    import re as _re
    import unicodedata as _ud
    s = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    t = [x for x in _re.sub(r"[^a-z0-9 ]", " ", s).split() if x]
    return t[-1] if t else ""


_AR_CSV = None


def ar_in_csv(pid, name, ar):
    """هل الاسم العربي `ar` مسجَّل بـplayers_ar.csv لهذا المعرّف (player_id) أو لهذا الاسم الإنجليزي (بلا حساسية للحالة/التشكيل)؟"""
    global _AR_CSV
    if _AR_CSV is None:
        import csv
        _AR_CSV = {"pid": set(), "name": set()}
        with open(Path(__file__).resolve().parent / "players_ar.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                a = (r.get("player_ar") or "").strip()
                if not a:
                    continue
                if (r.get("player_id") or "").strip().lstrip("-").isdigit():
                    _AR_CSV["pid"].add((int(r["player_id"]), a))
                _AR_CSV["name"].add((" ".join(sorted(_tokens(r.get("player_en") or ""))), a))
    return (pid, ar.strip()) in _AR_CSV["pid"] or (" ".join(sorted(_tokens(name))), ar.strip()) in _AR_CSV["name"]


def reconcile_stale(conn, mid, stored, players):
    """
    صف قديم (stale) = مخزَّن بمعرّف غاب عن إعادة السحب لهذه المباراة. يُطابَق بصف جديد: نفس الفريق + نفس رقم القميص + نفس آخر كلمة بالاسم
    (بلا حساسية للحالة/التشكيل). عند التطابق: ينتقل player_ar للصف الجديد إن كان فارغاً ثم يُحذف القديم (نفس اللاعب بمعرّف مزوّد قديم).
    غير المطابَق يبقى كما هو ويُسجَّل بـSTALE_LOG. يرجع (عدد المطابَق، عدد غير المطابَق).
    """
    new_ids = {pl[2] for pl in players}
    claimed = set()
    matched = unmatched = deleted_unmatched = 0
    for row in stored:   # (player_id, team_id, player_en, player_ar, number, starter)
        if row[0] in new_ids:
            continue
        pid, tid, name, ar, num, starter = row
        hit = None
        if isinstance(num, int):
            for pl in players:
                if pl[1] == tid and pl[5] == num and pl[2] not in claimed and _last_token(pl[3]) == _last_token(name) and _last_token(name):
                    hit = pl
                    break
        if hit is None:
            # بلا مطابقة (13 أكتوبر، الجولة الأخيرة): يُحذف أيضاً، لكن فقط إن كان اسمه العربي (إن وُجد) محفوظاً بـplayers_ar.csv لهذا المعرّف/الاسم
            # (فلا يضيع شيء)؛ وإلا يبقى الصف ويُسجَّل.
            if ar and not ar_in_csv(pid, name, ar):
                unmatched += 1
                STALE_LOG.append((mid, tid, num, name, starter, ar, "KEPT_NOT_IN_CSV"))
                continue
            conn.execute("DELETE FROM lineup_players WHERE match_id = ? AND player_id = ?", (mid, pid))
            deleted_unmatched += 1
            STALE_LOG.append((mid, tid, num, name, starter, ar or "", "DELETED_UNMATCHED"))
            continue
        claimed.add(hit[2])
        if ar:
            conn.execute("UPDATE lineup_players SET player_ar = ? WHERE match_id = ? AND player_id = ? AND COALESCE(player_ar, '') = ''",
                         (ar, mid, hit[2]))
        conn.execute("DELETE FROM lineup_players WHERE match_id = ? AND player_id = ?", (mid, pid))
        matched += 1
        STALE_LOG.append((mid, tid, num, name, starter, ar or "", hit[2]))
    return matched, unmatched, deleted_unmatched


def refetch(conn, ids_arg, apply, check, budget, out_dir, from_json=None):
    """
    --refetch: يعيد طلب مباريات ناقصة. بوضع --check **لا كتابة بالـDB إطلاقاً** (يُفتح للقراءة فقط) ويحفظ JSON الخام لكل مباراة.
    ids_arg: "auto" (المباريات الناقصة بالـDB) أو معرّفات مفصولة بفواصل.
    """
    if not (apply or check):
        print("  --refetch يتطلب --check (فحص بلا كتابة) أو --apply (تنفيذ)")
        return
    ids = short_fixtures(conn) if ids_arg == "auto" else [int(x) for x in ids_arg.split(",") if x.strip()]
    ids = ids[:budget]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 62}\n  إعادة سحب {len(ids)} مباراة — {'فحص فقط (بلا كتابة)' if check else 'تنفيذ'}\n  JSON خام ← {out}\n{'=' * 62}")

    tot = dict(requests=0, fetched=0, failed=0, null_players=0, teams_short_before=0, teams_fixed=0,
               teams_still_short=0, inserts=0, short_fixtures_fixed=0, short_fixtures_still=0)
    for i, mid in enumerate(ids, 1):
        m = conn.execute("SELECT home_id, away_id, league_code, season FROM matches WHERE match_id = ?", (mid,)).fetchone()
        if not m:
            print(f"  [{i}/{len(ids)}] {mid}: ليست بجدول matches — تخطّي")
            continue
        if from_json:   # إعادة استخدام JSON محفوظ: صفر طلبات API
            jf = Path(from_json) / f"{mid}.json"
            if not jf.exists():
                print(f"  [{i}/{len(ids)}] {mid}: لا ملف JSON محفوظ — تخطّي")
                continue
            success, data, reason = True, json.loads(jf.read_text(encoding="utf-8"))["response"], ""
        else:
            success, data, reason = get("fixtures/lineups", {"fixture": mid})
            tot["requests"] += 1
        if not success:
            tot["failed"] += 1
            print(f"  [{i}/{len(ids)}] {mid}: فشل — {reason}")
            time.sleep(DELAY)
            continue
        tot["fetched"] += 1
        if not from_json:
            (out / f"{mid}.json").write_text(json.dumps({"fixture": mid, "response": data}, ensure_ascii=False), encoding="utf-8")
        n_dup0 = len(DUP_LOG)
        lines, players, n_null = build_rows(mid, m["home_id"], m["away_id"], data, conn)
        for d in DUP_LOG[n_dup0:]:
            print(f"      ⚠️ معرّف مكرّر {d[2]} بالمباراة {d[0]} فريق {d[1]}: يبقى «{d[3]}» ويأخذ «{d[4]}» معرّفاً اصطناعياً")
        stored = {r[0]: r[1] for r in conn.execute(
            "SELECT team_id, COUNT(*) FROM lineup_players WHERE match_id = ? AND starter = 1 GROUP BY team_id", (mid,))}
        stored_ids = {r[0] for r in conn.execute("SELECT player_id FROM lineup_players WHERE match_id = ?", (mid,))}
        inserts = sum(1 for p in players if p[2] not in stored_ids)
        parts, fixed_all, any_short = [], True, False
        for ln in lines:
            tid, formation = ln[1], ln[2]
            xi = sum(1 for p in players if p[1] == tid and p[8] == 1)
            nulls = sum(1 for p in players if p[1] == tid and p[2] < 0)
            before = stored.get(tid, 0)
            after = xi
            if before < 11:
                tot["teams_short_before"] += 1
                if after >= 11:
                    tot["teams_fixed"] += 1
                else:
                    tot["teams_still_short"] += 1
                    fixed_all = False
            any_short = any_short or before < 11
            parts.append(f"{tid}: أساسيون {before}→{after}{' ✓11' if after >= 11 else ' ✗'} (بلا معرّف {nulls}, خطة {formation or '—'})")
        tot["null_players"] += n_null
        tot["inserts"] += inserts
        if any_short:
            tot["short_fixtures_fixed" if fixed_all else "short_fixtures_still"] += 1
        print(f"  [{i}/{len(ids)}] {mid} {m['league_code']}{m['season']}: بلا معرّف {n_null}, إدخالات جديدة {inserts} | " + " | ".join(parts))
        if apply:
            # ⚠️ دمج لا مسح (13 أكتوبر 2026): لا يُحذف أي صف مخزَّن غاب عن إعادة السحب، ولا يُمسح `player_ar`/`coach_ar` موجود
            #    (يُملأ فقط إن كان فارغاً). الصف الموجود بنفس (match_id, player_id) يُحدَّث بقيم المزوّد عدا الاسم العربي.
            try:
                stored = conn.execute("SELECT player_id, team_id, player_en, player_ar, number, starter FROM lineup_players WHERE match_id = ?", (mid,)).fetchall()
                conn.executemany("""INSERT INTO lineups (match_id, team_id, formation, coach_en, coach_ar) VALUES (?,?,?,?,?)
                    ON CONFLICT(match_id, team_id) DO UPDATE SET formation = excluded.formation, coach_en = excluded.coach_en,
                      coach_ar = CASE WHEN COALESCE(lineups.coach_ar, '') != '' THEN lineups.coach_ar ELSE excluded.coach_ar END""", lines)
                conn.executemany("""INSERT INTO lineup_players
                    (match_id, team_id, player_id, player_en, player_ar, number, pos, grid, starter)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(match_id, player_id) DO UPDATE SET team_id = excluded.team_id, player_en = excluded.player_en,
                      number = excluded.number, pos = excluded.pos, grid = excluded.grid, starter = excluded.starter,
                      player_ar = CASE WHEN COALESCE(lineup_players.player_ar, '') != '' THEN lineup_players.player_ar ELSE excluded.player_ar END""", players)
                m_, u_, d_ = reconcile_stale(conn, mid, [tuple(r) for r in stored], players)
                tot["stale_matched"] = tot.get("stale_matched", 0) + m_
                tot["stale_unmatched"] = tot.get("stale_unmatched", 0) + u_
                tot["stale_deleted_unmatched"] = tot.get("stale_deleted_unmatched", 0) + d_
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        time.sleep(DELAY)

    print(f"\n{'=' * 62}")
    print(f"  طلبات API: {tot['requests']} (نجح {tot['fetched']}, فشل {tot['failed']})")
    print(f"  لاعبون بلا معرّف وُجدوا: {tot['null_players']} | إدخالات جديدة ستُضاف: {tot['inserts']}")
    print(f"  فرق ناقصة قبلاً: {tot['teams_short_before']} → تصل 11: {tot['teams_fixed']} | تبقى ناقصة (فجوة مزوّد حقيقية): {tot['teams_still_short']}")
    print(f"  مباريات ناقصة صارت كاملة: {tot['short_fixtures_fixed']} | تبقى بها نقص: {tot['short_fixtures_still']}")
    if apply:
        print(f"  صفوف قديمة (معرّف غاب عن الرد): طُوبقت وحُذفت {tot.get('stale_matched', 0)} | بلا مطابقة وحُذفت (اسمها العربي محفوظ بالـCSV أو بلا اسم) {tot.get('stale_deleted_unmatched', 0)} | بقيت لأن اسمها العربي ليس بالـCSV {tot.get('stale_unmatched', 0)}")
        for d in STALE_LOG:
            if d[6] == "KEPT_NOT_IN_CSV":
                print(f"      ⚠️ بقي: {d[0]} فريق {d[1]} #{d[2]} {d[3]} ({d[5]}) — ليس بـplayers_ar.csv")
    print(f"{'=' * 62}")


def pending(conn, code, season):
    """مباريات منتهية بلا تشكيلات"""
    q = """
        SELECT m.match_id, m.league_code, m.season, m.date, m.home_id, m.away_id,
               h.short_name_ar AS home, a.short_name_ar AS away
        FROM matches m
        LEFT JOIN teams h ON h.team_id = m.home_id
        LEFT JOIN teams a ON a.team_id = m.away_id
        WHERE m.home_goals IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM lineups l WHERE l.match_id = m.match_id
        )
    """
    params = []
    if code:
        q += " AND m.league_code = ?"
        params.append(code)
    if season is not None:
        q += " AND m.season = ?"
        params.append(season)
    q += " ORDER BY m.date DESC"

    return conn.execute(q, params).fetchall()


def main():
    if not check_key():
        return

    code, budget, check_only, season = parse_args()
    ids_arg, do_apply, out_dir = parse_refetch()

    if ids_arg is not None:
        # --check = قراءة فقط (mode=ro)؛ الكتابة فقط بـ--apply
        db_path = argv_val("--db") or DB_FILE   # --db: نسخة تجريبية بدل القاعدة الحقيقية
        if do_apply:
            conn = sqlite3.connect(db_path)
        else:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        refetch(conn, ids_arg, do_apply, check_only, budget if "--budget" in sys.argv else 51, out_dir, argv_val("--from-json"))
        conn.close()
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM lineups LIMIT 1")
    except sqlite3.OperationalError:
        print("جداول التشكيلات غير موجودة — شغّل add_lineups_table.py أول")
        conn.close()
        return

    todo = pending(conn, code, season)

    print(f"\n{'=' * 58}")
    print(f"  مباريات بلا تشكيلات: {len(todo)}")
    print(f"{'=' * 58}")

    by = {}
    for m in todo:
        k = (m["league_code"], m["season"])
        by[k] = by.get(k, 0) + 1
    for (lg, s), n in sorted(by.items()):
        name = LEAGUES.get(lg, {}).get("name_ar", lg)
        print(f"  {name:<18} موسم {s}   {n}")

    if not todo:
        print("\n  ما في شي ناقص\n")
        conn.close()
        return

    if check_only:
        print(f"\n  [وضع الفحص] — ما انسحب شي")
        print(f"  الوقت لو سحبتهم كلهم: "
              f"~{len(todo) * DELAY / 60:.0f} دقيقة\n")
        conn.close()
        return

    to_fetch = todo[:budget]
    print(f"\n  رح أسحب {len(to_fetch)} ماتش "
          f"(~{len(to_fetch) * DELAY / 60:.0f} دقيقة)")
    print("  خليه يشتغل ولا تسكّره.\n")

    ok = failed = empty = 0
    n_players = 0
    failed_list = []

    for i, m in enumerate(to_fetch, 1):
        mid = m["match_id"]
        label = f"{m['home']} × {m['away']}"

        success, data, reason = get("fixtures/lineups", {"fixture": mid})

        if not success:
            print(f"  [{i}/{len(to_fetch)}] فشل — {label}")
            print(f"      السبب: {reason}")
            failed += 1
            failed_list.append((mid, label, reason))
            time.sleep(DELAY)
            continue

        if not data:
            empty += 1
            time.sleep(DELAY)
            continue

        lines, players, _n_null = build_rows(mid, m["home_id"], m["away_id"], data)

        if lines:
            conn.executemany("""
                INSERT OR REPLACE INTO lineups
                (match_id, team_id, formation, coach_en, coach_ar)
                VALUES (?, ?, ?, ?, ?)
            """, lines)

            if players:
                conn.executemany("""
                    INSERT OR REPLACE INTO lineup_players
                    (match_id, team_id, player_id, player_en, player_ar,
                     number, pos, grid, starter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, players)
                n_players += len(players)

            conn.commit()
            ok += 1
        else:
            empty += 1

        if i % 25 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}]  نجح: {ok}  "
                  f"لاعبين: {n_players}")

        time.sleep(DELAY)

    tot_l = conn.execute("SELECT COUNT(*) FROM lineups").fetchone()[0]
    tot_p = conn.execute(
        "SELECT COUNT(*) FROM lineup_players").fetchone()[0]
    uniq = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM lineup_players"
    ).fetchone()[0]

    print(f"""
{'=' * 58}
  فيها تشكيلات: {ok}   |   فاضية: {empty}   |   فشل: {failed}
  تشكيلات بالجدول: {tot_l}   |   سجلات لاعبين: {tot_p}
  لاعبون مختلفون: {uniq}
{'=' * 58}""")

    if failed_list:
        print("\n  اللي فشلت (أول 10):")
        for mid, label, reason in failed_list[:10]:
            print(f"    {mid}  {label}  [{reason}]")
        print("\n  شغّل نفس الأمر مرة تانية وبيحاول فيهم.")

    still = len(todo) - len(to_fetch)
    if still:
        print(f"\n  لسا ناقص {still} ماتش — أعد التشغيل بنفس الأمر.")
    else:
        print("\n  خلصت كل المباريات.")

    conn.close()


if __name__ == "__main__":
    main()
