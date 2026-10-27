#!/usr/bin/env python3
"""
Test helper (27 Oct 2026): build real match pages for FIXED fixtures into a temporary site, from an in-memory copy of football.db.
Used by test_live_lineup_page.py and test_live_events_page.py so they no longer depend on today's real fixtures.

    kit = Kit()                       # in-memory DB copy + temp site with assets/ (football.db only read)
    kit.reshape(fixture)              # rewrite rows of the fixed fixtures (see live_pages_fixture.json)
    kit.render(mid, now=epoch_secs)   # same steps as make_matches.main() for one match, both languages
    kit.root                          # serve this folder
The per-match steps mirror make_matches.main() exactly (no product code changes); `now` replaces the wall clock in live_lineup_due.
"""
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import make_matches as mm  # noqa: E402
from i18n import LANGS, T  # noqa: E402
from lineup_view import build_lineups, live_lineup_slot, pid_map_html  # noqa: E402
from live_view import ev_live_json  # noqa: E402

FIXTURE = json.loads((Path(__file__).resolve().parent / "live_pages_fixture.json").read_text(encoding="utf-8"))
MATCH_TABLES = ("lineups", "lineup_players", "player_stats", "events", "goals", "match_stats")


def epoch(date_str):
    return int(datetime.strptime(date_str[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


class Kit:
    def __init__(self):
        src = sqlite3.connect(f"file:{ROOT / 'football.db'}?mode=ro", uri=True)
        self.con = sqlite3.connect(":memory:")
        src.backup(self.con)
        src.close()
        self.con.row_factory = sqlite3.Row
        self.root = Path(tempfile.mkdtemp(prefix="match_kit_"))
        shutil.copytree(ROOT / "assets", self.root / "assets")
        (self.root / "matches").mkdir()
        (self.root / "en" / "matches").mkdir(parents=True)

    def reshape(self, fx=FIXTURE):
        c = self.con
        up = fx["upcoming"]
        for t in MATCH_TABLES:
            c.execute(f"DELETE FROM {t} WHERE match_id = ?", (up["match_id"],))
        c.execute("UPDATE matches SET home_goals = NULL, away_goals = NULL, status = 'NS', date = ? WHERE match_id = ?", (up["date"], up["match_id"]))
        go = fx["goals_only"]
        c.execute("DELETE FROM events WHERE match_id = ?", (go["match_id"],))
        c.execute("UPDATE matches SET date = ? WHERE match_id = ?", (go["date"], go["match_id"]))
        sv = fx["saved_events"]
        c.execute("UPDATE matches SET date = ? WHERE match_id = ?", (sv["date"], sv["match_id"]))
        c.commit()

    def row(self, mid):
        return self.con.execute("SELECT match_id, league_code, season, date, home_id, away_id, home_goals, away_goals, status "
                                "FROM matches WHERE match_id = ?", (mid,)).fetchone()

    def render(self, mid, now):
        """make_matches.main() for one match (both languages), live windows evaluated at `now` (epoch seconds)"""
        conn = self.con
        mm.LATEST_SEASON = conn.execute("SELECT MAX(season) FROM matches").fetchone()[0]
        mm._TABLES.clear()
        mm.build_form_index(conn)
        teams = mm.load_teams()
        m = self.row(mid)
        h, a = teams.get(m["home_id"]), teams.get(m["away_id"])
        for lang in LANGS:
            items = mm.build_items(conn, mid, lang)
            stats_html = mm.build_stats(conn, mid, m["home_id"], m["away_id"], lang)
            h2h_html = mm.build_h2h(conn, m, h, a, lang, mm.tname, mm.logo_url, teams)
            lineup_html = build_lineups(conn, m, h, a, lang, T, mm.tname, mm.logo_url)
            live_lu = not lineup_html and m["league_code"] not in ("IRQ", "JOR") and mm.live_lineup_due(m, now)
            if live_lu:
                lineup_html = live_lineup_slot(conn, m, h, a, lang, T, mm.tname, mm.logo_url)
                live_lu = bool(lineup_html)
            table_html = mm.build_table_panel(conn, m, teams, lang)
            form_html = mm.build_form_card(m, h, a, teams, lang)
            if m["home_goals"] is None:
                form_html += mm.build_positions(conn, m, teams, lang)
            live_ev = mm.live_lineup_due(m, now) and not conn.execute(
                "SELECT 1 FROM events WHERE match_id = ? AND type != 'none' LIMIT 1", (mid,)).fetchone()
            live_data = (ev_live_json(m) if live_ev else "") + (pid_map_html(conn, m) if lang == "ar" and (live_lu or live_ev) else "")
            html = mm.build_page(m, h, a, items, None, lang, stats_html, lineup_html, h2h_html, table_html, form_html, live_lu, live_ev, live_data)
            out = self.root / ("matches" if lang == "ar" else "en/matches") / f"{mid}.html"
            out.write_text(html, encoding="utf-8")
        return m
