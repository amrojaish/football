// Offline fallback per language: /en/ navigations get /en/offline.html, the rest /offline.html;
// both pages are precached; the English page really is English. Run: node test_sw_offline.mjs
import fs from "node:fs";
import vm from "node:vm";

const src = fs.readFileSync(new URL("./sw.js", import.meta.url), "utf8");
const handlers = {};
const added = [];
const lookups = [];
const cache = { add: async (u) => { added.push(u); }, put: async () => {} };
const caches = {
  open: async () => cache,
  keys: async () => [],
  match: async (r) => { const k = typeof r === "string" ? r : r.url; lookups.push(k); return k.endsWith("offline.html") ? { page: k } : undefined; },
};
const self_ = {
  location: { origin: "https://saffara.app" },
  addEventListener: (t, f) => { handlers[t] = f; },
  skipWaiting: async () => {}, clients: { claim: async () => {} },
};
vm.runInNewContext(src, { self: self_, caches, URL, Response, fetch: async () => { throw new Error("offline"); } });

let fail = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };

// install precaches both offline pages
let p;
handlers.install({ waitUntil: (x) => { p = x; } });
await p;
check("precache has /offline.html and /en/offline.html", added.includes("/offline.html") && added.includes("/en/offline.html"), added);

async function navigate(path) {
  lookups.length = 0;
  let out;
  handlers.fetch({
    request: { method: "GET", url: "https://saffara.app" + path, mode: "navigate" },
    respondWith: (x) => { out = x; },
  });
  return await out;
}
let r = await navigate("/en/clubs/962.html");
check("offline /en/clubs/962.html -> /en/offline.html", r && r.page === "/en/offline.html", r);
r = await navigate("/en/");
check("offline /en/ -> /en/offline.html", r && r.page === "/en/offline.html", r);
r = await navigate("/clubs/962.html");
check("offline /clubs/962.html -> /offline.html", r && r.page === "/offline.html", r);
r = await navigate("/");
check("offline / -> /offline.html", r && r.page === "/offline.html", r);
r = await navigate("/english-news.html");
check("a path merely starting with 'en' is not treated as English", r && r.page === "/offline.html", r);

// the files themselves
const en = fs.readFileSync(new URL("./en/offline.html", import.meta.url), "utf8");
const ar = fs.readFileSync(new URL("./offline.html", import.meta.url), "utf8");
check("en/offline.html: lang=en dir=ltr, English text, links to /en/", /<html lang="en" dir="ltr">/.test(en)
  && /No connection/.test(en) && /href="\/en\/"/.test(en) && !/[؀-ۿ]/.test(en));
check("offline.html stays Arabic and links to /", /<html lang="ar" dir="rtl">/.test(ar) && /href="\/"/.test(ar));

process.exit(fail ? 1 : 0);
