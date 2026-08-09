#!/usr/bin/env python3
"""
معالجة الشعارات دفعة واحدة
============================
بيمر على كل الصور بمجلد logos، بيشيل الخلفية البيضاء،
وبيحدّث عمود logo_local بملف teams_arabic.csv تلقائياً.

التشغيل:
    python clean_logos_all.py           <- معالجة + تحديث CSV
    python clean_logos_all.py --dry     <- عرض بس بدون تعديل
"""

from PIL import Image
from collections import deque
from pathlib import Path
import csv
import sys

from config import TEAMS_FILE, BASE_DIR

LOGOS_DIR = BASE_DIR / "logos"
WHITE_THRESHOLD = 235
DRY_RUN = "--dry" in sys.argv


def is_whiteish(px):
    r, g, b = px[:3]
    return r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD


def already_clean(img):
    """
    بيفحص إذا الصورة معالجة أصلاً — يعني حوافها شفافة.
    هيك ما نعالج نفس الصورة مرتين.
    """
    w, h = img.size
    px = img.load()
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    return all(px[x, y][3] == 0 for x, y in corners)


def remove_background(path):
    """بيرجع عدد البكسلات اللي انشالت، أو None إذا ما احتاجت معالجة"""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = img.load()

    if already_clean(img):
        return None

    visited = [[False] * h for _ in range(w)]
    queue = deque()

    # نبلش من الحواف الأربعة
    for x in range(w):
        for y in (0, h - 1):
            if is_whiteish(px[x, y]):
                queue.append((x, y))
                visited[x][y] = True

    for y in range(h):
        for x in (0, w - 1):
            if is_whiteish(px[x, y]) and not visited[x][y]:
                queue.append((x, y))
                visited[x][y] = True

    if not queue:
        return 0

    removed = 0
    while queue:
        x, y = queue.popleft()
        px[x, y] = (255, 255, 255, 0)
        removed += 1

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny]:
                if is_whiteish(px[nx, ny]):
                    visited[nx][ny] = True
                    queue.append((nx, ny))

    # نسخة احتياطية قبل الحفظ
    backup = path.parent / f"{path.stem}_original.png"
    if not backup.exists():
        Image.open(path).save(backup)

    img.save(path, "PNG")
    return removed


def update_csv(team_ids):
    """بيحط logos/<id>.png بعمود logo_local للأندية اللي عندها شعار محلي"""
    if not TEAMS_FILE.exists():
        print("  ما لقيت teams_arabic.csv")
        return 0

    with open(TEAMS_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    # نتأكد إنو العمودين موجودين
    for col in ("logo_local", "logo_note"):
        if col not in fields:
            fields.append(col)

    changed = 0
    for row in rows:
        tid = (row.get("team_id") or "").strip()
        if tid in team_ids:
            new_path = f"logos/{tid}.png"
            if (row.get("logo_local") or "").strip() != new_path:
                row["logo_local"] = new_path
                changed += 1
        # نضمن إنو كل الحقول موجودة
        row.setdefault("logo_local", "")
        row.setdefault("logo_note", "")

    if not DRY_RUN:
        with open(TEAMS_FILE, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    return changed


def main():
    if not LOGOS_DIR.exists():
        print("ما لقيت مجلد logos")
        return

    # نتجاهل النسخ الاحتياطية
    files = sorted(p for p in LOGOS_DIR.glob("*.png")
                   if not p.stem.endswith("_original"))

    if not files:
        print("ما في صور بمجلد logos")
        return

    print(f"\n{'=' * 55}")
    print(f"  لقيت {len(files)} شعار" + ("   [وضع العرض فقط]" if DRY_RUN else ""))
    print(f"{'=' * 55}\n")

    team_ids = set()
    processed = skipped = failed = 0

    for path in files:
        tid = path.stem

        if not tid.isdigit():
            print(f"  تخطي {path.name} — الاسم مش رقم team_id")
            continue

        team_ids.add(tid)

        try:
            if DRY_RUN:
                print(f"  {tid}: جاهز للمعالجة")
                continue

            removed = remove_background(path)

            if removed is None:
                print(f"  {tid}: معالج أصلاً — تخطي")
                skipped += 1
            elif removed == 0:
                print(f"  {tid}: ما في خلفية بيضا على الحواف")
                skipped += 1
            else:
                print(f"  {tid}: شُيّل {removed:,} بكسل")
                processed += 1

        except Exception as e:
            print(f"  {tid}: فشل — {e}")
            failed += 1

    changed = update_csv(team_ids)

    print(f"\n{'=' * 55}")
    print(f"  معالج: {processed}  |  متخطى: {skipped}  |  فاشل: {failed}")
    print(f"  خانات CSV محدّثة: {changed}")
    print(f"{'=' * 55}")

    if DRY_RUN:
        print("\n  هاد عرض فقط — شغّل بدون --dry للتنفيذ\n")
    else:
        print("""
  الخطوة الجاية:
      python make_site2.py

  ولو شعار انأكل جزء منه، ارجع للنسخة الاحتياطية
  <id>_original.png وقلّل WHITE_THRESHOLD.
        """)


if __name__ == "__main__":
    main()
