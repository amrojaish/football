#!/usr/bin/env python3
"""
استيراد أحداث العراقي والأردني من الـworker
=============================================
المزوّد لا يُسحب منه أحداث هذين الدوريين (update_all.py: DETAILED بلا IRQ/JOR)، لكن الردّ الحيّ يحملها: الـworker يحفظ نسخة
مضغوطة ev:<id> لـ36 ساعة ومعها نسخة نهائية (ft: 1) من ردّ نهاية المباراة (worker.js storeEvents، 19 أكتوبر 2026). هذا السكربت
يقرؤها من GET /events?id= (عام، بلا مفتاح ولا حصة) ويكتبها بجدول events **بنفس أعمدة وقيم fetch_events.py**.

⚠️ لا يكتب فوق شيء: مباراة لها أي صف بـevents (حتى 'none') تُتخطّى. النسخة غير النهائية (ft ≠ 1) تُرفض.
⚠️ الأعمدة كما هي بجدول events (لا extra ولا معرّفات لاعبين — fetch_events.py لا يخزّنها أيضاً):
      minute = الدقيقة (elapsed فقط) · team_id من جهة h/a ومعرّفي المباراة · player_en / assist_en بـclean_name · player_ar فارغ
      Card: y → Yellow Card · r → Red Card · yr → Second Yellow card (نص المزوّد)
      subst: «Substitution N» بترتيب تبديلات الفريق زمنياً (كما يرقّمها المزوّد) · Var: التفصيل كما هو · الأهداف تُتجاهل (جدول goals)
      نسخة نهائية بلا بطاقات/تبديلات/VAR = صف 'none' واحد (كما fetch_events.py: لا إعادة محاولة)
⚠️ النافذة: منتهية (FT/AET/PEN) انطلقت خلال آخر 36 ساعة — عمر ev:<id> بالـKV. ما فات بعدها يضيع.

صفر طلبات للمزوّد.

التشغيل:
    python import_live_events.py --check     ← لكل مباراة: ما سيُكتب، بلا أي كتابة
    python import_live_events.py             ← يكتب
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from config import DB_FILE, LEAGUES, clean_name
from push_ui import PUSH_WORKER   # رابط الـworker الوحيد بالمشروع (لا يوجد بـconfig.py)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LEAGUE_CODES = ("IRQ", "JOR")   # معرّفا المزوّد 542 و 387
# الكويتي (330، 24 أكتوبر 2026): نفس الحالة (المزوّد بلا بطاقات/تبديلات بالعيّنة) — يدخل فقط حين يُفعَّل بـconfig.ENABLED_LEAGUES
LEAGUE_CODES += tuple(c for c in ("KUW",) if c in LEAGUES)
WINDOW_SECS = 36 * 3600
FINAL = ("FT", "AET", "PEN")
CARD = {"y": "Yellow Card", "r": "Red Card", "yr": "Second Yellow card"}
TIMEOUT = 20


def candidates(conn, now):
    """منتهية من العراقي/الأردني، انطلقت خلال 36 ساعة، بلا أي صف بـevents."""
    out = []
    for mid, lg, d, h, a in conn.execute(f"""
            SELECT m.match_id, m.league_code, m.date, m.home_id, m.away_id FROM matches m
            WHERE m.league_code IN ({",".join("?" * len(LEAGUE_CODES))}) AND m.status IN ({",".join("?" * len(FINAL))})
              AND NOT EXISTS (SELECT 1 FROM events e WHERE e.match_id = m.match_id)
            ORDER BY m.date""", (*LEAGUE_CODES, *FINAL)):
        try:
            ko = datetime.strptime(str(d)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        if now - WINDOW_SECS <= ko <= now:
            out.append((mid, lg, h, a))
    return out


def fetch_live_events(mid, base=PUSH_WORKER):
    """(payload | None, سبب). 404 = لا نسخة محفوظة."""
    # ⚠️ User-Agent صريح: Cloudflare يرفض «Python-urllib» الافتراضي بـ403 (تحقّقنا 19 أكتوبر)
    req = urllib.request.Request(f"{base}/events?id={mid}", headers={"User-Agent": "saffara-import/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8")), "ok"
    except urllib.error.HTTPError as e:
        return None, "none stored" if e.code == 404 else f"HTTP {e.code}"
    except Exception as e:   # شبكة/مهلة/JSON
        return None, type(e).__name__


def map_rows(mid, home_id, away_id, payload):
    """صفوف compactEvents → صفوف events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en).
    [دقيقة, إضافي, نوع g/c/s/v, تفصيل, لاعب, مساعد/الداخل, جهة h/a, معرّف اللاعب, معرّف المساعد]"""
    rows, subs_n = [], {}
    ordered = sorted((r for r in payload.get("l") or [] if isinstance(r, list) and len(r) >= 7),
                     key=lambda r: ((r[0] or 0) * 1000 + (r[1] or 0)))
    for r in ordered:
        minute, _extra, ty, d, player, assist, side = r[:7]
        team = home_id if side == "h" else away_id if side == "a" else None
        if ty == "c":
            etype, detail = "Card", CARD.get(d, "Yellow Card")
        elif ty == "s":
            subs_n[team] = subs_n.get(team, 0) + 1
            etype, detail = "subst", f"Substitution {subs_n[team]}"
        elif ty == "v":
            etype, detail = "Var", str(d or "")
        else:
            continue   # الأهداف: جدول goals (fetch_events.py يتجاهلها أيضاً)
        rows.append((mid, team, minute, etype, detail, clean_name(player or ""), "", clean_name(assist or "")))
    return rows


def plan(conn, now, fetch=fetch_live_events):
    """[(mid, league, rows | None, سبب)] — rows=None = تخطٍّ."""
    out = []
    for mid, lg, h, a in candidates(conn, now):
        payload, why = fetch(mid)
        if payload is None:
            out.append((mid, lg, None, why))
        elif payload.get("ft") != 1:
            out.append((mid, lg, None, "not final (ft != 1)"))
        else:
            out.append((mid, lg, map_rows(mid, h, a, payload), "ok"))
    return out


def apply(conn, planned):
    """يكتب ما خُطّط له؛ يعيد فحص «لا صفوف» داخل المعاملة (لا كتابة فوق شيء). يرجع عدد المباريات المكتوبة."""
    done = 0
    for mid, _lg, rows, _why in planned:
        if rows is None:
            continue
        with conn:
            if conn.execute("SELECT 1 FROM events WHERE match_id = ? LIMIT 1", (mid,)).fetchone():
                continue
            if rows:
                conn.executemany("""INSERT INTO events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)
            else:
                conn.execute("""INSERT INTO events (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en)
                                VALUES (?, NULL, NULL, 'none', '', '', '', '')""", (mid,))
        done += 1
    return done


def main():
    check = "--check" in sys.argv
    conn = sqlite3.connect(DB_FILE)
    planned = plan(conn, time.time())
    total = 0
    print(f"IRQ/JOR live events import{' (--check: no writes)' if check else ''}: {len(planned)} candidate fixture(s)")
    for mid, lg, rows, why in planned:
        if rows is None:
            print(f"  {mid} {lg}: skip — {why}")
            continue
        total += len(rows)
        print(f"  {mid} {lg}: {len(rows)} row(s){' (none marker)' if not rows else ''}")
        if check:
            for r in rows:
                print(f"      {r[2]}' {r[3]:<5} {r[4]:<18} team {r[1]}  {r[5]}{(' <- ' + r[7]) if r[7] else ''}")
    print(f"  total rows: {total}")
    if not check:
        print(f"  written: {apply(conn, planned)} fixture(s)")
    conn.close()


if __name__ == "__main__":
    main()
