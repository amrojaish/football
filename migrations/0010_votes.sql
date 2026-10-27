-- Match voting «مين رح يفوز؟» / "Who will win?" (27 Oct 2026): one vote per device per fixture, before kickoff only.
--   device = random UUID the browser keeps in localStorage (no personal data, no IP stored here).
--   choice: h = home win · d = draw · a = away win. ts = unix seconds of the vote.
-- A second vote from the same device is refused by the PRIMARY KEY (worker answers 409, row unchanged).
-- Rows older than 30 days are pruned on the worker's dispatch cycle. Apply BEFORE deploying the worker that reads it.
CREATE TABLE IF NOT EXISTS votes (
  fixture_id  INTEGER NOT NULL,
  device      TEXT    NOT NULL,
  choice      TEXT    NOT NULL CHECK (choice IN ('h', 'd', 'a')),
  ts          INTEGER NOT NULL,
  PRIMARY KEY (fixture_id, device)
);
CREATE INDEX IF NOT EXISTS idx_votes_ts ON votes (ts);
