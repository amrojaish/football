#!/usr/bin/env python3
"""
رفع الحالة الدائمة (football.db + sitemap_state.json) مشفّرةً وفتح القفل
===========================================================================
    python db_push.py                  ← يرفع القاعدة المحلية كحالة جديدة ويفتح القفل
    python db_push.py --release-only   ← يفتح القفل بلا رفع (لم تغيّر القاعدة)
    python db_push.py --force-shrink   ← يسمح برفع قاعدة أصغر/أقدم (مقصود فقط)
    python db_push.py --init           ← التهيئة الأولى (ينشئ الإصدار ويرفع seq 1)
    python db_push.py --ci             ← من سير العمل (holder=ci)

يرفض الرفع إن: دُفعت حالة أحدث بعد سحبك (seq)، أو القفل لغيرك، أو القاعدة
معطوبة (integrity_check)، أو أعداد `matches/goals/events/lineup_players/
player_stats` أو أحدث مباراة أقل من البعيدة (راجع state_sync.push).

⚠️ **تعديل CSV وحده لا يحتاج رفعاً:** البوت يطبّق CSV على الحالة الدائمة كل تشغيل.
   الرفع لمن عدّل `football.db` مباشرةً (SQL يدوي) أو يريد تثبيت نتيجة apply محلية.
"""
import sys

import state_sync as ss

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ci = "--ci" in sys.argv
    holder = "ci" if ci else "local"
    store = ss.get_store()

    if "--release-only" in sys.argv:
        done = ss.release_lock(store, holder)
        print("🔓 فُتح القفل" if done else "ℹ️ لا قفل لك لفتحه")
        return

    key = ss.get_key()
    init = "--init" in sys.argv
    base = None
    if not init:
        b = ss.read_local_base()
        if not b:
            raise SystemExit("❌ لا سجل سحب (.db_base.json) — اسحب بـdb_pull.py أولاً")
        base = b["seq"]

    meta, uploaded = ss.push(store, key, ss.BASE, holder, base_seq=base,
                             force_shrink="--force-shrink" in sys.argv, init=init)
    ss.write_local_base(meta)
    if uploaded:
        print(f"✅ رُفعت seq {meta['seq']} ({meta['asset']}) — "
              f"matches {meta['counts']['matches']:,} · goals {meta['counts']['goals']:,}")
    else:
        print(f"ℹ️ لا تغيير بالمحتوى (seq {meta['seq']} كما هي) — فُتح القفل")
    keep = [h['seq'] for h in meta.get('history', [])]
    print(f"   المحفوظ: {keep}")


if __name__ == "__main__":
    main()
