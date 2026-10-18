#!/usr/bin/env python3
"""
fetch_player_info.py (18 Oct 2026) — offline tests, zero API calls, no write to football.db. Run:
    python C:\\Users\\User\\Projects\\Football\\test_fetch_player_info.py
Fixtures: test_data/player_profiles/<id>.json = the 20 raw provider replies of the read-only probe (10 ids < 500000, 10 >= 500000).
"""
import hashlib
import json
import sqlite3
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import fetch_player_info as F  # noqa: E402
from config import DB_FILE  # noqa: E402

FIX = ROOT / "test_data" / "player_profiles"
fails = 0


def check(name, cond, extra=None):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + json.dumps(extra, ensure_ascii=False, default=str)[:600]))
    if not cond:
        fails += 1


def mem():
    c = sqlite3.connect(":memory:")
    F.ensure_tables(c)
    return c


ids = sorted(int(p.stem) for p in FIX.glob("*.json"))
SIL = (FIX / "silhouette.png").read_bytes()   # the provider's "no photo" image, saved once from the CDN
replies = {i: json.loads((FIX / f"{i}.json").read_text(encoding="utf-8")) for i in ids}
check("fixtures: 20 cached replies, 10 old (<500000) + 10 new", len(ids) == 20 and sum(i < 500000 for i in ids) == 10, ids)

# ── parse ──
P = {i: F.parse(r) for i, r in replies.items()}
old = [i for i in ids if i < 500000]
new = [i for i in ids if i >= 500000]
check("parse: every old id has birth date + nationality + position + number + photo",
      all(P[i] and P[i]["birth_date"] and P[i]["nationality"] and P[i]["position"] and P[i]["number"] is not None and P[i]["photo"] for i in old))
check("parse: 533862 (empty reply) -> None", P[533862] is None)
check("parse: new ids mostly lack birth date/nationality (2 of 9 with a profile have them), all have position + photo",
      sum(1 for i in new if P[i] and P[i]["birth_date"]) == 2 and all(P[i]["position"] and P[i]["photo"] for i in new if P[i]),
      {i: (P[i] or {}).get("birth_date") for i in new})
raw_h = {i: replies[i]["response"][0]["player"].get("height") for i in old}
check("parse: height/weight for 4 old ids only; provider format varies ('183' / '179 cm') -> stored as integers (cm / kg)",
      sorted(i for i in ids if P[i] and P[i]["height_cm"]) == sorted(i for i in old if raw_h[i]) and sum(1 for i in old if raw_h[i]) == 4
      and all(isinstance(P[i]["height_cm"], int) and 150 <= P[i]["height_cm"] <= 210 for i in old if raw_h[i])
      and all(isinstance(P[i]["weight_kg"], int) and 50 <= P[i]["weight_kg"] <= 110 for i in old if raw_h[i]), {i: (raw_h[i], P[i]["height_cm"]) for i in old})
check("measure: '183' -> 183, '179 cm' -> 179, '72 kg' -> 72, None / '' / 'n/a' -> None",
      [F.measure(x) for x in ("183", "179 cm", "72 kg", None, "", "n/a")] == [183, 179, 72, None, None, None])
s = replies[187953]["response"][0]["player"]
check("parse: field mapping (187953): name, birth date/place/country, nationality, height, weight, number, position, photo",
      P[187953]["birth_date"] == s["birth"]["date"] and P[187953]["birth_country"] == s["birth"]["country"] and P[187953]["nationality"] == s["nationality"]
      and P[187953]["height_cm"] == F.measure(s["height"]) and P[187953]["weight_kg"] == F.measure(s["weight"]) and P[187953]["number"] == s["number"]
      and P[187953]["position"] == s["position"] and P[187953]["photo"] == s["photo"] and P[187953]["name"] == s["name"], P[187953])
check("parse: blank strings stored as NULL, not ''", F.parse({"response": [{"player": {"id": 1, "name": " ", "birth": {"date": ""}}}]})["name"] is None)

# ── run from cached JSON: rows written, statuses, zero calls ──
c = mem()
rep = F.run(c, ids, 1_000_000, from_json=FIX, photo=None)
st = dict(c.execute("SELECT status, COUNT(*) FROM player_info GROUP BY status").fetchall())
check("run(from_json): 19 'ok' + 1 'empty', zero API calls, nothing counted against the daily cap",
      st == {"ok": 19, "empty": 1} and rep["calls"] == 0 and F.calls_today(c, 1_000_000) == 0, (st, rep))
