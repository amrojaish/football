#!/usr/bin/env python3
"""
استيراد دوري جديد من قاعدة الاختبار إلى football.db (TUN أولاً، 26 أكتوبر 2026)
=================================================================================
المصدر: قاعدة اختبار بنفس المخطط (FootballBackups/football_newleagues_test.db) فيها
مباريات الدوري وأحداثه وتشكيلاته وبطاقات لاعبيه. صفر طلبات API لبيانات المباريات.

ما يُكتب (بالترتيب، بمعاملة واحدة):
    matches          كما هي (match_id من المزوّد)
    goals / events   **بلا عمود id** — AUTOINCREMENT يعطي معرّفات جديدة بعد آخر معرّف
                     بالقاعدة الحقيقية (ترتيبها النسبي محفوظ: ORDER BY id بالمصدر)
    lineups / lineup_players   كما هي
    player_info      لاعبو الدوري فقط (ملفات المزوّد + من بالتشكيلات)، **ويُتخطّى أي
                     player_id موجود أصلاً** بالقاعدة الحقيقية (INSERT OR IGNORE، يُعدّ)
ثم خارج المعاملة:
    الأندية          **لا إدراج مباشر**: صفوف جديدة تُلحَق بـteams_arabic.csv (الأسماء العربية
                     من CLUBS أدناه، معتمدة من Amr) ثم sync_teams.py — المصدر الوحيد للأندية
    تثبيت الأسماء    PIN_IDS تُثبَّت على اسمها المعروض **الآن** بالموقع (build_plan قبل
                     الاستيراد) بـplayer_name_pins.csv — فلا يغيّر الاستيراد اسم صفحة أو slug

⚠️ قبل الاستيراد: الصفحات والـstubs الحالية تُسجَّل بـplayer_url_history.json (update_history، كـmake_players بالـCI) فيحجز
   build_plan كل رابط قائم لصاحبه؛ بعده يُقارَن كل رابط (صفحة وإعادة توجيه) — أي تغيّر صاحب = توقّف. الملف حالة دائمة يرفعها db_push.
⚠️ ENABLED_LEAGUES = {"TUN"} فقط: قاعدة الاختبار فيها ALG/KUW أيضاً ولا تُلمس.
⚠️ أي تصادم (match_id أو team_id موجود، أو مخطط جدول مختلف) = توقّف كامل قبل أي كتابة.

ترتيب التشغيل الحقيقي (خطة 26 أكتوبر):
    1) python db_pull.py                    ← قفل محلي (يرفض --apply بدونه)
    2) python import_league.py TUN --src <test.db> --apply
         ← نسخة احتياطية تلقائية بـDB_BACKUP_DIR ← استيراد ← فحوص (فشلها = rollback)
         ← teams_arabic.csv + sync_teams.py ← player_name_pins.csv ← فحص الـpins
    3) python db_push.py
    4) دفع الكود (config.LEAGUES وغيره — خارج هذا السكربت)

--check: كل شيء يجري على **نسخة مؤقتة** من --db (وCSVات مؤقتة) ثم يُعرض: أعداد الصفوف،
التصادمات، التحذيرات، وأثر الاستيراد على صفحات اللاعبين الحالية. --db نفسه لا يُكتب.

التشغيل:
    python import_league.py TUN --src C:\\...\\football_newleagues_test.db --db <نسخة.db> --check
    python import_league.py TUN --src C:\\...\\football_newleagues_test.db --apply
"""
import csv
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, DB_FILE, TEAMS_FILE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ENABLED_LEAGUES = {"TUN"}
LEAGUE_AR = {"TUN": "الدوري التونسي"}
TABLES = ("matches", "goals", "events", "lineups", "lineup_players", "player_info", "teams")
PINS_FILE = BASE_DIR / "player_name_pins.csv"
HISTORY_FILE = BASE_DIR / "player_url_history.json"   # حالة دائمة (state_sync.STATE_FILES): db_push يرفعها مع القاعدة
PLAYERS_AR = BASE_DIR / "players_ar.csv"

