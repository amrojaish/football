"""
تنظيف SVG من كتلة C2PA
========================
ملفات الشعار الواصلة من محادثة تحمل أحياناً كتلة <metadata>...</metadata>
فيها manifest موقّع (C2PA) حُقنت عند التنزيل. الرسم نفسه سليم — نحذف
الكتلة فقط لأن الملف يُجلب مع كل صفحة بالموقع (لا داعي لنقل كيلوبايتات
زائدة مع كل تحميل). راجع مصيدة C2PA بالـREADME.

الاستعمال:
    python clean_svg.py [مسار الملف]
    (بلا وسيط: يستعمل المسار الافتراضي أدناه)
"""

import re
import sys

DEFAULT_PATH = r"C:\Users\User\logo_new\favicon.svg"
PATH = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

size_before = len(content.encode("utf-8"))

# احذف كتلة <metadata>...</metadata> بالكامل (غير جشعة، تدعم أسطراً متعددة)
content = re.sub(r"<metadata\b.*?</metadata>", "", content, flags=re.DOTALL)

# احذف سمة xmlns:c2pa="..."
content = re.sub(r'\s*xmlns:c2pa="[^"]*"', "", content)

with open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(content)

size_after = len(content.encode("utf-8"))
has_c2pa = "c2pa" in content.lower()

print(f"الملف: {PATH}")
print(f"الحجم قبل: {size_before} بايت")
print(f"الحجم بعد: {size_after} بايت")
print(f"c2pa ما زالت موجودة: {has_c2pa}")
print("--- المحتوى كاملاً ---")
print(content)