r = c.execute("SELECT birth_date, nationality, height_cm, position, number, photo, status, tries, fetched_at FROM player_info WHERE player_id = 187953").fetchone()
check("run: stored row for 187953 matches the reply", r[0] == s["birth"]["date"] and r[1] == s["nationality"] and r[3] == s["position"] and r[6] == "ok" and r[8] == 1_000_000, r)

# ── schedule ──
c = mem()
now = 10_000_000
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (1, 'empty', 1, ?)", (now - 3600,))          # 1 h ago: not due
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (2, 'empty', 1, ?)", (now - 2 * F.DAY,))     # 2 d: due
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (3, 'empty', 2, ?)", (now - 3 * F.DAY,))     # needs 7 d
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (4, 'empty', 4, ?)", (now - 400 * F.DAY,))   # given up 400 d ago
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (8, 'empty', 4, ?)", (now - 100 * F.DAY,))   # given up 100 d ago
c.execute("INSERT INTO player_info (player_id, status, tries, last_try) VALUES (9, 'error', 1, ?)", (now - 2 * F.DAY,))     # 4xx 2 d ago
c.execute("INSERT INTO player_info (player_id, status, tries, last_try, fetched_at) VALUES (5, 'ok', 0, ?, ?)", (now - 10 * F.DAY, now - 10 * F.DAY))
c.execute("INSERT INTO player_info (player_id, status, tries, last_try, fetched_at) VALUES (6, 'ok', 0, ?, ?)", (now - 200 * F.DAY, now - 200 * F.DAY))
due = F.select_due(c, [1, 2, 3, 4, 5, 6, 7, 8, 9], now)
check("schedule: new first; empty/error retries at +1/+7/+30 d; after that re-checked every 180 d (4 tries, 400 d ago = due, "
      "100 d ago = not yet); then 'ok' older than 180 d",
      due == [(7, "new"), (2, "retry 1"), (4, "recheck"), (9, "retry 1"), (6, "refresh")], due)

# ── budget / daily cap / quota guard / failures, with a fake provider ──
calls = []


def fake(rem_seq=None, fail=()):
    it = iter(rem_seq or [])

    def f(pid):
        calls.append(pid)
        if pid in fail:
            return False, None, next(it, 6000), "HTTP 500"
        return True, replies.get(pid, {"response": []}), next(it, 6000), ""
    return f


F.DELAY = 0
c = mem(); calls.clear()
rep = F.run(c, ids, now, budget=5, fetch=fake(), remaining=6000)
check("budget: 5 calls max per run", rep["calls"] == 5 and len(calls) == 5 and F.calls_today(c, now) == 5, rep)
c = mem(); calls.clear()
c.execute("INSERT INTO player_info_calls (day, n) VALUES (?, 1498)", (F.utc_day(now),))
rep = F.run(c, ids, now, budget=100, daily_cap=1500, fetch=fake(), remaining=6000)
check("daily cap 1,500 (UTC day): 1,498 already used -> 2 calls", rep["calls"] == 2 and F.calls_today(c, now) == 1500, rep)
rep = F.run(c, ids, now, budget=100, daily_cap=1500, fetch=fake(), remaining=6000)
check("daily cap reached -> 0 calls, reason reported", rep["calls"] == 0 and "daily cap" in rep["stop"], rep)
c = mem(); calls.clear()
rep = F.run(c, ids, now, fetch=fake(), remaining=3400)
check("/status remaining 3,400 < 3,500 before start -> nothing fetched", rep["calls"] == 0 and not calls and "3400" in rep["stop"], rep)
c = mem(); calls.clear()
rep = F.run(c, ids, now, fetch=fake(rem_seq=[3700, 3600, 3499, 3400]), remaining=3800)
check("reply header remaining drops under 3,500 -> stop right after that call (3 calls)", rep["calls"] == 3 and "3499" in rep["stop"], rep)
c = mem(); calls.clear()
rep = F.run(c, ids[:4], now, fetch=fake(fail={ids[1]}), remaining=6000)
row = c.execute("SELECT COUNT(*) FROM player_info WHERE player_id = ?", (ids[1],)).fetchone()[0]
check("transient failure (HTTP 500): not recorded (id stays due), but the call counts against the daily cap",
      rep["failed"] == 1 and row == 0 and F.calls_today(c, now) == 4 and (ids[1], "new") in F.select_due(c, ids[:4], now), rep)