# الإنجليزي المعروض (name_en_official) | العربي الكامل | المختصر — بمفتاح اسم المزوّد (teams.name_en بالمصدر)
CLUBS = {
    "TUN": {
        "ES Tunis": ("ES Tunis", "الترجي الرياضي التونسي", "الترجي"),
        "Club Africain": ("Club Africain", "النادي الإفريقي", "الإفريقي"),
        "ES Sahel": ("ES Sahel", "النجم الرياضي الساحلي", "النجم الساحلي"),
        "CS Sfaxien": ("CS Sfaxien", "النادي الرياضي الصفاقسي", "الصفاقسي"),
        "CA Bizertin": ("CA Bizertin", "النادي البنزرتي", "البنزرتي"),
        "Stade Tunisien": ("Stade Tunisien", "الملعب التونسي", "الملعب التونسي"),
        "US Monastirienne": ("US Monastirienne", "الاتحاد الرياضي المنستيري", "الاتحاد المنستيري"),
        "US Ben Guerdane": ("US Ben Guerdane", "الاتحاد الرياضي ببن قردان", "اتحاد بن قردان"),
        "Olympique Béja": ("Olympique Béja", "الأولمبي الباجي", "الأولمبي الباجي"),
        "ES Metlaoui": ("ES Metlaoui", "النجم الرياضي بالمتلوي", "نجم المتلوي"),
        "ES Zarzis": ("ES Zarzis", "الترجي الرياضي الجرجيسي", "الترجي الجرجيسي"),
        "Jeunesse Sportive Omrane": ("JS Omrane", "الشبيبة الرياضية بالعمران", "شبيبة العمران"),
        "AS Marsa": ("AS Marsa", "المستقبل الرياضي بالمرسى", "مستقبل المرسى"),
        "AS Soliman": ("AS Soliman", "المستقبل الرياضي بسليمان", "مستقبل سليمان"),
        "AS Gabes": ("AS Gabès", "المستقبل الرياضي بقابس", "مستقبل قابس"),
        "JS Kairouanaise": ("JS Kairouanaise", "الشبيبة الرياضية القيروانية", "شبيبة القيروان"),
        "US Tataouine": ("US Tataouine", "الاتحاد الرياضي بتطاوين", "اتحاد تطاوين"),
        "EGS Gafsa": ("EGS Gafsa", "القوافل الرياضية بقفصة", "قوافل قفصة"),
        "CS Hammam-Lif": ("CS Hammam-Lif", "النادي الرياضي بحمام الأنف", "نادي حمام الأنف"),
        "ES Hammam-Sousse": ("ES Hammam-Sousse", "الأمل الرياضي بحمام سوسة", "أمل حمام سوسة"),
        "Progrès Sakiet Eddaïer": ("PS Sakiet Eddaïer", "التقدم الرياضي بساقية الدائر", "تقدم ساقية الدائر"),
        "CS Chebba": ("CS Chebba", "الهلال الرياضي الشابي", "هلال الشابة"),
        "EO Sidi Bouzid": ("EO Sidi Bouzid", "أولمبيك سيدي بوزيد", "أولمبيك سيدي بوزيد"),
        "AS Rejiche": ("AS Rejiche", "المستقبل الرياضي بالرجيش", "مستقبل الرجيش"),
    },
}

# لاعبون موجودون بالموقع ولهم ظهور بالدوري الجديد — يُثبَّت اسمهم الحالي (اعتماد Amr)
PIN_IDS = {
    "TUN": [2947, 20536, 49418, 49424, 49481, 49617, 49735, 72142, 123737, 276270,
            335131, 341366, 365495, 392619, 395077, 406905, 433596, 502291],
}
PIN_REASON = "keep current site name before {code} import (26 Oct 2026)"


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


class Abort(Exception):
    pass


