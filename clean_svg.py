"""
تنظيف favicon.svg من كتلة C2PA
================================
الملف الجديد يصل بكتلة <metadata>...</metadata> فيها manifest موقّع
(C2PA) حُقنت عند التنزيل. الرسم نفسه سليم — نحذف الكتلة فقط لأن
هذا الملف يُجلب مع كل صفحة بالموقع (لا داعي لنقل ~7.7 ك.ب زائدة
مع كل تحميل).
"""

import re

PATH = r"C:\Users\User\logo_new\favicon.svg"

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

print(f"الحجم قبل: {size_before} بايت")
print(f"الحجم بعد: {size_after} بايت")
print(f"c2pa ما زالت موجودة: {has_c2pa}")
print("--- المحتوى كاملاً ---")
print(content)
