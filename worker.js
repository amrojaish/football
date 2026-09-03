/**
 * صافرة — النتائج المباشرة
 * ==========================
 * يسحب من API-Football كل دقيقة ويخزّن النتيجة في KV،
 * ويقدّمها للمتصفح بنفس بنية live.json تماماً.
 *
 * ⚠️ البنية مطابقة لـ fetch_live.py حرفياً: {"t":..,"m":{..}}
 *    أي تغيير هنا يكسر live_view.py.
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
 * الربط المطلوب:
 *    Secret   : API_KEY
 *    KV       : LIVE_KV
 *    Cron     : * * * * *
 */

const API = "https://v3.football.api-sports.io";
const LEAGUES = "387-542-307-233-301";   // الأردني · العراقي · السعودي · المصري · الإماراتي
const LIVE_STATUS = ["1H", "2H", "HT", "ET", "BT", "P", "LIVE"];
const KEY = "live";
const IDLE_SKIP_SECS = 5 * 60;   // ثوانٍ نتخطّاها حين لا شيء جارٍ

async function pull(env, diag) {
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
    m[String(fx.id)] = {
      h: gl.home,
      a: gl.away,
      e: st.elapsed,
      s: st.short,
    };
  }
  return { t: Math.floor(Date.now() / 1000), m };
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

    const payload = await pull(env, null);
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
      const p = await pull(env, diag);
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