# ---------------------------------------------------------------- فحوص قبل الكتابة
def preflight(conn, code):
    """تصادمات ومخطط — أي مشكلة = Abort. يرجّع (أعداد المصدر، مجموعة player_info المرشّحة)."""
    for t in TABLES:
        a = conn.execute("SELECT sql FROM main.sqlite_master WHERE name = ?", (t,)).fetchone()
        b = conn.execute("SELECT sql FROM s.sqlite_master WHERE name = ?", (t,)).fetchone()
        if not a or not b or a[0] != b[0]:
            raise Abort(f"مخطط {t} مختلف بين القاعدتين")

    src = {}
    src["matches"] = conn.execute("SELECT COUNT(*) FROM s.matches WHERE league_code = ?", (code,)).fetchone()[0]
    if not src["matches"]:
        raise Abort(f"لا مباريات {code} بالمصدر")
    for t in ("goals", "events", "lineups", "lineup_players"):
        src[t] = conn.execute(f"SELECT COUNT(*) FROM s.{t} WHERE match_id IN "
                              "(SELECT match_id FROM s.matches WHERE league_code = ?)", (code,)).fetchone()[0]

    coll = {}
    coll["match_id"] = conn.execute("""SELECT COUNT(*) FROM main.matches WHERE match_id IN
        (SELECT match_id FROM s.matches WHERE league_code = ?)""", (code,)).fetchone()[0]
    for t in ("goals", "events", "lineups", "lineup_players"):
        coll[t] = conn.execute(f"""SELECT COUNT(*) FROM main.{t} WHERE match_id IN
            (SELECT match_id FROM s.matches WHERE league_code = ?)""", (code,)).fetchone()[0]
    coll["team_id"] = conn.execute("""SELECT COUNT(*) FROM main.teams WHERE team_id IN
        (SELECT home_id FROM s.matches WHERE league_code = ? UNION
         SELECT away_id FROM s.matches WHERE league_code = ?)""", (code, code)).fetchone()[0]
    print("\n  تصادمات (يجب أن تكون كلها 0):")
    for k, v in coll.items():
        print(f"      {k:<16}: {v}")
    if any(coll.values()):
        raise Abort("تصادم مع القاعدة الحقيقية — لا كتابة")

    # player_info: ملفات المزوّد لهذا الدوري = من بالتشكيلات + من جُلب ملفه مع الدوري (بلا مطابقة مباراة)
    lp = {r[0] for r in conn.execute("""SELECT DISTINCT player_id FROM s.lineup_players
        WHERE player_id > 0 AND match_id IN (SELECT match_id FROM s.matches WHERE league_code = ?)""", (code,))}
    other = {r[0] for r in conn.execute("""SELECT DISTINCT player_id FROM s.lineup_players
        WHERE match_id IN (SELECT match_id FROM s.matches WHERE league_code != ?)""", (code,))}
    in_src = {r[0] for r in conn.execute("SELECT player_id FROM s.player_info")}
    real_lp = {r[0] for r in conn.execute("SELECT DISTINCT player_id FROM main.lineup_players")}
    # ملف بالمصدر لا يظهر بتشكيلات أي دوري آخر بالمصدر ولا بالحقيقية = جُلب مع هذا الدوري
    pi = (in_src & lp) | (in_src - other - real_lp - lp)
    have = {r[0] for r in conn.execute("SELECT player_id FROM main.player_info")}
    src["player_info"] = len(pi)
    return src, pi, pi & have, lp


