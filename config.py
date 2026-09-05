#!/usr/bin/env python3
"""
الإعدادات المشتركة
===================
هاد الملف بيقرأ المفتاح من ملف .env
كل السكربتات التانية بتستورد منه، فبتكتب المفتاح مرة وحدة بس.

ما بتشغّل هاد الملف لحاله — هو بس بيخدم الباقيين.
"""

import os
from pathlib import Path

# مسار المجلد اللي فيه هاد الملف
BASE_DIR = Path(__file__).parent

# ثوابت المشروع
API_BASE = "https://v3.football.api-sports.io"
SEASON = 2025
TEAMS_FILE = BASE_DIR / "teams_arabic.csv"
DB_FILE = BASE_DIR / "football.db"

LEAGUES = {
    "JOR": {"id": 387, "name_ar": "الدوري الأردني"},
    "IRQ": {"id": 542, "name_ar": "الدوري العراقي"},
    "SAU": {"id": 307, "name_ar": "الدوري السعودي"},
    "EGY": {"id": 233, "name_ar": "الدوري المصري"},
    "UAE": {"id": 301, "name_ar": "الدوري الإماراتي"},
    "QAT": {"id": 305, "name_ar": "دوري نجوم قطر"},
    "MAR": {"id": 200, "name_ar": "الدوري المغربي"},
}


def load_env():
    """بيقرأ ملف .env ويحوله لقاموس"""
    env_path = BASE_DIR / ".env"

    if not env_path.exists():
        return {}

    values = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # نتجاهل السطور الفاضية والتعليقات
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values


_env = load_env()
API_KEY = _env.get("API_FOOTBALL_KEY", "")


def check_key():
    """بيتأكد إنو المفتاح موجود، وبيطبع رسالة واضحة إذا لأ"""
    if not API_KEY or API_KEY == "ضع_مفتاحك_هنا":
        print("=" * 55)
        print("  ما في مفتاح")
        print("=" * 55)
        print("""
  اعمل ملف اسمه .env بنفس المجلد، وحط فيه سطر واحد:

      API_FOOTBALL_KEY=مفتاحك_هون

  بدون علامات تنصيص، وبدون مسافات حوالين =
        """)
        return False
    return True


def headers():
    """الهيدرز الجاهزة لطلبات الـAPI"""
    return {"x-apisports-key": API_KEY}
