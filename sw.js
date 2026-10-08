/*
 * صافرة — Service Worker
 * ======================
 * استراتيجية ثلاث طبقات:
 *   1. تخزين مسبق: الرئيسية · الدوريات · الأيقونات · صفحة البحث
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

/* ASSETS-BEGIN (يولّده make_assets.py — لا تعدّله يدوياً) */
const VER = 'saffara-4a4c16d5';
const ASSET_PRECACHE = [
  '/assets/site.css?v=c000237f',
  '/assets/site.js?v=a54a94dd',
];
/* ASSETS-END */
const CORE = VER + '-core';
const PAGES = VER + '-pages';

const PRECACHE = [
  '/',
  '/index.html',
  '/leagues.html',
  '/en/',
  '/en/index.html',
  '/en/leagues.html',
  '/search.html',
  '/en/search.html',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/offline.html',
  '/en/offline.html',
].concat(ASSET_PRECACHE);

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

  // ملفات /assets/*?v=<hash>: المخزون أولاً — الـhash يغيّر الرابط عند أي
  // تعديل فلا خطر من نسخة قديمة (make_assets.py يولّد VER وPRECACHE).
  if (url.pathname.indexOf('/assets/') === 0 && url.searchParams.get('v')) {
    e.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) {
          if (res && res.status === 200) {
            var copy = res.clone();
            caches.open(CORE).then(function (c) { c.put(req, copy); });
          }
          return res;
        });
      })
    );
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
          // ⚠️ صفحة "غير متصل" بلغة الصفحة المطلوبة (كان الزائر الإنجليزي يرى العربية)
          return caches.match(url.pathname.indexOf('/en/') === 0 || url.pathname === '/en'
            ? '/en/offline.html' : '/offline.html');
        }
        return new Response('', { status: 504 });
      });
    })
  );
});

/* ── تنبيهات الأهداف (دفعة 3: بيتا مخفية) ──
 * الحمولة JSON مشفّرة من الـworker: {title, body, tag, url}.
 * ⚠️ userVisibleOnly=true: كل push يجب أن يعرض إشعاراً (وإلا قد يلغي المتصفح
 *    الاشتراك) — لذلك نعرض إشعاراً حتى لو فشلت قراءة الحمولة.
 * tag: goal-<fixture>-<h>-<a> (لكل هدف) — إشعار جديد بنفس الـtag يحلّ محلّ القديم؛ إلغاء VAR يحمل tag الهدف الملغى فقط.
 * ⚠️ renotify لازم يبقى `!!d.tag`: renotify:true بلا tag يرمي TypeError بـChrome فيضيع الإشعار (userVisibleOnly).
 * تحديث الهدّاف (8 أكتوبر): الحمولة تحمل `renotify:false` فيحلّ محلّ إشعار الهدف بنفس الـtag بلا رنّة/اهتزاز جديد
 * (الأجهزة التي لم تحدّث الـSW بعد تتجاهل الحقل وقد ترنّ مرة ثانية). */
self.addEventListener('push', function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = {}; }
  var title = d.title || 'صافرة';
  e.waitUntil(self.registration.showNotification(title, {
    body: d.body || '',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: d.tag || undefined,
    renotify: d.renotify === false ? false : !!d.tag,
    data: { url: d.url || '/' }
  }));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var target = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        if (c.url === target && 'focus' in c) { return c.focus(); }
      }
      for (var j = 0; j < list.length; j++) {
        var w = list[j];
        if ('navigate' in w && 'focus' in w) {
          return w.focus().then(function (x) { return (x || w).navigate(target); });
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
