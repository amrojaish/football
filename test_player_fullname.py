#!/usr/bin/env python3
"""
Full-name line on player pages (1 Nov 2026). Static checks on the built pages (players/ + en/players/), no browser.
Run (after make_assets.py + make_players.py):
    python C:/Users/User/Projects/Football/test_player_fullname.py

  1  title / h1 are the known site name (unchanged): <title> = h1 + " — site"
  2  the grey line (p.pfull) is shown exactly when player_full_names.csv has a full name in the page language that differs
     from the h1, and it equals that name (HTML-escaped in the source)
  3  the AR page never shows Latin letters in that line, and never falls back to the English full name
  4  player.css styles .pfull with the muted text colour (dark mode follows the theme variables)
Reads football.db read-only (through player_pages.get_plan).
"""
import html
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import make_players as MP  # noqa: E402
from player_pages import get_plan  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + str(extra)[:800]))
    if not cond:
        fails += 1


conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
plan = get_plan(conn)
H1 = re.compile(r"<h1>(.*?)</h1>(<p class=\"pfull\">(.*?)</p>)?", re.S)
TITLE = re.compile(r"<title>(.*?) — ", re.S)
bad_title, bad_line, latin_ar, en_on_ar, missing = [], [], [], [], []
shown = {"ar": 0, "en": 0}
pages = 0
for p in plan["pages"]:
    pid = p["stats_pid"]
    for lang, path in (("ar", ROOT / "players" / f"{p['slug']}.html"), ("en", ROOT / "en" / "players" / f"{p['slug']}.html")):
        if not path.exists():
            missing.append(str(path))
            continue
        pages += 1
        h = path.read_text(encoding="utf-8")
        m, t = H1.search(h), TITLE.search(h)
        if not m or not t or html.unescape(t.group(1)) != html.unescape(m.group(1)):
            bad_title.append((p["slug"], lang, t and t.group(1), m and m.group(1)))
            continue
        h1 = html.unescape(m.group(1))
        got = html.unescape(m.group(3)) if m.group(2) else ""
        full = MP.full_name(pid, lang)
        want = full if full and full.strip() != h1.strip() else ""
        if got != want:
            bad_line.append((p["slug"], lang, pid, h1, got, want))
        if got:
            shown[lang] += 1
            if m.group(3) != html.escape(got, quote=True) and m.group(3) != html.escape(got, quote=False):
                bad_line.append((p["slug"], lang, "not escaped", m.group(3)))
        if lang == "ar" and got:
            if re.search(r"[A-Za-z]", got):
                latin_ar.append((p["slug"], got))
            if got == MP.full_name(pid, "en"):
                en_on_ar.append((p["slug"], got))

check(f"pages found for every plan entry ({pages} pages)", not missing, missing[:5])
check("1 title = h1 = known site name (full name never in the title)", not bad_title, bad_title[:5])
check(f"2 grey line shown exactly when the full name differs (AR {shown['ar']}, EN {shown['en']})", not bad_line, bad_line[:5])
check("3 AR line never has Latin letters", not latin_ar, latin_ar[:5])
check("3 AR line never falls back to the English full name", not en_on_ar, en_on_ar[:5])
css = (ROOT / "assets" / "player.css").read_text(encoding="utf-8")
check("4 player.css: .pfull small + muted colour", re.search(r"\.pfull\s*\{[^}]*color:\s*var\(--muted\)", css) is not None)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
