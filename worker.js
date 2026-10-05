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

// ── تنبيهات الأهداف (دفعة 2): واجهة الاشتراك ──
// معرّفات الأندية المسموحة = جدول teams بـfootball.db (الدوريات السبعة). عند إضافة
// دوري/أندية جدد أعد توليد هذه القائمة: select team_id from teams.
const TEAM_IDS = new Set([
  962,964,965,968,969,971,973,974,975,976,977,1030,1031,1032,
  1036,1037,1039,1040,1041,1044,1046,1048,1074,1075,1572,1574,1575,1576,
  1577,2865,2867,2868,2869,2870,2871,2872,2873,2874,2875,2876,2877,2879,
  2893,2894,2895,2896,2897,2898,2899,2900,2901,2902,2903,2904,2905,2907,
  2908,2916,2926,2928,2929,2930,2931,2932,2933,2934,2935,2936,2937,2938,
  2939,2940,2942,2944,2945,2950,2951,2956,2961,2977,2992,3449,3451,3453,
  3454,3455,3456,3458,4529,4530,4531,4532,4533,4534,4535,4536,4537,4538,
  4539,4543,4912,5242,6387,6689,7520,7527,8009,8010,9136,9139,9140,10121,
  10155,10509,10511,10513,11063,11064,11065,11066,11067,11069,11070,11071,11072,11073,
  11074,11474,13819,13822,14651,14806,15543,15544,15546,15547,15570,15731,15736,16431,
  17467,17469,17472,17792,18021,18036,18753,20458,20463,20464,22188,22218,22321,25058,
  25061,25062,25063,26598,26600,26738,28222,28223,
]);
const PUSH_ORIGIN = "https://saffara.app";
const MAX_TEAMS = 50;
const MAX_BODY = 8 * 1024;
const B64URL = /^[A-Za-z0-9_-]+$/;

function pushHostOk(h) {
  return h === "fcm.googleapis.com"
    || h === "updates.push.services.mozilla.com"
    || h.endsWith(".push.services.mozilla.com")
    || h === "web.push.apple.com" || h.endsWith(".push.apple.com")
    || h.endsWith(".notify.windows.com");
}

function validEndpoint(ep) {
  if (typeof ep !== "string" || ep.length > 2048) return false;
  let u;
  try { u = new URL(ep); } catch (e) { return false; }
  return u.protocol === "https:" && !u.username && !u.password && !u.port
    && pushHostOk(u.hostname);
}

// يرجع {error} أو {endpoint, p256dh, auth, lang, teams}
function validateSubscribe(body) {
  const sub = body && body.subscription;
  if (!sub || typeof sub !== "object") return { error: "subscription missing" };
  const k = sub.keys || {};
  if (!validEndpoint(sub.endpoint)) return { error: "bad endpoint" };
  if (typeof k.p256dh !== "string" || !B64URL.test(k.p256dh) || k.p256dh.length < 80 || k.p256dh.length > 90)
    return { error: "bad p256dh" };
  if (typeof k.auth !== "string" || !B64URL.test(k.auth) || k.auth.length < 20 || k.auth.length > 24)
    return { error: "bad auth" };
  if (body.lang !== "ar" && body.lang !== "en") return { error: "bad lang" };
  const t = body.teams;
  if (!Array.isArray(t) || t.length > MAX_TEAMS) return { error: "bad teams" };
  const teams = [];
  for (const x of t) {
    if (!Number.isInteger(x) || !TEAM_IDS.has(x)) return { error: "unknown team" };
    if (!teams.includes(x)) teams.push(x);
  }
  return { endpoint: sub.endpoint, p256dh: k.p256dh, auth: k.auth, lang: body.lang, teams };
}

function pushCors(request) {
  const origin = request.headers.get("Origin");
  if (origin && origin !== PUSH_ORIGIN) return null;   // origin غريب: مرفوض
  const h = {
    "Content-Type": "application/json;charset=UTF-8",
    "Cache-Control": "no-store",
    "Vary": "Origin",
  };
  if (origin) {
    h["Access-Control-Allow-Origin"] = PUSH_ORIGIN;
    h["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Content-Type";
    h["Access-Control-Max-Age"] = "86400";
  }
  return h;
}

async function handlePush(request, env, url) {
  const cors = pushCors(request);
  const reply = (status, obj) =>
    new Response(JSON.stringify(obj), { status, headers: cors || { "Content-Type": "application/json" } });
  if (!cors) return reply(400, { error: "origin not allowed" });
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  if (url.pathname === "/push/key" && request.method === "GET") {
    if (!env.VAPID_PUBLIC_KEY) return reply(500, { error: "not configured" });
    return reply(200, { key: env.VAPID_PUBLIC_KEY });
  }
  if (request.method !== "POST"
      || (url.pathname !== "/push/subscribe" && url.pathname !== "/push/unsubscribe"))
    return reply(404, { error: "not found" });
  if (!env.DB) return reply(500, { error: "not configured" });

  const text = await request.text();
  if (text.length > MAX_BODY) return reply(400, { error: "body too large" });
  let body;
  try { body = JSON.parse(text); } catch (e) { return reply(400, { error: "bad json" }); }
  if (!body || typeof body !== "object") return reply(400, { error: "bad json" });

  if (url.pathname === "/push/unsubscribe") {
    if (!validEndpoint(body.endpoint) || typeof body.auth !== "string" || !B64URL.test(body.auth))
      return reply(400, { error: "bad input" });
    const row = await env.DB.prepare("SELECT auth FROM subscriptions WHERE endpoint = ?")
      .bind(body.endpoint).first();
    if (!row) return reply(200, { ok: true, deleted: false });
    if (row.auth !== body.auth) return reply(403, { error: "auth mismatch" });
    await env.DB.batch([
      env.DB.prepare("DELETE FROM sub_teams WHERE endpoint = ?").bind(body.endpoint),
      env.DB.prepare("DELETE FROM subscriptions WHERE endpoint = ? AND auth = ?")
        .bind(body.endpoint, body.auth),
    ]);
    return reply(200, { ok: true, deleted: true });
  }

  const v = validateSubscribe(body);
  if (v.error) return reply(400, { error: v.error });
  const existing = await env.DB.prepare("SELECT auth FROM subscriptions WHERE endpoint = ?")
    .bind(v.endpoint).first();
  if (existing && existing.auth !== v.auth) return reply(403, { error: "auth mismatch" });
  const now = Math.floor(Date.now() / 1000);
  // ⚠️ json_each: معاملان فقط مهما كان عدد الأندية (حدّ D1: 100 معامل/استعلام)
  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO subscriptions (endpoint, p256dh, auth, lang, created_at, updated_at) " +
      "VALUES (?1, ?2, ?3, ?4, ?5, ?5) " +
      "ON CONFLICT(endpoint) DO UPDATE SET p256dh = ?2, lang = ?4, updated_at = ?5")
      .bind(v.endpoint, v.p256dh, v.auth, v.lang, now),
    env.DB.prepare("DELETE FROM sub_teams WHERE endpoint = ?").bind(v.endpoint),
    env.DB.prepare(
      "INSERT INTO sub_teams (endpoint, team_id) SELECT ?1, value FROM json_each(?2)")
      .bind(v.endpoint, JSON.stringify(v.teams)),
  ]);
  return reply(200, { ok: true, teams: v.teams.length });
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

    // ── تنبيهات الأهداف: /push/* (CORS خاص لا "*") ──
    if (url.pathname.startsWith("/push/")) return handlePush(request, env, url);

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
