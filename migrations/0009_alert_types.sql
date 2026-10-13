-- Alert types (13 Oct 2026, batch 3E): every subscription entity (club / single match / league) carries a bitmask of the alert types it wants.
--   1 kickoff · 2 goal · 4 half-time · 8 second-half start · 16 full-time · 32 red card · 64 reminder 30 min before kickoff  (127 = all, 115 = default for new)
-- NO lineups type. DEFAULTS: a NEW subscription (the client sends the mask) = kickoff + goal + full-time + red card + reminder = 115; half-time (4) and
-- second-half start (8) stay off until the user ticks them. EXISTING rows (clubs/matches subscribed before this migration only ever asked for goals) get
-- DEFAULT 2 = goals only, so nobody starts receiving new alert types they never chose. Old clients that resend without masks keep their stored mask.
-- Depends on 0008_sub_matches.sql. Apply BEFORE deploying the worker that reads these columns.
ALTER TABLE sub_teams ADD COLUMN types INTEGER NOT NULL DEFAULT 2;
ALTER TABLE sub_matches ADD COLUMN types INTEGER NOT NULL DEFAULT 2;

-- league-level subscription: all matches of a league (provider league id, e.g. 233 Egyptian Premier League)
CREATE TABLE IF NOT EXISTS sub_leagues (
  endpoint  TEXT NOT NULL,
  league    INTEGER NOT NULL,
  types     INTEGER NOT NULL DEFAULT 115,
  PRIMARY KEY (endpoint, league)
);
CREATE INDEX IF NOT EXISTS sub_leagues_by_league ON sub_leagues(league);

-- dedupe for the non-goal alerts (goals keep using `sent`): first INSERT wins. kind = ko|ht|sh|ft|red|rem; k = discriminator (red card key)
CREATE TABLE IF NOT EXISTS ev_sent (
  fixture  INTEGER NOT NULL,
  kind     TEXT NOT NULL,
  k        TEXT NOT NULL DEFAULT '',
  ts       INTEGER NOT NULL,
  PRIMARY KEY (fixture, kind, k)
);