def fake_reason(reasons):
    def f(pid):
        calls.append(pid)
        r = reasons.get(pid)
        return (False, None, 6000, r) if r else (True, replies.get(pid, {"response": []}), 6000, "")
    return f


c = mem(); calls.clear()
rs = {ids[0]: "persistent: HTTP 404", ids[1]: "persistent: API {\"player\": \"The Player field must contain an integer.\"}",
      ids[2]: "Timeout", ids[3]: "HTTP 503"}
rep = F.run(c, ids[:5], now, fetch=fake_reason(rs), remaining=6000)
st = {r[0]: r[1:] for r in c.execute("SELECT player_id, status, tries, last_error FROM player_info")}
check("persistent failures (HTTP 4xx, non-quota error body) recorded as 'error' with tries 1 + reason; timeout / 5xx not recorded",
      st.get(ids[0])[:2] == ("error", 1) and st[ids[0]][2] == "HTTP 404" and st.get(ids[1])[:2] == ("error", 1)
      and ids[2] not in st and ids[3] not in st and rep["errors"] == 2 and rep["failed"] == 2 and st.get(ids[4], ("",))[0] == "ok", (st, rep))
due = F.select_due(c, ids[:5], now)
check("recorded errors wait for their backoff (+1 d); transient ones are due again on the next run",
      [d[0] for d in due] == [ids[2], ids[3]] and [d[0] for d in F.select_due(c, ids[:5], now + F.DAY)] == [ids[2], ids[3], ids[0], ids[1]], due)
F.run(c, [ids[0]], now + F.DAY, fetch=fake_reason({ids[0]: "persistent: HTTP 404"}), remaining=6000)
check("a repeated 4xx climbs the same backoff ladder (tries 2 -> next wait 7 d)",
      c.execute("SELECT tries FROM player_info WHERE player_id = ?", (ids[0],)).fetchone()[0] == 2
      and not F.select_due(c, [ids[0]], now + 7 * F.DAY) and F.select_due(c, [ids[0]], now + 8 * F.DAY), None)
QB = "quota: {\"requests\": \"You have reached the request limit for the day\"}"


def fake_q(rem_for_quota):
    """ids[1] answers a quota-looking error body with the given remaining header; every other id is normal"""
    def f(pid):
        calls.append(pid)
        if pid == ids[1]:
            return False, None, rem_for_quota, QB
        return True, replies.get(pid, {"response": []}), 6000, ""
    return f


def nrow(c, pid):
    return c.execute("SELECT COUNT(*) FROM player_info WHERE player_id = ?", (pid,)).fetchone()[0]


c = mem(); calls.clear()
rep = F.run(c, ids[:5], now, fetch=fake_q(6000), remaining=6000)
r1 = c.execute("SELECT status, tries, last_error FROM player_info WHERE player_id = ?", (ids[1],)).fetchone()
check("quota-looking error body but header remaining 6,000 >= 3,500: recorded as 'error' (tries 1, reason kept), run goes on to the next ids",
      r1 and r1[:2] == ("error", 1) and "request limit" in r1[2] and "6000" in r1[2] and rep["calls"] == 5 and not rep["stop"]
      and all(nrow(c, x) for x in ids[2:5]) and rep["errors"] == 1, (r1, rep))
check("... and that id then waits its normal backoff (+1 d)", ids[1] not in [d[0] for d in F.select_due(c, ids[:5], now)]
      and ids[1] in [d[0] for d in F.select_due(c, ids[:5], now + F.DAY)])
c = mem(); calls.clear()
rep = F.run(c, ids[:5], now, fetch=fake_q(3200), remaining=6000)
check("quota-looking error body with header remaining 3,200 < 3,500: run stops at once, nothing recorded for that id, no later id called",
      rep["calls"] == 2 and "3200" in rep["stop"] and nrow(c, ids[1]) == 0 and calls == ids[:2], (rep, calls))
c = mem(); calls.clear()
rep = F.run(c, ids[:5], now, fetch=fake_q(None), remaining=6000, status=lambda: 5000)
check("no remaining header: the free /status is read (5,000 >= 3,500) -> recorded as 'error', run goes on",
      nrow(c, ids[1]) == 1 and rep["calls"] == 5 and not rep["stop"], rep)
