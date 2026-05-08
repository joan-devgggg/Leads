-- Ejecutar una sola vez en Supabase → SQL Editor

CREATE TABLE IF NOT EXISTS businesses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id        TEXT NOT NULL,
    name            TEXT NOT NULL,
    phone           TEXT DEFAULT '',
    address         TEXT DEFAULT '',
    zone            TEXT NOT NULL,
    business_type   TEXT NOT NULL,
    website         TEXT DEFAULT '',
    rating          REAL,
    reviews_count   INTEGER DEFAULT 0,
    sent_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_place_id  ON businesses(place_id);
CREATE INDEX        IF NOT EXISTS idx_zone_type ON businesses(zone, business_type);
