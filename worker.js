/**
 * صافرة — النتائج المباشرة
 * ==========================
 * يسحب من API-Football كل دقيقة ويخزّن النتيجة في KV،
 * ويقدّمها للمتصفح بنفس بنية live.json تماماً.
 *
 * ⚠️ البنية: {"t":..,"m":{..}} + `f` اختياري (النتائج النهائية الأخيرة).
 *    `live_view.py` يقرأ m وf؛ حذف m أو تغيير شكله يكسره.
 *
 * ⚠️ الحصة: الجدولة كل دقيقة = 1,440 طلباً يومياً من 7,500
 *    (حصة المزوّد api-sports.io). ولتقليلها: إن كان آخر سحب
 *    بلا مباريات جارية، نتباطأ إلى مرة كل 5 دقائق.
 *
 * ⚠️ **حصة KV منفصلة عن حصة المزوّد — درس 3 سبتمبر.** النسخة
 *    القديمة كانت تكتب على KV **كل دقيقة حتى بالخمول التام**
 *    (عداد "skip" بمفتاح منفصل يُكتب لينقص بواحد) — ~1,440
 *    كتابة/يوم مضمونة بلا أي مباراة، وهذا استهلك 90% من حصة
 *    Cloudflare KV المجانية بلا أي فائدة فعلية (كانت مصمَّمة
 *    لتقليل حصة *المزوّد* لا حصة *KV نفسها*). الحل: لا مفتاح
 *    "skip" منفصل — الوقت يُحسب من طابع مفتاح `live` نفسه
 *    (`t`)، فالخمول أصبح **قراءة بلا كتابة إطلاقاً**.
 *
 * ⚠️ **النتيجة النهائية بعد صافرة النهاية (4 أكتوبر 2026):** المباراة التي
 *    تختفي من ردّ `live=` (انتهت) كانت تعود بطاقتها لموعدها حتى يعيد
 *    deploy-site توليد الصفحة (3-6 ساعات). الآن: عند اختفاء مباراة كانت
 *    بـ`prev.m` نطلب **طلباً واحداً** `fixtures?ids=<حتى 20>` لنحصل على
 *    حالتها ونتيجتها النهائية الفعلية (لا آخر ما رأيناه بالسحب السابق —
 *    هدف الدقيقة الأخيرة قد يقع بين سحبين)، ونخزّنها بمفتاح إضافي `f`:
 *    {id: {h, a, s, ft: ts}}. الشكل {t, m} لم يتغيّر و`f` إضافة فقط، فالموقع
 *    القديم يتجاهله. `f` يُحتفظ به 12 ساعة ويُنظَّف عند أول كتابة بعدها.
 *    لا كتابات KV جديدة: الكتابة بنفس الشرط القديم (سحب بعد نافذة الخمول أو
 *    سحب أثناء مباريات)، و`wasIdle` يعتمد على `m` وحدها كما كان.
 *    إن فشل طلب `ids` أو لم يرجع حالة نهائية بعد، لا نكتب (تبقى النسخة السابقة
 *    ونعيد المحاولة بعد دقيقة) حتى GIVEUP_SECS ثم نكتب بدونها.
 *
 * الربط المطلوب:
 *    Secret   : API_KEY
 *    KV       : LIVE_KV
 *    Cron     : * * * * *
 */

const API = "https://v3.football.api-sports.io";
// الأردني · العراقي · السعودي · المصري · الإماراتي · القطري · المغربي (من config.py)
const LEAGUES = "387-542-307-233-301-305-200";
const LIVE_STATUS = ["1H", "2H", "HT", "ET", "BT", "P", "LIVE"];
// حالات تُسجَّل بـ`f` حين تختفي المباراة من الردّ الحيّ: نهائية ثم غير مكتملة
const FINAL_STATUS = ["FT", "AET", "PEN"];
const STOP_STATUS = ["SUSP", "ABD", "PST", "INT"];
const KEY = "live";
const IDLE_SKIP_SECS = 5 * 60;   // ثوانٍ نتخطّاها حين لا شيء جارٍ
const F_TTL_SECS = 12 * 3600;    // مدة بقاء f
const IDS_MAX = 20;              // حدّ المزوّد لـ fixtures?ids
const GIVEUP_SECS = 10 * 60;     // بعدها نكتب بلا f بدل إعادة المحاولة