c = mem(); calls.clear()
rep = F.run(c, ids[:5], now, fetch=fake_q(None), remaining=6000, status=lambda: 1200)
check("no header, /status says 1,200 < 3,500 -> run stops, nothing recorded", rep["calls"] == 2 and nrow(c, ids[1]) == 0 and "1200" in rep["stop"], rep)
c = mem(); calls.clear()
rep = F.run(c, ids[:5], now, fetch=fake_q(None), remaining=6000, status=lambda: None)
check("no header and /status unreadable -> safe side: stop, nothing recorded", rep["calls"] == 2 and nrow(c, ids[1]) == 0 and rep["stop"], rep)
check("failure_kind: 'persistent:' / 'quota:' prefixes, everything else transient",
      [F.failure_kind(x) for x in ("persistent: HTTP 404", "quota: x", "HTTP 500", "Timeout", "", None)]
      == ["persistent", "quota", "transient", "transient", "transient", "transient"])
c = mem()
F.save(c, 9, F.parse(replies[187953]), now)
F.save(c, 9, None, now + 200 * F.DAY)
F.save_miss(c, 9, "error", now + 201 * F.DAY, "HTTP 404")
r9 = c.execute("SELECT status, birth_date, fetched_at FROM player_info WHERE player_id = 9").fetchone()
check("an empty / error refresh never downgrades an 'ok' row (profile kept, refresh clock restarted)",
      r9[0] == "ok" and r9[1] and r9[2] == now + 201 * F.DAY and not F.select_due(c, [9], now + 210 * F.DAY), r9)

# ── photo flag (CDN GET + SHA-256 of the image): equal to the provider's silhouette = no photo ──
class Resp:
    def __init__(self, code, body, ctype="image/png"):
        self.status_code, self.content, self.headers = code, body, {"Content-Type": ctype, "Content-Length": str(len(body))}


import hashlib  # noqa: E402
check("fixture silhouette.png has the pinned SHA-256", hashlib.sha256(SIL).hexdigest() == F.SILHOUETTE_SHA256)
real = sys.modules.get("requests")
fake_req = types.SimpleNamespace(get=None)
sys.modules["requests"] = fake_req
try:
    res = []
    for resp in (Resp(200, SIL), Resp(200, b"\x89PNG" + b"x" * 5188), Resp(200, b"\x89PNG real photo bytes"),
                 Resp(404, b"nf"), Resp(200, b"<html>", "text/html"), Resp(200, b"")):
        fake_req.get = (lambda r: (lambda url, **k: r))(resp)
        res.append(F.photo_flag(1))

    def boom(url, **k):
        raise OSError("down")
    fake_req.get = boom
    res.append(F.photo_flag(1))
finally:
    if real is not None:
        sys.modules["requests"] = real
    else:
        del sys.modules["requests"]
check("photo: silhouette bytes -> 0; a DIFFERENT image of the same 5,192-byte size -> 1 (hash, not size); real -> 1; "
      "404 / not an image / empty / network failure -> None",
      res == [0, 1, 1, None, None, None, None], res)
c = mem()
flags = {ids[0]: 1, ids[1]: 0}
F.run(c, ids[:3], now, from_json=FIX, photo=lambda pid: flags.get(pid))
hp = dict(c.execute("SELECT player_id, has_photo FROM player_info").fetchall())
check("run: has_photo stored per id (HEAD None stays NULL for a later run)", hp[ids[0]] == 1 and hp[ids[1]] == 0 and hp[ids[2]] is None, hp)

# ── CI wiring + --check writes nothing ──
ua = (ROOT / "update_all.py").read_text(encoding="utf-8")
i_f, i_r, i_a = ua.index('"fetch_player_info.py"'), ua.index('"refresh_goal_names.py"'), ua.index('"apply_merges.py"')
check("update_all: step after the last fetcher (refresh_goal_names) and before the apply steps, cap 3000 / floor 2000",
      i_r < i_f < i_a and '"--daily-cap", "3000"' in ua and '"--min-remaining", "2000"' in ua)
md5 = lambda: hashlib.md5(DB_FILE.read_bytes()).hexdigest()
before = md5()
import subprocess  # noqa: E402
out = subprocess.run([sys.executable, str(ROOT / "fetch_player_info.py"), "--check", "--from-json", str(FIX), "--no-photo",
                      "--ids", ",".join(map(str, ids))], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
real_db = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
has_tbl = real_db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'player_info'").fetchone()[0]
real_db.close()
check("--check --from-json: football.db md5 unchanged, no player_info table created, 19 ok + 1 empty, 0 API calls",
      md5() == before and has_tbl == 0 and "ok 19" in out and "empty 1" in out and "API calls 0" in out, out[-400:])

print("TOTAL FAILS:", fails)
raise SystemExit(1 if fails else 0)
