#!/usr/bin/env python3
"""
إزالة الخلفية البيضاء من الشعارات
====================================
بيشيل الأبيض المحيط بالشعار بس، وبيحمي الأبيض اللي جوّاته.

الطريقة: flood fill من الحواف للداخل.
يعني بيبلش من زوايا الصورة وبيزحف، وبيوقف عند أول لون مختلف.
فالأبيض المحاصر جوّا الشعار ما بينلمس.

التثبيت (مرة وحدة):
    pip install Pillow

التشغيل:
    python clean_logo.py logos/4529.png
"""

from PIL import Image
from collections import deque
import sys
import os

# كم درجة نعتبرها "أبيض" — 240 يعني الأبيض والقريب منه
WHITE_THRESHOLD = 235


def is_whiteish(pixel):
    r, g, b = pixel[:3]
    return r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD


def remove_background(path):
    if not os.path.exists(path):
        print(f"ما لقيت الملف: {path}")
        return

    img = Image.open(path).convert("RGBA")
    w, h = img.size
    pixels = img.load()

    print(f"الصورة: {w}x{h}")

    visited = [[False] * h for _ in range(w)]
    queue = deque()

    # نبلش من كل بكسل على الحواف الأربعة
    for x in range(w):
        for y in (0, h - 1):
            if is_whiteish(pixels[x, y]):
                queue.append((x, y))
                visited[x][y] = True

    for y in range(h):
        for x in (0, w - 1):
            if is_whiteish(pixels[x, y]):
                queue.append((x, y))
                visited[x][y] = True

    if not queue:
        print("ما لقيت أبيض على الحواف — يمكن الصورة شفافة أصلاً؟")
        return

    removed = 0

    # الزحف: كل بكسل أبيض بنشيله وبنفحص جيرانه
    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (255, 255, 255, 0)   # شفاف
        removed += 1

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny]:
                if is_whiteish(pixels[nx, ny]):
                    visited[nx][ny] = True
                    queue.append((nx, ny))

    # نحفظ نسخة احتياطية من الأصل
    backup = path.replace(".png", "_original.png")
    if not os.path.exists(backup):
        Image.open(path).save(backup)
        print(f"نسخة احتياطية: {os.path.basename(backup)}")

    img.save(path, "PNG")

    total = w * h
    print(f"""
{'=' * 45}
  تم
{'=' * 45}
  بكسلات شُيّلت: {removed:,} من {total:,}  ({removed/total*100:.1f}%)

  افتح الصورة وتأكد إنو الشعار سليم.
  إذا أكل جزء منه، رجّع النسخة الاحتياطية
  وقلّل WHITE_THRESHOLD بأول الملف.
    """)


def main():
    if len(sys.argv) < 2:
        print("""
  الاستخدام:
      python clean_logo.py logos/4529.png
        """)
        return

    remove_background(sys.argv[1])


if __name__ == "__main__":
    main()
