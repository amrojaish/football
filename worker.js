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
 *    إن فشل طلب `ids` أو لم يرجع حالة نهائية بعد: تبقى المباراة معلّقة بـ`m` بآخر
 *    نتيجة (وأول وقت اختفاء بـ`g`) ونعيد طلب حالتها كل سحب حتى GIVEUP_SECS ثم تُسقَط
 *    بلا `f`. ⚠️ السحب نفسه لا يتوقف (10 أكتوبر: كان يعطّل كشف أهداف باقي المباريات).
 *
 * الربط المطلوب:
 *    Secret   : API_KEY
 *    KV       : LIVE_KV
 *    Cron     : * * * * *
 */

import { buildPushPayload } from "@block65/webcrypto-web-push";

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

// ── أحداث المباراة الجارية (13 أكتوبر 2026، دفعة 3D): بلا أي طلب إضافي ──
// ردّ `fixtures?live=` يحمل أصلاً مصفوفة `events` لكل مباراة (تحقّقنا: مطابقة تماماً لـ fixtures/events: 15 = 15 بنفس المفاتيح).
// فنخزّنها مضغوطة بحمولة `live` تحت `v` = {id: [[دقيقة, إضافي, نوع, تفصيل, لاعب, مساعد/خارج, جهة], …]} بدل استطلاع كل 3 دقائق (كان ≈ +250/يوم).
// نوع: g هدف · c بطاقة · s تبديل · v VAR. تفصيل الهدف: n عادي · p ركلة جزاء · o بالخطأ · m ركلة جزاء ضائعة؛ البطاقة: y صفراء · r حمراء · yr ثانية صفراء.
// ⚠️ حارس الحصة: رأس x-ratelimit-requests-remaining من نفس الردّ؛ إن نزل تحت EVENTS_MIN_REMAINING لا تُخزَّن/تُقدَّم الأحداث (`v` يغيب) —
//    تبقى النتيجة والمباشر وتنبيهات الأهداف وهدّافو الصفحة كما هي.
const EVENTS_MIN_REMAINING = 800;
// تنبيهات المشغّل (admin_devices فقط) عن الحصة — من رأس الردّ الحيّ نفسه (صفر طلبات). مرة واحدة باليوم UTC لكل مستوى. رأس غائب/NaN = لا تنبيه.
const QUOTA_WARN_REMAINING = 3000;
const QUOTA_LOW_REMAINING = 1500;
// ── أحداث بعد صافرة النهاية (19 أكتوبر 2026): KV ev:<id> (36 ساعة) = {fixture, t, th, ta, ft: 0|1, l: صفوف compactEvents} ──
// تُكتب فقط حين تتغيّر قائمة مباراة جارية عن السحب السابق (prev.v بالذاكرة: صفر قراءات) + نسخة نهائية من ردّ finals() نفسه (ft: 1).
// صفر طلبات إضافية. خلف حارس الحصة (evOk). يقرؤها GET /events?id= لصفحة المباراة بعد خروجها من m حين لا أحداث محفوظة.
const EV_KV_TTL = 36 * 3600;
async function storeEvents(env, prev, m, ev, finalEv, now) {
  const writes = [];
  const pv = (prev && prev.v) || {};
  for (const id of Object.keys(m)) {
    const cur = ev[id] || [];
    if (JSON.stringify(cur) === JSON.stringify(pv[id] || [])) continue;   // بلا تغيير (والفارغة سابقاً ولاحقاً) = لا كتابة
    writes.push([id, { fixture: Number(id), t: now, th: m[id].th, ta: m[id].ta, ft: 0, l: cur }]);
  }
  for (const [id, x] of Object.entries(finalEv || {})) {
    if (!x.l.length && !(pv[id] || []).length) continue;   // انتهت بلا أي حدث: لا شيء يُحفظ
    writes.push([id, { fixture: Number(id), t: now, th: x.th, ta: x.ta, ft: 1, l: x.l }]);
  }
  await Promise.all(writes.map(([id, v]) => env.LIVE_KV.put("ev:" + id, JSON.stringify(v), { expirationTtl: EV_KV_TTL })
    .catch((e) => console.log(JSON.stringify({ type: "events_store_error", fixture: Number(id), error: String((e && e.message) || e) })))));
  if (writes.length) console.log(JSON.stringify({ type: "events_store", fixtures: writes.map(([id, v]) => Number(id) * (v.ft ? -1 : 1)) }));
}
function compactEvents(evs, tm) {
  const out = [];
  const home = ((tm || {}).home || {}).id;
  for (const e of Array.isArray(evs) ? evs : []) {
    if (!e || !e.time) continue;
    const ty = e.type === "Goal" ? "g" : e.type === "Card" ? "c" : e.type === "subst" ? "s" : e.type === "Var" ? "v" : "";
    if (!ty) continue;
    const dt = String(e.detail || "");
    let d = "";
    if (ty === "g") d = dt === "Penalty" ? "p" : dt === "Own Goal" ? "o" : dt === "Missed Penalty" ? "m" : "n";
    else if (ty === "c") d = /second yellow/i.test(dt) ? "yr" : /red/i.test(dt) ? "r" : "y";
    else if (ty === "v") d = dt.slice(0, 30);
    // [7] [8] = معرّفا اللاعب والمساعد/الداخل (19 أكتوبر 2026، للأسماء العربية بالموقع)؛ إضافة بالآخر فلا يتغيّر أي فهرس قائم
    const pid = (e.player || {}).id, aid = (e.assist || {}).id;
    out.push([e.time.elapsed || 0, e.time.extra || 0, ty, d, String((e.player || {}).name || "").slice(0, 40),
      String((e.assist || {}).name || "").slice(0, 40), ((e.team || {}).id === home) ? "h" : "a",
      Number.isInteger(pid) ? pid : null, Number.isInteger(aid) ? aid : null]);
  }
  return out;
}

// محاولة سحب حيّ واحدة: {r, data} أو {why, retry, wait}. retry=false للحصة اليومية (errors.requests) وحدها.
// حدّ الدقيقة (HTTP 429 / errors.rateLimit، 19 أكتوبر 2026: فشلان 12:18 و12:19 من مستهلك آخر للمفتاح) = إعادة بعد 20 ثانية (الدقيقة التالية
// عند المزوّد)؛ باقي الأخطاء بعد 3 ثوانٍ.
const LIVE_RETRY_MS = 3000;
const LIVE_RATELIMIT_RETRY_MS = 20000;
const LIVE_TIMEOUT_MS = 10000;
async function liveAttempt(env, url, n) {
  let out;
  try {
    const r = await fetch(url, { headers: { "x-apisports-key": env.API_KEY }, signal: AbortSignal.timeout(LIVE_TIMEOUT_MS) });
    if (!r.ok) out = { why: `المزوّد رفض الطلب: HTTP ${r.status}`, retry: true, wait: r.status === 429 ? LIVE_RATELIMIT_RETRY_MS : LIVE_RETRY_MS };
    else {
      const data = await r.json();
      // المزوّد يرجع 200 مع أخطاء داخل errors
      if (data.errors && Object.keys(data.errors).length) {
        const daily = "requests" in data.errors, perMinute = "rateLimit" in data.errors;
        out = { why: "خطأ من المزوّد: " + JSON.stringify(data.errors).slice(0, 160), retry: !daily,
          wait: perMinute ? LIVE_RATELIMIT_RETRY_MS : LIVE_RETRY_MS };
      } else out = { r, data };
    }
  } catch (e) {
    const timeout = e && (e.name === "TimeoutError" || e.name === "AbortError");
    out = { why: timeout ? `مهلة ${LIVE_TIMEOUT_MS / 1000} ثوانٍ انتهت` : "خطأ شبكة: " + String((e && e.message) || e).slice(0, 120), retry: true,
      wait: LIVE_RETRY_MS };
  }
  if (out.why || n > 1) console.log(JSON.stringify({ type: "live_pull_attempt", attempt: n, ok: !out.why, why: out.why, retry: out.retry,
    ...(out.why && out.retry ? { wait_ms: out.wait } : {}) }));
  return out;
}

async function pull(env, diag, prev) {
  // ⚠️ الفشل الصامت أخطر نمط (درس 1): كل خروج مبكر
  //    يسجّل سببه في diag بدل أن يرجع null مجرّداً.
  if (!env.API_KEY) {
    if (diag) diag.why = "API_KEY غير موجود — السرّ لم يُحفظ";
    return null;
  }

  const url = `${API}/fixtures?live=${LEAGUES}`;
  // محاولة ثانية لأي فشل عدا الحصة اليومية: بعد 20 ثانية لحدّ الدقيقة وإلا بعد 3 (19 أكتوبر 2026)
  let got = await liveAttempt(env, url, 1);
  if (got.why && got.retry) {
    const first = got.why;
    await new Promise((res) => setTimeout(res, got.wait || LIVE_RETRY_MS));
    got = await liveAttempt(env, url, 2);
    if (got.why) got.why = `${first} / ${got.why}`;
  }
  if (got.why) {
    if (diag) diag.why = got.why;
    return null;
  }
  const { r, data } = got;

  const m = {};
  const ev = {};
  const remHdr = r.headers && r.headers.get ? r.headers.get("x-ratelimit-requests-remaining") : null;
  const remaining = remHdr == null || remHdr === "" ? NaN : Number(remHdr);   // رأس غائب = غير معروف (لا 0)
  const evOk = !(Number.isFinite(remaining) && remaining < EVENTS_MIN_REMAINING);   // حارس الحصة
  if (diag) diag.remaining = remaining;   // للمسار المجدول (تنبيهات المشغّل)؛ بلا أي طلب إضافي
  if (Number.isFinite(remaining)) lastRemaining = remaining;
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
      // اسما الفريقين الإنجليزيان من المزوّد: احتياط إن تعذّر جلب team_names.json
      nh: (tm.home || {}).name,
      na: (tm.away || {}).name,
    };
    if (evOk) {
      const ce = compactEvents(f.events, tm);
      if (ce.length) ev[String(fx.id)] = ce;
    }
  }
  const now = Math.floor(Date.now() / 1000);

  // ── f: نتائج المباريات التي انتهت للتو ──
  // ⚠️ الاحتفاظ بالقديم 12 ساعة؛ ويُحذف أي معرّف عاد ليكون جارياً.
  const f = {};
  for (const [id, e] of Object.entries((prev && prev.f) || {})) {
    if (e && now - e.ft < F_TTL_SECS && !(id in m)) f[id] = e;
  }

  const gone = Object.keys((prev && prev.m) || {}).filter((id) => !(id in m));
  let lateEvents = [];
  const ftEvents = [];
  const carried = {}, g = {}, finalEv = {};
  if (gone.length) {
    const ids = gone.slice(0, IDS_MAX);
    const got = await finals(env, ids, diag, finalEv);
    // لم نحصل على الحالة النهائية بعد: لا نوقف السحب (10 أكتوبر: كان يعطّل كشف أهداف باقي المباريات)؛ تبقى المباراة
    // معلّقة بـm بآخر نتيجة معروفة ونعيد طلب حالتها كل سحب، حتى GIVEUP_SECS من أول اختفاء (g[id]) ثم تُسقَط بلا f.
    const pending = [];
    for (const id of ids) {
      if (got && id in got) continue;
      const since = (prev.g && prev.g[id]) || now;
      if (now - since < GIVEUP_SECS) { carried[id] = prev.m[id]; g[id] = since; pending.push(id); }
    }
    if (pending.length && diag) diag.why = "حالة نهائية غير جاهزة للمعرّفات: " + pending.join(",");
    for (const [id, e] of Object.entries(got || {})) f[id] = { ...e, ft: now };
    lateEvents = finalGoalEvents(prev.m, got, ids);
    // نهاية المباراة (3E): من الحالة النهائية التي جلبناها أصلاً (finals) — بلا طلب إضافي
    for (const id of ids) {
      const e = got && got[id], old = prev.m[id];
      if (e && old && FINAL_STATUS.includes(e.s)) {
        ftEvents.push({ evt: "ft", fixture: Number(id), th: old.th, ta: old.ta, lg: old.lg, nh: old.nh, na: old.na,
          h: Number.isFinite(e.h) ? e.h : old.h, a: Number.isFinite(e.a) ? e.a : old.a });
      }
    }
  }

  // ⚠️ بعد كل مخارج null أعلاه: لو أُعيدت المحاولة (prev لم يتحدّث) لا يتكرّر السجل.
  const events = [...logGoalEvents(prev && prev.m, m), ...lateEvents];
  // سجل الكشف بـD1 (goal_log، 30 يوماً) مستقل عن الإرسال و GOAL_PUSH: لمقارنة الكشف بأحداث المباريات الحقيقية
  try { await recordGoalLog(env, events); }
  catch (e) { console.log(JSON.stringify({ type: "goal_log_error", error: String((e && e.message) || e) })); }
  // الإرسال معزول: أي فشل لا يمنع كتابة KV (sent يمنع التكرار عند إعادة السحب)
  try { await sendGoalPushes(env, events, { ...((prev && prev.m) || {}), ...m }); }
  catch (e) { console.log(JSON.stringify({ type: "goal_push_error", error: String((e && e.message) || e) })); }

  // تنبيهات الحالة (3E): انطلاق / نهاية الشوط الأول / بداية الثاني / بطاقة حمراء / نهاية المباراة — كلها من الردّ الحيّ نفسه (صفر طلبات)
  try { await sendAlertPushes(env, [...statusEvents(prev && prev.m, m), ...redCardEvents(prev, ev, m, evOk), ...missedPenaltyEvents(prev, ev, m, evOk), ...ftEvents]); }
  catch (e) { console.log(JSON.stringify({ type: "alert_push_error", error: String((e && e.message) || e) })); }

  // ev:<id> قبل ضمّ المعلّقة: m هنا = الجارية بهذا الردّ فقط
  if (evOk) {
    try { await storeEvents(env, prev, m, ev, finalEv, now); }
    catch (e) { console.log(JSON.stringify({ type: "events_store_error", error: String((e && e.message) || e) })); }
  }
  Object.assign(m, carried);   // بعد الكشف: المعلّقة لا تولّد أحداثاً
  // هدّافو المباريات الجارية للموقع (10 أكتوبر): جدولة جلب الأحداث لكل مباراة سُجّل بها هدف/إلغاء، وقراءة آخر قائمة مخزّنة
  try { await queueLiveScorers(env, events); }
  catch (e) { console.log(JSON.stringify({ type: "live_scorers_error", error: String((e && e.message) || e) })); }
  let liveSc = {};
  try { liveSc = await readLiveScorers(env, Object.keys(m)); }
  catch (e) { console.log(JSON.stringify({ type: "live_scorers_error", error: String((e && e.message) || e) })); }
  const out = { t: now, m };
  if (Object.keys(liveSc).length) out.s = liveSc;   // إضافة فقط: {id: [[side,minute,extra,name,ar,tag],…]}
  if (evOk) out.ve = 1;   // علامة: «الأحداث كانت مفعّلة بهذا السحب» (أساس لكشف البطاقات الحمراء بالسحب التالي)
  if (Object.keys(m).some((id) => ev[id])) {      // أحداث المباريات الجارية (إضافة فقط؛ تغيب بحارس الحصة)
    out.v = {};
    for (const id of Object.keys(m)) if (ev[id]) out.v[id] = ev[id];
  }
  if (Object.keys(g).length) out.g = g;   // أول وقت اختفاء للمعلّقة (يُحسب منه GIVEUP_SECS)
  if (Object.keys(f).length) out.f = f;   // {t, m} كما هي؛ f إضافة فقط
  return out;
}

