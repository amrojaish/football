#!/usr/bin/env python3
"""
كتلة TEAM_ID_ALIASES داخل worker.js من config.TEAM_ID_ALIASES (9 نوفمبر 2026) — مصدر واحد، نمط ASSETS-BEGIN بـsw.js
=================================================================================================================
الـworker لا يقرأ config.py، فهذا يكتب القاموس بين علامتي TEAM-ALIASES-BEGIN/END. شغّله بعد أي تعديل على TEAM_ID_ALIASES ثم انشر الـworker.
test_cups_push.py يفشل إن اختلفت الكتلة عن config.py. صفر طلبات، ولا يلمس football.db. لا خيارات.
    python make_worker_aliases.py
"""
import re
import sys
from pathlib import Path

from config import TEAM_ID_ALIASES

WORKER = Path(__file__).resolve().parent / "worker.js"
BLOCK_RE = re.compile(r"/\* TEAM-ALIASES-BEGIN.*?TEAM-ALIASES-END \*/", re.S)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def block():
    pairs = ", ".join(f"{k}: {v}" for k, v in sorted(TEAM_ID_ALIASES.items()))
    return ("/* TEAM-ALIASES-BEGIN (يولّده make_worker_aliases.py من config.TEAM_ID_ALIASES — لا تعدّله يدوياً) */\n"
            f"const TEAM_ID_ALIASES = {{ {pairs} }};\n"
            "/* TEAM-ALIASES-END */")


def main():
    raw = WORKER.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    s = raw.replace("\r\n", "\n")
    if len(BLOCK_RE.findall(s)) != 1:
        print("❌ علامتا TEAM-ALIASES غائبتان أو مكرّرتان بـworker.js")
        return 1
    new = BLOCK_RE.sub(lambda m: block(), s)
    if new == s:
        print("worker.js: كتلة الأسماء البديلة مطابقة (لا تغيير)")
        return 0
    WORKER.write_bytes(new.replace("\n", nl).encode("utf-8"))
    print(f"worker.js: كُتبت {len(TEAM_ID_ALIASES)} أسماء بديلة")
    return 0


if __name__ == "__main__":
    sys.exit(main())
