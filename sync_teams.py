import sqlite3, csv
from config import DB_FILE, TEAMS_FILE

conn = sqlite3.connect(DB_FILE)
rows = []

with open(TEAMS_FILE, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if not (r.get("team_id") or "").strip():
            continue
        rows.append((
            int(r["team_id"]),
            (r.get("league_code") or "").strip(),
            (r.get("name_en") or "").strip(),
            (r.get("name_ar") or "").strip(),
            (r.get("short_name_ar") or "").strip(),
            (r.get("city") or "").strip(),
            (r.get("logo") or "").strip(),
        ))

conn.executemany("""
    INSERT OR REPLACE INTO teams
    (team_id, league_code, name_en, name_ar, short_name_ar, city, logo)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", rows)
conn.commit()

print(f"تم نقل {len(rows)} نادي من CSV للديتابيس")
conn.close()