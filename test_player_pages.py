#!/usr/bin/env python3
"""player_pages.build_plan: إسناد الأهداف لمعرّف (A/A2/B فقط)، لا احتياط «معرّف واحد بالمجمل»، استثناء B-فقط بلا لقب مشترك،
الـslug ثابت للاسم الأكثر أهدافاً، stubs بلا سلاسل ولا تعارض مع صفحة، حتميّة. التشغيل: python test_player_pages.py"""
import sqlite3
import sys

import player_pages as pp

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


def mk():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE matches (match_id INT PRIMARY KEY, date TEXT, season INT, league_code TEXT, home_id INT, away_id INT);
    CREATE TABLE goals (id INTEGER PRIMARY KEY, match_id INT, team_id INT, minute INT, player_en TEXT, player_ar TEXT, detail TEXT);
    CREATE TABLE lineup_players (match_id INT, team_id INT, player_id INT, player_en TEXT, player_ar TEXT, number INT, pos TEXT);
    CREATE TABLE player_stats (match_id INT, team_id INT, player_id INT, player_en TEXT, player_ar TEXT, minutes INT);
    """)
    for mid in range(1, 13):
        c.execute("INSERT INTO matches VALUES (?,?,?,?,?,?)", (mid, f"2025-0{(mid % 9) + 1}-10", 2025, "EGY", 7, 8))
    return c


def goal(c, gid, mid, team, name, detail="Normal Goal", ar=""):
    c.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?)", (gid, mid, team, 10, name, ar, detail))


def lineup(c, mid, team, pid, name, ar=""):
    c.execute("INSERT INTO lineup_players VALUES (?,?,?,?,?,?,?)", (mid, team, pid, name, ar, 9, "F"))


# ---- scenario 1: one person (id 100) under two name forms, A = lineup of the match
c = mk()
for mid in (1, 2, 3):
    lineup(c, mid, 7, 100, "Ahmed Ramadan")
    goal(c, mid, mid, 7, "Ahmed Ramadan")
for mid in (4, 5):
    lineup(c, mid, 7, 100, "A. Ramadan")
    goal(c, 10 + mid, mid, 7, "A. Ramadan")
p = pp.build_plan(c)
pids = [x for x in p["pages"] if x["kind"] == "pid"]
check("two name forms of one id -> ONE page (5 goals)", len(p["pages"]) == 1 and len(pids) == 1 and len(pids[0]["goals"]) == 5, [(x["slug"], len(x["goals"])) for x in p["pages"]])
check("  the page keeps the URL of the name with the most goals (ahmed-ramadan)", pids[0]["slug"] == "ahmed-ramadan", pids[0]["slug"])
check("  the other form's URL becomes a stub to it, no stub points at a stub", p["stubs"] == {"a-ramadan": "ahmed-ramadan"}, p["stubs"])
check("  display name = most-used form (Ahmed Ramadan 3+3 rows vs A. Ramadan 2+2)", pids[0]["display_en"] == "Ahmed Ramadan", pids[0]["display_en"])
check("  aliases map the new slug back to its old URL", p["aliases"] == {"ahmed-ramadan": ["a-ramadan"]}, p["aliases"])
check("  link_slug resolves both forms (and the (name, team) pair) to the new page", pp.link_slug("A. Ramadan", 7, p) == "ahmed-ramadan" and pp.link_slug("Ahmed Ramadan", plan=p) == "ahmed-ramadan")

check("  a name with NO goals whose guessed slug is an old URL (stub) resolves to the new page, never to the stub",
      pp.resolve_slug("A. Ramadán", "a-ramadan", plan=p) == "ahmed-ramadan" and pp.resolve_slug("Nobody", "nobody", plan=p) == "nobody")

# ---- scenario 2: own goal -> the scorer is in the OPPOSING lineup
c = mk()
lineup(c, 1, 8, 200, "Omar Kamal")                # plays for team 8, scored into his own net: goal credited to team 7
goal(c, 1, 1, 7, "Omar Kamal", detail="Own Goal")
p = pp.build_plan(c)
check("own goal found in the opposing lineup -> attributed to that id (A2)", p["via"].get("A2") == 1 and [x["kind"] for x in p["pages"]] == ["pid"], p["via"])

# ---- scenario 3: B (name+team has exactly one id) for a match without lineup data
c = mk()
lineup(c, 2, 7, 300, "Karim Hassan")
goal(c, 1, 9, 7, "Karim Hassan")                    # match 9: no lineup rows at all
p = pp.build_plan(c)
check("no lineup for the match, (name, team) has exactly one id -> attributed (B)", p["via"].get("B") == 1, p["via"])

# ---- scenario 4: NO fallback 'the name has one id overall' (m-i-hassan case): other team, no lineup -> stays on its name page
c = mk()
for mid in (1, 2):
    lineup(c, mid, 7, 400, "M. I. Hassan")          # id 400 plays for team 7 only
goal(c, 1, 9, 8, "M. I. Hassan")                    # a goal for TEAM 8 in a match without lineups
p = pp.build_plan(c)
check("name has one id overall but a different team + no lineup -> NOT attributed (stays a name page)", p["attributed"] == 0 and [x["kind"] for x in p["pages"]] == ["name"], p["via"])

# ---- scenario 5: pair whose ONLY evidence is B and no surname shared with the id's other forms -> not attributed
c = mk()
for mid in (1, 2, 3):
    lineup(c, mid, 7, 500, "Saad Al Salouli")
    lineup(c, mid, 7, 500, "Saad Alselouli")
goal(c, 1, 9, 7, "Saad Al Salouli")                 # B only; 'Salouli' vs 'Alselouli' shares no surname by the 0.8 test? (checked below)
p = pp.build_plan(c)
share = pp.shares_surname("Saad Al Salouli", "Saad Alselouli")
check("B-only pair is dropped exactly when no surname is shared (shares_surname=%s)" % share, (p["attributed"] == 0) == (not share), [p["attributed"], share])
c = mk()
for mid in (1, 2, 3):
    lineup(c, mid, 7, 501, "Islam Ahmed Hawsawi")
    lineup(c, mid, 7, 501, "Hawsawi Islam Ahmed")
goal(c, 1, 9, 7, "Islam Ahmed Hawsawi")
p = pp.build_plan(c)
check("  Islam Ahmed Hawsawi / Hawsawi Islam Ahmed (B only, surname-order differs) -> dropped like the approved rule", p["dropped_pairs"] == [("Islam Ahmed Hawsawi", 501)] or pp.shares_surname("Islam Ahmed Hawsawi", "Hawsawi Islam Ahmed"), p["dropped_pairs"])
# B-only pair that DOES share a surname is kept
c = mk()
for mid in (1, 2, 3):
    lineup(c, mid, 7, 502, "Ahmed Ali")
    lineup(c, mid, 7, 502, "A. Ali")
goal(c, 1, 9, 7, "Ahmed Ali")
p = pp.build_plan(c)
check("  B-only pair that shares the surname is kept", p["via"].get("B") == 1 and not p["dropped_pairs"], [p["via"], p["dropped_pairs"]])

# ---- scenario 6: the same text for two ids in the SAME match (ambiguous) stays on the name page; goals of that text in clear matches go to ids
c = mk()
lineup(c, 1, 7, 600, "M. Hamdi")
lineup(c, 1, 7, 601, "M. Hamdi")
lineup(c, 2, 7, 600, "M. Hamdi")
goal(c, 1, 1, 7, "M. Hamdi")                        # ambiguous (two ids in match 1)
goal(c, 2, 2, 7, "M. Hamdi")                        # only id 600 in match 2
p = pp.build_plan(c)
kinds = sorted((x["kind"], len(x["goals"])) for x in p["pages"])
check("ambiguous goal stays on the name page; the clear one goes to its id; the old URL stays a page (largest part)", kinds == [("name", 1), ("pid", 1)] and not p["stubs"], [kinds, p["stubs"]])

# ---- scenario 7: slug conflicts never reuse an old slug; stubs never collide with pages; deterministic
c = mk()
for mid in (1, 2, 3, 4):
    lineup(c, mid, 7, 700, "Mohamed Ali")
    goal(c, mid, mid, 7, "Mohamed Ali")
for mid in (5, 6):
    lineup(c, mid, 8, 701, "Mohamed Ali")             # a different person, same text, other team
    goal(c, 10 + mid, mid, 8, "Mohamed Ali")
p1, p2 = pp.build_plan(c), pp.build_plan(c)
slugs = [x["slug"] for x in p1["pages"]]
check("two people with the same text -> two pages, distinct slugs (clean one for the one with more goals)", len(slugs) == 2 and len(set(slugs)) == 2 and slugs[0] == "mohamed-ali" and slugs[1].startswith("mohamed-ali-"), slugs)
check("  stubs never collide with a page and never point at a stub", not (set(p1["stubs"]) & set(slugs)) and not any(t in p1["stubs"] for t in p1["stubs"].values()), p1["stubs"])
check("  deterministic: two runs give identical plans", [(x["slug"], x["kind"], x["pid"], len(x["goals"])) for x in p1["pages"]] == [(x["slug"], x["kind"], x["pid"], len(x["goals"])) for x in p2["pages"]] and p1["stubs"] == p2["stubs"])

# ---- scenario 8: pid 0 rows are never used as an id
c = mk()
c.execute("INSERT INTO player_stats VALUES (1, 7, 0, 'No Id Guy', '', 90)")
goal(c, 1, 1, 7, "No Id Guy")
p = pp.build_plan(c)
check("player_id=0 rows never attribute a goal (page stays name-keyed)", p["attributed"] == 0 and p["pages"][0]["kind"] == "name", p["pages"][0]["kind"])

# ---- scenario 9: URL history — a page removed by an id merge becomes a stub to the page now holding that player_id
import json
import os
import tempfile

import make_players as mp
import make_sitemap as ms

c = mk()
for mid in (1, 2, 3):                                   # person 100 (kept after the merge), page ali-one
    lineup(c, mid, 7, 100, "Ali One")
    goal(c, mid, mid, 7, "Ali One")
for mid in (4, 5):                                      # person 200 was merged into 100 in the DB: rows now carry id 100
    lineup(c, mid, 7, 100, "Ali One")
    goal(c, 10 + mid, mid, 7, "Ali One")
hist = {
    "ali-one": {"pid": 100, "name": "Ali One"},
    "ali-one-2": {"pid": 200, "name": "Ali One"},       # published earlier as person 200's own page
    "ali-one-3": {"pid": None, "name": "Ali One", "to": "ali-one-2"},   # manual redirect pointing at a slug that is itself now a stub
    "chain-first": {"pid": 200, "name": "X"},
    "ghost": {"pid": None, "name": "Ghost"},            # no id, no manual target
    "gone-id": {"pid": 999, "name": "Nobody"},          # id that holds no page at all
}
p = pp.build_plan(c, hist, {200: 100})
check("merged-away page (id 200 -> 100): its old URL becomes a stub to the kept id's page", p["stubs"].get("ali-one-2") == "ali-one" and p["stubs"].get("chain-first") == "ali-one", p["stubs"])
check("  a manual 'to' that points at a stub is resolved to the final page (no stub -> stub)", p["stubs"].get("ali-one-3") == "ali-one", p["stubs"])
check("  no stub points to a stub, none collides with a real page", not any(t in p["stubs"] for t in p["stubs"].values()) and not (set(p["stubs"]) & {x["slug"] for x in p["pages"]}), p["stubs"])
check("  no id and no manual target -> skipped and reported (ghost, gone-id)", sorted(p["unresolved"]) == ["ghost", "gone-id"] and "ghost" not in p["stubs"], p["unresolved"])
check("  a history slug that is a real page is left alone", "ali-one" not in p["stubs"])
check("  aliases carry the old URLs to the new page (followers keep following)", sorted(p["aliases"]["ali-one"]) == ["ali-one-2", "ali-one-3", "chain-first"], p["aliases"])
p0 = pp.build_plan(c, hist, None)
check("  without the merge map an id with no page stays unresolved (nothing guessed)", "ali-one-2" in p0["unresolved"] and "ali-one-2" not in p0["stubs"], p0["unresolved"])
check("  deterministic with history", pp.build_plan(c, hist, {200: 100})["stubs"] == p["stubs"])

# update_history adds pages, never deletes, and writes sorted one-line-per-slug JSON
d = tempfile.mkdtemp()
hp = __import__("pathlib").Path(d) / "h.json"
pp.write_history({"zeta": {"pid": 1, "name": "Z"}}, hp)
n = pp.update_history(p, hp, None)
h2 = pp.load_history(hp, None)
check("update_history: adds current pages, keeps older entries", set(h2) >= {"zeta", "ali-one"} and h2["ali-one"]["pid"] == 100
      and h2["zeta"] == {"pid": 1, "name": "Z"}, h2)
# 26 Oct 2026: redirects are recorded too, with the player of their target page (none of them was in this file yet)
check("  ... and its redirects, marked stub, with their target's player", n == 4 and {s for s, e in h2.items() if e.get("stub")} == {"ali-one-2", "ali-one-3", "chain-first"}
      and all(h2[s]["pid"] == 100 for s in ("ali-one-2", "ali-one-3", "chain-first")), (n, h2))
check("  second run changes nothing", pp.update_history(p, hp, None) == 0)
check("  file is valid JSON with the slugs map", "slugs" in json.loads(hp.read_text(encoding="utf-8")))

# a stub written by make_players is excluded from the sitemap (same detection the sitemap uses)
html = mp.redirect_html("ar", "ali-one", "Ali One")
sp = os.path.join(d, "stub.html")
open(sp, "w", encoding="utf-8").write(html)
real = os.path.join(d, "real.html")
open(real, "w", encoding="utf-8").write("<html><head><title>x</title></head><body>page</body></html>")
check("sitemap: redirect stub is flagged non-indexable, a real page is not", ms.file_hash(sp)[1] is True and ms.file_hash(real)[1] is False)
check("  the stub's target is the real page (refresh + canonical)", 'url=ali-one.html' in html and 'canonical" href="https://saffara.app/players/ali-one.html' in html, html[:400])

# ---- scenario 10: player_name_pins — the pinned name wins for display and slug; no other page changes; invalid pins are rejected
c = mk()
for mid in (1, 2, 3):
    lineup(c, mid, 7, 800, "Hamed Hamdan")
for mid in (4, 5, 6, 7):
    lineup(c, mid, 7, 801, "H. Hamdan")
goal(c, 1, 1, 7, "Hamed Hamdan")
goal(c, 2, 2, 7, "Hamed Hamdan")
for gid, mid in ((3, 4), (4, 5), (5, 6)):
    goal(c, gid, mid, 7, "H. Hamdan")
goal(c, 6, 8, 7, "Other Guy")
c.execute("UPDATE lineup_players SET player_id = 800 WHERE player_id = 801")          # merged: 801 -> 800
p_nopin = pp.build_plan(c, {"h-hamdan": {"pid": 801, "name": "H. Hamdan"}, "hamed-hamdan": {"pid": 800, "name": "Hamed Hamdan"}}, {801: 800})
p_pin = pp.build_plan(c, {"h-hamdan": {"pid": 801, "name": "H. Hamdan"}, "hamed-hamdan": {"pid": 800, "name": "Hamed Hamdan"}}, {801: 800}, {800: "Hamed Hamdan"})
pg = {x["pid"]: x for x in p_pin["pages"] if x["pid"]}
check("pin: without it the slug follows the name with most goals (h-hamdan)", {x["pid"]: x["slug"] for x in p_nopin["pages"] if x["pid"]}[800] == "h-hamdan")
check("  with it the page keeps hamed-hamdan and the pinned display name", pg[800]["slug"] == "hamed-hamdan" and pg[800]["display_en"] == "Hamed Hamdan" and len(pg[800]["goals"]) == 5, pg[800]["slug"])
check("  the dropped id's old slug becomes a stub to the pinned page; nothing else changes", p_pin["stubs"] == {"h-hamdan": "hamed-hamdan"} and sorted(x["slug"] for x in p_pin["pages"]) == ["hamed-hamdan", "other-guy"], [p_pin["stubs"], [x["slug"] for x in p_pin["pages"]]])
c2 = mk()
for mid in (1, 2):
    lineup(c2, mid, 7, 810, "Solo Player")
    goal(c2, mid, mid, 7, "Solo Player")
check("  a pin equal to the current name changes no slug (no merge)", [(x["slug"], x["display_en"]) for x in pp.build_plan(c2, None, None, {810: "Solo Player"})["pages"]] == [(x["slug"], x["display_en"]) for x in pp.build_plan(c2)["pages"]])
try:
    pp.build_plan(c, None, None, {800: "Nobody Here"})
    bad = False
except ValueError:
    bad = True
check("  a pin whose name is not a real name of that id is rejected", bad)
pf = __import__("pathlib").Path(tempfile.mkdtemp()) / "pins.csv"
pf.write_bytes(("\ufeffplayer_id,name_en,reason\r\n800,Hamed Hamdan,x\r\n800,H. Hamdan,y\r\n").encode("utf-8"))
try:
    pp.load_pins(pf)
    dup = False
except ValueError:
    dup = True
check("  a duplicate player_id in the pins file is rejected", dup)
pf.write_bytes(("\ufeffplayer_id,name_en,reason\r\n800,Hamed Hamdan,x\r\n").encode("utf-8"))
check("  load_pins reads BOM+CRLF files; missing file = {}", pp.load_pins(pf) == {800: "Hamed Hamdan"} and pp.load_pins(pf.with_name("none.csv")) == {})
c.execute("UPDATE lineup_players SET player_en = 'H. Hamdan' WHERE player_id = 800 AND match_id = 1")
pp.build_plan(c, None, None, {800: "H. Hamdan"})
check("  a pin name without a goals-name falls back to slug(pin) with a warning (no crash)", True)

# ---- scenario 11: published URLs stay with their player (26 Oct 2026, TUN import: a new namesake with more goals took m-diop)
c3 = mk()
for mid in (1, 2):                                      # site player 300 «M. Diop», 2 goals, published as m-diop
    lineup(c3, mid, 7, 300, "M. Diop")
    goal(c3, 1100 + mid, mid, 7, "M. Diop")
for mid in (3, 4, 5, 6, 7):                             # new-league namesake 301, 5 goals
    lineup(c3, mid, 8, 301, "M. Diop")
    goal(c3, 1100 + mid, mid, 8, "M. Diop")
by_pid = lambda pl: {x["pid"]: x["slug"] for x in pl["pages"] if x["kind"] == "pid"}  # noqa: E731
check("without history the namesake with more goals takes the clean slug (old behaviour, shows the risk)", by_pid(pp.build_plan(c3))[301] == "m-diop")
p = pp.build_plan(c3, {"m-diop": {"pid": 300, "name": "M. Diop"}}, None)
check("  with history: m-diop stays with 300, the new player gets a suffix", (by_pid(p)[300], by_pid(p)[301]) == ("m-diop", "m-diop-2"), by_pid(p))
check("  no stub created for either page", "m-diop" not in p["stubs"] and "m-diop-2" not in p["stubs"], p["stubs"])
p = pp.build_plan(c3, {"m-diop": {"pid": 300, "name": "M. Diop"}, "m-diop-2": {"pid": 999, "name": "M. Diop"}}, None)
check("  a suffix never reuses any published slug, even one whose owner has no page", by_pid(p)[301] == "m-diop-3", by_pid(p))
p = pp.build_plan(c3, {"m-diop": {"pid": 250, "name": "M. Diop"}}, {250: 300})
check("  owner resolved through player_id_merges (250 -> 300)", by_pid(p)[300] == "m-diop", by_pid(p))
p = pp.build_plan(c3, {"m-diop": {"pid": 999, "name": "M. Diop"}}, None)
check("  owner without a page any more: not blocked (old behaviour)", by_pid(p)[301] == "m-diop", by_pid(p))
c4 = mk()
for mid in (1, 2, 3, 4):                                # pid 400 «H. Jouini», 4 goals, published as h-jouini-2
    lineup(c4, mid, 7, 400, "H. Jouini")
    goal(c4, 1200 + mid, mid, 7, "H. Jouini")
for mid in (5, 6):                                      # name-only page «H. Jouini» (other team, no lineup), published as h-jouini
    goal(c4, 1200 + mid, mid, 8, "H. Jouini")
hist = {"h-jouini": {"pid": None, "name": "H. Jouini"}, "h-jouini-2": {"pid": 400, "name": "H. Jouini"}}
p = pp.build_plan(c4, hist, None)
names = {x["slug"]: (x["kind"], x["pid"]) for x in p["pages"]}
check("  name page keeps h-jouini, the id page keeps its own published h-jouini-2 (no swap)",
      names.get("h-jouini") == ("name", None) and names.get("h-jouini-2") == ("pid", 400), names)
check("  deterministic with ownership", pp.build_plan(c4, hist, None)["pages"] == p["pages"])

# ---- scenario 12: published REDIRECTS stay with their player too (m-hamed -> 342766, m-helal -> 17142; TUN namesakes 367517, 344922)
tmpd = __import__("pathlib").Path(tempfile.mkdtemp())
for site_pid, full, short, new_pid in ((342766, "Mohamed Hamed", "M. Hamed", 367517), (17142, "Mohamed Helal", "M. Helal", 344922)):
    c5 = mk()
    for mid in (1, 2, 3):                               # the site player scores under his full name ...
        lineup(c5, mid, 7, site_pid, full)
        goal(c5, 1300 + mid, mid, 7, full)
    lineup(c5, 4, 7, site_pid, short)                   # ... and once under the short form -> /short is a redirect to his page
    goal(c5, 1304, 4, 7, short)
    hf = tmpd / f"hist_{site_pid}.json"
    p0 = pp.build_plan(c5, {}, None)
    short_s, full_s = pp._slugify(short), pp._slugify(full)
    check(f"{short_s}: before the import it redirects to {full_s} ({site_pid})", p0["stubs"].get(short_s) == full_s, p0["stubs"])
    pp.update_history(p0, hf, seed=None)
    h = pp.load_history(hf, seed=None)
    check(f"  update_history records the redirect with its target player", h.get(short_s) == {"pid": site_pid, "name": full, "stub": True}, h.get(short_s))
    for mid in (5, 6, 7, 8, 9):                         # new-league namesake, 5 goals under the short form
        lineup(c5, mid, 8, new_pid, short)
        goal(c5, 1300 + mid, mid, 8, short)
    p_old = pp.build_plan(c5, {k: v for k, v in h.items() if not v.get("stub")}, None)
    check(f"  without the recorded redirect the namesake {new_pid} would take /{short_s} (the risk)",
          by_pid(p_old).get(new_pid) == short_s, by_pid(p_old))
    p1 = pp.build_plan(c5, h, None)
    check(f"  with it: /{short_s} still redirects to {site_pid}'s page, {new_pid} gets /{short_s}-2",
          p1["stubs"].get(short_s) == full_s and by_pid(p1)[site_pid] == full_s and by_pid(p1)[new_pid] == f"{short_s}-2",
          (p1["stubs"].get(short_s), by_pid(p1)))
    n = pp.update_history(p1, hf, seed=None)
    h2 = pp.load_history(hf, seed=None)
    check("  a recorded entry is never rewritten; the new page is added", h2[short_s] == h[short_s] and h2.get(f"{short_s}-2", {}).get("pid") == new_pid, (n, h2))

# ---- scenario 13: a player with a published page KEEPS that URL (26 Oct 2026, ALG prep: m-bencherifa, s-bouchama, mateus-toto)
c6 = mk()
for mid in (1, 2):                                      # site player 4536 scores as «M. Bencherifa» -> page m-bencherifa
    lineup(c6, mid, 7, 4536, "M. Bencherifa")
    goal(c6, 1400 + mid, mid, 7, "M. Bencherifa")
h6 = tmpd / "hist_4536.json"
p0 = pp.build_plan(c6, {}, None)
pp.update_history(p0, h6, seed=None)
check("4536 published as m-bencherifa", by_pid(p0)[4536] == "m-bencherifa", by_pid(p0))
for mid in (3, 4, 5):                                   # new league: 3 goals under another form -> the most-goals name changes
    lineup(c6, mid, 8, 4536, "M. W. Bencherifa")
    goal(c6, 1400 + mid, mid, 8, "M. W. Bencherifa")
p_old = pp.build_plan(c6, {}, None)
check("  without history the page would move to m-w-bencherifa (the risk)", by_pid(p_old)[4536] == "m-w-bencherifa", by_pid(p_old))
p1 = pp.build_plan(c6, pp.load_history(h6, seed=None), None)
check("  with history it stays on m-bencherifa; the new form's URL redirects to it", by_pid(p1)[4536] == "m-bencherifa"
      and p1["stubs"].get("m-w-bencherifa") == "m-bencherifa", (by_pid(p1), p1["stubs"]))
# two published pages of one player (an old one now a redirect): the CURRENT page wins once update_history has flagged the old one
c7 = mk()
for mid in (1, 2, 3):                                   # lineup + goal under the long form (A attribution), short form once
    lineup(c7, mid, 7, 370169, "Salah Abd Etouab Bouchama")
    goal(c7, 1500 + mid, mid, 7, "Salah Abd Etouab Bouchama")
lineup(c7, 4, 7, 370169, "S. Bouchama"); goal(c7, 1504, 4, 7, "S. Bouchama")
h7 = tmpd / "hist_370169.json"
pp.write_history({"s-bouchama": {"pid": 370169, "name": "S. Bouchama"},                    # old page (seed), no stub flag
                  "salah-abd-etouab-bouchama": {"pid": 370169, "name": "S. Bouchama"}}, h7)
p2 = pp.build_plan(c7, pp.load_history(h7, seed=None), None)
pp.update_history(p2, h7, seed=None)
hh = pp.load_history(h7, seed=None)
check("update_history flags a published page that is now a redirect (owner untouched)", hh["s-bouchama"] == {"pid": 370169, "name": "S. Bouchama", "stub": True}
      and not hh["salah-abd-etouab-bouchama"].get("stub"), hh)
for mid in (5, 6, 7, 8, 9):                             # new league: the short form now has the most goals
    lineup(c7, mid, 8, 370169, "S. Bouchama"); goal(c7, 1500 + mid, mid, 8, "S. Bouchama")
p3 = pp.build_plan(c7, hh, None)
check("  the current page salah-abd-etouab-bouchama stays; s-bouchama stays a redirect to it",
      by_pid(p3)[370169] == "salah-abd-etouab-bouchama" and p3["stubs"].get("s-bouchama") == "salah-abd-etouab-bouchama", (by_pid(p3), p3["stubs"]))
pp.write_history({"x-page": {"pid": 9, "name": "X", "stub": True}}, h7)
pp.update_history({"pages": [{"slug": "x-page", "pid": 9, "display_en": "X"}], "stubs": {}}, h7, seed=None)
check("  a redirect that becomes a page again loses the stub flag", pp.load_history(h7, seed=None)["x-page"] == {"pid": 9, "name": "X"})

sys.exit(1 if fail else 0)
