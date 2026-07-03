-- filming-service/sql/schema.sql
-- Schéma MySQL pour la plateforme ciné-tourisme (nouveau service séparé de pelify.app).
-- MySQL 8.0+ recommandé (POINT SRID 4326 + index spatial nécessitent 8.0+).
-- Pensé pour migrer plus tard vers PostgreSQL/PostGIS sans changement de forme des données.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS movies (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    wikidata_id     VARCHAR(20) NULL,
    tmdb_id         BIGINT UNSIGNED NULL,
    title           VARCHAR(500) NOT NULL,
    original_title  VARCHAR(500) NULL,
    type            ENUM('film', 'series') NOT NULL,
    release_date    DATE NULL,
    release_year    SMALLINT UNSIGNED NULL,
    country         VARCHAR(150) NULL,
    poster_url      VARCHAR(500) NULL,
    description     TEXT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_movies_wikidata_id (wikidata_id),
    KEY idx_movies_tmdb_id (tmdb_id),
    KEY idx_movies_type (type),
    KEY idx_movies_release_year (release_year),
    KEY idx_movies_country (country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS filming_locations (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    movie_id            BIGINT UNSIGNED NOT NULL,
    name                VARCHAR(500) NOT NULL,
    description         TEXT NULL,
    scene_description   TEXT NULL,
    country             VARCHAR(150) NULL,
    region              VARCHAR(150) NULL,
    city                VARCHAR(150) NULL,
    address             VARCHAR(500) NULL,
    latitude            DECIMAL(10, 7) NOT NULL,
    longitude           DECIMAL(10, 7) NOT NULL,
    geom                POINT SRID 4326 NULL, -- rempli en plus des colonnes lat/lng, prêt pour PostGIS plus tard
    source              VARCHAR(100) NULL,     -- ex: 'wikidata', 'manual', 'tmdb'
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_filming_locations_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
    KEY idx_filming_locations_movie_id (movie_id),
    KEY idx_filming_locations_country (country),
    KEY idx_filming_locations_region (region),
    KEY idx_filming_locations_city (city),
    KEY idx_filming_locations_lat (latitude),
    KEY idx_filming_locations_lng (longitude),
    SPATIAL KEY idx_filming_locations_geom (geom)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS nearby_places (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    external_id     VARCHAR(150) NULL,     -- id source (ex: OSM node id)
    name            VARCHAR(500) NOT NULL,
    category        ENUM('accommodation', 'restaurant', 'transport', 'tourism_office', 'activity', 'safety') NOT NULL,
    subcategory     VARCHAR(100) NULL,     -- ex: 'police', 'hospital', 'pharmacy' sous 'safety'
    country         VARCHAR(150) NULL,
    region          VARCHAR(150) NULL,
    city            VARCHAR(150) NULL,
    address         VARCHAR(500) NULL,
    latitude        DECIMAL(10, 7) NOT NULL,
    longitude       DECIMAL(10, 7) NOT NULL,
    website         VARCHAR(500) NULL,
    phone           VARCHAR(50) NULL,
    opening_hours   VARCHAR(255) NULL,
    source          VARCHAR(100) NULL,     -- ex: 'overpass', 'nominatim'
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_nearby_places_external (source, external_id),
    KEY idx_nearby_places_category (category),
    KEY idx_nearby_places_country (country),
    KEY idx_nearby_places_region (region),
    KEY idx_nearby_places_city (city),
    KEY idx_nearby_places_lat (latitude),
    KEY idx_nearby_places_lng (longitude)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS location_nearby_cache (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    filming_location_id     BIGINT UNSIGNED NOT NULL,
    nearby_place_id         BIGINT UNSIGNED NOT NULL,
    category                ENUM('accommodation', 'restaurant', 'transport', 'tourism_office', 'activity', 'safety') NOT NULL,
    distance_meters         INT UNSIGNED NOT NULL,
    travel_time_minutes     SMALLINT UNSIGNED NULL,
    rank_position           TINYINT UNSIGNED NOT NULL, -- 1 = plus proche de sa catégorie
    is_closest              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_location_nearby_cache_location FOREIGN KEY (filming_location_id) REFERENCES filming_locations(id) ON DELETE CASCADE,
    CONSTRAINT fk_location_nearby_cache_place FOREIGN KEY (nearby_place_id) REFERENCES nearby_places(id) ON DELETE CASCADE,
    UNIQUE KEY uq_location_nearby (filming_location_id, nearby_place_id),
    KEY idx_location_nearby_cache_location (filming_location_id),
    KEY idx_location_nearby_cache_category (category),
    KEY idx_location_nearby_cache_closest (is_closest)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS api_jobs (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    filming_location_id     BIGINT UNSIGNED NOT NULL,
    status                  ENUM('pending', 'running', 'done', 'failed') NOT NULL DEFAULT 'pending',
    attempt_count           TINYINT UNSIGNED NOT NULL DEFAULT 0,
    last_error              TEXT NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_api_jobs_location FOREIGN KEY (filming_location_id) REFERENCES filming_locations(id) ON DELETE CASCADE,
    UNIQUE KEY uq_api_jobs_location (filming_location_id), -- garantit 1 seul job actif par lieu (cf. règle anti-surcharge)
    KEY idx_api_jobs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analytics_events (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type              ENUM('movie_view', 'location_click', 'nearby_place_click', 'filter_country', 'filter_date', 'filter_type') NOT NULL,
    movie_id                BIGINT UNSIGNED NULL,
    filming_location_id     BIGINT UNSIGNED NULL,
    country                 VARCHAR(150) NULL,
    region                  VARCHAR(150) NULL,
    city                    VARCHAR(150) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_analytics_events_type (event_type),
    KEY idx_analytics_events_movie (movie_id),
    KEY idx_analytics_events_location (filming_location_id),
    KEY idx_analytics_events_country (country),
    KEY idx_analytics_events_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
