-- Instructor reference. Students author all five CREATE TABLE statements.
CREATE TABLE assets
(
    asset_id        TEXT PRIMARY KEY NOT NULL,
    collection      TEXT             NOT NULL,
    item_id         TEXT             NOT NULL,
    asset_key       TEXT             NOT NULL CHECK (asset_key IN ('red', 'nir')),
    source_url      TEXT             NOT NULL,
    metadata_json   TEXT             NOT NULL CHECK (json_valid(metadata_json)),
    metadata_sha256 TEXT             NOT NULL,
    created_at      TEXT             NOT NULL,
    UNIQUE (collection, item_id, asset_key, metadata_sha256),
    FOREIGN KEY (collection, item_id) REFERENCES scenes (collection, item_id)
);
CREATE TABLE subset_requests
(
    subset_id          TEXT PRIMARY KEY NOT NULL,
    asset_id           TEXT             NOT NULL REFERENCES assets (asset_id),
    aoi_key            TEXT             NOT NULL,
    aoi_json           TEXT             NOT NULL CHECK (json_valid(aoi_json)),
    recipe_version     TEXT             NOT NULL,
    status             TEXT             NOT NULL CHECK (status IN ('pending', 'ready', 'failed')),
    latest_artifact_id TEXT,
    updated_at         TEXT             NOT NULL,
    CHECK (status <> 'ready' OR latest_artifact_id IS NOT NULL),
    UNIQUE (asset_id, aoi_key, recipe_version),
    FOREIGN KEY (latest_artifact_id, subset_id) REFERENCES artifacts (artifact_id, subset_id)
);
CREATE TABLE download_attempts
(
    attempt_id    TEXT PRIMARY KEY NOT NULL,
    subset_id     TEXT             NOT NULL REFERENCES subset_requests (subset_id),
    run_id        TEXT             NOT NULL REFERENCES runs (run_id),
    status        TEXT             NOT NULL CHECK (status IN ('running', 'succeeded', 'reused', 'failed')),
    stage         TEXT             NOT NULL,
    started_at    TEXT             NOT NULL,
    finished_at   TEXT,
    network_bytes INTEGER          NOT NULL DEFAULT 0 CHECK (network_bytes >= 0),
    http_status   INTEGER,
    artifact_id   TEXT,
    error_code    TEXT,
    error_message TEXT,
    UNIQUE (attempt_id, subset_id),
    FOREIGN KEY (artifact_id, subset_id) REFERENCES artifacts (artifact_id, subset_id),
    CHECK ((status = 'running' AND finished_at IS NULL) OR (status <> 'running' AND finished_at IS NOT NULL)),
    CHECK (status NOT IN ('succeeded', 'reused') OR artifact_id IS NOT NULL)
);
CREATE TABLE artifacts
(
    artifact_id           TEXT PRIMARY KEY NOT NULL,
    subset_id             TEXT             NOT NULL REFERENCES subset_requests (subset_id),
    created_by_attempt_id TEXT             NOT NULL,
    sha256                TEXT             NOT NULL,
    size_bytes            INTEGER          NOT NULL CHECK (size_bytes > 0),
    raster_json           TEXT             NOT NULL CHECK (json_valid(raster_json)),
    created_at            TEXT             NOT NULL,
    UNIQUE (subset_id, sha256),
    UNIQUE (artifact_id, subset_id),
    FOREIGN KEY (created_by_attempt_id, subset_id) REFERENCES download_attempts (attempt_id, subset_id)
);
CREATE TABLE artifact_locations
(
    location_id TEXT PRIMARY KEY NOT NULL,
    artifact_id TEXT             NOT NULL REFERENCES artifacts (artifact_id),
    local_path  TEXT             NOT NULL UNIQUE,
    status      TEXT             NOT NULL CHECK (status IN ('available', 'missing', 'corrupt')),
    checked_at  TEXT             NOT NULL
);
