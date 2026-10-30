#!/usr/bin/env python3
"""
فهرس البحث — ملف واحد خارجي
==============================
بيولّد `search_data.js` بجذر الموقع: أندية + لاعبون، بالعربي
والإنجليزي، للبحث الفوري داخل المتصفح.

⚠️ **لماذا ملف خارجي لا حقن في كل صفحة:**
   الفهرس ~80 كيلوبايت. ضربه في 6,444 صفحة = ~500 ميغابايت.
   الملف الخارجي يُحمَّل **مرة واحدة** ويُخزَّن في كاش المتصفح.

⚠️ **لماذا `.js` لا `.json`:**
   الاختبار المحلي يفتح الصفحات بـ`file://`، و`fetch()` ممنوع
   هناك بسبب CORS. بينما `<script src>` يعمل في الحالتين.
   الملف يعرّف متغيّراً عاماً: `window.FBSEARCH`.

⚠️ **البنية مصفوفات لا كائنات** — توفّر ~40% من الحجم:
   نادٍ  : [id, ar, en, league]
   لاعب : [ar, en, club_id, slug, player_id|0]

⚠️ **اسم النادي لا يتكرّر لكل لاعب — 3 سبتمبر.** كان كل صفّ
   لاعب يحمل نص اسم ناديه (`club_ar`/`club_en`) كاملاً، مكرَّراً
   لكل هدّاف بنفس النادي. بعد توسّع الفهرس لـ5 دوريات (315
   ك.ب، فوق الحد الداخلي 300)، صار اللاعب يحمل `club_id` فقط
   والواجهة (`search_view.py`) تبحث الاسم بمصفوفة الأندية —
   وفّر ~100 ك.ب بلا أي فقدان وظيفة.

⚠️ ضغط اللاعب يوديه **لصفحة ناديه** — صفحة اللاعب غير موجودة
   بعد. لذلك اسم النادي معروض بجانبه في النتائج.

⚠️ (30 أكتوبر 2026، plan_search_size.md) **ملفّان بـ/assets بدل search_data.js الواحد** (430 ك.ب خام):
   assets/search_top.js   window.FBSEARCH = {c: كل الأندية، p: أول TOP_N لاعب (الأكثر أهدافاً)، n: عدد كل اللاعبين}
                          — يُحمَّل فوراً بصفحة البحث (وورقة «إضافة فرق» بالمتابَعة: الأندية منه وحده)
   assets/search_full.js  window.FBSEARCH_P = كل اللاعبين — يُحمَّل كسولاً (أول كتابة أو بعد التحميل بقليل)
   الرابط بـ?v=<hash> (asset_v) فيخدمه sw.js من المخزون أولاً كبقية /assets (زيارة ثانية = صفر بايت).
   **حقل الرابط (p[3])**: 1 = يُشتق بـslug(الاسم الإنجليزي) بالمتصفح (SLUG_JS بـmake_search_page، مطابق لـplayer_slug.slug —
   test_search_size.py يقارن كل الصفوف)، "" = بلا صفحة، نص = رابط يختلف عن المشتق. صفوف collect() بالصيغة القديمة حرفياً
   (نتائج البحث مطابقة للقديم — نفس الصفوف بنفس الترتيب).

صفر طلبات API.

التشغيل:
    python make_search.py
"""

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from config import DB_FILE, TEAMS_FILE
from player_slug import slug

BASE = DB_FILE.parent
OUT = BASE / "search_data.js"          # القديم — لم يعد يُولَّد (generated_paths: removed)
OUT_TOP = BASE / "assets" / "search_top.js"
OUT_FULL = BASE / "assets" / "search_full.js"
TOP_N = 300   # ~12 ك.ب مضغوطاً مع الأندية (plan_search_size.md: الفهرس الفوري)


def asset_v(path):
    """?v= لملف بـ/assets — نفس صيغة make_assets (sha1 للبايتات، أول 8)؛ "" إن لم يوجد"""
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]
    except OSError:
        return ""


def js_slug(name):
    """نسخة بايثون من SLUG_JS (make_search_page) حرفياً: كل علامة يونيكود (فئة M*) تُحذف — player_slug.slug يحذف ذات صنف
    التركيب فقط، فقد يختلفان بحرف نادر؛ لذلك لا يُعلَّم رابط بـ1 إلا إن طابقه الاثنان"""
    import unicodedata
    s = (name or "").strip()
    if not s:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.category(c).startswith("M"))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "player"


def encode_player(p):
    """[ar, en, club, slug, pid] → نفس الصف، والرابط 1 إن طابق slug(en) وjs_slug(en) معاً (يُشتق بالمتصفح)"""
    s = p[3]
    return [p[0], p[1], p[2], 1 if (s and s == slug(p[1]) == js_slug(p[1])) else s, p[4]]


def clean(v):
    return (v or "").strip()


