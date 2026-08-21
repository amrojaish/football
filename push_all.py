#!/usr/bin/env python3
"""
رفع بأمر واحد — مع حل تعارض الملفات الثنائية تلقائياً
=========================================================
يجمع: add -> commit -> pull --rebase -> حل التعارض -> push

⚠️ سبب وجوده: football.db متتبَّع بـGit وهو ملف ثنائي لا يُدمَج،
   والأتمتة تعدّله وترفعه كل 30 دقيقة. أي جلسة تتجاوز نصف ساعة
   تصطدم به حتماً (درس 40).

⚠️ أثناء rebase تنقلب الخيارات: --theirs هي نسختك أنت لا الخادم
   (درس 65). السكربت يستعمل --theirs عمداً وهذا صحيح.

⚠️ لا يستعمل force push إطلاقاً. عند أي حالة غير متوقعة يوقف
   ويترك القرار للمستخدم بدل التخمين.

التشغيل:
    python push_all.py "رسالة الكوميت"
    python push_all.py "رسالة" --check    <- عرض بس بلا رفع
"""

import subprocess
import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ملفات نأخذ فيها نسختنا المحلية دائماً عند التعارض
# (مولّدة أو ثنائية — إعادة التوليد أرخص من الدمج اليدوي، درس 31)
OURS_ALWAYS = {
    "football.db",
    "sitemap_state.json",
    "sitemap.xml",
    "search_data.js",
    "live.json",
    "index.html",
}
OURS_PREFIX = ("clubs/", "en/", "matches/", "players/")


def run(args, check=False):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def conflicts():
    _, out, _ = run(["git", "diff", "--name-only", "--diff-filter=U"])
    return [x for x in out.splitlines() if x.strip()]


def is_ours(path):
    p = path.replace("\\", "/")
    return p in OURS_ALWAYS or p.startswith(OURS_PREFIX)


def abort(msg):
    print()
    print("!" * 58)
    print(f"  توقّف: {msg}")
    print("  لم يُرفع شيء. حالة المستودع كما تركها الأمر الأخير.")
    print("!" * 58)
    sys.exit(1)


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    check_only = "--check" in sys.argv

    if not args:
        print('الاستعمال: python push_all.py "رسالة الكوميت"')
        sys.exit(1)
    message = args[0]

    # لا يعمل إلا داخل مستودع
    rc, _, _ = run(["git", "rev-parse", "--git-dir"])
    if rc != 0:
        abort("لست داخل مستودع Git")

    # rebase عالق من مرة سابقة؟
    if os.path.isdir(".git/rebase-merge") or os.path.isdir(".git/rebase-apply"):
        abort("هناك rebase غير مكتمل. أنهِه أولاً "
              "(git rebase --continue أو git rebase --abort)")

    # 1) ما الذي سيُرفع
    _, out, _ = run(["git", "status", "--porcelain"])
    changed = [l for l in out.splitlines() if l.strip()]

    print()
    print("=" * 58)
    print(f"  ملفات متغيّرة: {len(changed)}")
    print("=" * 58)
    for l in changed[:12]:
        print("   ", l)
    if len(changed) > 12:
        print(f"    ... و{len(changed) - 12} غيرها")

    if not changed:
        print("\n  لا شيء للرفع — كل شيء محفوظ أصلاً")
        # قد يكون هناك commits محلية غير مرفوعة
        _, ahead, _ = run(["git", "rev-list", "--count", "@{u}..HEAD"])
        if ahead.isdigit() and int(ahead) > 0:
            print(f"  لكن هناك {ahead} كوميت محلي غير مرفوع — سيُرفع")
        else:
            return

    if check_only:
        print("\n  [وضع الفحص] — ما انرفع شي\n")
        return

    # 2) add + commit
    if changed:
        rc, _, err = run(["git", "add", "-A"])
        if rc != 0:
            abort(f"فشل git add: {err}")

        rc, out, err = run(["git", "commit", "-m", message])
        if rc != 0 and "nothing to commit" not in (out + err):
            abort(f"فشل git commit: {err or out}")
        print(f"\n  ✔ كوميت: {message}")

    # 3) pull --rebase
    env_editor = dict(os.environ, GIT_EDITOR="true")
    print("\n  سحب تحديثات الخادم...")
    r = subprocess.run(["git", "pull", "--rebase"],
                       capture_output=True, text=True,
                       encoding="utf-8", env=env_editor)
    pull_out = (r.stdout or "") + (r.stderr or "")

    if r.returncode != 0:
        c = conflicts()
        if not c:
            abort(f"فشل pull لسبب غير التعارض:\n{pull_out.strip()}")

        print(f"\n  تعارض في {len(c)} ملف — يُحلّ تلقائياً:")
        unknown = [p for p in c if not is_ours(p)]
        if unknown:
            print("\n  ⚠️ ملفات غير معروفة بالتعارض — لن أخمّن فيها:")
            for p in unknown:
                print("     ", p)
            abort("ملفات تحتاج قراراً بشرياً. "
                  "حُلّها يدوياً ثم: git rebase --continue")

        for p in c:
            # ⚠️ --theirs أثناء rebase = نسختنا المحلية (درس 65)
            rc, _, err = run(["git", "checkout", "--theirs", "--", p])
            if rc != 0:
                abort(f"فشل حل التعارض في {p}: {err}")
            run(["git", "add", "--", p])
            print(f"     ✔ {p}  (نسختك المحلية)")

        r2 = subprocess.run(["git", "rebase", "--continue"],
                            capture_output=True, text=True,
                            encoding="utf-8", env=env_editor)
        if r2.returncode != 0:
            if conflicts():
                abort("بقيت تعارضات بعد المحاولة — تدخّل يدوي مطلوب")
            abort(f"فشل rebase --continue:\n"
                  f"{((r2.stdout or '') + (r2.stderr or '')).strip()}")
        print("\n  ✔ اكتمل الـrebase")
    else:
        print("  ✔ لا تعارض")

    # 4) push
    print("\n  رفع...")
    rc, out, err = run(["git", "push"])
    if rc != 0:
        print("  المحاولة الأولى فشلت — إعادة سحب ومحاولة ثانية")
        r = subprocess.run(["git", "pull", "--rebase"],
                           capture_output=True, text=True,
                           encoding="utf-8", env=env_editor)
        if conflicts():
            abort("تعارض جديد بالمحاولة الثانية — أعد تشغيل السكربت")
        rc, out, err = run(["git", "push"])
        if rc != 0:
            abort(f"فشل الرفع:\n{err or out}")

    print()
    print("=" * 58)
    print("  ✔ تم الرفع")
    print("=" * 58)
    print("""
  ⚠️ تحقّق الآن أن الديتابيس نسختك (درس 65):
      python export_to_translate.py
    """)


if __name__ == "__main__":
    main()
