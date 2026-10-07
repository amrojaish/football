-- Devices that receive operator alerts (e.g. a stuck deploy run). Kept separate from `subscriptions` so the public
-- subscribe path can never read or write the flag; rows are added only via POST /push/admin-device (Bearer ADMIN_TOKEN).
CREATE TABLE IF NOT EXISTS admin_devices (
  endpoint    TEXT PRIMARY KEY,   -- must already exist in subscriptions to be registered
  created_at  INTEGER NOT NULL
);