async function pull(env, diag, prev) {
  // ⚠️ الفشل الصامت أخطر نمط (درس 1): كل خروج مبكر
  //    يسجّل سببه في diag بدل أن يرجع null مجرّداً.
  if (!env.API_KEY) {
    if (diag) diag.why = "API_KEY غير موجود — السرّ لم يُحفظ";
    return null;
  }

  const url = `${API}/fixtures?live=${LEAGUES}`;
  const r = await fetch(url, {
    headers: { "x-apisports-key": env.API_KEY },
  });
  if (!r.ok) {
    if (diag) diag.why = `المزوّد رفض الطلب: HTTP ${r.status}`;
    return null;
  }

  const data = await r.json();
  // المزوّد يرجع 200 مع أخطاء داخل errors
  if (data.errors && Object.keys(data.errors).length) {
    if (diag) diag.why = "خطأ من المزوّد: " + JSON.stringify(data.errors);
    return null;
  }

  const m = {};
  for (const f of data.response || []) {
    const fx = f.fixture || {};
    const st = fx.status || {};
    if (!LIVE_STATUS.includes(st.short)) continue;
    if (fx.id == null) continue;
    const gl = f.goals || {};
    const tm = f.teams || {};
    m[String(fx.id)] = {
      h: gl.home,
      a: gl.away,
      e: st.elapsed,
      s: st.short,
      // إضافات (دفعة 1 تنبيهات الأهداف): معرّفا الفريقين والدوري — حقول جديدة فقط
      th: (tm.home || {}).id,
      ta: (tm.away || {}).id,
      lg: (f.league || {}).id,
    };
  }
  const now = Math.floor(Date.now() / 1000);

  // ── f: نتائج المباريات التي انتهت للتو ──
  // ⚠️ الاحتفاظ بالقديم 12 ساعة؛ ويُحذف أي معرّف عاد ليكون جارياً.
  const f = {};
  for (const [id, e] of Object.entries((prev && prev.f) || {})) {
    if (e && now - e.ft < F_TTL_SECS && !(id in m)) f[id] = e;
  }

  const gone = Object.keys((prev && prev.m) || {}).filter((id) => !(id in m));
  if (gone.length) {
    const got = await finals(env, gone.slice(0, IDS_MAX), diag);
    const unresolved = got === null
      ? gone.slice(0, IDS_MAX)
      : gone.slice(0, IDS_MAX).filter((id) => !(id in got));
    // لم نحصل على الحالة النهائية بعد: لا نكتب، فتبقى المباراة بـprev.m
    // ونعيد المحاولة — حتى GIVEUP_SECS من آخر كتابة ناجحة.
    if (unresolved.length && prev && now - prev.t < GIVEUP_SECS) {
      if (diag) diag.why = "حالة نهائية غير جاهزة للمعرّفات: " + unresolved.join(",");
      return null;
    }
    for (const [id, e] of Object.entries(got || {})) f[id] = { ...e, ft: now };
  }

  // ⚠️ بعد كل مخارج null أعلاه: لو أُعيدت المحاولة (prev لم يتحدّث) لا يتكرّر السجل.
  logGoalEvents(prev && prev.m, m);

  const out = { t: now, m };
  if (Object.keys(f).length) out.f = f;   // {t, m} كما هي؛ f إضافة فقط
  return out;
}

