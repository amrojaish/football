#!/usr/bin/env python3
"""
فهارس أسماء اللاعبين (R4، 15 نوفمبر 2026) — CREATE INDEX IF NOT EXISTS، آمنة للتكرار
=====================================================================================
apply_players_ar.py وapply_player_merges.py يبحثان بـ`player_en = ?` (و`assist_en = ?`) آلاف المرات على جداول بلا فهرس
لهذا العمود (مسح كامل لكل استعلام): 172 ث و78 ث بالـCI. بالفهرس: ~6 ث و<1 ث، ونفس النتيجة حرفياً (بصمة player_ar
والأسماء متطابقة قبل/بعد). الفهارس تبقى بالقاعدة (الحالة الدائمة) — البيانات نفسها لا تتغيّر، والصفحات المولّدة لا تتأثر.
"""
import sqlite3

NAME_INDEXES = (
    ("goals", "player_en"),
    ("lineup_players", "player_en"),
    ("player_stats", "player_en"),
    ("events", "player_en"),
    ("events", "assist_en"),
)


def ensure_name_indexes(conn):
    """ينشئ الفهارس الناقصة فقط (جدول أو عمود غائب = يُتخطّى). يرجّع عدد الفهارس المطلوبة الموجودة الآن."""
    n = 0
    for table, col in NAME_INDEXES:
        try:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if col not in cols:
            continue
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col})")
        n += 1
    conn.commit()
    return n