# ---------------------------------------------------------------- الكتابة
def import_rows(conn, code, pi_ids):
    q = "(SELECT match_id FROM s.matches WHERE league_code = ?)"
    n = {}
    n["matches"] = conn.execute("INSERT INTO main.matches SELECT * FROM s.matches WHERE league_code = ?",
                                (code,)).rowcount
    n["goals"] = conn.execute(f"""INSERT INTO main.goals (match_id, team_id, minute, player_en, player_ar, detail)
        SELECT match_id, team_id, minute, player_en, player_ar, detail FROM s.goals
        WHERE match_id IN {q} ORDER BY id""", (code,)).rowcount
    n["events"] = conn.execute(f"""INSERT INTO main.events
        (match_id, team_id, minute, type, detail, player_en, player_ar, assist_en)
        SELECT match_id, team_id, minute, type, detail, player_en, player_ar, assist_en FROM s.events
        WHERE match_id IN {q} ORDER BY id""", (code,)).rowcount
    n["lineups"] = conn.execute(f"INSERT INTO main.lineups SELECT * FROM s.lineups WHERE match_id IN {q}",
                                (code,)).rowcount
    n["lineup_players"] = conn.execute(f"""INSERT INTO main.lineup_players SELECT * FROM s.lineup_players
        WHERE match_id IN {q}""", (code,)).rowcount
    conn.execute("CREATE TEMP TABLE _pi (player_id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO _pi VALUES (?)", [(p,) for p in sorted(pi_ids)])
    n["player_info"] = conn.execute("""INSERT OR IGNORE INTO main.player_info
        SELECT * FROM s.player_info WHERE player_id IN (SELECT player_id FROM _pi)""").rowcount
    conn.execute("DROP TABLE _pi")
    return n


def post_checks(conn, code, src, n, pi_skip):
    """فحوص داخل المعاملة — يرجّع قائمة أخطاء (فارغة = نجح) وقائمة تحذيرات."""
    errs, warns = [], []
    for t in ("matches", "goals", "events", "lineups", "lineup_players"):
        if n[t] != src[t]:
            errs.append(f"{t}: كُتب {n[t]} والمصدر {src[t]}")
    if n["player_info"] != src["player_info"] - len(pi_skip):
        errs.append(f"player_info: كُتب {n['player_info']} والمتوقَّع {src['player_info'] - len(pi_skip)}")
    q = "(SELECT match_id FROM main.matches WHERE league_code = ?)"
    bad = conn.execute(f"""SELECT m.match_id, m.home_goals + m.away_goals,
        (SELECT COUNT(*) FROM main.goals g WHERE g.match_id = m.match_id)
        FROM main.matches m WHERE m.match_id IN {q}
          AND m.home_goals + m.away_goals != (SELECT COUNT(*) FROM main.goals g WHERE g.match_id = m.match_id)""",
                       (code,)).fetchall()
    if bad:
        warns.append(f"{len(bad)} مباراة عدد أهدافها ≠ النتيجة (أول 5: {bad[:5]})")
    e = conn.execute(f"SELECT COUNT(*) FROM main.goals WHERE match_id IN {q} AND (player_en IS NULL OR player_en = '')",
                     (code,)).fetchone()[0]
    if e:
        warns.append(f"{e} هدف بلا اسم لاعب (refresh_goal_names يعالجه لاحقاً)")
    st = conn.execute(f"SELECT status, COUNT(*) FROM main.matches WHERE match_id IN {q} GROUP BY status",
                      (code,)).fetchall()
    if any(s != "FT" for s, _ in st):
        warns.append(f"حالات غير FT: {st}")
    ok = conn.execute("PRAGMA quick_check").fetchone()[0]
    if ok != "ok":
        errs.append(f"quick_check: {ok}")
    return errs, warns


