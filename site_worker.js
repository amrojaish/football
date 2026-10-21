// saffara-site (wrangler.site.toml): GitHub Pages' directory/extensionless rules on Workers static assets.
// Runs only when no asset matched (run_worker_first = false): html_handling = "none" keeps the .html URLs as they are
// (no 307 rewrites) but serves nothing for /, /en/ or /matches/1 — this fills exactly those gaps (21 Oct 2026).
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const p = url.pathname;
    const tryAsset = async (path) => {
      const r = await env.ASSETS.fetch(new Request(new URL(path + url.search, url), request));
      return r.status === 200 ? r : null;
    };
    if (p.endsWith("/")) {                                   // /  /en/  -> index.html (200, same URL)
      const r = await tryAsset(p + "index.html"); if (r) return r;
    } else if (!/\.[a-z0-9]+$/i.test(p.split("/").pop())) {  // /en -> 301 /en/ ; /matches/1 -> matches/1.html (200)
      if (await tryAsset(p + "/index.html")) return Response.redirect(new URL(p + "/" + url.search, url), 301);
      const r = await tryAsset(p + ".html"); if (r) return r;
    }
    return env.ASSETS.fetch(request);                        // fall back: not_found_handling = 404-page
  },
};
