#!/usr/bin/env python3
"""state_sync.GitHubStore._req: يعيد المحاولة عند ConnectionError/Timeout كما عند 5xx/429
(run 42154405195، 6 نوفمبر 2026: RemoteDisconnected عند 03:05Z). بلا شبكة — requests مزيَّف، والنوم مُلغى.
التشغيل: python test_state_sync_retry.py"""
import sys

import requests

import state_sync as ss

fail = 0


def check(name, cond, extra=None):
    global fail
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" {extra}"))
    if not cond:
        fail += 1


class Resp:
    def __init__(self, status):
        self.status_code = status


class FakeRequests:
    """يرمي/يرجّع عناصر script بالترتيب (استثناء = يُرمى)."""
    exceptions = requests.exceptions

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, **kw):
        self.calls += 1
        x = self.script.pop(0)
        if isinstance(x, BaseException):
            raise x
        return x


sleeps = []
ss.time.sleep = lambda s: sleeps.append(s)


def store(script):
    s = ss.GitHubStore("owner/repo", "token")
    s.r = FakeRequests(script)
    return s


def run(script):
    sleeps.clear()
    s = store(script)
    try:
        return s._req("GET", "https://api.github.com/x"), s.r.calls, None
    except Exception as e:  # noqa: BLE001
        return None, s.r.calls, e


RD = requests.exceptions.ConnectionError("('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))")

# 1) انقطاع واحد ثم 200 ← ينجح بالمحاولة الثانية
r, n, e = run([RD, Resp(200)])
check("ConnectionError then 200 -> 200", e is None and r.status_code == 200 and n == 2, (r, n, e))
check("  backoff 1s before retry", sleeps == [1], sleeps)

# 2) مهلة قراءة ثم 200
r, n, e = run([requests.exceptions.ReadTimeout("read timed out"), Resp(200)])
check("ReadTimeout then 200 -> 200", e is None and r.status_code == 200 and n == 2, (r, n, e))

# 3) مهلة اتصال (ConnectTimeout يرث الاثنين) ثم 502 ثم 200 — خليط الأعطال
r, n, e = run([requests.exceptions.ConnectTimeout("connect"), Resp(502), Resp(201)])
check("ConnectTimeout, 502, 201 -> 201", e is None and r.status_code == 201 and n == 3, (r, n, e))
check("  backoff 1s, 2s", sleeps == [1, 2], sleeps)

# 3b) انقطاع أثناء قراءة جسم الردّ (ChunkedEncodingError — لا يرث ConnectionError) ثم 200
r, n, e = run([requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead"), Resp(200)])
check("ChunkedEncodingError then 200 -> 200", e is None and r.status_code == 200 and n == 2, (r, n, e))
r, n, e = run([requests.exceptions.ChunkedEncodingError("x")] * 4)
check("4x ChunkedEncodingError -> raises after 4", isinstance(e, requests.exceptions.ChunkedEncodingError) and n == 4, (r, n, e))

# 4) أربعة انقطاعات ← يُرفع الاستثناء بعد 4 محاولات (لا ابتلاع صامت)
r, n, e = run([RD, RD, RD, RD])
check("4x ConnectionError -> raises after 4 attempts", isinstance(e, requests.exceptions.ConnectionError) and n == 4, (r, n, e))
check("  3 sleeps 1/2/4 (none after last)", sleeps == [1, 2, 4], sleeps)

# 5) انقطاعات ثم 5xx بالمحاولة الأخيرة ← يرجّع الردّ الأخير كالسلوك القديم
r, n, e = run([RD, RD, RD, Resp(503)])
check("3x ConnectionError then 503 -> returns 503", e is None and r.status_code == 503 and n == 4, (r, n, e))

# 6) أخطاء غير شبكية لا يُعاد عليها (خطأ برمجي يظهر فوراً)
r, n, e = run([ValueError("bug"), Resp(200)])
check("ValueError not retried", isinstance(e, ValueError) and n == 1, (r, n, e))

# 7) السلوك القديم: 4xx غير 429 يرجع فوراً، 429 يُعاد
r, n, e = run([Resp(404)])
check("404 returned immediately", e is None and r.status_code == 404 and n == 1, (r, n, e))
r, n, e = run([Resp(429), Resp(200)])
check("429 retried", e is None and r.status_code == 200 and n == 2, (r, n, e))

print(f"\n{'ALL PASS' if not fail else f'{fail} FAILED'}")
sys.exit(1 if fail else 0)
