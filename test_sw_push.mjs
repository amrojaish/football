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
check("push: title/body/icon/tag/url", n.title === "هدف!" && n.opts.body === "1-0" && /^\/icons\/icon-192\.png\?v=[0-9a-f]{8}$/.test(n.opts.icon) && n.opts.badge === n.opts.icon
  && n.opts.tag === "g-1" && n.opts.data.url === "/clubs/962.html" && n.opts.renotify === true, n);

// scorer update (8 Oct): same tag + renotify:false in the payload -> replaces silently; without the field renotify stays !!tag
await run("push", { data: { json: () => ({ title: "هدف!", body: "1-0 34", tag: "g-1", url: "/clubs/962.html", renotify: false }) } });
check("push with renotify:false (scorer update) -> showNotification renotify:false, same tag", shown.at(-1).opts.tag === "g-1" && shown.at(-1).opts.renotify === false, shown.at(-1));
shown.pop();
await run("push", { data: { json: () => ({ title: "x", body: "y", url: "/" }) } });
check("push with NO tag and no renotify field -> renotify false (never true without a tag: Chrome would throw)", shown.at(-1).opts.tag === undefined && shown.at(-1).opts.renotify === false, shown.at(-1));
shown.pop();

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

// (11 Nov 2026) iOS ignores same-tag replacement: close the shown notifications with that tag first, then show
{
  const reg = self_.registration, calls = [];
  let closes = 0;
  reg.getNotifications = async (f) => { calls.push(["get", f && f.tag]); return [{ close: () => { closes++; calls.push(["close"]); } }]; };
  const showOrig = reg.showNotification;
  reg.showNotification = (t, o) => { calls.push(["show", o.tag]); return showOrig(t, o); };
  const before = shown.length;
  await run("push", { data: { json: () => ({ title: "upd", body: "15' X", tag: "goal-1-1-0", renotify: false }) } });
  check("tag: getNotifications({tag}) -> close() once -> showNotification once, in that order",
    JSON.stringify(calls) === JSON.stringify([["get", "goal-1-1-0"], ["close"], ["show", "goal-1-1-0"]]) && closes === 1
    && shown.length === before + 1 && shown.at(-1).opts.renotify === false, calls);

  calls.length = 0;
  reg.getNotifications = () => { throw new Error("boom"); };
  await run("push", { data: { json: () => ({ title: "a", body: "b", tag: "t1" }) } });
  check("getNotifications throws -> showNotification still called", JSON.stringify(calls) === JSON.stringify([["show", "t1"]]), calls);

  calls.length = 0;
  reg.getNotifications = async () => { throw new Error("reject"); };
  await run("push", { data: { json: () => ({ title: "a", body: "b", tag: "t2" }) } });
  check("getNotifications rejects -> showNotification still called", JSON.stringify(calls) === JSON.stringify([["show", "t2"]]), calls);

  calls.length = 0;
  reg.getNotifications = async () => [{ close: () => { throw new Error("close failed"); } }];
  await run("push", { data: { json: () => ({ title: "a", body: "b", tag: "t3" }) } });
  check("close() throws -> showNotification still called", JSON.stringify(calls) === JSON.stringify([["show", "t3"]]), calls);

  calls.length = 0;
  let got = 0;
  reg.getNotifications = async () => { got++; return []; };
  await run("push", { data: { json: () => ({ title: "a", body: "b" }) } });
  check("no tag -> no getNotifications call, showNotification once", got === 0 && calls.length === 1 && calls[0][0] === "show" && calls[0][1] === undefined, calls);

  calls.length = 0;
  delete reg.getNotifications;
  await run("push", { data: { json: () => ({ title: "a", body: "b", tag: "t4" }) } });
  check("getNotifications missing -> showNotification still called", JSON.stringify(calls) === JSON.stringify([["show", "t4"]]), calls);
  reg.showNotification = showOrig;
}

process.exit(fail ? 1 : 0);