// ── كشف الأهداف (تسجيل فقط، بلا إرسال): مقارنة نتيجة كل مباراة بالسحب السابق ──
// سطر JSON واحد لكل حدث:
//   {"type":"goal"|"goal_cancelled","fixture","th","ta","h","a","prev_h","prev_a","minute","league"}
// ⚠️ مباراة لا وجود لها بـprev: لا حدث (إعادة تشغيل/ظهور وسط المباراة ≠ هدف).
// ⚠️ لا طلبات API ولا كتابات KV هنا — console.log فقط.
function logGoalEvents(prevM, m) {
  if (!prevM) return;
  for (const [id, cur] of Object.entries(m)) {
    const old = prevM[id];
    if (!old) continue;
    const ph = old.h ?? 0, pa = old.a ?? 0;
    const h = cur.h ?? 0, a = cur.a ?? 0;
    const base = {
      fixture: Number(id), th: cur.th, ta: cur.ta, h, a,
      prev_h: ph, prev_a: pa, minute: cur.e, league: cur.lg,
    };
    if (h < ph || a < pa) console.log(JSON.stringify({ type: "goal_cancelled", ...base }));
    if (h > ph || a > pa) console.log(JSON.stringify({ type: "goal", ...base }));
  }
}

// طلب واحد: fixtures?ids=a-b-c → {id: {h, a, s}} للحالات النهائية/غير المكتملة
// فقط. يرجع null عند فشل الطلب.
async function finals(env, ids, diag) {
  const r = await fetch(`${API}/fixtures?ids=${ids.join("-")}`, {
    headers: { "x-apisports-key": env.API_KEY },
  });
  if (!r.ok) {
    if (diag) diag.why = `طلب ids رُفض: HTTP ${r.status}`;
    return null;
  }
  const data = await r.json();
  if (data.errors && Object.keys(data.errors).length) {
    if (diag) diag.why = "خطأ ids من المزوّد: " + JSON.stringify(data.errors);
    return null;
  }
  const got = {};
  for (const x of data.response || []) {
    const fx = x.fixture || {};
    const s = (fx.status || {}).short;
    if (fx.id == null) continue;
    if (!FINAL_STATUS.includes(s) && !STOP_STATUS.includes(s)) continue;
    const gl = x.goals || {};
    got[String(fx.id)] = { h: gl.home, a: gl.away, s };
  }
  return got;
}

export default {
  // ── الجدولة: كل دقيقة ──
  async scheduled(event, env, ctx) {
    // ⚠️ قراءة وحدة، بلا أي كتابة، طوال فترة الخمول — درس 3 سبتمبر
    let prev = null;
    try {
      const raw = await env.LIVE_KV.get(KEY);
      if (raw) prev = JSON.parse(raw);
    } catch (e) {}

    const wasIdle = prev && Object.keys(prev.m || {}).length === 0;
    const secsSince = prev ? Math.floor(Date.now() / 1000) - prev.t : Infinity;

    // كنا بالخمول والنافذة لسا ما خلصت → صفر كتابة، رجوع فوري
    if (wasIdle && secsSince < IDLE_SKIP_SECS) return;

    const payload = await pull(env, null, prev);
    if (!payload) return;   // فشل الطلب: نُبقي آخر نسخة سليمة

    await env.LIVE_KV.put(KEY, JSON.stringify(payload));   // كتابة وحدة فقط هنا
  },

  // ── القراءة: يقدّمها للمتصفح ──
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Content-Type": "application/json;charset=UTF-8",
      "Cache-Control": "no-store",
    };

    const url = new URL(request.url);

    // تشغيل يدوي للاختبار: /pull
    if (url.pathname === "/pull") {
      const diag = {};
      let prev0 = null;
      try {
        const raw0 = await env.LIVE_KV.get(KEY);
        if (raw0) prev0 = JSON.parse(raw0);
      } catch (e) {}
      const p = await pull(env, diag, prev0);
      if (p) {
        await env.LIVE_KV.put(KEY, JSON.stringify(p));
      }
      return new Response(
        JSON.stringify(p || { error: diag.why || "سبب غير معروف" }),
        { headers: cors });
    }

    const v = await env.LIVE_KV.get(KEY);
    // ⚠️ لا نرجع خطأً حين لا توجد نسخة بعد — الصفحة تتعامل
    //    مع "لا مباريات" لا مع فشل.
    return new Response(v || JSON.stringify({ t: 0, m: {} }),
                        { headers: cors });
  },
};
