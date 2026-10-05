#!/usr/bin/env python3
"""
بناء ملفات /assets (CSS/JS المشتركة) + manifest + كتلة sw.js
==============================================================
يولّد من نفس الثوابت/الدوال التي كانت تحقنها المولِّدات مضمَّنةً (فيبقى
السلوك مطابقاً بالبايت قدر الإمكان):

  assets/site.css          SEARCH_CSS + NAV_CSS + LIVE_CSS   (مشترك)
  assets/match.css         VARS + أنماط المباراة + LINEUP_CSS
  assets/player.css        VARS + أنماط اللاعب
  assets/club.css          VARS + أنماط النادي
  assets/site.js           THEME_SCRIPT + BACK_SCRIPT + matchtime + nav + pwa (لا يتأثر باللغة)
  assets/{match,club,player}.{ar,en}.js   باقي سكربتات النوع (نصوص اللغة)
  assets/manifest.json     {"files": {اسم: hash8}}

⚠️ **كل سكربت بلا تصريحات عليا يُغلَّف بـtry/catch** — بالصفحات القديمة كان
   كل سكربت عنصراً مستقلاً فاستثناء أحدها لا يوقف التالي؛ ملف واحد يوقفه.
   السكربتات ذات التصريحات العليا (`var`/`const`/`function` بالعمود 0:
   goals وfollow وpage_script للنادي وسكربت المباراة) تبقى بلا تغليف
   (تغليفها يغيّر نطاق ما تصرّح به) وتوضع **أخيراً** بالحزمة كي لا يوقف
   استثناؤها غيرها.

⚠️ **مسارات مطلقة:** `UP`/`UPL` بسكربت البحث تصير `"/"` و`"/"` أو `"/en/"`.

⚠️ يعيد كتابة كتلة `ASSETS-BEGIN/END` بـ`sw.js` (VER = saffara-<hash>
   يتغيّر عند تغيّر أي أصل فينظّف المخزون القديم، وPRECACHE لـsite.css/js).

لا يُكتب ملف إن لم يتغيّر محتواه. التشغيل (من جذر المشروع):
    python make_assets.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from i18n import T  # noqa: E402
import theme  # noqa: E402
import navbar  # noqa: E402
import matchtime  # noqa: E402
import prefs  # noqa: E402
import search_view  # noqa: E402
import live_view  # noqa: E402
import make_matches  # noqa: E402
import make_players  # noqa: E402
import make_clubs  # noqa: E402

ASSETS = BASE / "assets"
SW = BASE / "sw.js"

SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)
DECL_RE = re.compile(r"^(?:var|let|const|function)\b", re.M)
UP_RE = re.compile(r'var UP="[^"]*", UPL="[^"]*";')


def inner(html):
    """نصوص <script> بلا سمات (وسم src=... يُهمَل)."""
    found = SCRIPT_RE.findall(html)
    assert found, "لا <script> بالمخرج"
    return "\n".join(x.strip("\n") for x in found)


def search_js(t, lang):
    js = inner(search_view.search_script(t, 0, lang))
    absolute = '/en/' if lang == "en" else '/'
    js, n = UP_RE.subn(f'var UP="/", UPL="{absolute}";', js)
    assert n == 1, "تعذّر تحويل UP/UPL إلى مطلق"
    return js


def bundle(parts):
    """parts: [(label, js)] — المعزولة أولاً مغلَّفة، ثم ذات التصريحات العليا."""
    iso, raw = [], []
    report = []
    for label, js in parts:
        if DECL_RE.search(js):
            raw.append((label, js))
            report.append(f"{label}=raw")
        else:
            iso.append((label, js))
            report.append(f"{label}=try")
    out = []
    for label, js in iso:
        out.append(f"/* {label} */\ntry{{\n{js}\n}}catch(e){{console.error('{label}',e);}}")
    for label, js in raw:
        out.append(f"/* {label} */\n{js}")
    return "\n;\n".join(out) + "\n", report


def main():
    ASSETS.mkdir(exist_ok=True)
    t_ar, t_en = T["ar"], T["en"]

    # ---- CSS ----
    files = {
        "site.css": theme_shared_css(),
        "match.css": make_matches.CSS_TYPE,
        "player.css": make_players.CSS_TYPE,
        "club.css": make_clubs.CSS_TYPE,
    }

    # ---- JS ----
    assert navbar.nav_script(t_ar) == navbar.nav_script(t_en), "nav_script يختلف بين اللغتين"
    site_js, rep = bundle([
        ("theme", inner(theme.THEME_SCRIPT)),
        ("back", inner(theme.BACK_SCRIPT)),
        ("matchtime", inner(matchtime.matchtime_script())),
        ("nav", inner(navbar.nav_script(t_ar))),
        # تسجيل sw.js + شريط "غير متصل" لكل صفحات الأصول (مباراة/نادي/لاعب)
        ("pwa", navbar.PWA_JS),
    ])
    files["site.js"] = site_js
    reports = {"site.js": rep}

    for lang in ("ar", "en"):
        t = T[lang]
        files[f"match.{lang}.js"], reports[f"match.{lang}.js"] = bundle([
            ("live", inner(live_view.live_script(t, 1))),
            ("match-page", make_matches.MATCH_PAGE_JS),
        ])
        files[f"club.{lang}.js"], reports[f"club.{lang}.js"] = bundle([
            ("live", inner(live_view.live_script(t, 1))),
            ("club-page", inner(make_clubs.page_script(t, lang))),
        ])
        files[f"player.{lang}.js"], reports[f"player.{lang}.js"] = bundle([
            ("prefs", inner(prefs.prefs_script())),
            ("goals", inner(make_players.goals_script(t))),
            ("follow", inner(make_players.follow_script(t))),
        ])

    # ---- كتابة + hash ----
    manifest = {}
    written = 0
    for name in sorted(files):
        data = files[name].encode("utf-8")
        manifest[name] = hashlib.sha1(data).hexdigest()[:8]
        p = ASSETS / name
        if not p.exists() or p.read_bytes() != data:
            p.write_bytes(data)
            written += 1
    mtxt = json.dumps({"files": manifest}, indent=1, sort_keys=True) + "\n"
    mp = ASSETS / "manifest.json"
    if not mp.exists() or mp.read_text(encoding="utf-8") != mtxt:
        mp.write_text(mtxt, encoding="utf-8")

    # ---- sw.js ----
    ver = hashlib.sha1(
        "|".join(f"{k}:{v}" for k, v in sorted(manifest.items())).encode()
    ).hexdigest()[:8]
    patch_sw(manifest, ver)

    total = sum(len(v.encode("utf-8")) for v in files.values())
    print(f"\n{'=' * 55}")
    print(f"  /assets: {len(files)} ملفاً، {total / 1000:.1f} ك.ب — كُتب {written}")
    for name in sorted(files):
        print(f"    {name:16} {len(files[name].encode('utf-8')) / 1000:7.1f} ك.ب  v={manifest[name]}")
    print(f"  sw.js VER = saffara-{ver}")
    for k, v in reports.items():
        print(f"    {k}: {', '.join(v)}")
    print(f"{'=' * 55}")


def theme_shared_css():
    return search_view.SEARCH_CSS + navbar.NAV_CSS + live_view.LIVE_CSS


def patch_sw(manifest, ver):
    s = SW.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in s else "\n"
    s = s.replace("\r\n", "\n")
    pre = [f"/assets/site.css?v={manifest['site.css']}",
           f"/assets/site.js?v={manifest['site.js']}"]
    block = ("/* ASSETS-BEGIN (يولّده make_assets.py — لا تعدّله يدوياً) */\n"
             f"const VER = 'saffara-{ver}';\n"
             "const ASSET_PRECACHE = [\n"
             + "".join(f"  '{u}',\n" for u in pre) +
             "];\n/* ASSETS-END */")
    m = re.search(r"/\* ASSETS-BEGIN.*?ASSETS-END \*/", s, re.S)
    assert m, "علامات ASSETS-BEGIN/END غائبة بـsw.js"
    new = s[:m.start()] + block + s[m.end():]
    if new != s:
        SW.write_text(new.replace("\n", nl), encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
