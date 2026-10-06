-- Goal detection log (kept 30 days, pruned by the worker on the :05/:35 dispatch cycle).
-- One row per detected goal / goal_cancelled event, written whether or not GOAL_PUSH is on, so detection can be
-- compared with real match events (football.db) without Workers Logs access.
CREATE TABLE IF NOT EXISTS goal_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       INTEGER NOT NULL,     -- unix seconds of detection
  kind     TEXT NOT NULL,        -- 'goal' | 'goal_cancelled'
  fixture  INTEGER NOT NULL,
  th       INTEGER,
  ta       INTEGER,
  h        INTEGER NOT NULL,     -- score after the event (home)
  a        INTEGER NOT NULL,
  prev_h   INTEGER NOT NULL,     -- score at the previous poll
  prev_a   INTEGER NOT NULL,
  minute   INTEGER,
  league   INTEGER
);
CREATE INDEX IF NOT EXISTS goal_log_by_fixture ON goal_log(fixture, ts);
CREATE INDEX IF NOT EXISTS goal_log_by_ts ON goal_log(ts);