# ---------------------------------------------------------------- الأندية (CSV + sync_teams)
def club_rows(conn, code, csv_path):
    """صفوف teams_arabic.csv الجديدة. اسم مزوّد بلا ترجمة بـCLUBS = Abort."""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        have = {int(r["team_id"]) for r in rd if (r.get("team_id") or "").strip()}
    clubs = CLUBS[code]
    rows, missing = [], []
    for tid, name, city, logo in conn.execute("""SELECT team_id, name_en, city, logo FROM s.teams
            WHERE team_id IN (SELECT home_id FROM s.matches WHERE league_code = ?
                              UNION SELECT away_id FROM s.matches WHERE league_code = ?)
            ORDER BY name_en""", (code, code)):
        if tid in have:
            continue
        if name not in clubs:
            missing.append((tid, name))
            continue
        off, ar, short = clubs[name]
        rows.append({"league_code": code, "league_ar": LEAGUE_AR[code], "team_id": tid, "name_en": name,
                     "name_en_official": off, "name_ar": ar, "short_name_ar": short, "city": city or "",
                     "logo": logo or f"https://media.api-sports.io/football/teams/{tid}.png",
                     "logo_local": "", "logo_note": ""})
    if missing:
        raise Abort(f"أندية بلا اسم عربي بـCLUBS: {missing}")
    unused = set(clubs) - {r["name_en"] for r in rows} - {
        r[0] for r in conn.execute("SELECT name_en FROM main.teams WHERE league_code = ?", (code,))}
    if unused:
        raise Abort(f"أسماء بـCLUBS لا تطابق أي نادٍ بالمصدر: {sorted(unused)}")
    return fields, rows


def append_csv(path, fields, rows):
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        for r in rows:
            w.writerow(r)


def run_sync_teams(db_path, teams_csv):
    """sync_teams.py نفسه — بنسخة مؤقتة (check) نوجّهه لملفاتها، وبالحقيقي يُشغَّل كما هو."""
    if Path(db_path).resolve() == DB_FILE.resolve() and Path(teams_csv).resolve() == TEAMS_FILE.resolve():
        r = subprocess.run([sys.executable, str(BASE_DIR / "sync_teams.py")], cwd=str(BASE_DIR))
        if r.returncode:
            raise Abort("sync_teams.py فشل")
        return
    import sync_teams
    sync_teams.DB_FILE, sync_teams.TEAMS_FILE = Path(db_path), Path(teams_csv)
    sync_teams.main()


# ---------------------------------------------------------------- تثبيت الأسماء
def site_plan(db_path, pins_path, hist_path, record=False):
    """خطة صفحات اللاعبين كما يبنيها الموقع -> (names, urls).
    names = {pid: (display_en, slug)} لصفحات المعرّفات؛ urls = {slug: صاحبه} للصفحات **وروابط إعادة التوجيه** (stub → صاحب وجهته).
    record=True: يسجّل الصفحات والـstubs الحالية بسجلّ الروابط أولاً (كما يفعل make_players بالـCI) فيحجزها build_plan لأصحابها."""
    import player_pages as pp
    c = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    try:
        plan = pp.build_plan(c, pp.load_history(hist_path), pp.load_id_merges(), pp.load_pins(pins_path))
        if record:
            n = pp.update_history(plan, hist_path)
            print(f"  سجلّ الروابط: {n} مدخلاً جديداً/محدَّثاً ({hist_path})")
            plan = pp.build_plan(c, pp.load_history(hist_path), pp.load_id_merges(), pp.load_pins(pins_path))
    except ValueError as e:
        raise Abort(f"player_pages: {e}")
    finally:
        c.close()
    who = {p["slug"]: (p["kind"], p["pid"] if p["kind"] == "pid" else p["display_en"]) for p in plan["pages"]}
    urls = dict(who)
    urls.update({s: ("stub →",) + who.get(d, (d,)) for s, d in plan["stubs"].items()})
    return {p["pid"]: (p["display_en"], p["slug"]) for p in plan["pages"] if p["kind"] == "pid"}, urls


def lineup_name(conn, pid):
    """لاعب بلا صفحة (لم يسجّل): اسمه بالموقع = اسم التشكيلات؛ نفس قاعدة display() بـplayer_pages
    (الأكثر صفوفاً، ثم الأطول، ثم الأكبر أبجدياً) على القاعدة **قبل** الاستيراد."""
    use = conn.execute("""SELECT player_en, COUNT(*) FROM (
            SELECT player_en FROM main.lineup_players WHERE player_id = ? UNION ALL
            SELECT player_en FROM main.player_stats WHERE player_id = ?)
        WHERE player_en IS NOT NULL AND player_en != '' GROUP BY player_en""", (pid, pid)).fetchall()
    return max(use, key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0] if use else None


