#!/usr/bin/env python3
"""حالة الحالة الدائمة: البعيدة، القفل، سجل السحب المحلي، عمر آخر نسخة احتياطية."""
import os
import sys
from datetime import datetime
from pathlib import Path

import state_sync as ss

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ss.load_env()
    store = ss.get_store()
    meta = store.get_meta()
    if not meta:
        print("لا حالة بعد (db_push.py --init)")
        return
    print(f"البعيدة: seq {meta['seq']} — {meta['created_at']} ({meta['created_by']})")
    print(f"  الأصل: {meta['asset']}")
    print(f"  أعداد: {meta['counts']}  · أحدث مباراة: {meta.get('max_match_date')}")
    print(f"  محفوظ: {[h['seq'] for h in meta.get('history', [])]}")
    lk = ss.lock_info(meta)
    print(f"  القفل: {('لـ' + lk['holder'] + ' حتى ' + lk['expires_at']) if lk else 'لا'}")
    base = ss.read_local_base()
    if base:
        same = ss.content_sha(ss.BASE) == base["content_sha"] if (ss.BASE / "football.db").exists() else None
        print(f"محلياً: سُحبت seq {base['seq']} ({base['pulled_at']}) — "
              f"{'بلا تعديلات' if same else 'فيها تعديلات لم تُرفع' if same is False else 'لا قاعدة'}"
              f"{' — ⚠️ أقدم من البعيدة' if base['seq'] < meta['seq'] else ''}")
    else:
        print("محلياً: لا سجل سحب")
    bdir = os.environ.get("DB_BACKUP_DIR")
    if bdir and Path(os.path.expandvars(bdir)).exists():
        files = sorted(Path(os.path.expandvars(bdir)).glob("football-*.db"))
        if files:
            age = (datetime.now().timestamp() - files[-1].stat().st_mtime) / 86400
            print(f"نسخ احتياطية: {len(files)} — الأحدث {files[-1].name} (عمر {age:.1f} يوماً"
                  f"{' ⚠️ أكثر من 7' if age > 7 else ''})")
        else:
            print("نسخ احتياطية: لا شيء بالمجلد")
    else:
        print("نسخ احتياطية: DB_BACKUP_DIR غير مضبوط")


if __name__ == "__main__":
    main()
