-- Per-match goal alerts (13 Oct 2026): a subscription can follow single matches in addition to clubs.
-- Recipients of a goal = subscribers of either team (sub_teams) UNION subscribers of that fixture (sub_matches).
-- Rows are replaced as a set on every /push/subscribe that carries `matches` (max 20), deleted with the subscription,
-- and pruned after 21 days by the :05/:35 cycle. Apply BEFORE deploying the worker that reads this table.
CREATE TABLE IF NOT EXISTS sub_matches (
  endpoint    TEXT NOT NULL,
  fixture     INTEGER NOT NULL,
  created_at  INTEGER NOT NULL,   -- unix seconds
  PRIMARY KEY (endpoint, fixture)
);
CREATE INDEX IF NOT EXISTS sub_matches_by_fixture ON sub_matches(fixture);
