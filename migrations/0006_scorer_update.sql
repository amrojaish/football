-- Goal scorer update (two-step goal alert): one row per (fixture, score) once the scorer-name update push has been claimed.
-- INSERT OR IGNORE then send => the update goes out at most once per goal even if the queue redelivers a message.
-- Rows for a score are removed when a goal is cancelled (same rule as `sent`) and pruned after 2 days by the :05/:35 cycle.
CREATE TABLE IF NOT EXISTS scorer_update (
  fixture  INTEGER NOT NULL,
  h        INTEGER NOT NULL,
  a        INTEGER NOT NULL,
  ts       INTEGER NOT NULL,   -- unix seconds of the claim
  PRIMARY KEY (fixture, h, a)
);