def pin_rows(conn, code, before, pins_path):
    import player_pages as pp
    old = pp.load_pins(pins_path)
    rows, notes, nopage = [], [], {}
    for pid in PIN_IDS[code]:
        if pid in old:
            notes.append(f"pin {pid} موجود أصلاً ({old[pid]!r}) — يبقى")
            continue
        if pid in before:
            name = before[pid][0]
        else:
            name = lineup_name(conn, pid)
            if not name:
                raise Abort(f"pin {pid}: لا صفحة ولا تشكيلات له بالقاعدة — لا اسم حالي لتثبيته")
            nopage[pid] = name
        rows.append({"player_id": pid, "name_en": name, "reason": PIN_REASON.format(code=code)})
    return rows, notes, nopage


# ---------------------------------------------------------------- تحذيرات الأسماء العربية
def arabic_gaps(conn, code):
    have = set()
    with open(PLAYERS_AR, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("player_ar") or "").strip():
                have.add((r.get("player_en") or "").strip())
    q = "(SELECT match_id FROM s.matches WHERE league_code = ?)"
    names = {r[0] for r in conn.execute(f"""SELECT player_en FROM s.goals WHERE match_id IN {q}
        UNION SELECT player_en FROM s.lineup_players WHERE match_id IN {q}""", (code, code)) if r[0]}
    scorers = {r[0] for r in conn.execute(f"SELECT DISTINCT player_en FROM s.goals WHERE match_id IN {q}",
                                          (code,)) if r[0]}
    coaches = conn.execute(f"""SELECT COUNT(DISTINCT coach_en) FROM s.lineups WHERE match_id IN {q}
        AND coach_en IS NOT NULL AND coach_en != ''""", (code,)).fetchone()[0]
    return len(names), len(names - have), len(scorers), len(scorers - have), coaches


# ---------------------------------------------------------------- القفل والنسخة الاحتياطية
def require_local_lock():
    import state_sync as ss
    meta = ss.get_store().get_meta()
    lk = ss.lock_info(meta)
    base = ss.read_local_base()
    if not lk or lk["holder"] != "local":
        raise Abort("لا قفل محلي — شغّل db_pull.py (بلا --no-lock) أولاً")
    if not base or base.get("seq") != meta["seq"]:
        raise Abort(f"القاعدة المحلية ليست آخر نسخة (seq {meta['seq']}) — اسحب من جديد")
    if ss.content_sha(ss.BASE) != base["content_sha"]:
        raise Abort("القاعدة المحلية فيها تعديلات غير مرفوعة")
    print(f"  🔒 قفل محلي حتى {lk['expires_at']} — seq {meta['seq']}")


def backup(db_path, code):
    from config import load_env
    raw = os.environ.get("DB_BACKUP_DIR") or load_env().get("DB_BACKUP_DIR", "")
    if not raw:
        raise Abort("DB_BACKUP_DIR غير مضبوط — لا كتابة بلا نسخة احتياطية")
    d = Path(os.path.expandvars(raw))
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"football-before-{code}-import-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(db_path, dst)
    print(f"  💾 نسخة احتياطية: {dst}")
    return dst


