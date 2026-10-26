#!/usr/bin/env python3
"""
جدولة إعادة المحاولة لإحصائيات المباراة وإحصائيات اللاعبين (13 أكتوبر 2026)
=============================================================================
المشكلة: `pending()` بـfetch_stats.py وfetch_player_stats.py = «مباراة منتهية بلا صفوف بالجدول». ردّ المزوّد الفارغ لا يُخزَّن شيئاً فتبقى المباراة
«ناقصة» وتُعاد **بكل دورة deploy-site (48 باليوم) إلى الأبد**: ≈ 74 طلباً فارغاً بكل دورة ≈ 2,300–2,400 طلب/يوم من حصة 7,500 (قياس 13 أكتوبر).

الحل: جدول `stats_attempts (match_id, kind, tries, last_ts)` يسجّل **كل محاولة فارغة** لكل (مباراة، نوع: stats | pstats). جدول المحاولات بعد نهاية المباراة
(FT ≈ الانطلاق + ساعتان): محاولة أولى فور الانتهاء، ثم +1 س، +6 س، +24 س، +72 س، ثم **توقف نهائي** (5 محاولات كحدّ أقصى)، وبين أي محاولتين ساعة على الأقل (MIN_GAP_H).
  • الردّ الفارغ وحده يُسجَّل؛ **الفشل** (HTTP/شبكة) لا يُسجَّل فيُعاد بالدورة التالية كما كان.
  • مباراة انتهت قبل أكثر من 72 س بلا أي سجل محاولات = استُنفدت فعلياً (كانت تُعاد مئات المرات دون نتيجة) فلا تُطلب.
  • **MAR player-stats مُتخطّاة كلياً** (المزوّد لا يوفّرها لأي موسم، README بند 14).
  • `--no-backoff` على الأمر يتجاوز الكل (تمريرة يدوية كاملة).
صفر طلبات هنا — طبقة فرز وتسجيل فقط.
"""
import time
from datetime import datetime, timezone

SCHEDULE_HOURS = [0, 1, 6, 24, 72]      # المحاولة رقم n (n = المحاولات الفارغة حتى الآن) مسموحة بعد FT + SCHEDULE_HOURS[n] ساعة
FT_AFTER_KICKOFF_H = 2.0                # FT تقريبي = الانطلاق + ساعتان (matches.date = وقت الانطلاق UTC)
MIN_GAP_H = 1.0                         # حدّ أدنى بين محاولتين متتاليتين (لمباراة متأخرة لحقت كل مواعيدها: تتوزّع محاولاتها بدل أن تُستهلك بدورات متلاصقة)
SKIP_KINDS = {("pstats", "MAR")}        # المزوّد لا يوفّر إحصائيات لاعبي الدوري المغربي لأي موسم
# التونسي والجزائري (24 أكتوبر 2026، عيّنة 5 مباريات لكل منهما): بلا إحصائيات مباراة ولا لاعبين — لا إعادة لها. الكويتي احتياطاً (ليس بـDETAILED)
SKIP_KINDS |= {(k, c) for k in ("stats", "pstats") for c in ("TUN", "ALG", "KUW")}


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS stats_attempts (
        match_id INTEGER NOT NULL, kind TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL,
        PRIMARY KEY (match_id, kind))""")


def _ft_ts(date_str):
    s = str(date_str or "")
    try:
        t = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            t = datetime.strptime(s[:10] + " 12:00", "%Y-%m-%d %H:%M")
        except ValueError:
            return None
    return t.replace(tzinfo=timezone.utc).timestamp() + FT_AFTER_KICKOFF_H * 3600


def filter_due(conn, kind, rows, now=None):
    """rows: صفوف pending() (match_id, league_code, date…). يرجع (المستحَقّ بترتيبه، {سبب: عدد} للمتخطّى)."""
    now = time.time() if now is None else now
    try:
        tries = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT match_id, tries, last_ts FROM stats_attempts WHERE kind = ?", (kind,))}
    except Exception:
        tries = {}
    due, skipped = [], {"league_skip": 0, "exhausted": 0, "not_yet": 0}
    last = len(SCHEDULE_HOURS)
    for r in rows:
        if (kind, r["league_code"]) in SKIP_KINDS:
            skipped["league_skip"] += 1
            continue
        ft = _ft_ts(r["date"])
        if ft is None:
            due.append(r)   # تاريخ غير مفهوم: لا نخاطر بحجب مباراة
            continue
        rec = tries.get(r["match_id"])
        n = None if rec is None else rec[0]
        if n is None:
            # بلا سجل: حديثة (لم تمضِ عليها الجدولة كلها) ← مستحقة الآن؛ أقدم ← مستنفدة فعلياً
            if now - ft > SCHEDULE_HOURS[-1] * 3600:
                skipped["exhausted"] += 1
            else:
                due.append(r)   # أول محاولة فور ظهور النتيجة بالقاعدة (لا ننتظر تقدير FT)
            continue
        if n >= last:
            skipped["exhausted"] += 1
        elif now >= ft + SCHEDULE_HOURS[n] * 3600 and now >= rec[1] + MIN_GAP_H * 3600:
            due.append(r)
        else:
            skipped["not_yet"] += 1
    return due, skipped


def record_empty(conn, kind, match_id, now=None):
    ensure_table(conn)
    conn.execute("INSERT INTO stats_attempts (match_id, kind, tries, last_ts) VALUES (?, ?, 1, ?) "
                 "ON CONFLICT(match_id, kind) DO UPDATE SET tries = tries + 1, last_ts = excluded.last_ts",
                 (match_id, kind, int(time.time() if now is None else now)))
    conn.commit()
