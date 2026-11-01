#!/usr/bin/env python3
"""
Short names parity (1 Nov 2026): short_names.short_name (Python, static pages) and SN.one from SHORT_JS (live pages) must give
identical output for ALL distinct names — Arabic from players_ar.csv + player_en / player_ar from football.db (read-only).
Needs node on PATH. Run:
    python C:/Users/User/Projects/Football/test_short_names_parity.py
"""
import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import short_names as SN  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

names = set()
with open(ROOT / "players_ar.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        for k in ("player_ar", "player_en"):
            if (r.get(k) or "").strip():
                names.add(r[k])
conn = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
for t in ("lineup_players", "player_stats", "goals", "events"):
    for a, b in conn.execute(f"SELECT player_en, player_ar FROM {t}"):
        for n in (a, b):
            if n and n.strip():
                names.add(n)
for (a,) in conn.execute("SELECT assist_en FROM events"):
    if a and a.strip():
        names.add(a)
names = sorted(names)
js = "var window={};" + SN.SHORT_JS + """
var d='';process.stdin.setEncoding('utf8');process.stdin.on('data',function(c){d+=c;});
process.stdin.on('end',function(){var a=JSON.parse(d);process.stdout.write(JSON.stringify(a.map(function(n){return window.SN.one(n);})));});
"""
r = subprocess.run(["node", "-e", js], input=json.dumps(names, ensure_ascii=False).encode("utf-8"), capture_output=True, check=True)
out_js = json.loads(r.stdout.decode("utf-8"))
diff = [(n, SN.short_name(n), j) for n, j in zip(names, out_js) if SN.short_name(n) != j]
print(f"names {len(names)} | shortened (python) {sum(1 for n in names if SN.short_name(n) != n.strip())} | python/js differences {len(diff)}")
for n, p, j in diff[:20]:
    print(f"  DIFF {n!r} | py {p!r} | js {j!r}")
# map() parity on a few collision groups
grp = ["Mohammed Ali Saleh", "Mohammed Ahmed Saleh", "Ali Hassan Omar", "Ali Omar", "عز الدين دوخة", "محمد أمين بوزيان"]
r2 = subprocess.run(["node", "-e", "var window={};" + SN.SHORT_JS + "var a=" + json.dumps(grp, ensure_ascii=False)
                     + ";var f=window.SN.map(a);process.stdout.write(JSON.stringify(a.map(f)));"], capture_output=True, check=True)
pm = SN.page_map(grp)
mdiff = [n for n, j in zip(grp, json.loads(r2.stdout.decode("utf-8"))) if pm[n] != j]
print(f"map() differences {len(mdiff)} {mdiff}")
ok = not diff and not mdiff
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
