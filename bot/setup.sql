-- Ejecutar una sola vez en Supabase → SQL Editor

CREATE TABLE IF NOT EXISTS negocios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id        TEXT NOT NULL,
    name            TEXT NOT NULL,
    phone           TEXT DEFAULT '',
    address         TEXT DEFAULT '',
    formatted_address TEXT DEFAULT '',
    city            TEXT DEFAULT '',
    country         TEXT DEFAULT '',
    latitude        REAL,
    longitude       REAL,
    zone            TEXT NOT NULL,
    business_type   TEXT NOT NULL,
    website         TEXT DEFAULT '',
    rating          REAL,
    reviews_count   INTEGER DEFAULT 0,
    sent_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_negocios_place_id  ON negocios(place_id);
CREATE INDEX        IF NOT EXISTS idx_negocios_zone_type ON negocios(zone, business_type);

CREATE TABLE IF NOT EXISTS usuarios_autorizados (
    telegram_user_id BIGINT PRIMARY KEY,
    nombre           TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE usuarios_autorizados IS 'Whitelist de Telegram user IDs con acceso al bot.';
