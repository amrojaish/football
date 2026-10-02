#!/usr/bin/env python3
"""
سحب الحالة الدائمة (football.db + sitemap_state.json) وفك تشفيرها
====================================================================
محلياً (بداية الجلسة):
    python db_pull.py                       ← يسحب آخر حالة، ويضع **قفلاً 6 ساعات**
                                              فيتخطى البوت تشغيله حتى db_push.py
    python db_pull.py --no-lock             ← قراءة بلا قفل (لا تدفع بعدها)
    python db_pull.py --backup-only         ← نسخة غير مشفَّرة مؤرَّخة فقط (بلا لمس
                                              ملفات المشروع ولا قفل) — للجدولة الدورية
    python db_pull.py --backup-dir D:\\backups   ← مجلد النسخ (أو DB_BACKUP_DIR بـ.env)
    python db_pull.py --version 12          ← نسخة قديمة (7 تواريخ محفوظة) — بلا قفل
                                              ولا يمكن الرفع بعدها بلا سحب جديد
    python db_pull.py --force               ← الكتابة فوق قاعدة محلية فيها تعديلات
                                              لم تُرفع (مرفوض افتراضياً)

بالـCI: python db_pull.py --ci  (يكتب skip=true بمخرجات الخطوة إن كان القفل لغيره).

⚠️ **النسخ الاحتياطية المحلية غير مشفَّرة عمداً** (حماية من فقدان DB_KEY) —
   احفظها خارج المستودع. التحذير يظهر إن تجاوز عمر آخر نسخة 7 أيام.
"""
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import state_sync as ss

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def backup_age_days(d):
    files = sorted(Path(d).glob("football-*.db"))
    if not files:
        return None
    return (datetime.now().timestamp() - files[-1].stat().st_mtime) / 86400


def write_backup(d, tmp, meta):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = d / f"football-{stamp}-seq{meta['seq']}.db"
    if list(d.glob(f"football-*-seq{meta['seq']}.db")):
        print(f"  ℹ️ نسخة seq {meta['seq']} موجودة أصلاً بـ{d}")
        return None
    shutil.copy2(Path(tmp) / "football.db", dst)
    return dst


def main():
    ci = "--ci" in sys.argv
    holder = "ci" if ci else "local"
    store = ss.get_store()
    key = ss.get_key()
    version = arg("--version")
    backup_only = "--backup-only" in sys.argv
    force = "--force" in sys.argv
    bdir = arg("--backup-dir") or os.environ.get("DB_BACKUP_DIR")
    if bdir:
        bdir = os.path.expandvars(bdir)

    hours = 0 if ("--no-lock" in sys.argv or backup_only or version) else \
        float(arg("--lock-hours", 1.5 if ci else 6))

    local_db = ss.BASE / "football.db"
    if not backup_only and not ci and local_db.exists() and not force:
        base = ss.read_local_base()
        sha = ss.content_sha(ss.BASE)
        if base and sha != base["content_sha"]:
            raise SystemExit("❌ القاعدة المحلية فيها تعديلات لم تُرفع (db_push.py) — "
                             "الاسحب يمحوها. --force لو متأكد.")
        if not base:
            remote = store.get_meta()
            if remote and remote["content_sha"] != sha:
                raise SystemExit("❌ قاعدة محلية بلا سجل سحب سابق وتختلف عن البعيدة — "
                                 "--force للكتابة فوقها (احتفظ بنسخة قبلها).")

    try:
        meta, tmp = ss.pull(store, key, holder, lock_hours=hours,
                            version=int(version) if version else None)
    except ss.Locked as e:
        if ci:
            print(f"⏸️ {e} — يُتخطى هذا التشغيل")
            ss.gh_output(skip="true")
            return
        raise SystemExit(f"❌ {e}")

    if bdir:
        dst = write_backup(bdir, tmp, meta)
        if dst:
            print(f"  💾 نسخة غير مشفَّرة: {dst}")
        age = backup_age_days(bdir)
        if age is not None and age > 7:
            print(f"  ⚠️ آخر نسخة احتياطية بعمر {age:.0f} يوماً")
    elif not ci and not backup_only:
        print("  ⚠️ لا مجلد نسخ احتياطية (DB_BACKUP_DIR أو --backup-dir) — فقدان DB_KEY "
              "يعني فقدان الحالة")

    if backup_only:
        print(f"✅ نسخة seq {meta['seq']} فقط (لم يُمَس المشروع)")
        return

    for name in ss.STATE_FILES:
        src = Path(tmp) / name
        if src.exists():
            try:
                os.replace(src, ss.BASE / name)
            except OSError:
                shutil.move(str(src), str(ss.BASE / name))
    if version:
        print(f"✅ نسخة {version} وُضعت (بلا قفل ولا سجل سحب — الرفع بعدها مرفوض)")
    else:
        ss.write_local_base(meta)
        lk = ss.lock_info(meta)
        print(f"✅ seq {meta['seq']} ({meta['created_at']}، {meta['created_by']})")
        if hours:
            print(f"🔒 القفل لـ{holder} حتى {lk['expires_at'] if lk else '?'} — "
                  "افتحه بـdb_push.py (أو --release-only)")
    if ci:
        ss.gh_output(skip="false")


if __name__ == "__main__":
    main()
