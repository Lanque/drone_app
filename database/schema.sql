CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255),
    google_subject VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_google_subject
    ON users(google_subject)
    WHERE google_subject IS NOT NULL;

CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DECIMAL(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    description TEXT,
    no_fly_zone_status BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_locations_owner_id
    ON locations(owner_id);

CREATE TABLE IF NOT EXISTS location_photos (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL
        REFERENCES locations(id)
        ON DELETE CASCADE,
    stored_name VARCHAR(255) NOT NULL UNIQUE,
    original_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    caption VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_location_photos_location_id
    ON location_photos(location_id);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE users, locations, location_photos
    TO drone_app;

GRANT USAGE, SELECT
    ON SEQUENCE users_id_seq, locations_id_seq, location_photos_id_seq
    TO drone_app;
