"""
تحقّق من ملفات الشعار الجديدة قبل نقلها
==========================================
يفتح كل PNG بمجلد logo_new ويطبع: الاسم، الصيغة، وضع الألوان،
المقاس، ولون البكسل (2,2) — للتأكد أن كل ملف يطابق اسمه قبل أي
نقل فعلي. لا يعدّل أو ينقل أي شيء.
"""

from pathlib import Path
from PIL import Image

DIR = Path(r"C:\Users\User\logo_new")

EXPECTED_SIZES = {
    "icon-32.png": (32, 32),
    "icon-180.png": (180, 180),
    "icon-192.png": (192, 192),
    "icon-512.png": (512, 512),
    "maskable-192.png": (192, 192),
    "maskable-512.png": (512, 512),
}

all_ok = True

for name, expected in EXPECTED_SIZES.items():
    path = DIR / name
    if not path.exists():
        print(f"{name}: ⛔ الملف غير موجود")
        all_ok = False
        continue

    with Image.open(path) as img:
        fmt = img.format
        mode = img.mode
        size = img.size
        pixel = img.convert("RGBA").getpixel((2, 2))

    size_ok = size == expected
    if not size_ok:
        all_ok = False

    print(
        f"{name:20s} صيغة={fmt:5s} وضع={mode:5s} مقاس={size!s:12s} "
        f"(متوقَّع {expected}) {'✅' if size_ok else '⛔ لا يطابق'}  "
        f"بكسل(2,2)={pixel}"
    )

print()
print("النتيجة الإجمالية:", "✅ كل المقاسات مطابقة" if all_ok else "⛔ يوجد خلل — لا تنقل شيئاً")