# ---------------------------------------------------------------- التشغيل
def run(code, src, db_path, teams_csv, pins_csv, hist_path, real):
    print(f"\n{'=' * 62}\n  استيراد {code} من {src}\n  الهدف: {db_path}\n{'=' * 62}")
    before, urls_before = site_plan(db_path, pins_csv, hist_path, record=True)

    conn = sqlite3.connect(Path(db_path).as_uri(), uri=True, isolation_level=None)
    conn.execute("ATTACH DATABASE ? AS s", (Path(src).as_uri() + "?mode=ro",))
    src_n, pi_ids, pi_skip, lp_ids = preflight(conn, code)
    fields, new_clubs = club_rows(conn, code, teams_csv)
    new_pins, pin_notes, pin_nopage = pin_rows(conn, code, before, pins_csv)
    n_names, n_names_noar, n_sc, n_sc_noar, n_coaches = arabic_gaps(conn, code)
    shared = conn.execute(f"""SELECT COUNT(DISTINCT player_id) FROM main.lineup_players
        WHERE player_id IN ({','.join(map(str, lp_ids)) or 0})""").fetchone()[0]

    conn.execute("BEGIN")
    n = import_rows(conn, code, pi_ids)
    errs, warns = post_checks(conn, code, src_n, n, pi_skip)
    if errs:
        conn.rollback()
        conn.close()
        raise Abort("فحوص ما بعد الاستيراد فشلت (rollback):\n      " + "\n      ".join(errs))
    conn.commit()
    conn.close()

    append_csv(teams_csv, fields, new_clubs)
    run_sync_teams(db_path, teams_csv)
    append_csv(pins_csv, ["player_id", "name_en", "reason"], new_pins)

    # ---- أثر الاستيراد على صفحات اللاعبين: بالـpins الجديدة (المطلوب) وبدونها (للمقارنة)
    after, urls_after = site_plan(db_path, pins_csv, hist_path)
    # كل رابط قائم (صفحة أو إعادة توجيه) يبقى لنفس اللاعب
    url_changed = [(s, b, urls_after.get(s)) for s, b in sorted(urls_before.items()) if urls_after.get(s) != b]
    # صاحب صفحة: الاسم والـslug كما هما. بلا صفحة: إن صارت له صفحة (هدف بالدوري الجديد) فاسمها = المثبَّت
    pin_fail = [(p, before[p], after.get(p)) for p in PIN_IDS[code] if p in before and after.get(p) != before[p]]
    pin_fail += [(p, ("بلا صفحة", pin_nopage[p]), after[p]) for p in pin_nopage
                 if p in after and after[p][0] != pin_nopage[p]]
    pin_newpage = [(p, after[p]) for p in pin_nopage if p in after]
    changed = [(p, before[p], after.get(p)) for p in before if p not in PIN_IDS[code] and after.get(p) != before[p]]
    new_pages = len(set(after) - set(before))

    t = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    orphan = t.execute("""SELECT COUNT(*) FROM matches WHERE league_code = ? AND
        (home_id NOT IN (SELECT team_id FROM teams) OR away_id NOT IN (SELECT team_id FROM teams))""",
                       (code,)).fetchone()[0]
    nteams = t.execute("SELECT COUNT(*) FROM teams WHERE league_code = ? AND short_name_ar != ''",
                       (code,)).fetchone()[0]
    seasons = t.execute("SELECT season, COUNT(*) FROM matches WHERE league_code = ? GROUP BY season",
                        (code,)).fetchall()
    t.close()

    print("\n  الصفوف المكتوبة (المصدر → المكتوب):")
    for k in ("matches", "goals", "events", "lineups", "lineup_players"):
        print(f"      {k:<16}: {src_n[k]:>6} → {n[k]:>6}")
    print(f"      {'player_info':<16}: {src_n['player_info']:>6} → {n['player_info']:>6}"
          f"  (متخطّى لوجوده: {len(pi_skip)})")
    print(f"      المواسم         : {seasons}")
    print(f"      الأندية         : {len(new_clubs)} صفاً بـteams_arabic.csv → {nteams} بجدول teams"
          f" | مباريات بنادٍ مفقود: {orphan}")
    print(f"      الـpins         : {len(new_pins)} جديداً" + (f" | {'; '.join(pin_notes)}" if pin_notes else ""))
    for r in new_pins:
        tag = "اسم التشكيلات (بلا صفحة)" if r["player_id"] in pin_nopage else "اسم الصفحة الحالية"
        print(f"          {r['player_id']:>7}  {r['name_en']:<24} ← {tag}")

    print("\n  صفحات اللاعبين:")
    print(f"      لاعبو {code} الموجودون أصلاً بالموقع: {shared} | صفحات معرّف جديدة: {new_pages}")
    print(f"      الـ{len(PIN_IDS[code])} المثبَّتون — اسم/slug تغيّر: {len(pin_fail)}")
    for p, b, a in pin_fail:
        print(f"          ❌ {p}: {b} → {a}")
    for p, a in pin_newpage:
        print(f"          ℹ️ {p}: صفحة جديدة بعد الاستيراد → {a[0]} /{a[1]}")
    print(f"      صفحات أخرى قائمة تغيّر اسمها/slug: {len(changed)}")
    for p, b, a in changed[:30]:
        print(f"          ⚠️ {p}: {b} → {a}")
    n_stub = sum(1 for v in urls_before.values() if v[0] == "stub →")
    print(f"      روابط قائمة ({len(urls_before) - n_stub} صفحة + {n_stub} إعادة توجيه) تغيّر صاحبها: {len(url_changed)}")
    for s, b, a in url_changed[:30]:
        print(f"          ⚠️ /{s}: {b} → {a}")

    print("\n  تحذيرات:")
    for w in warns:
        print(f"      ⚠️ {w}")
    print(f"      ⚠️ أسماء لاعبين بلا عربي بـplayers_ar.csv: {n_names_noar}/{n_names}"
          f" (منهم هدّافون: {n_sc_noar}/{n_sc}) — تظهر بالإنجليزي حتى تُترجَم")
    print(f"      ⚠️ مدرّبون بلا coach_ar: {n_coaches} (العمود فارغ بالمصدر)")
    if pin_fail or changed or url_changed:
        raise Abort("أسماء صفحات أو روابط قائمة تغيّرت — راجع أعلاه" + (" (القاعدة الحقيقية: استرجع النسخة الاحتياطية)"
                                                               if real else ""))


