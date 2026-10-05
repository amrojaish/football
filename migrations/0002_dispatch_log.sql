-- Cron-triggered deploy-site dispatch attempts (kept to the last 500 rows by the worker).
-- result: dispatched | skipped_queued | skipped_in_progress | auth_failed | check_failed | failed
CREATE TABLE IF NOT EXISTS dispatch_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           INTEGER NOT NULL,   -- unix seconds of the scheduled minute
  result       TEXT NOT NULL,
  http_status  INTEGER
);
