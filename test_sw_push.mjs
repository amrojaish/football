// sw.js push + notificationclick handlers, run in a vm with a mocked service-worker scope.
// Run: node test_sw_push.mjs
import fs from "node:fs";
import vm from "node:vm";

const src = fs.readFileSync(new URL("./sw.js", import.meta.url), "utf8");
const handlers = {};
const shown = [];
const opened = [];
const focused = [];
const origin = "https://saffara.app";
let windows = [];
const self_ = {
  location: { origin },
  addEventListener: (t, f) => { handlers[t] = f; },
  registration: { showNotification: (title, opts) => { shown.push({ title, opts }); return Promise.resolve(); } },
  clients: {
    matchAll: async () => windows,
    openWindow: async (u) => { opened.push(u); return {}; },
    claim: async () => {}, },
  skipWaiting: async () => {},
};
vm.runInNewContext(src, { self: self_, caches: { open: async () => ({ add: async () => {} }), keys: async () => [], match: async () => null },
  URL, Response, fetch: async () => new Response("") });

let fail = 0;
const check = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " " + JSON.stringify(x))); if (!c) fail++; };
const run = async (type, ev) => { let p; ev.waitUntil = (x) => { p = x; }; handlers[type](ev); await p; };

check("push + notificationclick handlers registered", typeof handlers.push === "function" && typeof handlers.notificationclick === "function");

await run("push", { data: { json: () => ({ title: "هدف!", body: "1-0", tag: "g-1", url: "/clubs/962.html" }) } });
const n = shown[0];
check("push: title/body/icon/tag/url", n.title === "هدف!" && n.opts.body === "1-0" && n.opts.icon === "/icons/icon-192.png"
  && n.opts.tag === "g-1" && n.opts.data.url === "/clubs/962.html" && n.opts.renotify === true, n);

await run("push", { data: null });
check("push without payload still shows a notification (userVisibleOnly)", shown.length === 2 && shown[1].title === "صافرة", shown[1]);
await run("push", { data: { json: () => { throw new Error("bad"); } } });
check("push with unreadable payload still shows a notification", shown.length === 3);

// click: no open window -> openWindow(absolute url)
let closed = 0;
windows = [];
await run("notificationclick", { notification: { close: () => { closed++; }, data: { url: "/clubs/962.html" } } });
check("click: closes + opens new window to absolute url", closed === 1 && opened[0] === origin + "/clubs/962.html", opened);

// click: window already on that url -> focus it, no new window
windows = [{ url: origin + "/clubs/962.html", focus: async () => { focused.push("same"); return {}; } }];
await run("notificationclick", { notification: { close() {}, data: { url: "/clubs/962.html" } } });
check("click: focuses the existing window on the same url", focused[0] === "same" && opened.length === 1, [focused, opened]);

// click: other window open -> focus + navigate
const navs = [];
windows = [{ url: origin + "/", focus: async function () { return this; }, navigate: async (u) => { navs.push(u); } }];
await run("notificationclick", { notification: { close() {}, data: { url: "/en/clubs/962.html" } } });
check("click: reuses another open window (navigate)", navs[0] === origin + "/en/clubs/962.html" && opened.length === 1, navs);

process.exit(fail ? 1 : 0);
