-- Scorer update correction (13 Oct 2026): remember what the scorer-name update carried so a LATER change of the provider's
-- event minute / scorer (e.g. 10 -> 4) can send exactly ONE correction (same tag, renotify:false). Additive only:
-- old rows keep NULL minute/name (no comparison possible => never corrected). Apply BEFORE deploying the worker that reads these columns.
ALTER TABLE scorer_update ADD COLUMN minute TEXT;
ALTER TABLE scorer_update ADD COLUMN name TEXT;
ALTER TABLE scorer_update ADD COLUMN corrected INTEGER NOT NULL DEFAULT 0;
