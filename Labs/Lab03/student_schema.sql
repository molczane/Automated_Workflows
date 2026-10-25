-- Lab 03: source revisions, AOI requests, attempt history and local artifacts.
-- The original scenes/streams/downloads/runs/stream_scenes tables are supplied.
-- Foreign keys must be enabled by each connection (as in lab03_store.open_db).

CREATE TABLE assets (
    asset_id TEXT NOT NULL PRIMARY KEY,
    collection TEXT NOT NULL,
    item_id TEXT NOT NULL,
    asset_key TEXT NOT NULL CHECK (asset_key IN ('red', 'nir')),
    source_url TEXT NOT NULL,
    metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
    metadata_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (collection, item_id, asset_key, metadata_sha256),
    FOREIGN KEY (collection, item_id) REFERENCES scenes (collection, item_id)
);

CREATE TABLE subset_requests (
    subset_id TEXT NOT NULL PRIMARY KEY,
    asset_id TEXT NOT NULL,
    aoi_key TEXT NOT NULL,
    aoi_json TEXT NOT NULL CHECK (json_valid(aoi_json)),
    recipe_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'failed')),
    latest_artifact_id TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (asset_id, aoi_key, recipe_version),
    CHECK (status <> 'ready' OR latest_artifact_id IS NOT NULL),
    FOREIGN KEY (asset_id) REFERENCES assets (asset_id),
    FOREIGN KEY (latest_artifact_id, subset_id)
        REFERENCES artifacts (artifact_id, subset_id)
);

CREATE TABLE download_attempts (
    attempt_id TEXT NOT NULL PRIMARY KEY,
    subset_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'reused', 'failed')),
    -- Stage is diagnostic text; lifecycle is constrained separately by status.
    stage TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    network_bytes INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(network_bytes) = 'integer' AND network_bytes >= 0),
    http_status INTEGER,
    artifact_id TEXT,
    error_code TEXT,
    error_message TEXT,
    UNIQUE (attempt_id, subset_id),
    CHECK ((status = 'running' AND finished_at IS NULL)
        OR (status <> 'running' AND finished_at IS NOT NULL)),
    CHECK (status NOT IN ('succeeded', 'reused') OR artifact_id IS NOT NULL),
    FOREIGN KEY (subset_id) REFERENCES subset_requests (subset_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
    FOREIGN KEY (artifact_id, subset_id)
        REFERENCES artifacts (artifact_id, subset_id)
);

CREATE TABLE artifacts (
    artifact_id TEXT NOT NULL PRIMARY KEY,
    subset_id TEXT NOT NULL,
    created_by_attempt_id TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
        CHECK (typeof(size_bytes) = 'integer' AND size_bytes > 0),
    raster_json TEXT NOT NULL CHECK (json_valid(raster_json)),
    created_at TEXT NOT NULL,
    UNIQUE (subset_id, sha256),
    -- Explicit parent keys are required for SQLite composite foreign keys.
    UNIQUE (artifact_id, subset_id),
    FOREIGN KEY (subset_id) REFERENCES subset_requests (subset_id),
    FOREIGN KEY (created_by_attempt_id, subset_id)
        REFERENCES download_attempts (attempt_id, subset_id)
);

CREATE TABLE artifact_locations (
    location_id TEXT NOT NULL PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    local_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('available', 'missing', 'corrupt')),
    checked_at TEXT NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
);

CREATE INDEX attempts_by_run ON download_attempts (run_id);
CREATE INDEX attempts_by_subset ON download_attempts (subset_id);
CREATE INDEX locations_by_artifact ON artifact_locations (artifact_id);
CREATE INDEX artifacts_by_creator ON artifacts (created_by_attempt_id, subset_id);
