#!/usr/bin/env python3
"""
توليد DB_KEY (32 بايت عشوائية) — يُكتب بـ.env وينسخ للحافظة، ولا يُطبَع
=========================================================================
    python db_keygen.py          ← يولّد ويكتب DB_KEY=… بـ.env (يرفض لو موجود)
    python db_keygen.py --force  ← يستبدل (⚠️ المفتاح القديم لا يفك الحالة المرفوعة!)

بعد التشغيل (الحافظة تحمل المفتاح):
  1) الصقه بسرّ المستودع: Settings → Secrets and variables → Actions → DB_KEY
  2) الصقه بمدير كلمات المرور (نسخة ثانية)
  3) امسح الحافظة.
⚠️ المفتاح لا يُطبَع بالطرفية عمداً (حتى لا يدخل سجلات الجلسة). ضياعه = ضياع
   الحالة المشفّرة — احتفظ بنسخ غير مشفّرة دورية (db_pull.py --backup-only).
"""
import base64
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"


def main():
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    has = any(l.startswith("DB_KEY=") for l in lines)
    if has and "--force" not in sys.argv:
        raise SystemExit("❌ DB_KEY موجود بـ.env أصلاً (--force لاستبداله — يُبطل الحالة المرفوعة)")
    key = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    lines = [l for l in lines if not l.startswith("DB_KEY=")] + [f"DB_KEY={key}"]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    copied = False
    try:
        if os.name == "nt":
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Set-Clipboard -Value ([Console]::In.ReadToEnd().Trim())"],
                           input=key.encode(), check=True)
            copied = True
    except Exception:
        pass
    print("✅ كُتب DB_KEY بـ.env" + (" ونُسخ للحافظة" if copied else
                                      " (انسخه يدوياً من .env — لم تتوفر الحافظة)"))
    print("   الصقه بسرّ المستودع DB_KEY وبمدير كلمات المرور، ثم امسح الحافظة.")


if __name__ == "__main__":
    main()