// صف لكل حدث goal/goal_cancelled: {ts, kind, fixture, th, ta, h, a, prev_h, prev_a, minute, league}
const GOAL_LOG_KEEP_DAYS = 30;
async function recordGoalLog(env, events) {
  if (!env.DB || !events || !events.length) return;
  const ts = Math.floor(Date.now() / 1000);
  await env.DB.batch(events.map((e) => env.DB.prepare(
    "INSERT INTO goal_log (ts, kind, fixture, th, ta, h, a, prev_h, prev_a, minute, league) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(ts, e.type, e.fixture, e.th ?? null, e.ta ?? null, e.h, e.a, e.prev_h, e.prev_a, e.minute ?? null, e.league ?? null)));
}

// ── كشف الأهداف (تسجيل فقط، بلا إرسال): مقارنة نتيجة كل مباراة بالسحب السابق ──
// سطر JSON واحد لكل حدث:
//   {"type":"goal"|"goal_cancelled","fixture","th","ta","h","a","prev_h","prev_a","minute","league"}
// ⚠️ مباراة لا وجود لها بـprev: لا حدث (إعادة تشغيل/ظهور وسط المباراة ≠ هدف) — **إلا** إن ظهرت أول مرة والنتيجة ≠ 0-0
//    والمباراة بالشوط الأول وelapsed ≤ FIRST_SIGHT_MAX_MIN (9 أكتوبر 2026: هدف الدقيقة 3 بالمباراة 1627995 فُقد لأن أول سحب
//    بعد نافذة الخمول 5 دقائق رأى 1-0 أصلاً). عندها الأساس 0-0 وكل هدف حدث مستقل (أهداف الأرض ثم الضيف: ترتيبها الحقيقي
//    مجهول؛ النتيجة الأخيرة صحيحة دائماً) و`first:true` بالسطر. بعد 20 دقيقة (إعادة تشغيل وسط المباراة) السلوك القديم: لا حدث.
//    تكرار الإشعار عند عودة مباراة اختفت وعادت ممنوع بجدول `sent` (fixture,h,a).
// ⚠️ لا طلبات API ولا كتابات KV هنا — console.log فقط.
// يرجع قائمة الأحداث [{type, ...base}] ليستعملها الإرسال (دفعة 5).
const FIRST_SIGHT_MAX_MIN = 20;
function logGoalEvents(prevM, m) {
  const events = [];
  for (const [id, cur] of Object.entries(m)) {
    const old = prevM && prevM[id];
    if (!old) {
      const h0 = cur.h ?? 0, a0 = cur.a ?? 0;
      if (!(cur.s === "1H" && Number.isFinite(cur.e) && cur.e <= FIRST_SIGHT_MAX_MIN && h0 + a0 > 0)) continue;
      let ch = 0, ca = 0;
      while (ch < h0 || ca < a0) {
        const ph = ch, pa = ca;
        if (ch < h0) ch++; else ca++;
        events.push({ type: "goal", fixture: Number(id), th: cur.th, ta: cur.ta, h: ch, a: ca,
          prev_h: ph, prev_a: pa, minute: cur.e, league: cur.lg, first: true });
      }
      continue;
    }
    const ph = old.h ?? 0, pa = old.a ?? 0;
    const h = cur.h ?? 0, a = cur.a ?? 0;
    const base = {
      fixture: Number(id), th: cur.th, ta: cur.ta, h, a,
      prev_h: ph, prev_a: pa, minute: cur.e, league: cur.lg,
    };
    if (h < ph || a < pa) events.push({ type: "goal_cancelled", ...base });
    if (h > ph || a > pa) events.push({ type: "goal", ...base });
  }
  for (const ev of events) console.log(JSON.stringify(ev));
  return events;
}

// ── أهداف فاتت قبل اختفاء المباراة من الردّ الحيّ (10 أكتوبر 2026) ──
// الردّ الحيّ قد يتأخر عن الواقع بآخر دقائق المباراة، فتختفي المباراة بنتيجة أقدم من النهائية (1603041: آخر سحب 0-4 والنهائية 0-5؛
// 1627993: لا سحب ظهر فيه 2-0 أبداً). فرق النتيجة النهائية (من finals) عن آخر نتيجة مخزّنة بـprev.m يصير حدثاً لكل هدف ناقص بنفس
// شكل أحداث logGoalEvents (فيمرّ بنفس جدول `sent` والكشف والـD1 ومسار تحديث الهدّاف) + late:true. الدقيقة مجهولة => null (الإشعار
// يحذفها). النقص (نهائية أقل من المخزّنة) يُبلَّغ إلغاءً لحالة نهائية فقط. إشعار متأخر خير من لا إشعار.
function finalGoalEvents(prevM, got, ids) {
  const events = [];
  for (const id of ids) {
    const old = prevM && prevM[id], fin = got && got[id];
    if (!old || !fin || !Number.isFinite(fin.h) || !Number.isFinite(fin.a)) continue;
    const ph = old.h ?? 0, pa = old.a ?? 0;
    const base = { fixture: Number(id), th: old.th, ta: old.ta, minute: null, league: old.lg, late: true };
    if ((fin.h < ph || fin.a < pa) && FINAL_STATUS.includes(fin.s)) {
      events.push({ type: "goal_cancelled", ...base, h: fin.h, a: fin.a, prev_h: ph, prev_a: pa });
    }
    let ch = ph, ca = pa;
    while (ch < fin.h || ca < fin.a) {
      const bh = ch, ba = ca;
      if (ch < fin.h) ch++; else ca++;
      events.push({ type: "goal", ...base, h: ch, a: ca, prev_h: bh, prev_a: ba });
    }
  }
  for (const ev of events) console.log(JSON.stringify(ev));
  return events;
}

// ── هدّافو المباريات الجارية بحمولة `live` (10 أكتوبر 2026) ──
// الردّ الحيّ بلا أحداث. لكل مباراة سُجّل بها هدف (أو أُلغي) نضع رسالة `live_scorers` بالطابور بتأخير 45 ث؛ المستهلك يطلب
// fixtures/events?fixture= **مرة واحدة** (وإعادتين فقط إن لم يُدرج المزوّد الهدف بعد: 90 ث ثم 180 ث) ويخزّن القائمة الكاملة
// بمفتاح KV منفصل `sc:<id>` (8 ساعات) — منفصل لا بـ`live` كي لا يسابق كتابةَ السحب. السحب التالي يقرأ مفاتيح المباريات الجارية فقط
// ويضمّها بـ`s` بالحمولة. بلا أحداث بعد = لا `s[id]` والموقع يعرض النتيجة وحدها. صفر طلبات للمزوّد بلا أهداف.
// الصف: [side "h"|"a" (المستفيد: الهدف العكسي للخصم), دقيقة, إضافي, اسم لاتيني (اسم العائلة), اسم عربي مؤكَّد أو "", وسم "" | "p" | "og"]
const LIVE_SC_DELAYS = [45, 90, 180];
const LIVE_SC_TTL = 8 * 3600;
async function queueLiveScorers(env, events) {
  if (!env.GOAL_QUEUE || !events || !events.length) return;
  const last = {};
  for (const ev of events) last[ev.fixture] = ev;
  for (const ev of Object.values(last)) {
    await env.GOAL_QUEUE.send({ kind: "live_scorers", fixture: ev.fixture, th: ev.th, ta: ev.ta, h: ev.h, a: ev.a, step: 0, ts: Date.now() },
      { delaySeconds: LIVE_SC_DELAYS[0] });
  }
}
async function readLiveScorers(env, ids) {
  const out = {};
  await Promise.all(ids.map(async (id) => {
    try {
      const raw = await env.LIVE_KV.get("sc:" + id);
      const j = raw ? JSON.parse(raw) : null;
      if (j && Array.isArray(j.l) && j.l.length) out[id] = j.l;
    } catch (e) {}
  }));
  return out;
}
async function liveScorersStep(env, msg) {
  const step = msg.step || 0;
  const log = (o) => console.log(JSON.stringify({ type: "live_scorers", fixture: msg.fixture, h: msg.h, a: msg.a, step, ...o }));
  if (!env.API_KEY) return log({ skipped: "nokey" });
  const retry = async (why) => {
    if (step + 1 < LIVE_SC_DELAYS.length) {
      await env.GOAL_QUEUE.send({ ...msg, step: step + 1 }, { delaySeconds: LIVE_SC_DELAYS[step + 1] });
      return log({ [why]: true, retry_in: LIVE_SC_DELAYS[step + 1], events_request: 1 });
    }
    return log({ [why]: true, gave_up: true, events_request: 1 });
  };
  let j;
  try {
    const r = await fetch(`${API}/fixtures/events?fixture=${msg.fixture}`, {
      headers: { "x-apisports-key": env.API_KEY }, signal: AbortSignal.timeout(4000) });
    if (!r.ok) return retry("error");
    j = await r.json();
    if (j.errors && Object.keys(j.errors).length) return retry("error");
  } catch (e) { return retry("error"); }
  const t = (e) => ((e.time && e.time.elapsed) || 0) * 1000 + ((e.time && e.time.extra) || 0);
  const goals = (j.response || []).filter((e) => e && e.type === "Goal" && e.detail !== "Missed Penalty" && e.team && e.player)
    .sort((x, y) => t(x) - t(y));
  const pn = await playerNames();
  const list = goals.map((e) => {
    const og = e.detail === "Own Goal";
    const benefit = og ? (e.team.id === msg.th ? msg.ta : msg.th) : e.team.id;
    const byId = e.player.id != null ? pn[e.player.id] : null;
    const byName = e.player.name && pn._n ? pn._n[e.team.id + "|" + e.player.name] : null;
    return [benefit === msg.th ? "h" : "a", (e.time && e.time.elapsed) || 0, (e.time && e.time.extra) || 0,
      surname(e.player.name || ""), (byId && byId.ar) || (byName && byName.ar) || "", og ? "og" : e.detail === "Penalty" ? "p" : ""];
  });
  const key = "sc:" + msg.fixture;
  if (list.length) await env.LIVE_KV.put(key, JSON.stringify({ l: list }), { expirationTtl: LIVE_SC_TTL });
  else if (msg.h + msg.a === 0) await env.LIVE_KV.delete(key);   // كل الأهداف أُلغيت
  if (list.length < msg.h + msg.a) return retry("lag");           // المزوّد لم يُدرج الهدف بعد: ما لدينا مخزَّن، ونعيد
  log({ goals: list.length, events_request: 1 });
}

// طلب واحد: fixtures?ids=a-b-c → {id: {h, a, s}} للحالات النهائية/غير المكتملة
// فقط. يرجع null عند فشل الطلب.
// evOut (اختياري): {id: {th, ta, l}} أحداث المنتهية من الردّ نفسه (ev:<id> النهائية) — بلا طلب إضافي
async function finals(env, ids, diag, evOut) {
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
    // 12 أكتوبر: معرّفا الفريقين والدوري بكل مدخل f (كما بـm) ليحسب الموقع الترتيب المباشر بنتائج المباريات التي انتهت للتو؛ حقول إضافية فقط
    const tm = x.teams || {}, lgid = (x.league || {}).id;
    if (evOut && FINAL_STATUS.includes(s)) evOut[String(fx.id)] = { th: (tm.home || {}).id, ta: (tm.away || {}).id, l: compactEvents(x.events, tm) };
    got[String(fx.id)] = { h: gl.home, a: gl.away, s,
      ...((tm.home || {}).id != null ? { th: tm.home.id } : {}),
      ...((tm.away || {}).id != null ? { ta: tm.away.id } : {}),
      ...(lgid != null ? { lg: lgid } : {}) };
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
// أنواع التنبيه (13 أكتوبر 2026، دفعة 3E): قناع بتّات لكل كيان مشترَك (نادٍ/مباراة/دوري). بلا نوع «تشكيلات». 127 = الكل (الافتراضي).
const T_KICKOFF = 1, T_GOAL = 2, T_HT = 4, T_SH = 8, T_FT = 16, T_RED = 32, T_REM = 64, T_MISSPEN = 128, T_LINEUP = 256, ALL_TYPES = 511;
// T_LINEUP (19 أكتوبر 2026): «التشكيلة الرسمية». ليس بـDEFAULT_TYPES: الأقنعة المخزَّنة والعملاء بلا قناع لا يستلمونه؛ العميل الجديد يرسله صراحةً.
// T_MISSPEN (13 أكتوبر، 3E2): ضربة جزاء ضائعة (حدث Goal بتفصيل Missed Penalty بالردّ الحيّ)؛ الأقنعة المخزَّنة قبله بلا هذا البتّ فلا تتغيّر.
// افتراضي الاشتراك الجديد (13 أكتوبر): انطلاق + هدف + نهاية + حمراء + تذكير = 115؛ نهاية الشوط الأول وبداية الثاني (4/8) مطفأتان حتى يفعّلهما المستخدم.
// ⚠️ صفوف ما قبل 3E (نادٍ/مباراة اشتركت للأهداف فقط) = LEGACY_TYPES = 2 (الأهداف فقط): لا يبدأ أحد باستلام ما لم يختره.
const DEFAULT_TYPES = 115 | T_MISSPEN, LEGACY_TYPES = 2, MASK_UNSET = -1;   // 243: الجديد = الافتراضي القديم + الجزاء الضائع
const LEAGUE_IDS = new Set([387, 542, 307, 233, 301, 305, 200]);   // معرّفات دوريات المزوّد السبعة (= LEAGUES أدناه)
const MAX_MATCHES = 20;   // تنبيهات مباريات مفردة (13 أكتوبر 2026): جدول sub_matches، الهجرة 0008
const MAX_BODY = 8 * 1024;
const B64URL = /^[A-Za-z0-9_-]+$/;
// الإطلاق العام: حدّ طلبات الاشتراك لكل IP بالساعة وسقف عام للاشتراكات (يُتجاوزان بمتغيرين بيئيين).
// ⚠️ لماذا عدّاد D1 لا Workers Rate Limiting binding: الـbinding يقبل فترتين فقط (10 أو 60 ثانية)
//    ولا يدعم "20 بالساعة"، وعدّاده محلي لكل موقع (colo) وغير متسق. D1 موجود أصلاً بلا تكلفة جديدة.
const SUBSCRIBE_PER_HOUR = 20;
const MAX_SUBSCRIPTIONS = 5000;

// يزيد عدّاد (IP، ساعة) ويرجع {n, retry} — retry = ثوانٍ حتى نهاية الساعة
async function bumpRate(env, request) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const dig = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip + ":saffara"));
  const h = Array.from(new Uint8Array(dig).slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
  const now = Math.floor(Date.now() / 1000);
  const bucket = Math.floor(now / 3600);
  const exp = (bucket + 1) * 3600;
  const row = await env.DB.prepare(
    "INSERT INTO rate_limit (k, n, exp) VALUES (?1, 1, ?2) " +
    "ON CONFLICT(k) DO UPDATE SET n = n + 1 RETURNING n")
    .bind(h + ":" + bucket, exp).first();
  const n = row ? row.n : 1;
  if (n === 1) await env.DB.prepare("DELETE FROM rate_limit WHERE exp < ?").bind(now).run();
  return { n, retry: exp - now };
}

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
  // `matches` اختياري (13 أكتوبر): غائب = لا تُمَس قائمة مباريات الاشتراك؛ مصفوفة = تستبدلها (حتى MAX_MATCHES معرّفاً صحيحاً موجباً)
  let matches = null;
  if (body.matches !== undefined) {
    if (!Array.isArray(body.matches) || body.matches.length > MAX_MATCHES) return { error: "bad matches" };
    matches = [];
    for (const x of body.matches) {
      if (!Number.isInteger(x) || x <= 0) return { error: "bad matches" };
      if (!matches.includes(x)) matches.push(x);
    }
  }
  // `leagues` اختياري: اشتراك بكل مباريات دوري (معرّف المزوّد من LEAGUE_IDS)؛ غائب = لا يُمَس
  let leagues = null;
  if (body.leagues !== undefined) {
    if (!Array.isArray(body.leagues) || body.leagues.length > LEAGUE_IDS.size) return { error: "bad leagues" };
    leagues = [];
    for (const x of body.leagues) {
      if (!Number.isInteger(x) || !LEAGUE_IDS.has(x)) return { error: "bad leagues" };
      if (!leagues.includes(x)) leagues.push(x);
    }
  }
  // أقنعة الأنواع (3E): tt/mt/lt = {معرّف: قناع 1..127}. غائب = الكل (127) — فعملاء ما قبل 3E لا يتغيّر سلوكهم
  const maskOf = (m, id) => {   // MASK_UNSET = لم يرسل العميل قناعاً: يحلّه معالج الاشتراك (الموجود، وإلا الافتراضي)
    if (m === undefined) return MASK_UNSET;
    if (!m || typeof m !== "object" || Array.isArray(m)) return null;
    const v = m[String(id)];
    if (v === undefined) return MASK_UNSET;
    return Number.isInteger(v) && v >= 1 && v <= ALL_TYPES ? v : null;
  };
  const withMasks = (ids, m) => {
    if (!ids) return null;
    const out = [];
    for (const id of ids) { const v = maskOf(m, id); if (v === null) return false; out.push([id, v]); }
    return out;
  };
  const teamTypes = withMasks(teams, body.tt), matchTypes = withMasks(matches, body.mt), leagueTypes = withMasks(leagues, body.lt);
  if (teamTypes === false || matchTypes === false || leagueTypes === false) return { error: "bad types" };
  return { endpoint: sub.endpoint, p256dh: k.p256dh, auth: k.auth, lang: body.lang, teams, matches, leagues, teamTypes, matchTypes, leagueTypes };
}

// مستلمو حدث بنوع معيّن: مشتركو أحد الفريقين + مشتركو هذه المباراة + مشتركو دوريها، كلٌّ بقناعه (UNION: من يتابع بأكثر من طريق يصله مرة)
function recipientWhere(teamIds, fixture, lg, bit) {
  const ids = teamIds.filter((x) => Number.isInteger(x));
  const sql = "endpoint IN (SELECT endpoint FROM sub_teams WHERE team_id IN (" + ids.map(() => "?").join(",") + ") AND (types & ?) != 0 " +
    "UNION SELECT endpoint FROM sub_matches WHERE fixture = ? AND (types & ?) != 0 " +
    "UNION SELECT endpoint FROM sub_leagues WHERE league = ? AND (types & ?) != 0)";
  return { sql, binds: [...ids, bit, fixture, bit, Number.isInteger(lg) ? lg : -1, bit] };
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

// ── الإرسال (دفعة 3): sendToTeam ──
// ⚠️ سقف الاشتراكات للاستدعاء الواحد: خطة Workers المجانية = 50 subrequest. نرسل حتى 40
//    (الباقي لاحقاً بالـQueues حين يلزم). الاشتراكات التي يردّ عليها خادم الدفع 404/410
//    (انتهت/أُلغيت) تُحذف فوراً. لا يُستدعى من كشف الأهداف بعد (الدفعة 5).
const SEND_CAP = 40;
const PUSH_TTL_SECS = 600;   // هدف يصل بعد 10 دقائق لا قيمة له

// payload: كائن، أو دالة (lang) => كائن {title, body, tag, url} لكل لغة اشتراك
async function sendToTeam(env, teamId, payload) {
  return sendToTeams(env, [teamId], payload);
}

// مشتركو أي من الفريقين، كل endpoint مرة واحدة (من يتابع الفريقين يصله إشعار واحد).
// ⚠️ للاختبار اليدوي (/push/test) فقط: محدود بـSEND_CAP. مسار الأهداف يمرّ بالطابور (goalPushPage) بلا سقف.
async function sendToTeams(env, teamIds, payload) {
  const ids = [...new Set(teamIds.filter((x) => Number.isInteger(x)))];
  if (!ids.length) return { sent: 0, gone: 0, failed: 0, capped: false };
  const { results } = await env.DB.prepare(
    "SELECT endpoint, p256dh, auth, lang FROM subscriptions WHERE endpoint IN " +
    "(SELECT endpoint FROM sub_teams WHERE team_id IN (" + ids.map(() => "?").join(",") + ")) LIMIT ?")
    .bind(...ids, SEND_CAP + 1).all();
  const capped = results.length > SEND_CAP;
  const out = await deliver(env, results.slice(0, SEND_CAP), payload);
  return { sent: out.sent, gone: out.gone, failed: out.failed, capped };
}

// يرسل لقائمة اشتراكات. يرجع {sent, gone, failed, retryable:[endpoint]} — retryable = فشل عابر
// (شبكة/429/5xx/408) يستحق إعادة؛ 404/410 تُحذف فوراً؛ باقي 4xx فشل دائم بلا إعادة.
async function deliver(env, subs, payload) {
  const vapid = {
    subject: env.VAPID_SUBJECT,
    publicKey: env.VAPID_PUBLIC_KEY,
    privateKey: env.VAPID_PRIVATE_KEY,
  };
  const out = { sent: 0, gone: 0, failed: 0, skipped: 0, retryable: [] };
  const goneEndpoints = [];
  await Promise.all(subs.map(async (s) => {
    try {
      const data = typeof payload === "function" ? payload(s.lang) : payload;
      if (data == null) { out.skipped++; return; }   // مثلاً: تحديث الهدّاف لمشترك عربي بلا اسم عربي مؤكد
      const req = await buildPushPayload(
        { data, options: { ttl: PUSH_TTL_SECS, urgency: "high" } },
        { endpoint: s.endpoint, expirationTime: null, keys: { p256dh: s.p256dh, auth: s.auth } },
        vapid);
      const res = await fetch(s.endpoint, req);
      if (res.status === 404 || res.status === 410) { goneEndpoints.push(s.endpoint); out.gone++; }
      else if (res.status >= 200 && res.status < 300) out.sent++;
      else {
        out.failed++;
        if (res.status === 429 || res.status === 408 || res.status >= 500) out.retryable.push(s.endpoint);
      }
    } catch (e) {
      out.failed++;
      out.retryable.push(s.endpoint);
    }
  }));
  if (goneEndpoints.length) {
    try {
      const j = JSON.stringify(goneEndpoints);
      await env.DB.batch([
        env.DB.prepare("DELETE FROM sub_teams WHERE endpoint IN (SELECT value FROM json_each(?))").bind(j),
        env.DB.prepare("DELETE FROM sub_matches WHERE endpoint IN (SELECT value FROM json_each(?))").bind(j),
        env.DB.prepare("DELETE FROM sub_leagues WHERE endpoint IN (SELECT value FROM json_each(?))").bind(j),
        env.DB.prepare("DELETE FROM subscriptions WHERE endpoint IN (SELECT value FROM json_each(?))").bind(j),
      ]);
    } catch (e) {
      console.log(JSON.stringify({ type: "goal_push_error", error: "gone_cleanup: " + String((e && e.message) || e) }));
    }
  }
  return out;
}

// مقارنة بزمن ثابت (لا تسرّب طول التطابق)
function safeEqual(a, b) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] || 0) ^ (y[i] || 0);
  return d === 0;
}