def load_teams():
    """نفس منطق make_clubs — الأسماء من CSV"""
    teams = {}
    if not TEAMS_FILE.exists():
        return teams
    with open(TEAMS_FILE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tid = clean(r.get("team_id"))
            if not tid:
                continue
            teams[int(tid)] = {
                "ar": clean(r.get("short_name_ar")),
                "full_ar": clean(r.get("name_ar")),
                "en": (clean(r.get("name_en_official"))
                       or clean(r.get("name_en"))),
                "league": clean(r.get("league_code")),
                "logo": clean(r.get("logo")),
                "logo_local": clean(r.get("logo_local")),
            }
    return teams


def collect():
    """(clubs, players) بالصيغة القديمة حرفياً (صفوف search_data.js قبل 30 أكتوبر 2026) — مصدر الملفّين والاختبار"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    teams = load_teams()

    # ── الأندية التي لها صفحة فعلاً ───────────────────
    have_page = set()
    for d in ("clubs", "en/clubs"):
        p = BASE / d
        if p.exists():
            for f in p.iterdir():
                if f.suffix == ".html":
                    try:
                        have_page.add(int(f.stem))
                    except ValueError:
                        pass

    # شعبية النادي لترتيب نتائج البحث بنفس درجة المطابقة (27 أكتوبر 2026): عدد مبارياته المنتهية — حقل سادس يُلحَق (القرّاء الحاليون
    # يقرؤون r[0..4] فقط: صفحة البحث وورقة «+» بالمتابَعة)
    played = {}
    for tid, n in conn.execute("SELECT team, COUNT(*) FROM (SELECT home_id AS team FROM matches WHERE home_goals IS NOT NULL "
                               "UNION ALL SELECT away_id FROM matches WHERE home_goals IS NOT NULL) GROUP BY team"):
        played[tid] = n
    clubs = []
    for tid, t in sorted(teams.items()):
        if tid not in have_page:
            continue
        ar = t["ar"] or t["full_ar"]
        en = t["en"]
        if not (ar or en):
            continue
        logo = (t.get("logo_local") or "").strip() or (t.get("logo") or "").strip()
        clubs.append([tid, ar, en, t["league"], logo, played.get(tid, 0)])

    # ── اللاعبون — من جدول الأهداف ────────────────────
    # ⚠️ صفحة لكل player_id (player_pages.py): صيغ الاسم المدموجة بصفحة واحدة تُعرض مرة واحدة بنفس الاسم والنادي
    from player_pages import get_plan
    plan = get_plan()
    pg_by_slug = {pg["slug"]: pg for pg in plan["pages"]}
    players = []
    seen = set()
    q = """
        SELECT g.player_en, g.player_ar, g.team_id,
               COUNT(g.player_en) AS n
        FROM goals g
        WHERE g.player_en IS NOT NULL AND g.player_en != ''
        GROUP BY g.player_en, g.team_id
        ORDER BY n DESC
    """
    for r in conn.execute(q):
        en = clean(r["player_en"])
        ar = clean(r["player_ar"])
        tid = r["team_id"]
        slg = (plan["nt_slug"].get((r["player_en"], tid))
               or plan["name_slug"].get(r["player_en"]) or "")

        key = (slg or en, tid)
        if key in seen:
            continue
        seen.add(key)

        club = teams.get(tid)
        if not club:
            continue

        pg = pg_by_slug.get(slg)
        if pg and pg["kind"] == "pid":
            en = clean(pg["display_en"])
            ar = clean(pg["display_ar"]) or ar
        players.append([ar, en, tid, slg])

    # معرّف المزوّد للصورة (اسم ← معرّف واحد فقط، كجسر make_players.gather)
    pid_of = {pg["slug"]: (pg["stats_pid"] or 0) for pg in plan["pages"]}
    for p in players:
        p.append(pid_of.get(p[3], 0))

    conn.close()

        # الرابط يُقرأ من الملفات الفعلية لا يُعاد حسابه —
    # أي فرق في المنطق عن make_players.py ينتج رابطاً مكسوراً
    player_pages = set()
    ppl_dir = BASE / "players"
    if ppl_dir.exists():
        player_pages = {f.stem for f in ppl_dir.glob("*.html")}

    for p in players:
        p[3] = p[3] if p[3] in player_pages else ""
    return clubs, players


def main():
    if not DB_FILE.exists():
        print("ما لقيت football.db")
        return
    clubs, players = collect()
    enc = [encode_player(p) for p in players]

    def dump(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))

    head = "/* فهرس البحث — مولّد بـmake_search.py. لا تعدّله يدوياً. */\n"
    OUT_TOP.parent.mkdir(exist_ok=True)
    OUT_TOP.write_text(head + "window.FBSEARCH=" + dump({"c": clubs, "p": enc[:TOP_N], "n": len(enc)}) + ";\n",
                       encoding="utf-8")
    OUT_FULL.write_text(head + "window.FBSEARCH_P=" + dump(enc) + ";\n", encoding="utf-8")
    if OUT.exists():
        OUT.unlink()   # الملف القديم الواحد — لا يُنشر بعد الآن
    kb = OUT_FULL.stat().st_size / 1024

    print(f"\n{'=' * 55}")
    print(f"  assets/search_top.js — {OUT_TOP.stat().st_size / 1024:.0f} ك.ب (الأندية + أول {min(TOP_N, len(enc))} لاعب)")
    print(f"  assets/search_full.js — {kb:.0f} كيلوبايت")
    print(f"{'=' * 55}")
    print(f"  أندية  : {len(clubs)}")
    print(f"  لاعبون : {len(players)}")

    ar_n = sum(1 for p in players if p[0])
    print(f"  منهم بأسماء عربية: {ar_n} "
          f"({ar_n / len(players) * 100:.0f}%)" if players else "")

    if kb > 400:   # الملف الكامل الكسول (30 أكتوبر 2026: كان 300 للملف الواحد القديم)
        print("\n  ⚠️ الحجم كبير — راجع ما يُدرَج بالفهرس")

    print()


if __name__ == "__main__":
    main()
