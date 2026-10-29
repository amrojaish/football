#!/usr/bin/env python3
"""
سحب الترتيب الرسمي من المزوّد
================================
طلب واحد لكل (دوري، موسم) — رخيص جداً.

⚠️ **لا يلمس** أي جدول آخر. مرجع للمقارنة فقط.

⚠️ الترتيب يتغيّر مع كل جولة، فأعد السحب دورياً للمواسم
   الجارية. المواسم المنتهية ثابتة.

التشغيل:
    python fetch_standings.py --check      <- أي تركيبات ناقصة
    python fetch_standings.py              <- كل الموجود بالـDB
    python fetch_standings.py SAU
    python fetch_standings.py --season 2026
    python fetch_standings.py --season 2026 --changed-only   <- (CI) فقط ما تغيّر

⚠️ (29 أكتوبر 2026) **--changed-only** (update_all.py، مرة واحدة بكل تشغيلة نشر): يُسحب الدوري/الموسم فقط إن
   (أ) لا ترتيب مخزَّن له، أو عدد صفوفه ≠ فرقنا، أو (ب) ترتيب المزوّد المخزَّن لا يطابق جدولنا (tiebreak.provider_order = None: انتهت مباراة
   بعد آخر سحب) **وآخر سحب قبل انطلاق آخر مباراة منتهية + 4 ساعات** (مهلة لتأخّر المزوّد؛ بعدها لا إعادة حتى مباراة
   جديدة — فرق دائم كحسم إداري غير مطبَّق لا يستهلك طلباً كل تشغيلة). كان 1 طلب لكل دوري بكل تشغيلة (~480 باليوم).
⚠️ (29 أكتوبر 2026) **الصفوف تُستبدل كاملة لكل دوري/موسم** (DELETE ثم INSERT): صف بلا معرّف فريق (تونس: «Monastir»)
   لا يستبدله INSERT OR REPLACE (NULL بالمفتاح) فكان يتراكم صفاً جديداً بكل سحب. fetched_at بتوقيت UTC.
"""

import requests
import sqlite3
import time
import sys
import csv
from datetime import datetime, timedelta, timezone

from config import API_BASE, DB_FILE, LEAGUES, BASE_DIR, check_key, headers

LEAGUE_LOGOS_FILE = BASE_DIR / "league_logos.csv"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3


def parse_args():
    code = None
    season = None
    check_only = "--check" in sys.argv

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].upper() in LEAGUES:
        code = args[0].upper()

    if "--season" in sys.argv:
        i = sys.argv.index("--season")
        if i + 1 < len(sys.argv):
            try:
                season = int(sys.argv[i + 1])
            except ValueError:
                pass

    return code, check_only, season


def get(params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{API_BASE}/standings",
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
                time.sleep(attempt * 3)
            else:
                return False, [], "مهلة انتهت"

        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 5)
            else:
                return False, [], "انقطاع اتصال"

        except Exception as e:
            return False, [], f"خطأ: {type(e).__name__}"

    return False, [], "فشل بعد كل المحاولات"


