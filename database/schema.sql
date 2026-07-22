CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DECIMAL(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    description TEXT,
    no_fly_zone_status BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