def main():
    src = arg("--src")
    vals = {arg("--src"), arg("--db")}
    codes = [a.upper() for a in sys.argv[1:] if not a.startswith("--") and a not in vals]
    code = codes[0] if codes else "TUN"
    check, apply = "--check" in sys.argv, "--apply" in sys.argv
    if code not in ENABLED_LEAGUES:
        raise SystemExit(f"❌ {code} خارج ENABLED_LEAGUES {sorted(ENABLED_LEAGUES)}")
    if not src or not Path(src).exists():
        raise SystemExit("❌ --src <قاعدة الاختبار> مطلوب")
    if check == apply:
        raise SystemExit("❌ اختر واحداً: --check أو --apply")
    try:
        if check:
            db = Path(arg("--db") or DB_FILE)
            work = Path(tempfile.mkdtemp(prefix=f"import_{code}_check_"))
            for s, d in ((db, "football.db"), (TEAMS_FILE, "teams_arabic.csv"), (PINS_FILE, "player_name_pins.csv"),
                         (HISTORY_FILE, "player_url_history.json")):
                shutil.copy2(s, work / d)
            print(f"  [وضع الفحص] نسخة عمل: {work} — {db} لا يُكتب")
            run(code, src, work / "football.db", work / "teams_arabic.csv", work / "player_name_pins.csv",
                work / "player_url_history.json", False)
            print(f"\n  ✅ الفحص نجح — نسخة العمل بعد الاستيراد: {work}")
        else:
            if arg("--db") and Path(arg("--db")).resolve() != DB_FILE.resolve():
                raise SystemExit("❌ --apply على football.db الحقيقية فقط")
            require_local_lock()
            backup(DB_FILE, code)
            run(code, src, DB_FILE, TEAMS_FILE, PINS_FILE, HISTORY_FILE, True)
            print("\n  ✅ تم. التالي: python db_push.py ثم دفع الكود")
    except Abort as e:
        raise SystemExit(f"\n  ❌ {e}")


if __name__ == "__main__":
    main()