// نص وصل "؟؟؟؟؟" أي "?????" بلا أي حرف عربي/لاتيني = ترميز ضاع قبل وصوله (PowerShell/curl.exe
// على ويندوز يحوّل الوسائط لصفحة الشيفرة المحلية). نرفضه بدل إرسال إشعار مشوَّه.
function looksMangled(s) {
  return /\?{2,}/.test(s) && !/[A-Za-z؀-ۿ]/.test(s);
}

// POST /push/test {team_id, title, body} + Authorization: Bearer <ADMIN_TOKEN>
async function handlePushTest(request, env) {
  const json = (status, obj) => new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json;charset=UTF-8", "Cache-Control": "no-store" } });
  const m = /^Bearer (.+)$/.exec(request.headers.get("Authorization") || "");
  if (!env.ADMIN_TOKEN || !m || !safeEqual(m[1], env.ADMIN_TOKEN)) return json(401, { error: "unauthorized" });
  if (request.method !== "POST") return json(405, { error: "method" });
  if (!env.DB || !env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY) return json(500, { error: "not configured" });
  let b;
  try { b = JSON.parse(await request.text()); } catch (e) { return json(400, { error: "bad json" }); }
  if (!b || !Number.isInteger(b.team_id) || !TEAM_IDS.has(b.team_id)
      || typeof b.title !== "string" || !b.title || b.title.length > 100
      || typeof b.body !== "string" || b.body.length > 300) return json(400, { error: "bad input" });
  if (looksMangled(b.title) || looksMangled(b.body))
    return json(400, { error: "text looks like lost encoding (runs of '?'): send UTF-8 JSON, e.g. from node" });
  const r = await sendToTeam(env, b.team_id, (lang) => ({
    title: b.title, body: b.body, tag: "test-" + b.team_id,
    url: (lang === "en" ? "/en/clubs/" : "/clubs/") + b.team_id + ".html",
  }));
  return json(200, r);
}

// POST /push/admin-device {endpoint} (يسجّل) · DELETE (يزيل) + Authorization: Bearer <ADMIN_TOKEN>
// الجهاز يجب أن يكون مشتركاً أصلاً بـsubscriptions. العلم بجدول منفصل لا يلمسه مسار الاشتراك العام.
async function handleAdminDevice(request, env) {
  const json = (status, obj) => new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json;charset=UTF-8", "Cache-Control": "no-store" } });
  const m = /^Bearer (.+)$/.exec(request.headers.get("Authorization") || "");
  if (!env.ADMIN_TOKEN || !m || !safeEqual(m[1], env.ADMIN_TOKEN)) return json(401, { error: "unauthorized" });
  if (request.method !== "POST" && request.method !== "DELETE") return json(405, { error: "method" });
  if (!env.DB) return json(500, { error: "not configured" });
  let b;
  try { b = JSON.parse(await request.text()); } catch (e) { return json(400, { error: "bad json" }); }
  if (!b || typeof b.endpoint !== "string" || !validEndpoint(b.endpoint)) return json(400, { error: "bad input" });
  if (request.method === "DELETE") {
    await env.DB.prepare("DELETE FROM admin_devices WHERE endpoint = ?").bind(b.endpoint).run();
    return json(200, { ok: true, admin: false });
  }
  const sub = await env.DB.prepare("SELECT 1 AS x FROM subscriptions WHERE endpoint = ?").bind(b.endpoint).first();
  if (!sub) return json(404, { error: "endpoint not subscribed" });
  await env.DB.prepare("INSERT OR IGNORE INTO admin_devices (endpoint, created_at) VALUES (?, ?)")
    .bind(b.endpoint, Math.floor(Date.now() / 1000)).run();
  return json(200, { ok: true, admin: true });
}

// POST /push/admin-test + Bearer ADMIN_TOKEN: push تجريبي «النشر عالق (تجربة)» لأجهزة admin_devices فقط، بلا أي تشغيلة حقيقية ولا كتابة بالسجل.
async function handleAdminTest(request, env) {
  const json = (status, obj) => new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json;charset=UTF-8", "Cache-Control": "no-store" } });
  const m = /^Bearer (.+)$/.exec(request.headers.get("Authorization") || "");
  if (!env.ADMIN_TOKEN || !m || !safeEqual(m[1], env.ADMIN_TOKEN)) return json(401, { error: "unauthorized" });
  if (request.method !== "POST") return json(405, { error: "method" });
  if (!env.DB || !env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY) return json(500, { error: "not configured" });
  const r = await notifyAdmins(env, {
    title: "⚠️ النشر عالق (تجربة)",
    body: "تجربة — لا يوجد تشغيل عالق",
    tag: "stuck-run-test", url: "/",
  });
  return json(200, r);
}

