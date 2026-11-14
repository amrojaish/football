// saffara-site worker (R3, 14 Nov 2026; prototype r2_proto/site_worker.js).
// With wrangler.site.next.toml: static assets = _hot (every non-.html file + HOT_HTML), page .html from R2 (binding PAGES,
// uploaded by upload_changed.py). run_worker_first = false, so present hot files never reach this code.
// With the old wrangler.site.toml (no PAGES binding, every file in assets): behaves exactly like the pre-R3 worker
// (fills the /, /en/, extensionless gaps) — so either config can deploy this file safely.
// URL -> key (same as html_handling = "none" + the old gap rules):
//   /x/ -> x/index.html    /matches/1 -> matches/1.html    /en -> 301 /en/    /matches/1.html -> matches/1.html
// R2 headers = live saffara.app HTML (Content-Type: text/html, Cache-Control: public, max-age=0, must-revalidate) + ETag;
// If-None-Match -> 304 via R2 conditional get. Missing -> /404.html with status 404 (as not_found_handling = "404-page").
// Keep HOT_HTML in sync with build_site.py HOT_HTML.
const HOT_HTML = new Set(["index.html", "en/index.html", "404.html", "offline.html", "en/offline.html",
  "search.html", "en/search.html", "following.html", "en/following.html", "notifications.html",
  "en/notifications.html", "google42cb06cb72108c7f.html"]);

// pre-R3 behaviour (all files in static assets)
async function assetsOnly(request, env) {
  const url = new URL(request.url);
  const p = url.pathname;
  const tryAsset = async (path) => {
    const r = await env.ASSETS.fetch(new Request(new URL(path + url.search, url), request));
    return r.status === 200 ? r : null;
  };
  if (p.endsWith("/")) {
    const r = await tryAsset(p + "index.html"); if (r) return r;
  } else if (!/\.[a-z0-9]+$/i.test(p.split("/").pop())) {
    if (await tryAsset(p + "/index.html")) return Response.redirect(new URL(p + "/" + url.search, url), 301);
    const r = await tryAsset(p + ".html"); if (r) return r;
  }
  return env.ASSETS.fetch(request);
}

function htmlHeaders(obj) {
  const h = new Headers();
  h.set("content-type", "text/html");
  h.set("cache-control", "public, max-age=0, must-revalidate");
  if (obj.httpEtag) h.set("etag", obj.httpEtag);
  return h;
}

async function notFound(env, url, request) {
  const r = await env.ASSETS.fetch(new Request(new URL("/404.html", url), { method: "GET", headers: request.headers }));
  const h = new Headers(r.headers);
  h.set("content-type", "text/html");
  h.set("cache-control", "public, max-age=0, must-revalidate");
  h.delete("etag");
  return new Response(request.method === "HEAD" ? null : r.body, { status: 404, headers: h });
}

// Edge cache for R2 pages (14 Nov 2026): caches.default, 60 s, key = https://<host>/<R2 key> (normalized: no query,
// /matches/1 and /matches/1.html share one entry). Only 200 page bodies are stored (404s never). The stored copy carries
// s-maxage=60; the browser still gets max-age=0, must-revalidate. x-r2-cache: HIT|MISS for checks.
const PAGE_CACHE_TTL = 60;

async function fromR2Cached(env, key, request, url, ctx) {
  const cache = caches.default;
  const ckey = new Request(url.origin + "/" + key.split("/").map(encodeURIComponent).join("/"), { method: "GET" });
  const hit = await cache.match(ckey);
  if (hit) {
    const h = new Headers(hit.headers);
    h.set("cache-control", "public, max-age=0, must-revalidate");
    h.set("x-r2-cache", "HIT");
    const etag = h.get("etag");
    const inm = request.headers.get("if-none-match");
    if (etag && inm && inm.replace(/^W\//, "") === etag.replace(/^W\//, "")) return new Response(null, { status: 304, headers: h });
    return new Response(request.method === "HEAD" ? null : hit.body, { status: 200, headers: h });
  }
  // miss: full GET from R2 (no conditional), store a copy, then answer like fromR2
  const obj = await env.PAGES.get(key);
  if (!obj) return null;
  const body = await obj.arrayBuffer();
  const store = htmlHeaders(obj);
  store.set("cache-control", `public, s-maxage=${PAGE_CACHE_TTL}, max-age=0`);
  const put = cache.put(ckey, new Response(body, { status: 200, headers: store }));
  if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
  const h = htmlHeaders(obj);
  h.set("x-r2-cache", "MISS");
  const inm = request.headers.get("if-none-match");
  if (obj.httpEtag && inm && inm.replace(/^W\//, "") === obj.httpEtag.replace(/^W\//, "")) return new Response(null, { status: 304, headers: h });
  return new Response(request.method === "HEAD" ? null : body, { status: 200, headers: h });
}

async function fromR2(env, key, request) {
  const inm = request.headers.get("if-none-match");
  const obj = await env.PAGES.get(key, inm ? { onlyIf: { etagDoesNotMatch: inm.replace(/^W\//, "").replace(/"/g, "") } } : undefined);
  if (!obj) return null;
  const h = htmlHeaders(obj);
  if (!("body" in obj) || obj.body === undefined) return new Response(null, { status: 304, headers: h });
  return new Response(request.method === "HEAD" ? null : obj.body, { status: 200, headers: h });
}

export default {
  async fetch(request, env, ctx) {
    if (!env.PAGES) return assetsOnly(request, env);
    const url = new URL(request.url);
    let p;
    try { p = decodeURIComponent(url.pathname); } catch { return notFound(env, url, request); }
    if (request.method !== "GET" && request.method !== "HEAD") return env.ASSETS.fetch(request);
    const last = p.split("/").pop();
    const hasExt = /\.[a-z0-9]+$/i.test(last);

    // non-HTML -> static assets as today
    if (hasExt && !p.toLowerCase().endsWith(".html")) return env.ASSETS.fetch(request);

    let key;
    if (p.endsWith("/")) key = p.slice(1) + "index.html";
    else if (!hasExt) {
      const idx = p.slice(1) + "/index.html";
      if (HOT_HTML.has(idx) || await env.PAGES.head(idx)) return Response.redirect(new URL(p + "/" + url.search, url), 301);
      key = p.slice(1) + ".html";
    } else key = p.slice(1);

    if (HOT_HTML.has(key)) {
      const r = await env.ASSETS.fetch(new Request(new URL("/" + key, url), request));
      return r.status === 404 ? notFound(env, url, request) : r;
    }
    if (key.includes("..") || key.startsWith("_")) return notFound(env, url, request);  // no _manifest/_pending via .html
    return (await fromR2Cached(env, key, request, url, ctx)) || notFound(env, url, request);
  },
};
