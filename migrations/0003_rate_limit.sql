-- Public launch (batch 6): per-IP hourly counter for POST /push/subscribe.
-- k = first 16 hex chars of SHA-256(ip + ":saffara") + ":" + hour bucket (the raw IP is never stored).
-- Rows are pruned once their hour has passed.
CREATE TABLE IF NOT EXISTS rate_limit (
  k    TEXT PRIMARY KEY,
  n    INTEGER NOT NULL,
  exp  INTEGER NOT NULL      -- unix seconds, end of the bucket
);
