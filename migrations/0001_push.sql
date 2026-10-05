-- Goal alerts, batch 2: subscription storage (D1 database "saffara-push", binding DB).
-- No accounts: a subscription is identified by its push endpoint; `auth` is the
-- ownership proof the client resends on every change.
CREATE TABLE IF NOT EXISTS subscriptions (
  endpoint    TEXT PRIMARY KEY,
  p256dh      TEXT NOT NULL,
  auth        TEXT NOT NULL,
  lang        TEXT NOT NULL,        -- 'ar' | 'en'
  created_at  INTEGER NOT NULL,     -- unix seconds
  updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sub_teams (
  endpoint  TEXT NOT NULL,
  team_id   INTEGER NOT NULL,
  PRIMARY KEY (endpoint, team_id)
);
CREATE INDEX IF NOT EXISTS sub_teams_by_team ON sub_teams(team_id);

-- Goal dedupe for the sender (batch 5): first INSERT wins.
CREATE TABLE IF NOT EXISTS sent (
  fixture  INTEGER NOT NULL,
  h        INTEGER NOT NULL,
  a        INTEGER NOT NULL,
  PRIMARY KEY (fixture, h, a)
);
