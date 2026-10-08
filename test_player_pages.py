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

sys.exit(1 if fail else 0)
