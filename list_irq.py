import sqlite3
import sys
from config import DB_FILE

sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

for r in conn.execute(
    "SELECT season, COUNT(*) n, MIN(date) first, MAX(date) last "
    "FROM matches WHERE league_code='IRQ' "
    "AND (home_id=11069 OR away_id=11069) GROUP BY season"
):
    print("موسم", r["season"], "|", r["n"], "مباراة |",
          r["first"], "→", r["last"])

conn.close()