// POST /push/simulate {fixture, th, ta, h, a, minute, kind:"goal"|"cancel", side?, prev_h?, prev_a?, player_id?, player_name?, detail?, admin_only?} + Bearer ADMIN_TOKEN
// تجربة كاملة بلا مباراة حقيقية: يضع نفس رسالة الهدف الحقيقية بنفس الطابور (فيمرّ المستهلك والإرسال والـTTL
// والسجل كلها). ⚠️ لا يلمس جدول `sent` (الـINSERT/DELETE يحدثان بمنتج الكشف فقط) ولا KV ولا نتيجة المباراة.
// السجل يحمل sim:true. يحترم GOAL_PUSH (غير "on" => 409).
async function handlePushSimulate(request, env) {
  const json = (status, obj) => new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json;charset=UTF-8", "Cache-Control": "no-store" } });
  const m = /^Bearer (.+)$/.exec(request.headers.get("Authorization") || "");
  if (!env.ADMIN_TOKEN || !m || !safeEqual(m[1], env.ADMIN_TOKEN)) return json(401, { error: "unauthorized" });
  if (request.method !== "POST") return json(405, { error: "method" });
  if (!env.GOAL_QUEUE) return json(500, { error: "not configured" });
  if (env.GOAL_PUSH !== "on") return json(409, { error: "GOAL_PUSH is off" });
  let b;
  try { b = JSON.parse(await request.text()); } catch (e) { return json(400, { error: "bad json" }); }
  const int = (x, lo, hi) => Number.isInteger(x) && x >= lo && x <= hi;
  if (!b || !int(b.fixture, 1, 2147483647) || !TEAM_IDS.has(b.th) || !TEAM_IDS.has(b.ta)
      || !int(b.h, 0, 99) || !int(b.a, 0, 99) || !int(b.minute, 0, 130)
      || (b.kind !== "goal" && b.kind !== "cancel")) return json(400, { error: "bad input" });
  if (b.side !== undefined && b.side !== "home" && b.side !== "away") return json(400, { error: "bad input" });
  const side = b.side || (b.kind === "goal" ? (b.a > b.h ? "away" : "home") : undefined);
  // اختياري لتجربة اسم الهدّاف بلا مباراة: player_id (+ player_name بصيغة المزوّد "A. Ersan" للبحث بالاسم، + detail)
  if ((b.player_id !== undefined && !int(b.player_id, 1, 2147483647))
      || (b.player_name !== undefined && (typeof b.player_name !== "string" || b.player_name.length > 80))
      || (b.detail !== undefined && !["Normal Goal", "Penalty", "Own Goal"].includes(b.detail))) return json(400, { error: "bad input" });
  let sc = null;
  if (b.player_id !== undefined || b.player_name !== undefined) {
    const own = b.detail === "Own Goal";
    const sideTeam = side === "home" ? b.th : b.ta, otherTeam = side === "home" ? b.ta : b.th;
    sc = { pid: b.player_id ?? null, pname: b.player_name || null, ptid: own ? otherTeam : sideTeam, pdet: b.detail || "Normal Goal" };
  }
  if ((b.prev_h !== undefined && !int(b.prev_h, 0, 99)) || (b.prev_a !== undefined && !int(b.prev_a, 0, 99))) return json(400, { error: "bad input" });
  let ph = b.prev_h, pa = b.prev_a;
  if (b.kind === "cancel" && ph === undefined && pa === undefined && side) {   // النتيجة قبل الإلغاء = هدف زائد للفريق الملغى
    ph = side === "home" ? b.h + 1 : b.h; pa = side === "away" ? b.a + 1 : b.a;
  }
  if (b.admin_only !== undefined && typeof b.admin_only !== "boolean") return json(400, { error: "bad input" });
  // الإشعار الأول بلا اسم (كالحقيقي)؛ لو أُعطي لاعب يصل اسمه بعد 60 ث برسالة التحديث (simsc) بدل جلب events.
  // admin_only: يذهب لأجهزة admin_devices فقط (لتجربة جهاز المشغّل بلا إزعاج مشتركين حقيقيين).
  await env.GOAL_QUEUE.send({ fixture: b.fixture, kind: b.kind, th: b.th, ta: b.ta, h: b.h, a: b.a,
    minute: b.minute, offset: 0, ts: Date.now(), sim: true, ...(side ? { side } : {}),
    ...(ph !== undefined ? { ph, pa } : {}), ...(sc ? { simsc: sc } : {}), ...(b.admin_only ? { admin: true } : {}) });
  return json(200, { ok: true, queued: true });
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
      || (url.pathname !== "/push/subscribe" && url.pathname !== "/push/unsubscribe"
          && url.pathname !== "/push/teams"))
    return reply(404, { error: "not found" });
  if (!env.DB) return reply(500, { error: "not configured" });

  if (url.pathname === "/push/subscribe") {
    const limit = Number(env.SUBSCRIBE_PER_HOUR) || SUBSCRIBE_PER_HOUR;
    const r = await bumpRate(env, request);
    if (r.n > limit) {
      const h = new Headers(cors || { "Content-Type": "application/json" });
      h.set("Retry-After", String(r.retry));
      return new Response(JSON.stringify({ error: "rate_limited" }), { status: 429, headers: h });
    }
  }

  const text = await request.text();
  if (text.length > MAX_BODY) return reply(400, { error: "body too large" });
  let body;
  try { body = JSON.parse(text); } catch (e) { return reply(400, { error: "bad json" }); }
  if (!body || typeof body !== "object") return reply(400, { error: "bad json" });

  // أندية اشتراك قائم (لنقل المستخدمين القدامى لقائمة fbPushTeams): نفس بوابة auth
  if (url.pathname === "/push/teams") {
    if (!validEndpoint(body.endpoint) || typeof body.auth !== "string" || !B64URL.test(body.auth))
      return reply(400, { error: "bad input" });
    const row = await env.DB.prepare("SELECT auth FROM subscriptions WHERE endpoint = ?")
      .bind(body.endpoint).first();
    if (!row) return reply(200, { teams: [] });
    if (row.auth !== body.auth) return reply(403, { error: "auth mismatch" });
    const { results } = await env.DB.prepare(
      "SELECT team_id FROM sub_teams WHERE endpoint = ? ORDER BY team_id LIMIT ?")
      .bind(body.endpoint, MAX_TEAMS).all();
    return reply(200, { teams: results.map((r) => r.team_id) });
  }

  if (url.pathname === "/push/unsubscribe") {
    if (!validEndpoint(body.endpoint) || typeof body.auth !== "string" || !B64URL.test(body.auth))
      return reply(400, { error: "bad input" });
    const row = await env.DB.prepare("SELECT auth FROM subscriptions WHERE endpoint = ?")
      .bind(body.endpoint).first();
    if (!row) return reply(200, { ok: true, deleted: false });
    if (row.auth !== body.auth) return reply(403, { error: "auth mismatch" });
    await env.DB.batch([
      env.DB.prepare("DELETE FROM sub_teams WHERE endpoint = ?").bind(body.endpoint),
      env.DB.prepare("DELETE FROM sub_matches WHERE endpoint = ?").bind(body.endpoint),
      env.DB.prepare("DELETE FROM sub_leagues WHERE endpoint = ?").bind(body.endpoint),
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
  // أقنعة لم يرسلها العميل (زر نادٍ قديم بلا tt…): الموجود بالقاعدة يبقى، وإلا فريق/مباراة جديدة = LEGACY_TYPES (الأهداف فقط، كل ما كان يعرضه الزر القديم)،
  // ودوري جديد = DEFAULT_TYPES. العملاء الجدد يرسلون القناع دائماً فلا يمرّون من هنا.
  if (existing) {
    const keep = async (tbl, col) => Object.fromEntries(((await env.DB.prepare(`SELECT ${col} AS id, types FROM ${tbl} WHERE endpoint = ?`)
      .bind(v.endpoint).all()).results || []).map((r) => [r.id, r.types]));
    const [exT, exM, exL] = await Promise.all([keep("sub_teams", "team_id"), keep("sub_matches", "fixture"), keep("sub_leagues", "league")]);
    v.teamTypes = v.teamTypes.map(([id, m]) => [id, m === MASK_UNSET ? (exT[id] ?? LEGACY_TYPES) : m]);
    if (v.matchTypes) v.matchTypes = v.matchTypes.map(([id, m]) => [id, m === MASK_UNSET ? (exM[id] ?? LEGACY_TYPES) : m]);
    if (v.leagueTypes) v.leagueTypes = v.leagueTypes.map(([id, m]) => [id, m === MASK_UNSET ? (exL[id] ?? DEFAULT_TYPES) : m]);
  }
  v.teamTypes = v.teamTypes.map(([id, m]) => [id, m === MASK_UNSET ? LEGACY_TYPES : m]);
  if (v.matchTypes) v.matchTypes = v.matchTypes.map(([id, m]) => [id, m === MASK_UNSET ? LEGACY_TYPES : m]);
  if (v.leagueTypes) v.leagueTypes = v.leagueTypes.map(([id, m]) => [id, m === MASK_UNSET ? DEFAULT_TYPES : m]);
  // سقف عام: اشتراك جديد فقط يُرفض (تحديث قائم يمرّ دائماً) — 503 ليعرض الزر رسالة لطيفة
  if (!existing) {
    const cap = Number(env.MAX_SUBSCRIPTIONS) || MAX_SUBSCRIPTIONS;
    const c = await env.DB.prepare("SELECT COUNT(*) AS c FROM subscriptions").first();
    if (c && c.c >= cap) return reply(503, { error: "full" });
  }
  const now = Math.floor(Date.now() / 1000);
  // ⚠️ json_each: معاملان فقط مهما كان عدد الأندية (حدّ D1: 100 معامل/استعلام)
  const stmts = [
    env.DB.prepare(
      "INSERT INTO subscriptions (endpoint, p256dh, auth, lang, created_at, updated_at) " +
      "VALUES (?1, ?2, ?3, ?4, ?5, ?5) " +
      "ON CONFLICT(endpoint) DO UPDATE SET p256dh = ?2, lang = ?4, updated_at = ?5")
      .bind(v.endpoint, v.p256dh, v.auth, v.lang, now),
    env.DB.prepare("DELETE FROM sub_teams WHERE endpoint = ?").bind(v.endpoint),
    env.DB.prepare(
      "INSERT INTO sub_teams (endpoint, team_id, types) SELECT ?1, json_extract(value, '$[0]'), json_extract(value, '$[1]') FROM json_each(?2)")
      .bind(v.endpoint, JSON.stringify(v.teamTypes)),
  ];
  // مباريات مفردة: تُستبدل فقط حين يرسلها العميل (زر النادي القديم بلا `matches` لا يمسّها)
  if (v.matches) {
    stmts.push(
      env.DB.prepare("DELETE FROM sub_matches WHERE endpoint = ?").bind(v.endpoint),
      env.DB.prepare(
        "INSERT INTO sub_matches (endpoint, fixture, created_at, types) SELECT ?1, json_extract(value, '$[0]'), ?3, json_extract(value, '$[1]') FROM json_each(?2)")
        .bind(v.endpoint, JSON.stringify(v.matchTypes), now));
  }
  if (v.leagues) {
    stmts.push(
      env.DB.prepare("DELETE FROM sub_leagues WHERE endpoint = ?").bind(v.endpoint),
      env.DB.prepare(
        "INSERT INTO sub_leagues (endpoint, league, types) SELECT ?1, json_extract(value, '$[0]'), json_extract(value, '$[1]') FROM json_each(?2)")
        .bind(v.endpoint, JSON.stringify(v.leagueTypes)));
  }
  await env.DB.batch(stmts);
  return reply(200, { ok: true, teams: v.teams.length, ...(v.matches ? { matches: v.matches.length } : {}), ...(v.leagues ? { leagues: v.leagues.length } : {}) });
}

// ── ربط كشف الأهداف بالإرسال (دفعة 5) ──
// GOAL_PUSH="on" فقط يرسل؛ أي قيمة أخرى = تسجيل الأحداث بلا إرسال ولا لمس D1.
// الهدف: INSERT OR IGNORE بـsent ثم إرسال فقط إن changes=1 (سحب مكرر/إعادة محاولة = صفر تكرار).
// إلغاء (VAR): حذف صفوف sent لنفس المباراة التي نتيجتها أعلى من الحالية (ليصل الهدف إن عاد)،
// ثم إشعار "أُلغي" بنفس الـtag فيستبدل إشعار الهدف.
const NAMES_URL = "https://saffara.app/assets/team_names.json";
const PLAYERS_URL = "https://saffara.app/assets/player_names.json";
const NAMES_TTL_MS = 60 * 60 * 1000;
const jsonCache = {};   // url -> {at, data}

// JSON من الموقع بكاش ساعة؛ عند الفشل: النسخة القديمة إن وُجدت وإلا {}
async function cachedJson(url, ttl = NAMES_TTL_MS) {
  const now = Date.now();
  const c = jsonCache[url];
  if (c && now - c.at < ttl) return c.data;
  try {
    const r = await fetch(url);
    if (r.ok) {
      const data = await r.json();
      if (data && typeof data === "object") { jsonCache[url] = { at: now, data }; return data; }
    }
  } catch (e) {}
  return c ? c.data : {};
}
const teamNames = () => cachedJson(NAMES_URL);     // {team_id: {ar, en}}
// {player_id: {ar?, en}} + "_n": {"<team_id>|<اسم المزوّد>": {ar}} (الأردن والعراق بلا معرّفات لاعبين بالـDB)
const playerNames = () => cachedJson(PLAYERS_URL);

// ── اسم الهدّاف (7 أكتوبر؛ 10 أكتوبر: من قائمة الموقع) ──
// خطوة التحديث لا تطلب شيئاً من المزوّد: تقرأ القائمة `sc:<id>` التي يكتبها مستهلك live_scorers (طلب events واحد لكل هدف —
// نفس مصدر أسماء صفحة المباراة، فاسم التنبيه = اسم الصفحة دائماً). الهدف رقم `score` للفريق الذي سجّل (لا آخر هدف). حارس التأخّر:
// إن كان عدد أهداف الفريق بالقائمة أقل من نتيجته فالقائمة لم تصل بعد (`lag`) فنعيد بتأخيرات SCORER_DELAYS ثم نترك بلا اسم.
// الصف المخزَّن [side, دقيقة, إضافي, اسم لاتيني (عائلة), عربي مؤكَّد أو "", وسم]؛ side = المستفيد (الهدف العكسي للخصم).
async function lookupLiveScorer(env, msg) {
  if (msg.side !== "home" && msg.side !== "away") return { sc: null, lookup: "noside" };
  let l = [];
  try {
    const raw = await env.LIVE_KV.get("sc:" + msg.fixture);
    const j = raw ? JSON.parse(raw) : null;
    if (j && Array.isArray(j.l)) l = j.l;
  } catch (e) { return { sc: null, lookup: "error" }; }
  const side = msg.side === "home" ? "h" : "a";
  const mine = l.filter((r) => r && r[0] === side);
  if (!mine.length) return { sc: null, lookup: "nomatch" };
  const score = side === "h" ? msg.h : msg.a;
  if (mine.length < score) return { sc: null, lookup: "lag" };
  const r = mine[Math.max(0, score - 1)];
  // دقيقة حدث المزوّد لهذا الهدف (90+X عند وجود إضافي): الكشف يتأخّر دقائق فدقيقته أكبر؛ التحديث يصحّحها
  const em = Number.isFinite(r[1]) && r[1] > 0 ? (r[2] > 0 ? `${r[1]}+${r[2]}` : r[1]) : null;
  return { sc: { n: r[3] || "", ar: r[4] || "", tag: r[5] || "" }, lookup: "hit", minute: em };
}

// «A. Ersan» / «N. Al Rawabdeh» => اسم العائلة فقط («Ersan» / «Al Rawabdeh»)؛ الاسم الكامل يبقى كما هو.
function surname(n) {
  const m = /^(?:[A-Za-z]\.\s*)+(\S.*)$/.exec(n.trim());
  return m ? m[1] : n;
}

// اسم الهدّاف + وسم جزاء/عكسي. العربي: فقط اسم عربي مؤكد (بالمعرّف أو بمفتاح الاسم) وإلا لا شيء — لا يوضع
// إنجليزي داخل النص العربي. الإنجليزي: الاسم الكامل من الملف وإلا اسم المزوّد.
// وسما الجزاء/العكسي بكلمات كاملة (12 أكتوبر، نمط FotMob): « (ركلة جزاء)» « (هدف عكسي)» / " (pen)" " (OG)" — من تفصيل حدث المزوّد
const PEN_TAG = { ar: " (\u0631\u0643\u0644\u0629 \u062C\u0632\u0627\u0621)", en: " (pen)" };
const OG_TAG = { ar: " (\u0647\u062F\u0641 \u0639\u0643\u0633\u064A)", en: " (OG)" };
function scorerLabel(lang, sc, pn) {
  if (!sc) return "";
  if (sc.n !== undefined) {   // من قائمة الموقع (lookupLiveScorer): العربي مؤكَّد مسبقاً، واللاتيني اسم العائلة
    const nm0 = lang === "ar" ? sc.ar : sc.n;
    if (!nm0) return "";
    return nm0 + (sc.tag === "p" ? PEN_TAG[lang === "ar" ? "ar" : "en"] : sc.tag === "og" ? OG_TAG[lang === "ar" ? "ar" : "en"] : "");
  }
  const byId = sc.pid != null ? pn[sc.pid] : null;
  const byName = sc.pname && sc.ptid != null && pn._n ? pn._n[sc.ptid + "|" + sc.pname] : null;
  let nm = lang === "ar" ? ((byId && byId.ar) || (byName && byName.ar)) : ((byId && byId.en) || sc.pname);
  if (!nm) return "";
  if (lang !== "ar") nm = surname(nm);
  const tag = sc.pdet === "Penalty" ? PEN_TAG[lang === "ar" ? "ar" : "en"]
    : sc.pdet === "Own Goal" ? OG_TAG[lang === "ar" ? "ar" : "en"] : "";
  return nm + tag;
}

// ⚠️ النص العربي (6 أكتوبر): النتيجة داخل جملة عربية تنقلب أرقامها (الرقم 1 يلتصق باسم السلط). لذلك كل رقم
//    وكل شرطة بين RLM (U+200F) يثبّت الاتجاه، ورقم الفريق الذي سجّل بين قوسين «(1)». الأقواس تُكتب بترتيبها
//    المنطقي ( ثم الرقم ثم ) وتنعكس بصرياً تلقائياً داخل فقرة RTL — لا تُقلب يدوياً. العنوان: «هدف للفيصلي»
//    باسم الفريق الذي سجّل (side: "home"|"away" من مقارنة h/a بالنتيجة السابقة عند الكشف)؛ بلا side عنوان عام.
//    الإنجليزي بلا تغيير.
const RLM = "\u200F";
function arForTeam(name) {   // للـ + الفيصلي => للفيصلي ، لـ + نهضة بركان => لنهضة بركان
  return name.startsWith("\u0627\u0644") ? "\u0644\u0644" + name.slice(2) : "\u0644" + name;
}
function goalPayload(lang, kind, ev, names, m, sc, pn, upd) {
  const pick = (id, provider) => {
    const n = names[id] || {};
    return (lang === "ar" ? (n.ar || n.en) : (n.en || n.ar)) || provider || "";
  };
  const home = pick(ev.th, m && m.nh), away = pick(ev.ta, m && m.na);
  const min = ev.minute;
  const url = (lang === "en" ? "/en/matches/" : "/matches/") + ev.fixture + ".html";
  // tag لكل نتيجة: الإلغاء يحمل tag الهدف الملغى (النتيجة قبل الإلغاء ph/pa) فيستبدل ذلك الإشعار وحده
  const tag = kind === "goal" || ev.ph == null || ev.pa == null
    ? `goal-${ev.fixture}-${ev.h}-${ev.a}` : `goal-${ev.fixture}-${ev.ph}-${ev.pa}`;
  const who = kind === "goal" ? scorerLabel(lang, sc, pn || {}) : "";
  if (upd && !who && !ev.mchg) return null;   // تحديث بلا اسم بهذه اللغة وبلا تغيير دقيقة = إشعار مطابق للأول: لا يُرسَل
  const extra = upd ? { renotify: false } : {};   // نفس الـtag يحلّ محلّ الأول بلا رنّة جديدة (sw.js يقرأ renotify)
  const team = ev.side === "home" ? home : ev.side === "away" ? away : "";   // الفريق الذي سجّل / ألغي هدفه
  const mark = kind === "goal";   // رقم من سجّل بين أقواس مربّعة بالهدف فقط
  // ⚠️ صيغة الهدف (12 أكتوبر، نمط FotMob، موافقة عمرو): العنوان «<الفريق> يسجّل!» / "<Team> scores!"؛ السطر 1 «<الدقيقة>' <الهدّاف>[ (ركلة جزاء)]»
  //    (بلا اسم معروف بعد: الدقيقة وحدها، والتحديث يحلّ محلّها بنفس الـtag وrenotify:false)؛ السطر 2 النتيجة مع [ ] حول رقم من سجّل:
  //    «الزمالك 0 - [1] الأهلي». بلا «Goal for» ولا سطر دقيقة منفصل ولا إيموجي. الإلغاء كما كان (النتيجة ثم لا سطر ثانٍ).
  if (lang !== "ar") {
    const hs = mark && ev.side === "home" ? `[${ev.h}]` : String(ev.h);
    const as = mark && ev.side === "away" ? `[${ev.a}]` : String(ev.a);
    const score = `${home} ${hs} - ${as} ${away}`;
    if (kind === "goal") {
      const title = team ? `${team} scores!` : "Goal!";
      const l1 = [min != null ? `${min}'` : "", who].filter(Boolean).join(" ");
      return { title, body: l1 ? l1 + "\n" + score : score, tag, url, ...extra };
    }
    const title = team ? `\u274C Goal disallowed \u2013 ${team}` : "\u274C Goal disallowed";
    return { title, body: score, tag, url, ...extra };
  }
  // ⚠️ العربي: كل رقم وكل شرطة بين RLM (U+200F) كي لا تنقلب الأرقام داخل الجملة؛ رقم من سجّل بين [ ] مكتوباً بترتيبه المنطقي
  //    فينعكس بصرياً صحيحاً داخل فقرة RTL (الأقواس المربّعة تنعكس كالدائرية).
  const num = (n, m2) => RLM + (m2 ? `[${n}]` : String(n)) + RLM;
  const score = `${home} ${num(ev.h, mark && ev.side === "home")} ${RLM}-${RLM} ${num(ev.a, mark && ev.side === "away")} ${away}`;
  if (kind === "goal") {
    const title = team ? `${team} \u064A\u0633\u062C\u0651\u0644!` : "\u0647\u062F\u0641!";
    const l1 = [min != null ? RLM + `${min}'` + RLM : "", who].filter(Boolean).join(" ");
    return { title, body: l1 ? l1 + "\n" + score : score, tag, url, ...extra };
  }
  const title = team ? `\u274C \u0623\u064F\u0644\u063A\u064A \u0647\u062F\u0641 ${team}` : "\u274C \u0623\u064F\u0644\u063A\u064A \u0627\u0644\u0647\u062F\u0641";
  return { title, body: score, tag, url, ...extra };
}

async function sendGoalPushes(env, events, m) {
  if (!events || !events.length || !env.DB || env.GOAL_PUSH !== "on") return;
  if (!env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY) return;
  // الإلغاءات أولاً (حدث نادر يجمع هدفاً وإلغاءً بنفس السحب)
  const ordered = [...events.filter((e) => e.type === "goal_cancelled"), ...events.filter((e) => e.type === "goal")];
  for (const ev of ordered) {
    const stat = { fixture: ev.fixture, kind: ev.type, sent: 0, gone: 0, failed: 0, capped: false };
    try {
      if (ev.type === "goal") {
        const ins = await env.DB.prepare("INSERT OR IGNORE INTO sent (fixture, h, a) VALUES (?, ?, ?)")
          .bind(ev.fixture, ev.h, ev.a).run();
        if (!(ins && ins.meta && ins.meta.changes === 1)) { stat.duplicate = true; console.log(JSON.stringify({ type: "goal_push", ...stat })); continue; }
      } else {
        await env.DB.prepare("DELETE FROM sent WHERE fixture = ? AND (h > ? OR a > ?)")
          .bind(ev.fixture, ev.h, ev.a).run();
        // الهدف الملغى قد يعود بنفس النتيجة: لا يبقى «تحديث الهدّاف» مأخوذاً لها (معزول: لا يمنع إشعار الإلغاء)
        try {
          await env.DB.prepare("DELETE FROM scorer_update WHERE fixture = ? AND (h > ? OR a > ?)")
            .bind(ev.fixture, ev.h, ev.a).run();
        } catch (e) { console.log(JSON.stringify({ type: "goal_push_error", fixture: ev.fixture, error: "scorer_update_cleanup" })); }
      }
      if (!env.GOAL_QUEUE) { stat.error = "no_queue"; stat.failed++; console.log(JSON.stringify({ type: "goal_push", ...stat })); continue; }
      const cur = m[String(ev.fixture)] || {};
      // رسالة واحدة بالهدف؛ المستهلك يقسّم المشتركين دفعات. ts = لحظة الكشف (TTL 10 دقائق يُحسب منه)
      await env.GOAL_QUEUE.send({
        fixture: ev.fixture, kind: ev.type === "goal" ? "goal" : "cancel", th: ev.th, ta: ev.ta, lg: ev.league,
        h: ev.h, a: ev.a, minute: ev.minute, offset: 0, ts: Date.now(), nh: cur.nh, na: cur.na,
        ph: ev.prev_h, pa: ev.prev_a,
        side: ev.type === "goal" ? (ev.h > ev.prev_h ? "home" : "away") : (ev.h < ev.prev_h ? "home" : "away"),
      });
      stat.queued = true;
    } catch (e) {
      stat.failed++; stat.error = String((e && e.message) || e);
    }
    console.log(JSON.stringify({ type: "goal_push", fixture: stat.fixture, kind: stat.kind, queued: !!stat.queued,
      ...(stat.error ? { error: stat.error } : {}) }));
  }
}

// ── المستهلك: صفحة واحدة من المشتركين لرسالة هدف ──
// الصفحة 200 مشترك بترتيب endpoint ثابت ومؤشر `after` (آخر endpoint) لا offset رقمي: حذف 404/410
// بين الصفحات يزيح الإزاحة الرقمية فيُتخطى مشتركون. `offset` يبقى عدّاداً للسجل فقط.
// 1) الأقدم من 10 دقائق لا يُرسل (TTL). 2) الصفحة التالية تُوضع بالطابور **قبل** الإرسال: فإن فشل ذلك
// نرمي والطابور يعيد الرسالة ولم يُرسل شيء (بلا تكرار). 3) الفشل العابر لبعض المشتركين يُعاد بأنفسهم فقط
// برسالة `only` بتأخير متزايد (حتى 3 محاولات) — من وصلهم لا يُعاد لهم.
//
// ⚠️ إشعار الهدف بخطوتين (8 أكتوبر): (1) الإشعار يُرسَل فوراً بلا اسم الهدّاف (عنوان + نتيجة + دقيقة) — لا طلب للمزوّد
//    بمسار الإرسال إطلاقاً. (2) بعد إرسال أول صفحة تُوضع رسالة `goal_scorer` بتأخير 60 ث: المستهلك (scorerUpdateStep)
//    يجلب fixtures/events، فإن وجد الهدّاف يُرسل **نفس الإشعار بنفس الـtag** + سطر الاسم (renotify:false) فيحلّ
//    محلّ الأول. لم يجده: محاولتان إضافيتان بتأخير 120 ثم 240 ث (كل تأخير من المحاولة السابقة؛ المجموع 7 دقائق < TTL)
//    ثم يُترك. لا يُرسَل التحديث إن تغيّرت نتيجة المباراة (إلغاء أو هدف بعده)، ولا أكثر من مرة لكل هدف (`scorer_update`).
const GOAL_PAGE = 200;
const GOAL_RETRY_MAX = 3;
const SCORER_DELAYS = [60, 120, 240];   // ثوانٍ قبل المحاولة 0 / 1 / 2 (كل واحدة من سابقتها)
// ⚠️ محاولات متأخرة صامتة (13 أكتوبر 2026، مباراة 1644210): الاسم قد لا يصل بـ7 دقائق، ودقيقة الحدث قد تتغيّر لاحقاً (10' ← 4').
//    الخطوات 3/4/5 عند 8 و15 و30 دقيقة **من لحظة الكشف** (ts): كل واحدة تجلب fixtures/events من جديد (طلب واحد، يحدّث `sc:<id>` أيضاً)
//    ثم: بلا اسم مُرسَل بعدُ ← تحديث الاسم؛ أُرسل تحديث وتغيّرت الدقيقة/الاسم ← **تصحيح واحد** فقط (corrected=1)؛ لا تغيّر ← لا إرسال.
//    كلها بنفس الـtag وrenotify:false. الحجز بـD1 `scorer_update` (minute/name/corrected، الهجرة 0007): لا تحديث مكرّر.
const SCORER_FAST = SCORER_DELAYS.length;                // الخطوات 0..2 تقرأ قائمة KV فقط (بلا طلب مزوّد)
const SCORER_LATE_AT = [480, 900, 1800];                 // ثوانٍ من الكشف للخطوات 3/4/5
const SCORER_STEPS = SCORER_FAST + SCORER_LATE_AT.length;
const SCORER_LATE_TTL_SECS = 35 * 60;                    // عمر رسالة التحديث/المتابعة الأقصى (الإشعار الأول يبقى بـ PUSH_TTL_SECS)
function scorerStepDelay(step, ts) {
  if (step < SCORER_FAST) return SCORER_DELAYS[step];
  return Math.max(60, Math.round(SCORER_LATE_AT[step - SCORER_FAST] - (Date.now() - ts) / 1000));
}

async function goalPushPage(env, msg) {
  const base = { type: "goal_push", fixture: msg.fixture, kind: msg.kind, offset: msg.offset || 0,
    ...(msg.sim ? { sim: true } : {}), ...(msg.upd ? { upd: true } : {}) };
  if (env.GOAL_PUSH !== "on") { console.log(JSON.stringify({ ...base, skipped: "off" })); return; }
  if (!(Date.now() - msg.ts <= (msg.upd ? SCORER_LATE_TTL_SECS : PUSH_TTL_SECS) * 1000)) {   // التحديث المتأخر (اسم/تصحيح) يعيش أطول من الأول
    console.log(JSON.stringify({ ...base, expired: true, sent: 0, gone: 0, failed: 0 }));
    return;
  }
  const cols = "SELECT endpoint, p256dh, auth, lang FROM subscriptions WHERE ";
  let subs, nextAfter = null;
  if (Array.isArray(msg.only)) {
    subs = (await env.DB.prepare(cols + "endpoint IN (SELECT value FROM json_each(?)) ORDER BY endpoint")
      .bind(JSON.stringify(msg.only)).all()).results;
  } else if (msg.admin) {   // تجربة /push/simulate بـadmin_only: أجهزة المشغّل فقط، بلا ترقيم
    subs = (await env.DB.prepare(cols + "endpoint IN (SELECT endpoint FROM admin_devices) ORDER BY endpoint")
      .all()).results;
  } else {
    const ids = [...new Set([msg.th, msg.ta].filter((x) => Number.isInteger(x)))];
    if (!ids.length) return;
    // مشتركو الفريقين + المباراة + الدوري بنوع «هدف» (13 أكتوبر، 3E): UNION فمن يتابع بأكثر من طريق يصله إشعار واحد
    const rw = recipientWhere(ids, msg.fixture, msg.lg, T_GOAL);
    const rows = (await env.DB.prepare(cols + "endpoint > ? AND " + rw.sql + " ORDER BY endpoint LIMIT ?")
      .bind(msg.after || "", ...rw.binds, GOAL_PAGE + 1).all()).results;
    subs = rows.slice(0, GOAL_PAGE);
    if (rows.length > GOAL_PAGE) nextAfter = subs[GOAL_PAGE - 1].endpoint;
  }
  // بلا مشتركين: لا طلب للمزوّد (صفر كلفة)
  if (!subs.length) { console.log(JSON.stringify({ ...base, sent: 0, gone: 0, failed: 0 })); return; }
  // الهدّاف: الإشعار الأول بلا اسم دائماً (sc=null). الاسم يصل فقط برسالة التحديث (upd) التي يحمل جسمها `sc`
  // من scorerUpdateStep، ويُحمَل بالصفحات التالية وإعادات الفاشلين.
  const sc = msg.sc || null;
  const core = { fixture: msg.fixture, kind: msg.kind, th: msg.th, ta: msg.ta, lg: msg.lg, h: msg.h, a: msg.a,
    minute: msg.minute, ts: msg.ts, nh: msg.nh, na: msg.na, side: msg.side, ph: msg.ph, pa: msg.pa, sc, scd: true,
    ...(msg.sim ? { sim: true } : {}), ...(msg.upd ? { upd: true } : {}), ...(msg.mchg ? { mchg: true } : {}), ...(msg.admin ? { admin: true } : {}) };
  if (nextAfter) await env.GOAL_QUEUE.send({ ...core, offset: (msg.offset || 0) + GOAL_PAGE, after: nextAfter });
  const [names, pn] = await Promise.all([teamNames(), msg.kind === "goal" ? playerNames() : Promise.resolve({})]);
  const ev = { fixture: msg.fixture, th: msg.th, ta: msg.ta, h: msg.h, a: msg.a, minute: msg.minute, side: msg.side,
    ph: msg.ph, pa: msg.pa, mchg: !!msg.mchg };
  const out = await deliver(env, subs, (lang) => goalPayload(lang, msg.kind, ev, names, { nh: msg.nh, na: msg.na }, sc, pn, !!msg.upd));
  // الخطوة 2: تُجدوَل مرة واحدة لكل هدف — من أول صفحة للإرسال الأصلي (لا من الصفحات التالية ولا الإعادات ولا التحديث نفسه).
  // فشل الجدولة لا يُعيد الصفحة (لا تكرار للإشعار): يُسجَّل فقط.
  let scheduled = false;
  if (msg.kind === "goal" && !msg.upd && !msg.after && !(msg.offset > 0) && !Array.isArray(msg.only) && !msg.attempt
      && !(msg.sim && !msg.simsc)) {
    try {
      await env.GOAL_QUEUE.send({ ...core, kind: "goal_scorer", step: 0, sc: undefined,
        ...(msg.simsc ? { simsc: msg.simsc } : {}) }, { delaySeconds: SCORER_DELAYS[0] });
      scheduled = true;
    } catch (e) {
      console.log(JSON.stringify({ type: "goal_push_error", fixture: msg.fixture, error: "scorer_schedule_failed" }));
    }
  }
  let retrying = 0;
  const attempt = msg.attempt || 0;
  if (out.retryable.length && attempt < GOAL_RETRY_MAX) {
    try {
      await env.GOAL_QUEUE.send({ ...core, offset: msg.offset || 0, only: out.retryable, attempt: attempt + 1 },
        { delaySeconds: 5 * 2 ** attempt });
      retrying = out.retryable.length;
    } catch (e) {
      console.log(JSON.stringify({ type: "goal_push_error", fixture: msg.fixture, error: "requeue_failed" }));
    }
  }
  console.log(JSON.stringify({ ...base, sent: out.sent, gone: out.gone, failed: out.failed, retrying,
    ...(out.skipped ? { skipped_no_name: out.skipped } : {}), ...(scheduled ? { scorer_scheduled: SCORER_DELAYS[0] } : {}),
    ...(attempt ? { attempt } : {}) }));
}

// ── تنبيهات غير الأهداف (13 أكتوبر 2026، دفعة 3E): انطلاق · نهاية الشوط الأول · بداية الثاني · نهاية المباراة · بطاقة حمراء · تذكير قبل 30 د ──
// لا طلبات مزوّد إضافية إطلاقاً: الحالة من انتقالات `s` بين سحبين، والبطاقات من `v` (أحداث الردّ الحيّ)، والنهاية من finals، والتذكير من next_kickoffs.json.
// منع التكرار: جدول ev_sent (أول INSERT يفوز). المستلمون بالقناع (recipientWhere). نفس نمط عنوان إشعار الهدف، وrenotify غير مستعمل.
function statusEvents(prevM, m) {
  const out = [];
  for (const [id, cur] of Object.entries(m)) {
    const old = prevM && prevM[id];
    const base = { fixture: Number(id), th: cur.th, ta: cur.ta, lg: cur.lg, nh: cur.nh, na: cur.na, h: cur.h ?? 0, a: cur.a ?? 0 };
    if (cur.s === "1H" && !old && Number.isFinite(cur.e) && cur.e <= 5) out.push({ evt: "ko", ...base });
    if (cur.s === "HT" && old && old.s !== "HT") out.push({ evt: "ht", ...base });
    if (cur.s === "2H" && old && old.s === "HT") out.push({ evt: "sh", ...base });
  }
  return out;
}
// بطاقة حمراء جديدة: مفتاحها دقيقة+إضافي+لاعب؛ الأساس = أحداث السحب السابق (prev.v) ويلزم prev.ve (وإلا لا أساس معروف فلا نعلن قديماً)
function redCardEvents(prev, ev, m, evOk) {
  const out = [];
  if (!evOk || !prev || !prev.ve || !prev.m) return out;
  for (const [id, list] of Object.entries(ev)) {
    if (!prev.m[id] || !m[id]) continue;   // ظهرت للتو: لا أساس
    const seen = new Set(((prev.v && prev.v[id]) || []).filter((x) => x[2] === "c" && (x[3] === "r" || x[3] === "yr")).map((x) => `${x[0]}|${x[1]}|${x[4]}`));
    for (const x of list) {
      if (x[2] !== "c" || !(x[3] === "r" || x[3] === "yr")) continue;
      const k = `${x[0]}|${x[1]}|${x[4]}`;
      if (seen.has(k)) continue;
      const cur = m[id];
      out.push({ evt: "red", k, fixture: Number(id), th: cur.th, ta: cur.ta, lg: cur.lg, nh: cur.nh, na: cur.na, h: cur.h ?? 0, a: cur.a ?? 0,
        minute: x[0], player: x[4], side: x[6] === "h" ? "home" : "away" });
    }
  }
  return out;
}
// ضربة جزاء ضائعة: حدث Goal بتفصيل m بـ`v` (مفتاحه دقيقة+إضافي+لاعب)؛ نفس أساس البطاقات الحمراء (prev.ve) كي لا نعلن قديماً بعد فجوة
function missedPenaltyEvents(prev, ev, m, evOk) {
  const out = [];
  if (!evOk || !prev || !prev.ve || !prev.m) return out;
  for (const [id, list] of Object.entries(ev)) {
    if (!prev.m[id] || !m[id]) continue;
    const seen = new Set(((prev.v && prev.v[id]) || []).filter((x) => x[2] === "g" && x[3] === "m").map((x) => `${x[0]}|${x[1]}|${x[4]}`));
    for (const x of list) {
      if (x[2] !== "g" || x[3] !== "m") continue;
      const k = `${x[0]}|${x[1]}|${x[4]}`;
      if (seen.has(k)) continue;
      const cur = m[id];
      out.push({ evt: "mp", k, fixture: Number(id), th: cur.th, ta: cur.ta, lg: cur.lg, nh: cur.nh, na: cur.na, h: cur.h ?? 0, a: cur.a ?? 0,
        minute: x[0], player: x[4], side: x[6] === "h" ? "home" : "away" });
    }
  }
  return out;
}
const ALERT_BIT = { ko: T_KICKOFF, ht: T_HT, sh: T_SH, ft: T_FT, red: T_RED, rem: T_REM, mp: T_MISSPEN, lineup: T_LINEUP };
async function sendAlertPushes(env, list) {
  if (!list || !list.length || !env.DB || env.GOAL_PUSH !== "on") return;
  if (!env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY || !env.GOAL_QUEUE) return;
  const ts = Math.floor(Date.now() / 1000);
  for (const e of list) {
    try {
      const ins = await env.DB.prepare("INSERT OR IGNORE INTO ev_sent (fixture, kind, k, ts) VALUES (?, ?, ?, ?)")
        .bind(e.fixture, e.evt, e.k || "", ts).run();
      if (!(ins && ins.meta && ins.meta.changes === 1)) continue;
      await env.GOAL_QUEUE.send({ ...e, kind: "alert", offset: 0, ts: Date.now() });
      console.log(JSON.stringify({ type: "alert_push", evt: e.evt, fixture: e.fixture, queued: true }));
    } catch (err) {
      console.log(JSON.stringify({ type: "alert_push_error", evt: e.evt, fixture: e.fixture, error: String((err && err.message) || err) }));
    }
  }
}
function alertPayload(lang, e, names) {
  const pick = (id, provider) => { const n = names[id] || {}; return (lang === "ar" ? (n.ar || n.en) : (n.en || n.ar)) || provider || ""; };
  const home = pick(e.th, e.nh), away = pick(e.ta, e.na);
  const url = (lang === "en" ? "/en/matches/" : "/matches/") + e.fixture + ".html";
  const ar = lang === "ar";
  const vs = `${home} ${ar ? RLM + "-" + RLM : "-"} ${away}`;
  const score = ar
    ? `${home} ${RLM}${e.h}${RLM} ${RLM}-${RLM} ${RLM}${e.a}${RLM} ${away}`
    : `${home} ${e.h} - ${e.a} ${away}`;
  const tag = `${e.evt}-${e.fixture}` + (e.k ? "-" + e.k.replace(/[^0-9A-Za-z|]/g, "").slice(0, 24) : "");
  const mk = (title, body) => ({ title, body, tag, url });
  switch (e.evt) {
    case "ko": return mk(ar ? "\u0627\u0646\u0637\u0644\u0642\u062A \u0627\u0644\u0645\u0628\u0627\u0631\u0627\u0629" : "Kick-off!", vs);
    case "ht": return mk(ar ? "\u0646\u0647\u0627\u064A\u0629 \u0627\u0644\u0634\u0648\u0637 \u0627\u0644\u0623\u0648\u0644" : "Half-time", score);
    case "sh": return mk(ar ? "\u0628\u062F\u0627\u064A\u0629 \u0627\u0644\u0634\u0648\u0637 \u0627\u0644\u062B\u0627\u0646\u064A" : "Second half underway", score);
    case "ft": return mk(ar ? "\u0627\u0646\u062A\u0647\u062A \u0627\u0644\u0645\u0628\u0627\u0631\u0627\u0629" : "Full-time", score);
    case "rem": return mk(ar ? "\u062A\u0646\u0637\u0644\u0642 \u0628\u0639\u062F 30 \u062F\u0642\u064A\u0642\u0629" : "Kick-off in 30 minutes", vs);
    case "lineup": return { ...mk(ar ? "\u0627\u0644\u062A\u0634\u0643\u064A\u0644\u0629 \u0627\u0644\u0631\u0633\u0645\u064A\u0629" : "Lineups out", ar ? vs : `${home} vs ${away}`), url: url + "#lineups" };
    case "mp": {
      const team = e.side === "home" ? home : away;
      const title = ar ? `\u0636\u0631\u0628\u0629 \u062C\u0632\u0627\u0621 \u0636\u0627\u0626\u0639\u0629 \u2013 ${team}` : `Missed penalty \u2013 ${team}`;
      const l1 = [Number.isFinite(e.minute) ? (ar ? RLM + e.minute + "'" + RLM : e.minute + "'") : "", e.player || ""].filter(Boolean).join(" ");
      return mk(title, l1 ? l1 + "\n" + score : score);
    }
    case "red": {
      const team = e.side === "home" ? home : away;
      const title = ar ? `\uD83D\uDFE5 \u0628\u0637\u0627\u0642\u0629 \u062D\u0645\u0631\u0627\u0621 \u2013 ${team}` : `\uD83D\uDFE5 Red card \u2013 ${team}`;
      const l1 = [Number.isFinite(e.minute) ? (ar ? RLM + e.minute + "'" + RLM : e.minute + "'") : "", e.player || ""].filter(Boolean).join(" ");
      return mk(title, l1 ? l1 + "\n" + score : score);
    }
  }
  return null;
}
async function alertPushPage(env, msg) {
  const base = { type: "alert_push", evt: msg.evt, fixture: msg.fixture, offset: msg.offset || 0 };
  if (env.GOAL_PUSH !== "on") { console.log(JSON.stringify({ ...base, skipped: "off" })); return; }
  if (!(Date.now() - msg.ts <= PUSH_TTL_SECS * 1000)) { console.log(JSON.stringify({ ...base, expired: true, sent: 0 })); return; }
  const bit = ALERT_BIT[msg.evt];
  if (!bit) return;
  const cols = "SELECT endpoint, p256dh, auth, lang FROM subscriptions WHERE ";
  let subs, nextAfter = null;
  if (Array.isArray(msg.only)) {
    subs = (await env.DB.prepare(cols + "endpoint IN (SELECT value FROM json_each(?)) ORDER BY endpoint").bind(JSON.stringify(msg.only)).all()).results;
  } else {
    const rw = recipientWhere([msg.th, msg.ta], msg.fixture, msg.lg, bit);
    const rows = (await env.DB.prepare(cols + "endpoint > ? AND " + rw.sql + " ORDER BY endpoint LIMIT ?")
      .bind(msg.after || "", ...rw.binds, GOAL_PAGE + 1).all()).results;
    subs = rows.slice(0, GOAL_PAGE);
    if (rows.length > GOAL_PAGE) nextAfter = subs[GOAL_PAGE - 1].endpoint;
  }
  if (!subs.length) { console.log(JSON.stringify({ ...base, sent: 0, gone: 0, failed: 0 })); return; }
  const { kind, ...core } = msg;
  if (nextAfter) await env.GOAL_QUEUE.send({ ...core, kind: "alert", offset: (msg.offset || 0) + GOAL_PAGE, after: nextAfter });
  const names = await teamNames();
  const out = await deliver(env, subs, (lang) => alertPayload(lang, msg, names));
  const attempt = msg.attempt || 0;
  let retrying = 0;
  if (out.retryable.length && attempt < GOAL_RETRY_MAX) {
    try {
      await env.GOAL_QUEUE.send({ ...core, kind: "alert", offset: msg.offset || 0, only: out.retryable, attempt: attempt + 1 }, { delaySeconds: 5 * 2 ** attempt });
      retrying = out.retryable.length;
    } catch (e) { console.log(JSON.stringify({ type: "goal_push_error", fixture: msg.fixture, error: "requeue_failed" })); }
  }
  console.log(JSON.stringify({ ...base, sent: out.sent, gone: out.gone, failed: out.failed, retrying }));
}

// تذكير قبل 30 دقيقة: يمسح مواعيد اليوم من assets/next_kickoffs.json (حقل f المضاف: [ts, id, th, ta, lg, nh, na]؛ كاش 10 دقائق). يعمل قبل
// أي خروج خمول بالجدولة، والنافذة 28–32 دقيقة قبل الانطلاق + ev_sent يضمنان مرة واحدة ولو فاتت دقيقة.
const REMINDER_MIN_SECS = 28 * 60, REMINDER_MAX_SECS = 32 * 60;
async function sendReminders(env) {
  if (env.GOAL_PUSH !== "on" || !env.DB) return;
  let j;
  try { j = await cachedJson(KICKOFFS_URL, KICKOFFS_TTL_MS); } catch (e) { return; }
  if (!j || !Array.isArray(j.f)) return;
  const now = Math.floor(Date.now() / 1000);
  const due = [];
  for (const r of j.f) {
    if (!Array.isArray(r) || !Number.isFinite(r[0])) continue;
    const dt = r[0] - now;
    if (dt >= REMINDER_MIN_SECS && dt <= REMINDER_MAX_SECS)
      due.push({ evt: "rem", fixture: r[1], th: r[2], ta: r[3], lg: r[4], nh: r[5], na: r[6], h: 0, a: 0 });
  }
  if (due.length) await sendAlertPushes(env, due);
}

// ── «التشكيلة الرسمية» (19 أكتوبر 2026): T_LINEUP + التشكيلة الحيّة لصفحة المباراة ──
// كل مباريات f بـnext_kickoffs.json بنافذة KO-60..KO+5 دقيقة لم تُنجَز بعد (ev_sent fixture=<id> kind='lineup'): fixtures?ids= (حتى 20
// بطلب) كل 5 دقائق. التشكيلتان معاً بـstartXI = تُخزَّن مضغوطة بـKV lu:<id> (36 ساعة، يقرؤها GET /lineup?id=) ثم تنبيه مرة واحدة لمشتركي
// بتّ 256 فقط؛ بلا مشترك (أو GOAL_PUSH مطفأ) = صف ev_sent وحده (منجَزة، لا طابور). فشل الكتابة = لا إنجاز (تُعاد بالدورة التالية).
// حارس الحصة نفسه (EVENTS_MIN_REMAINING) على آخر رأس معروف بهذا الـisolate (السحب الحيّ أو طلب تشكيلات سابق)؛ مجهول = نسحب.
// مسبار 18 أكتوبر: القطري ظهر قبل الانطلاق بأكثر من 3 دقائق، العراقي لم يظهر حتى بعده بـ37 دقيقة.
const LINEUP_LEAD_SECS = 60 * 60, LINEUP_TAIL_SECS = 5 * 60, LINEUP_EVERY_MIN = 5;
const LINEUP_KV_TTL = 36 * 3600;
// العراقي (542) والأردني (387): المزوّد لا يوفّر لهما تشكيلات أصلاً (درس 25؛ مسبار 18 أكتوبر: العراقي لا شيء حتى KO+37) — لا طلبات لهما
const LINEUP_SKIP_LEAGUES = new Set([542, 387]);
let lastRemaining = NaN;   // ذاكرة الـisolate فقط (تضيع مع إعادة التشغيل)
const hasXI = (L, team) => L.some((x) => x && x.team && x.team.id === team && Array.isArray(x.startXI) && x.startXI.length > 0);
// تشكيلة فريق مضغوطة: {id, formation, coach, xi: [{id, name, number, pos, grid}], subs: […]}
function compactTeam(L, team) {
  const x = L.find((y) => y && y.team && y.team.id === team) || {};
  const pl = (arr) => (Array.isArray(arr) ? arr : []).map((e) => e && e.player).filter(Boolean).map((p) => ({
    id: Number.isInteger(p.id) ? p.id : null, name: String(p.name || "").slice(0, 60),
    number: Number.isInteger(p.number) ? p.number : null, pos: String(p.pos || "").slice(0, 2), grid: p.grid ? String(p.grid).slice(0, 5) : null }));
  return { id: team, formation: String(x.formation || "").slice(0, 12), coach: String((x.coach || {}).name || "").slice(0, 60),
    xi: pl(x.startXI), subs: pl(x.substitutes) };
}
async function sendLineups(env, nowMs, diag) {
  if (!env.DB || !env.API_KEY || !env.LIVE_KV) return;
  if (Math.floor(nowMs / 60000) % LINEUP_EVERY_MIN !== 0) return;
  let j;
  try { j = await cachedJson(KICKOFFS_URL, KICKOFFS_TTL_MS); } catch (e) { return; }
  if (!j || !Array.isArray(j.f)) return;
  const now = Math.floor(nowMs / 1000);
  const cand = [];
  for (const r of j.f) {
    if (!Array.isArray(r) || !Number.isFinite(r[0]) || !Number.isInteger(r[1])) continue;
    if (now < r[0] - LINEUP_LEAD_SECS || now > r[0] + LINEUP_TAIL_SECS) continue;
    if (LINEUP_SKIP_LEAGUES.has(r[4])) continue;
    if (await env.DB.prepare("SELECT 1 x FROM ev_sent WHERE fixture = ? AND kind = 'lineup'").bind(r[1]).first()) continue;
    cand.push({ fixture: r[1], th: r[2], ta: r[3], lg: r[4], nh: r[5], na: r[6] });
  }
  if (!cand.length) return;
  if (Number.isFinite(lastRemaining) && lastRemaining < EVENTS_MIN_REMAINING) {
    console.log(JSON.stringify({ type: "lineup_poll", skipped: "quota", remaining: lastRemaining, fixtures: cand.length }));
    return;
  }
  const due = [], stored = [];
  let calls = 0;
  for (let i = 0; i < cand.length; i += IDS_MAX) {
    const part = cand.slice(i, i + IDS_MAX);
    calls++;
    try {
      const r = await fetch(`${API}/fixtures?ids=${part.map((c) => c.fixture).join("-")}`,
        { headers: { "x-apisports-key": env.API_KEY }, signal: AbortSignal.timeout(LIVE_TIMEOUT_MS) });
      const remH = r.headers && r.headers.get ? r.headers.get("x-ratelimit-requests-remaining") : null;
      if (remH != null && remH !== "" && Number.isFinite(Number(remH))) lastRemaining = Number(remH);
      if (!r.ok) { console.log(JSON.stringify({ type: "lineup_poll_error", why: `HTTP ${r.status}` })); continue; }
      const data = await r.json();
      if (data.errors && Object.keys(data.errors).length) {
        console.log(JSON.stringify({ type: "lineup_poll_error", why: JSON.stringify(data.errors).slice(0, 160) }));
        continue;
      }
      const byId = {};
      for (const f of data.response || []) if (f && f.fixture) byId[f.fixture.id] = f;
      for (const c of part) {
        const f = byId[c.fixture];
        if (!f) continue;
        const L = Array.isArray(f.lineups) ? f.lineups : [];
        const tm = f.teams || {};
        const h = (tm.home || {}).id ?? c.th, a = (tm.away || {}).id ?? c.ta;
        if (!(hasXI(L, h) && hasXI(L, a))) continue;
        try {
          await env.LIVE_KV.put("lu:" + c.fixture, JSON.stringify({ fixture: c.fixture, t: now, home: compactTeam(L, h), away: compactTeam(L, a) }),
            { expirationTtl: LINEUP_KV_TTL });
        } catch (e) {
          console.log(JSON.stringify({ type: "lineup_poll_error", fixture: c.fixture, why: "kv: " + String((e && e.message) || e).slice(0, 120) }));
          continue;
        }
        stored.push(c.fixture);
        const rw = recipientWhere([c.th, c.ta], c.fixture, c.lg, T_LINEUP);
        if (env.GOAL_PUSH === "on" && await env.DB.prepare("SELECT 1 x FROM subscriptions WHERE " + rw.sql + " LIMIT 1").bind(...rw.binds).first()) {
          due.push({ evt: "lineup", ...c, h: 0, a: 0 });
        } else {
          await env.DB.prepare("INSERT OR IGNORE INTO ev_sent (fixture, kind, k, ts) VALUES (?, 'lineup', '', ?)").bind(c.fixture, now).run();
        }
      }
    } catch (e) {
      console.log(JSON.stringify({ type: "lineup_poll_error", why: String((e && e.message) || e).slice(0, 120) }));
    }
    if (Number.isFinite(lastRemaining) && lastRemaining < EVENTS_MIN_REMAINING) break;
  }
  if (diag) diag.lineupCalls = (diag.lineupCalls || 0) + calls;
  console.log(JSON.stringify({ type: "lineup_poll", fixtures: cand.length, calls, stored, due: due.map((d) => d.fixture) }));
  if (due.length) await sendAlertPushes(env, due);
}

// الحالة الحالية للمباراة من KV (آخر سحب): {h, a} أو null إن لم تُعرف
async function currentScore(env, fixture) {
  try {
    const raw = await env.LIVE_KV.get(KEY);
    if (!raw) return null;
    const j = JSON.parse(raw);
    const e = (j.m && j.m[String(fixture)]) || (j.f && j.f[String(fixture)]);
    if (!e || e.h == null || e.a == null) return null;
    return { h: e.h, a: e.a };
  } catch (e) { return null; }
}

// الخطوة 2 من إشعار الهدف: تُنفَّذ بعد 60 ث (ثم 120 ثم 240 عند عدم وجود الهدّاف). سطر JSON لكل محاولة.
async function scorerUpdateStep(env, msg) {
  const step = msg.step || 0;
  const base = { type: "goal_scorer", fixture: msg.fixture, h: msg.h, a: msg.a, step,
    ...(msg.sim ? { sim: true } : {}) };
  const log = (o) => console.log(JSON.stringify({ ...base, ...o }));
  if (env.GOAL_PUSH !== "on") return log({ skipped: "off" });
  if (!(Date.now() - msg.ts <= SCORER_LATE_TTL_SECS * 1000)) return log({ expired: true });
  // النتيجة تغيّرت (إلغاء أو هدف بعده) أو لا حالة معروفة: لا تحديث — اسم قد يخصّ هدفاً آخر
  if (!msg.sim) {
    const cur = await currentScore(env, msg.fixture);
    if (!cur) return log({ skipped: "no_state" });
    if (cur.h !== msg.h || cur.a !== msg.a) return log({ skipped: "score_changed", now: cur.h + "-" + cur.a });
  }
  const row = await env.DB.prepare("SELECT minute, name, corrected FROM scorer_update WHERE fixture = ? AND h = ? AND a = ?")
    .bind(msg.fixture, msg.h, msg.a).first();
  if (row && step < SCORER_FAST) return log({ skipped: "already_updated" });   // رسالة مكرّرة؛ المتابعة المتأخرة تُجدوَل مرة من الإرسال نفسه

  // الخطوات المتأخرة: جلب أحداث جديد أولاً (يحدّث sc:<id>)؛ فشله لا يوقف القراءة من القائمة المخزَّنة
  let refreshed = false;
  if (step >= SCORER_FAST && !msg.sim) {
    try {
      await liveScorersStep(env, { fixture: msg.fixture, th: msg.th, ta: msg.ta, h: msg.h, a: msg.a, step: LIVE_SC_DELAYS.length - 1 });
      refreshed = true;
    } catch (e) { console.log(JSON.stringify({ type: "goal_push_error", fixture: msg.fixture, error: "scorer_refresh_failed" })); }
  }
  // المتابعة: الخطوة التالية (إن بقيت) بتوقيتها من لحظة الكشف
  const next = step + 1;
  const watch = async (o) => {
    const wn = Math.max(next, SCORER_FAST);   // بعد إرسال تحديث نقفز للخطوات المتأخرة مباشرة (المبكرة تقرأ القائمة نفسها)
    if (msg.sim || wn >= SCORER_STEPS) return log({ ...o, watch_done: true });
    const d = scorerStepDelay(wn, msg.ts);
    await env.GOAL_QUEUE.send({ ...msg, step: wn }, { delaySeconds: d });
    return log({ ...o, retry_in: d, ...(refreshed ? { events_request: 1 } : {}) });
  };

  let sc = null, lookup = "nomatch", evMin = null;
  if (msg.sim) { sc = msg.simsc || null; lookup = sc ? "hit" : "nomatch"; }
  else { const look = await lookupLiveScorer(env, msg); sc = look.sc; lookup = look.lookup; evMin = look.minute; }
  // دقيقة الحدث من المزوّد تحلّ محلّ دقيقة الكشف (فارقها حتى 11 د)؛ لا حدث بدقيقة (null) = تبقى دقيقة الكشف
  const minute = evMin != null ? evMin : msg.minute;
  const mchg = evMin != null && String(evMin) !== String(msg.minute);
  const nameSig = sc ? (sc.n || "") + "|" + (sc.ar || "") : null;

  if (row) {
    // أُرسل تحديث من قبل: لا شيء جديد = لا إرسال؛ تغيّرت الدقيقة/الاسم = تصحيح واحد فقط
    if (row.corrected) return log({ skipped: "already_corrected" });
    if (!sc) return watch({ skipped: "already_updated", scorer: lookup });
    const minChg = row.minute != null && String(minute) !== row.minute;
    const nameChg = row.name != null && row.name !== nameSig;
    if (!minChg && !nameChg) return watch({ skipped: "already_updated", scorer: lookup });
    const claim = await env.DB.prepare("UPDATE scorer_update SET corrected = 1, minute = ?, name = ? WHERE fixture = ? AND h = ? AND a = ? AND corrected = 0")
      .bind(String(minute), nameSig, msg.fixture, msg.h, msg.a).run();
    if (!(claim && claim.meta && claim.meta.changes === 1)) return log({ skipped: "already_corrected" });
    try {
      await env.GOAL_QUEUE.send({ fixture: msg.fixture, kind: "goal", th: msg.th, ta: msg.ta, lg: msg.lg, h: msg.h, a: msg.a,
        minute, offset: 0, ts: msg.ts, nh: msg.nh, na: msg.na, side: msg.side, ph: msg.ph, pa: msg.pa,
        sc, scd: true, upd: true, ...(minChg ? { mchg: true } : {}), ...(msg.sim ? { sim: true } : {}), ...(msg.admin ? { admin: true } : {}) });
    } catch (e) {
      try { await env.DB.prepare("UPDATE scorer_update SET corrected = 0, minute = ?, name = ? WHERE fixture = ? AND h = ? AND a = ?").bind(row.minute, row.name, msg.fixture, msg.h, msg.a).run(); } catch (e2) {}
      throw e;
    }
    return log({ scorer: lookup, correction_queued: true, ...(minChg ? { minute_from: row.minute, minute_to: String(minute) } : {}), ...(nameChg ? { name_changed: true } : {}) });
  }

  if (!sc) {
    if (next < SCORER_STEPS) {
      const d = scorerStepDelay(next, msg.ts);
      await env.GOAL_QUEUE.send({ ...msg, step: next }, { delaySeconds: d });
      return log({ scorer: lookup, retry_in: d, ...(refreshed ? { events_request: 1 } : {}) });
    }
    return log({ scorer: lookup, gave_up: true });
  }
  // مرة وحدة لكل هدف: نأخذ الصف ثم نضع صفحات الإرسال؛ إن فشل الوضع نحرّر الصف ونرمي (الطابور يعيد الخطوة)
  const ins = await env.DB.prepare("INSERT OR IGNORE INTO scorer_update (fixture, h, a, ts, minute, name) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(msg.fixture, msg.h, msg.a, Math.floor(Date.now() / 1000), String(minute), nameSig).run();
  if (!(ins && ins.meta && ins.meta.changes === 1)) return log({ skipped: "already_updated" });
  try {
    await env.GOAL_QUEUE.send({ fixture: msg.fixture, kind: "goal", th: msg.th, ta: msg.ta, lg: msg.lg, h: msg.h, a: msg.a,
      minute, offset: 0, ts: msg.ts, nh: msg.nh, na: msg.na, side: msg.side, ph: msg.ph, pa: msg.pa,
      sc, scd: true, upd: true, ...(mchg ? { mchg: true } : {}), ...(msg.sim ? { sim: true } : {}), ...(msg.admin ? { admin: true } : {}) });
  } catch (e) {
    try { await env.DB.prepare("DELETE FROM scorer_update WHERE fixture = ? AND h = ? AND a = ?").bind(msg.fixture, msg.h, msg.a).run(); } catch (e2) {}
    throw e;
  }
  // متابعة التصحيح (دقيقة/اسم لاحق) بالخطوات المتأخرة؛ فشل الجدولة لا يُلغي الإرسال (ولا يُعيد الخطوة)
  const o = { scorer: lookup, update_queued: true, ...(mchg ? { minute_from: msg.minute, minute_to: minute } : {}) };
  try { await watch(o); } catch (e) { log({ ...o, watch_schedule_failed: true }); }
}

// ── تشغيل deploy-site كل 30 دقيقة من الـCron (GitHub يؤخّر جدوله ساعات) ──
// عند الدقيقة 5 و35 (UTC): POST workflow_dispatch على main، إلا إن كان هناك تشغيل
// queued/in_progress (لا تراكم). كل محاولة تُسجَّل بـD1 (dispatch_log، آخر 500) وبسطر JSON.
// 401/403 => "dispatch_auth_failed" (توكن منتهٍ يصير ظاهراً). جدول GitHub بالـyml يبقى احتياطاً.
// ⚠️ يُنفَّذ بعد سحب النتائج وبـctx.waitUntil ومعزولاً بـtry/catch: لا يؤخّر ولا يكسر السحب.
const GH_REPO = "amrojaish/football";
const GH_WORKFLOW = "deploy-site.yml";
const DISPATCH_MINUTES = [5, 35];
const DISPATCH_LOG_KEEP = 500;
// تشغيلة queued/in_progress أقدم من هذا العمر تُعتبر عالقة (حادثة Actions 5 أكتوبر) فتُتجاهل ولا تمنع النشر.
const STALE_RUN_MS = 45 * 60 * 1000;

function ghHeaders(env) {
  return {
    Authorization: "Bearer " + env.GH_DISPATCH_TOKEN,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "saffara-live",
  };
}

async function logDispatch(env, ts, result, status, extra) {
  const type = result === "auth_failed" ? "dispatch_auth_failed" : "dispatch";
  console.log(JSON.stringify({ type, result, http_status: status, ts, ...extra }));
  if (result === "auth_failed") {
    await adminAlertOnce(env, "gh_auth_failed:" + utcDay(ts * 1000), {
      title: "\uD83D\uDD11 \u062A\u0648\u0643\u0646 GitHub \u0645\u0631\u0641\u0648\u0636",
      body: `\u0641\u0634\u0644 dispatch \u0628\u0640HTTP ${status} \u2014 GH_DISPATCH_TOKEN`,
    });
  }
  if (!env.DB) return;
  try {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO dispatch_log (ts, result, http_status) VALUES (?, ?, ?)")
        .bind(ts, result, status),
      env.DB.prepare("DELETE FROM dispatch_log WHERE id <= (SELECT MAX(id) FROM dispatch_log) - ?")
        .bind(DISPATCH_LOG_KEEP),
    ]);
  } catch (e) {
    console.log(JSON.stringify({ type: "dispatch_log_failed", error: String(e && e.message || e) }));
  }
}

// تشغيلة waiting/pending/requested أقدم من STALE_RUN_MS = عالقة (حادثة 6 أكتوبر: deploy بـwaiting 18 ساعة حجز concurrency).
// تسجيل فقط (stuck_run:<id> بـdispatch_log + سطر JSON): لا إلغاء ولا منع للـdispatch، وأي فشل هنا يُبلَع.
const STUCK_STATUSES = ["waiting", "pending", "requested"];
const STUCK_LOG_MAX = 5;
// إشعار المشغّل (أجهزة admin_devices فقط، حتى ADMIN_DEVICES_MAX) بتشغيلة عالقة جديدة. معزول: أي فشل يُسجَّل ولا يكسر الدورة.
const ADMIN_DEVICES_MAX = 10;
async function notifyAdmins(env, payload) {
  const { results } = await env.DB.prepare(
    "SELECT s.endpoint, s.p256dh, s.auth, s.lang FROM subscriptions s JOIN admin_devices a ON a.endpoint = s.endpoint LIMIT ?")
    .bind(ADMIN_DEVICES_MAX).all();
  if (!results.length) return { devices: 0, sent: 0, gone: 0, failed: 0 };
  const out = await deliver(env, results, payload);
  return { devices: results.length, sent: out.sent, gone: out.gone, failed: out.failed };
}
// ── تنبيهات المشغّل الصحّية (admin_devices فقط، لا مشتركين أبداً) ──
// مرة واحدة لكل مفتاح: INSERT OR IGNORE بـev_sent (fixture=0, kind='adm', k=المفتاح؛ ينظَّف بعد 3 أيام). أول INSERT يفوز.
// ⚠️ معزول كلياً: أي فشل يُسجَّل ولا يُرمى. فشل الإرسال (لا نجاح مع وجود أجهزة) يحذف الصف ليُعاد بالدورة التالية.
function utcDay(ms) { return new Date(ms).toISOString().slice(0, 10); }
async function adminAlertOnce(env, key, payload) {
  let claimed = false;
  try {
    if (!env.DB || !env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY) return false;
    const ins = await env.DB.prepare("INSERT OR IGNORE INTO ev_sent (fixture, kind, k, ts) VALUES (0, 'adm', ?, ?)")
      .bind(key, Math.floor(Date.now() / 1000)).run();
    if (!(ins && ins.meta && ins.meta.changes === 1)) return false;
    claimed = true;
    const r = await notifyAdmins(env, { ...payload, tag: "adm-" + key, url: "/" });
    console.log(JSON.stringify({ type: "admin_alert", key, ...r }));
    if (r.devices > 0 && r.sent === 0) {
      claimed = false;
      await env.DB.prepare("DELETE FROM ev_sent WHERE fixture = 0 AND kind = 'adm' AND k = ?").bind(key).run();
    }
    return r.sent > 0;
  } catch (e) {
    console.log(JSON.stringify({ type: "admin_alert_error", key, error: String((e && e.message) || e) }));
    if (claimed) { try { await env.DB.prepare("DELETE FROM ev_sent WHERE fixture = 0 AND kind = 'adm' AND k = ?").bind(key).run(); } catch (e2) {} }
    return false;
  }
}
// حصة API: low يغني عن warn (إشعار واحد لا اثنان حين ننزل مباشرة تحت 1500).
async function quotaAlerts(env, remaining, nowMs) {
  if (!Number.isFinite(remaining)) return;
  const day = utcDay(nowMs);
  if (remaining < QUOTA_LOW_REMAINING) {
    await adminAlertOnce(env, "quota_low:" + day, {
      title: "\uD83D\uDEA8 \u0631\u0635\u064A\u062F \u0627\u0644\u0640API \u0642\u0644\u064A\u0644 \u062C\u062F\u0627\u064B",
      body: `\u0627\u0644\u0645\u062A\u0628\u0642\u064A ${remaining} \u2014 \u0627\u0644\u0623\u062D\u062F\u0627\u062B \u0628\u062A\u0648\u0642\u0641 \u062A\u062D\u062A ${EVENTS_MIN_REMAINING}`,
    });
  } else if (remaining < QUOTA_WARN_REMAINING) {
    await adminAlertOnce(env, "quota_warn:" + day, {
      title: "\u26A0\uFE0F \u0631\u0635\u064A\u062F \u0627\u0644\u0640API \u0646\u0627\u0632\u0644",
      body: `\u0627\u0644\u0645\u062A\u0628\u0642\u064A ${remaining} \u0637\u0644\u0628 \u0627\u0644\u064A\u0648\u0645`,
    });
  }
}
// النتائج الحية واقفة: آخر سحب ناجح = t بحمولة KV (يُكتب عند كل سحب ناجح فقط؛ الفشل يُبقي القديمة). المتوقَّع حيّاً = m غير فارغ أو نافذة انطلاق.
const LIVE_STALE_SECS = 10 * 60;
const LIVE_STALE_BUCKET_HOURS = 2;
async function liveStaleAlert(env, lastOkSec, expectedLive, nowMs, why = "") {
  if (!Number.isFinite(lastOkSec) || lastOkSec <= 0) return;
  const age = Math.floor(nowMs / 1000) - lastOkSec;
  if (!(age > LIVE_STALE_SECS)) return;
  if (!(await expectedLive())) return;   // كسول: ملف المواعيد لا يُجلب إلا إن كان t قديماً فعلاً
  const d = new Date(nowMs);
  const bucket = utcDay(nowMs) + "T" + String(Math.floor(d.getUTCHours() / LIVE_STALE_BUCKET_HOURS) * LIVE_STALE_BUCKET_HOURS).padStart(2, "0");
  await adminAlertOnce(env, "live_stale:" + bucket, {
    title: "\u23F8\uFE0F \u0627\u0644\u0646\u062A\u0627\u0626\u062C \u0627\u0644\u062D\u064A\u0629 \u0648\u0627\u0642\u0641\u0629",
    body: `\u0622\u062E\u0631 \u062A\u062D\u062F\u064A\u062B \u0646\u0627\u062C\u062D \u0642\u0628\u0644 ${Math.round(age / 60)} \u062F\u0642\u064A\u0642\u0629` + (why ? " \u2014 " + why : ""),
  });
}
// النشر فشل مرتين: نجلب آخر 5 تشغيلات مكتملة، نُسقط cancelled/skipped (تُتجاهل كلياً)، ونُنبّه إن كانت أول اثنتين من الباقي كلتاهما failure/timed_out/startup_failure.
// مرة لكل رقم أحدث تشغيلة فاشلة. يعمل بعد منطق الـdispatch على كل مساراته (dispatched / skipped_* / stale_ignored / check_failed) بطلب GitHub واحد.
const DEPLOY_FAIL_CONCLUSIONS = ["failure", "timed_out", "startup_failure"];
async function detectDeployFailures(env, base, h) {
  try {
    const r = await fetch(`${base}/runs?status=completed&per_page=5`, { headers: h });
    if (!r.ok) return;
    const j = await r.json();
    const runs = (j.workflow_runs || []).filter((x) => x && x.conclusion !== "cancelled" && x.conclusion !== "skipped").slice(0, 2);
    if (runs.length < 2 || !runs.every((x) => DEPLOY_FAIL_CONCLUSIONS.includes(x.conclusion))) return;
    await adminAlertOnce(env, "deploy_fail:" + runs[0].id, {
      title: "\u274C \u0627\u0644\u0646\u0634\u0631 \u0641\u0634\u0644 \u0645\u0631\u062A\u064A\u0646",
      body: `\u0627\u0644\u062A\u0634\u063A\u064A\u0644 ${runs[0].id}`,
    });
  } catch (e) {
    console.log(JSON.stringify({ type: "deploy_fail_check_error", error: String((e && e.message) || e) }));
  }
}
async function notifyStuckRun(env, runId, mins) {
  try {
    if (!env.DB || !env.VAPID_PRIVATE_KEY || !env.VAPID_PUBLIC_KEY) return;
    const r = await notifyAdmins(env, {
      title: "⚠️ النشر عالق", body: `التشغيل ${runId} — صار له ${mins} دقيقة`,
      tag: "stuck-run-" + runId, url: "/",
    });
    console.log(JSON.stringify({ type: "stuck_run_push", run_id: runId, ...r }));
  } catch (e) {
    console.log(JSON.stringify({ type: "stuck_run_push_error", run_id: runId, error: String((e && e.message) || e) }));
  }
}

async function detectStuckRuns(env, ts, scheduledMs, base, h) {
  let logged = 0;
  for (const st of STUCK_STATUSES) {
    try {
      const r = await fetch(`${base}/runs?status=${st}&per_page=100`, { headers: h });
      if (!r.ok) continue;
      const j = await r.json();
      for (const run of j.workflow_runs || []) {
        if (logged >= STUCK_LOG_MAX) return;
        const age = scheduledMs - Date.parse(run.created_at);
        if (!(age > STALE_RUN_MS)) continue;   // created_at غير مقروء (NaN) => لا نعتبرها عالقة
        const key = "stuck_run:" + run.id;
        // أول مرة نرى هذا الرقم = لا صف سابق بالسجل (سجل بآخر 500 صف؛ عالق أطول من أيام قليلة قد يُنبَّه ثانية). بلا DB => لا إشعار.
        let first = false;
        if (env.DB) {
          try { first = !(await env.DB.prepare("SELECT 1 AS x FROM dispatch_log WHERE result = ? LIMIT 1").bind(key).first()); }
          catch (e) {}
        }
        const mins = Math.round(age / 60000);
        await logDispatch(env, ts, key, r.status,
          { run_id: run.id, run_status: st, created_at: run.created_at, age_min: mins });
        if (first) await notifyStuckRun(env, run.id, mins);
        logged++;
      }
    } catch (e) {}
  }
}

async function maybeDispatch(env, scheduledMs) {
  await dispatchCore(env, scheduledMs);
  // بعد الـdispatch دائماً (لا يؤخّره ولا يكسره): فحص فشل النشر مرتين بطلب GitHub إضافي واحد
  try {
    if (env.GH_DISPATCH_TOKEN) await detectDeployFailures(env, `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}`, ghHeaders(env));
  } catch (e) {}
}
async function dispatchCore(env, scheduledMs) {
  const ts = Math.floor(scheduledMs / 1000);
  try {
    if (!env.GH_DISPATCH_TOKEN) {
      console.log(JSON.stringify({ type: "dispatch", result: "no_token", ts }));
      return;
    }
    const base = `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}`;
    const h = ghHeaders(env);
    await detectStuckRuns(env, ts, scheduledMs, base, h);
    for (const st of ["queued", "in_progress"]) {
      const r = await fetch(`${base}/runs?status=${st}&per_page=1`, { headers: h });
      if (r.status === 401 || r.status === 403) return logDispatch(env, ts, "auth_failed", r.status);
      if (!r.ok) return logDispatch(env, ts, "check_failed", r.status);
      const j = await r.json();
      if ((j.total_count || 0) > 0) {
        const run = (j.workflow_runs || [])[0] || {};
        const age = scheduledMs - Date.parse(run.created_at);
        // الأحدث أولاً: إن كان الأحدث عالقاً فكل ما بعده أقدم منه. created_at غير مقروء => نتصرف كأنها حديثة (skip).
        if (age > STALE_RUN_MS) {
          await logDispatch(env, ts, "stale_ignored", r.status,
            { run_id: run.id, run_status: st, created_at: run.created_at, age_min: Math.round(age / 60000) });
          continue;
        }
        return logDispatch(env, ts, "skipped_" + st, r.status);
      }
    }
    const d = await fetch(`${base}/dispatches`, {
      method: "POST",
      headers: { ...h, "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    });
    if (d.status === 401 || d.status === 403) return logDispatch(env, ts, "auth_failed", d.status);
    return logDispatch(env, ts, d.status === 204 ? "dispatched" : "failed", d.status);
  } catch (e) {
    console.log(JSON.stringify({ type: "dispatch", result: "error", error: String(e && e.message || e), ts }));
    try { await logDispatch(env, ts, "error", null); } catch (e2) {}
  }
}

// ── قرب موعد انطلاق (9 أكتوبر 2026) ──
// خمول الـ5 دقائق كان يضيّع أول دقائق المباراة (هدف الدقيقة 3 بالمباراة 1627995). assets/next_kickoffs.json يولّده
// make_kickoffs.py ضمن deploy-site: {"t": توليد, "k": [مواعيد انطلاق بالثواني UTC، تصاعدياً]} للدوريات السبعة (48 ساعة).
// من 10 دقائق قبل أي موعد وحتى 30 دقيقة بعده (إن لم تصبح المباراة حيّة) نسحب كل دقيقة بدل نافذة الخمول. بلا طلبات API:
// ملف ثابت من الموقع بكاش 10 دقائق. تعذّر الملف/فساده = السلوك القديم (خمول 5 دقائق).
const KICKOFFS_URL = "https://saffara.app/assets/next_kickoffs.json";
const KICKOFFS_TTL_MS = 10 * 60 * 1000;
const KICKOFF_LEAD_SECS = 10 * 60;
const KICKOFF_TAIL_SECS = 30 * 60;
async function nearKickoff() {
  try {
    const j = await cachedJson(KICKOFFS_URL, KICKOFFS_TTL_MS);
    const now = Math.floor(Date.now() / 1000);
    return Array.isArray(j.k) && j.k.some((t) => Number.isFinite(t) && now >= t - KICKOFF_LEAD_SECS && now <= t + KICKOFF_TAIL_SECS);
  } catch (e) { return false; }
}

// سحب النتائج الحية (كان جسم scheduled): لا تغيير بالمنطق.
async function livePoll(env) {
  // ⚠️ قراءة وحدة، بلا أي كتابة، طوال فترة الخمول — درس 3 سبتمبر
  let prev = null;
  try {
    const raw = await env.LIVE_KV.get(KEY);
    if (raw) prev = JSON.parse(raw);
  } catch (e) {}

  const wasIdle = prev && Object.keys(prev.m || {}).length === 0;
  const secsSince = prev ? Math.floor(Date.now() / 1000) - prev.t : Infinity;
  // حالة للمسار المجدول (تنبيهات المشغّل): آخر سحب ناجح + هل المتوقَّع مباراة حيّة؛ بلا قراءة KV ثانية
  // attempted/why: تنبيه «واقفة» فقط بعد سحب فعلي فاشل، وسببه بنص التنبيه (19 أكتوبر 2026)
  const st = { lastOk: prev ? prev.t : NaN, liveNow: !!(prev && Object.keys(prev.m || {}).length), remaining: NaN, attempted: false, why: "" };

  // كنا بالخمول والنافذة لسا ما خلصت → صفر كتابة، رجوع فوري
  if (wasIdle && secsSince < IDLE_SKIP_SECS && !(await nearKickoff())) return st;

  const diag = {};
  st.attempted = true;
  const payload = await pull(env, diag, prev);
  if (!payload) {   // فشل الطلب: نُبقي آخر نسخة سليمة
    st.why = diag.why || "?";
    console.log(JSON.stringify({ type: "live_pull_fail", why: st.why }));
    return st;
  }

  await env.LIVE_KV.put(KEY, JSON.stringify(payload));   // كتابة وحدة فقط هنا
  st.lastOk = payload.t;
  st.remaining = diag.remaining;
  return st;
}
// تنبيهات المشغّل بعد السحب: معزولة تماماً (لا تؤخّر ولا تكسر مسار السحب الذي انتهى وكُتب قبلها)
async function adminHealth(env, st, nowMs) {
  try { await quotaAlerts(env, st.remaining, nowMs); } catch (e) {}
  if (st.attempted) {
    try { await liveStaleAlert(env, st.lastOk, async () => st.liveNow || (await nearKickoff()), nowMs, st.why); } catch (e) {}
  }
}

export default {
  // ── الجدولة: كل دقيقة ──
  async scheduled(event, env, ctx) {
    try { await sendReminders(env); }   // 3E: قبل أي خمول، ومعزول
    catch (e) { console.log(JSON.stringify({ type: "alert_push_error", error: "reminders: " + String((e && e.message) || e) })); }
    try {
      const st = await livePoll(env);
      if (st) await adminHealth(env, st, Date.now());
      // التشكيلات بعد السحب الحيّ (رأس الحصة الأحدث)، معزولة ولا تكسر شيئاً
      const ms = event && Number.isFinite(event.scheduledTime) ? event.scheduledTime : Date.now();
      try { await sendLineups(env, ms, st); }
      catch (e) { console.log(JSON.stringify({ type: "alert_push_error", error: "lineups: " + String((e && e.message) || e) })); }
    } finally {
      // بعد السحب دائماً (حتى لو كان السحب خاملاً أو فشل): الدقيقة 5/35 UTC فقط
      const ms = event && event.scheduledTime;
      if (Number.isFinite(ms) && DISPATCH_MINUTES.includes(new Date(ms).getUTCMinutes())) {
        const run = maybeDispatch(env, ms);
        if (ctx && typeof ctx.waitUntil === "function") ctx.waitUntil(run);
        else await run;
        // تنظيف عدّاد حدّ الاشتراك المنتهي (وعد صفحة الخصوصية: يُمسح خلال ساعتين). معزول ولا يكسر شيئاً.
        if (env.DB) {
          try { await env.DB.prepare("DELETE FROM rate_limit WHERE exp < ?").bind(Math.floor(ms / 1000)).run(); }
          catch (e) {}
          try { await env.DB.prepare("DELETE FROM goal_log WHERE ts < ?").bind(Math.floor(ms / 1000) - GOAL_LOG_KEEP_DAYS * 86400).run(); }
          catch (e) {}
          try { await env.DB.prepare("DELETE FROM scorer_update WHERE ts < ?").bind(Math.floor(ms / 1000) - 2 * 86400).run(); }
          catch (e) {}
          // اشتراكات مباريات مفردة أقدم من 21 يوماً (المباراة انتهت منذ زمن؛ العميل يحذفها أصلاً بعد 14 يوماً من الانطلاق)
          try { await env.DB.prepare("DELETE FROM sub_matches WHERE created_at < ?").bind(Math.floor(ms / 1000) - 21 * 86400).run(); }
          catch (e) {}
          try { await env.DB.prepare("DELETE FROM ev_sent WHERE ts < ?").bind(Math.floor(ms / 1000) - 3 * 86400).run(); }
          catch (e) {}
        }
      }
    }
  },

  // ── طابور إشعارات الأهداف (max_batch_size=1: كل صفحة تشغيلة مستقلة بميزانيتها) ──
  async queue(batch, env) {
    for (const m of batch.messages) {
      try {
        if (m.body && m.body.kind === "live_scorers") await liveScorersStep(env, m.body);
        else if (m.body && m.body.kind === "goal_scorer") await scorerUpdateStep(env, m.body);
        else if (m.body && m.body.kind === "alert") await alertPushPage(env, m.body);
        else await goalPushPage(env, m.body);
        m.ack();
      } catch (e) {
        // فشل قبل أي إرسال (D1/الطابور): الإعادة آمنة بلا تكرار
        console.log(JSON.stringify({ type: "goal_push_error", fixture: m.body && m.body.fixture,
          error: String((e && e.message) || e) }));
        m.retry({ delaySeconds: 10 });
      }
    }
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
    if (url.pathname === "/push/test") return handlePushTest(request, env);
    if (url.pathname === "/push/simulate") return handlePushSimulate(request, env);
    if (url.pathname === "/push/admin-device") return handleAdminDevice(request, env);
    if (url.pathname === "/push/admin-test") return handleAdminTest(request, env);
    if (url.pathname.startsWith("/push/")) return handlePush(request, env, url);

    // التشكيلة الحيّة (lu:<id>، sendLineups) وأحداث ما بعد النهاية (ev:<id>، storeEvents) لصفحة المباراة (19 أكتوبر 2026): غائبة = 404 {}
    if (url.pathname === "/lineup" || url.pathname === "/events") {
      const id = url.searchParams.get("id") || "";
      const h = { ...cors, "Cache-Control": "public, max-age=60" };
      if (!/^[0-9]{1,10}$/.test(id)) return new Response(JSON.stringify({ error: "bad id" }), { status: 400, headers: h });
      const v = await env.LIVE_KV.get((url.pathname === "/lineup" ? "lu:" : "ev:") + id);
      return v ? new Response(v, { headers: h }) : new Response("{}", { status: 404, headers: h });
    }

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