def needs_fetch(conn, lg, s):
    """(--changed-only) (سحب؟، السبب) — راجع رأس الملف"""
    last = conn.execute("SELECT MAX(fetched_at) FROM api_standings WHERE league_code = ? AND season = ?", (lg, s)).fetchone()[0]
    if not last:
        return True, "لا ترتيب مخزَّن"
    from make_site3 import get_table
    from tiebreak import provider_order
    table = get_table(conn, lg, s)
    if provider_order(conn, lg, s, table):
        return False, "مطابق لجدولنا"
    n = conn.execute("SELECT COUNT(*) FROM api_standings WHERE league_code = ? AND season = ?", (lg, s)).fetchone()[0]
    if table and n != len(table):   # صفوف زائدة/ناقصة (تراكم صف بلا معرّف قبل 29 أكتوبر 2026) — سحب واحد يستبدلها
        return True, f"{n} صفاً مخزَّناً مقابل {len(table)} فريقاً"
    ko = conn.execute("SELECT MAX(date) FROM matches WHERE league_code = ? AND season = ? AND home_goals IS NOT NULL",
                      (lg, s)).fetchone()[0]
    if not ko:
        return False, "لا مباريات منتهية"
    try:
        until = (datetime.strptime(str(ko)[:16], "%Y-%m-%d %H:%M") + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        until = str(ko)[:10] + " 23:59"
    if str(last) < until:
        return True, f"غير مطابق، آخر سحب {last} قبل {until}"
    return False, f"غير مطابق لكن سُحب بعد مهلة آخر مباراة ({last})"


def save_league_logo(code, logo):
    """
    يحدّث عمود logo فقط بـleague_logos.csv (صف league_code) —
    لا يلمس logo_local/logo_note (استثناء يدوي منفصل تماماً).

    ⚠️ **صفر طلب API جديد** — logo يأتي من استجابة /standings
       الموجودة أصلاً بالذاكرة (data[0]["league"]["logo"])، لا من
       نقطة إضافية. نفس أسلوب clean_logos_all.py::update_csv —
       قراءة كاملة → تعديل الصف المطابق → كتابة كاملة.
    """
    if not logo or not LEAGUE_LOGOS_FILE.exists():
        return False

    with open(LEAGUE_LOGOS_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    changed = False
    for row in rows:
        if row.get("league_code") == code:
            if (row.get("logo") or "").strip() != logo:
                row["logo"] = logo
                changed = True
            break

    if changed:
        with open(LEAGUE_LOGOS_FILE, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    return changed


def main():
    if not check_key():
        return

    code, check_only, season = parse_args()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM api_standings LIMIT 1")
    except sqlite3.OperationalError:
        print("جدول api_standings غير موجود — "
              "شغّل add_standings_table.py أول")
        conn.close()
        return

    # التركيبات الموجودة بالـDB
    q = """
        SELECT DISTINCT league_code AS lg, season AS s
        FROM matches ORDER BY season DESC, league_code
    """
    combos = conn.execute(q).fetchall()

    if code:
        combos = [c for c in combos if c["lg"] == code]
    if season is not None:
        combos = [c for c in combos if c["s"] == season]

    print(f"\n{'=' * 62}")
    print(f"  سحب الترتيب الرسمي — {len(combos)} تركيبة")
    print(f"{'=' * 62}")

    if check_only:
        for c in combos:
            n = conn.execute("""
                SELECT COUNT(*) FROM api_standings
                WHERE league_code = ? AND season = ?
            """, (c["lg"], c["s"])).fetchone()[0]
            name = LEAGUES.get(c["lg"], {}).get("name_ar", c["lg"])
            mark = f"{n} صف" if n else "ناقص"
            print(f"      {name:<18} {c['s']}   {mark}")
        print(f"\n  الطلبات المطلوبة: {len(combos)}\n")
        conn.close()
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    changed_only = "--changed-only" in sys.argv
    ok = failed = 0
    total_rows = 0
    logos_saved = set()  # ⚠️ شعار الدوري ثابت لكل مواسمه — تحديث مرة واحدة بالتشغيلة لا لكل موسم

    for c in combos:
        lg, s = c["lg"], c["s"]
        name = LEAGUES.get(lg, {}).get("name_ar", lg)
        if changed_only:
            go, why = needs_fetch(conn, lg, s)
            if not go:
                print(f"  {name} {s}: تخطٍّ — {why}")
                continue
            print(f"  {name} {s}: سحب — {why}")

        success, data, reason = get({
            "league": LEAGUES[lg]["id"], "season": s
        })

        if not success:
            print(f"\n  {name} {s}: فشل — {reason}")
            failed += 1
            time.sleep(DELAY)
            continue

        if not data:
            print(f"\n  {name} {s}: ما رجع ترتيب")
            failed += 1
            time.sleep(DELAY)
            continue

        rows = []
        # البنية: response[0].league.standings[0] = قائمة الفرق
        try:
            groups = data[0]["league"]["standings"]
        except (KeyError, IndexError, TypeError):
            print(f"\n  {name} {s}: بنية غير متوقعة")
            failed += 1
            time.sleep(DELAY)
            continue

        # ⚠️ شعار الدوري من نفس استجابة /standings — صفر طلب إضافي
        if lg not in logos_saved:
            logo = data[0]["league"].get("logo") or ""
            if save_league_logo(lg, logo):
                print(f"      ↳ شعار {name} محدَّث بـleague_logos.csv")
            logos_saved.add(lg)

        for group in groups:
            for t in group:
                all_ = t.get("all") or {}
                goals = all_.get("goals") or {}
                rows.append((
                    lg, s,
                    (t.get("team") or {}).get("id"),
                    t.get("rank"),
                    all_.get("played"),
                    all_.get("win"),
                    all_.get("draw"),
                    all_.get("lose"),
                    goals.get("for"),
                    goals.get("against"),
                    t.get("points"),
                    t.get("form") or "",
                    t.get("description") or "",
                    now,
                ))

        if rows:
            conn.execute("DELETE FROM api_standings WHERE league_code = ? AND season = ?", (lg, s))
            conn.executemany("""
                INSERT OR REPLACE INTO api_standings
                (league_code, season, team_id, rank, played, wins,
                 draws, losses, goals_for, goals_against, points,
                 form, description, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)
            conn.commit()
            print(f"\n  ✅ {name} {s}   {len(rows)} فريق")
            ok += 1
            total_rows += len(rows)

        time.sleep(DELAY)

    tot = conn.execute("SELECT COUNT(*) FROM api_standings").fetchone()[0]
    conn.close()

    print(f"""
{'=' * 62}
  نجح: {ok}   |   فشل: {failed}   |   صفوف: {total_rows}
  إجمالي الجدول: {tot}
{'=' * 62}

  الخطوة الجاية:  python compare_standings.py
""")


if __name__ == "__main__":
    main()
