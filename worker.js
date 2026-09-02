/**
 * صافرة — النتائج المباشرة
 * ==========================
 * يسحب من API-Football كل دقيقة ويخزّن النتيجة في KV،
 * ويقدّمها للمتصفح بنفس بنية live.json تماماً.
 *
 * ⚠️ البنية مطابقة لـ fetch_live.py حرفياً: {"t":..,"m":{..}}
 *    أي تغيير هنا يكسر live_view.py.
 *
 * ⚠️ الحصة: الجدولة كل دقيقة = 1,440 طلباً يومياً من 7,500.
 *    ولتقليلها: إن كان آخر سحب بلا مباريات جارية، نتباطأ
 *    إلى مرة كل 5 دقائق (نتخطى 4 من كل 5 نبضات).
 *
 * الربط المطلوب:
 *    Secret   : API_KEY
 *    KV       : LIVE_KV
 *    Cron     : * * * * *
 */

const API = "https://v3.football.api-sports.io";
const LEAGUES = "387-542-307";   // الأردني · العراقي · السعودي
const LIVE_STATUS = ["1H", "2H", "HT", "ET", "BT", "P", "LIVE"];
const KEY = "live";
const IDLE_SKIP = 5;             // نبضات نتخطاها حين لا شيء جارٍ

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
    let skip = 0;
    try {
      skip = parseInt((await env.LIVE_KV.get("skip")) || "0", 10);
    } catch (e) {}

    // لا شيء جارٍ → نتباطأ حفاظاً على الحصة
    if (skip > 0) {
      await env.LIVE_KV.put("skip", String(skip - 1));
      return;
    }

    const payload = await pull(env, null);
    if (!payload) return;   // فشل الطلب: نُبقي آخر نسخة سليمة

    await env.LIVE_KV.put(KEY, JSON.stringify(payload));

    const idle = Object.keys(payload.m).length === 0;
    await env.LIVE_KV.put("skip", idle ? String(IDLE_SKIP - 1) : "0");
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
        await env.LIVE_KV.put("skip", "0");
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
