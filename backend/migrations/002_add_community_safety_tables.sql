CREATE TABLE IF NOT EXISTS place_safety_ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    place_name VARCHAR(255) NOT NULL,
    address VARCHAR(500) NOT NULL,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    rating_value SMALLINT NOT NULL CHECK (rating_value >= 0 AND rating_value <= 255),
    comment TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_place_safety_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_place_safety_location ON place_safety_ratings(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_place_safety_user ON place_safety_ratings(user_id);

CREATE TABLE IF NOT EXISTS road_segment_ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    segment_key VARCHAR(120) NOT NULL,
    start_latitude DECIMAL(10, 7) NOT NULL,
    start_longitude DECIMAL(10, 7) NOT NULL,
    end_latitude DECIMAL(10, 7) NOT NULL,
    end_longitude DECIMAL(10, 7) NOT NULL,
    rating_value SMALLINT NOT NULL CHECK (rating_value >= 0 AND rating_value <= 255),
    comment TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_road_segment_ratings_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_road_segment_key ON road_segment_ratings(segment_key);
CREATE INDEX IF NOT EXISTS idx_road_segment_user ON road_segment_ratings(user_id);

CREATE TABLE IF NOT EXISTS road_segment_safety_scores (
    segment_key VARCHAR(120) NOT NULL PRIMARY KEY,
    start_latitude DECIMAL(10, 7) NOT NULL,
    start_longitude DECIMAL(10, 7) NOT NULL,
    end_latitude DECIMAL(10, 7) NOT NULL,
    end_longitude DECIMAL(10, 7) NOT NULL,
    normalized_score DECIMAL(5, 4) NOT NULL,
    rating_count INTEGER NOT NULL DEFAULT 0 CHECK (rating_count >= 0),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create trigger function for updating updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $func$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP
    RETURN NEW
END
$func$ language 'plpgsql';

-- Create trigger for road_segment_safety_scores
CREATE TRIGGER update_road_segment_safety_scores_updated_at
    BEFORE UPDATE ON road_segment_safety_scores
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS favorite_places (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    place_name VARCHAR(255) NOT NULL,
    address VARCHAR(500) NOT NULL,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_favorite_places_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    UNIQUE (user_id, latitude, longitude)
);

CREATE INDEX IF NOT EXISTS idx_favorite_places_user ON favorite_places(user_id);

CREATE TABLE IF NOT EXISTS safety_comments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL CHECK (user_id >= 0),
    target_type VARCHAR(20) NOT NULL,
    target_key VARCHAR(191) NOT NULL,
    place_name VARCHAR(255) NULL,
    address VARCHAR(500) NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_safety_comments_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_safety_comments_target ON safety_comments(target_type, target_key);
CREATE INDEX IF NOT EXISTS idx_safety_comments_user ON safety_comments(user_id);
