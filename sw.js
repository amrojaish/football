/*
 * صافرة — Service Worker
 * ======================
 * استراتيجية ثلاث طبقات:
 *   1. تخزين مسبق: الرئيسية · الدوريات · الأيقونات · فهرس البحث
 *   2. تخزين عند الزيارة: أي صفحة نادٍ أو مباراة يفتحها المستخدم
 *   3. الشبكة أولاً دائماً للمحتوى — فمع الإنترنت لا يُعرض مخزون
 *
 * ⚠️ **لماذا الشبكة أولاً لا المخزون أولاً:** الموقع يتحدّث كل
 *    30 دقيقة. المخزون أولاً كان سيُظهر نتائج قديمة لزائر متصل
 *    — وعرض نتيجة خاطئة بثقة أسوأ من بطء بسيط.
 *
 * ⚠️ **لا نخزّن الـ9,810 صفحة مسبقاً** — عشرات الميغابايتات
 *    يمسحها المتصفح تلقائياً عند امتلاء المساحة، فتضيع بلا فائدة.
 */

const VER = 'saffara-v2';
const CORE = VER + '-core';
const PAGES = VER + '-pages';

const PRECACHE = [
  '/football/',
  '/football/index.html',
  '/football/leagues.html',
  '/football/en/',
  '/football/en/index.html',
  '/football/en/leagues.html',
  '/football/search_data.js',
  '/football/icons/icon-192.png',
  '/football/icons/icon-512.png',
  '/football/offline.html',
];

self.addEventListener('install', function (e) {
  // ⚠️ addAll يفشل كلياً لو سقط ملف واحد — نخزّن كلاً على حدة
  e.waitUntil(
    caches.open(CORE).then(function (c) {
      return Promise.all(PRECACHE.map(function (u) {
        return c.add(u).catch(function () { return null; });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CORE && k !== PAGES) { return caches.delete(k); }
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') { return; }

  var url = new URL(req.url);

  /* ⚠️ **شعارات الأندية من خادم خارجي** (media.api-sports.io) —
   * 654 صورة على الرئيسية وحدها. تجاهُل كل ما هو خارجي كان
   * يعني أن أي شعار لا يظهر بلا إنترنت مهما زار المستخدم.
   * الشعارات **لا تتغيّر أبداً**، فتخزينها آمن تماماً — بخلاف
   * النتائج التي رفضنا تخزينها المسبق لخطر البيانات القديمة. */
  if (url.origin !== self.location.origin) {
    if (url.hostname === 'media.api-sports.io') {
      e.respondWith(
        caches.match(req).then(function (hit) {
          if (hit) { return hit; }
          return fetch(req).then(function (res) {
            var copy = res.clone();
            caches.open(CORE).then(function (c) { c.put(req, copy); });
            return res;
          }).catch(function () {
            return new Response('', { status: 504 });
          });
        })
      );
    }
    return;
  }

  // الأيقونات والشعارات: المخزون أولاً (لا تتغيّر)
  if (/\.(png|jpg|jpeg|svg|ico|webp|woff2?)$/i.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) {
          var copy = res.clone();
          caches.open(CORE).then(function (c) { c.put(req, copy); });
          return res;
        }).catch(function () { return hit; });
      })
    );
    return;
  }

  // ⚠️ live.json لا يُخزَّن إطلاقاً — نتائج مباشرة، المخزون
  //    منها مضلِّل بطبيعته.
  if (url.pathname.indexOf('live.json') !== -1) { return; }

  // كل ما عدا ذلك: الشبكة أولاً، والمخزون احتياط
  e.respondWith(
    fetch(req).then(function (res) {
      if (res && res.status === 200) {
        var copy = res.clone();
        caches.open(PAGES).then(function (c) { c.put(req, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) {
        if (hit) { return hit; }
        if (req.mode === 'navigate') {
          return caches.match('/football/offline.html');
        }
        return new Response('', { status: 504 });
      });
    })
  );
});
