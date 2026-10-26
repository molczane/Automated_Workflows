-- Processing extension: keep the existing discovery/acquisition tables intact.
-- IDs, checksums and UTC timestamps are supplied by Python. Each connection
-- must enable PRAGMA foreign_keys = ON, as processing_store.connect does.

CREATE TABLE processing_artifacts (
    artifact_id TEXT NOT NULL PRIMARY KEY,
    source_artifact_id TEXT UNIQUE,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    size_bytes INTEGER NOT NULL
        CHECK (typeof(size_bytes) = 'integer' AND size_bytes > 0),
    raster_json TEXT NOT NULL CHECK (json_valid(raster_json)),
    lineage_json TEXT NOT NULL CHECK (json_valid(lineage_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_artifact_id) REFERENCES artifacts (artifact_id)
);

CREATE TABLE processing_artifact_locations (
    location_id TEXT NOT NULL PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    local_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('available', 'missing', 'corrupt')),
    checked_at TEXT NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES processing_artifacts (artifact_id)
);

CREATE TABLE processing_requests (
    request_id TEXT NOT NULL PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64),
    stage TEXT NOT NULL CHECK (length(trim(stage)) > 0),
    normalized_json TEXT NOT NULL CHECK (json_valid(normalized_json)),
    created_at TEXT NOT NULL
);

CREATE TABLE processing_inputs (
    request_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (length(trim(role)) > 0),
    artifact_id TEXT NOT NULL,
    PRIMARY KEY (request_id, role),
    FOREIGN KEY (request_id) REFERENCES processing_requests (request_id),
    FOREIGN KEY (artifact_id) REFERENCES processing_artifacts (artifact_id)
);

CREATE TABLE processing_attempts (
    attempt_id TEXT NOT NULL PRIMARY KEY,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('running', 'succeeded', 'failed', 'interrupted', 'reused')),
    stage TEXT NOT NULL CHECK (length(trim(stage)) > 0),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    environment_json TEXT NOT NULL CHECK (json_valid(environment_json)),
    original_config TEXT NOT NULL,
    resolved_config_json TEXT NOT NULL CHECK (json_valid(resolved_config_json)),
    temp_path TEXT NOT NULL UNIQUE,
    final_path TEXT NOT NULL UNIQUE,
    log_path TEXT NOT NULL UNIQUE,
    receipt_json TEXT
        CHECK (receipt_json IS NULL OR json_valid(receipt_json)),
    error_code TEXT,
    error_message TEXT,
    reused_from_attempt_id TEXT,
    -- SQLite needs this explicit parent key for the composite reuse reference.
    UNIQUE (attempt_id, request_id),
    CHECK ((status = 'running' AND finished_at IS NULL)
        OR (status <> 'running' AND finished_at IS NOT NULL)),
    CHECK (status <> 'succeeded' OR receipt_json IS NOT NULL),
    CHECK (status NOT IN ('failed', 'interrupted')
        OR (error_code IS NOT NULL AND length(trim(error_code)) > 0)),
    CHECK ((status = 'reused' AND reused_from_attempt_id IS NOT NULL)
        OR (status <> 'reused' AND reused_from_attempt_id IS NULL)),
    CHECK (reused_from_attempt_id IS NULL OR reused_from_attempt_id <> attempt_id),
    FOREIGN KEY (request_id) REFERENCES processing_requests (request_id),
    FOREIGN KEY (reused_from_attempt_id, request_id)
        REFERENCES processing_attempts (attempt_id, request_id)
);

CREATE TABLE processing_outputs (
    attempt_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (length(trim(role)) > 0),
    artifact_id TEXT NOT NULL,
    PRIMARY KEY (attempt_id, role),
    FOREIGN KEY (attempt_id) REFERENCES processing_attempts (attempt_id),
    FOREIGN KEY (artifact_id) REFERENCES processing_artifacts (artifact_id)
);

CREATE INDEX processing_locations_by_artifact
    ON processing_artifact_locations (artifact_id);
CREATE INDEX processing_attempts_by_request
    ON processing_attempts (request_id);
CREATE INDEX processing_attempts_by_reused_producer
    ON processing_attempts (reused_from_attempt_id, request_id);
CREATE INDEX processing_inputs_by_artifact
    ON processing_inputs (artifact_id);
CREATE INDEX processing_outputs_by_artifact
    ON processing_outputs (artifact_id);

-- Cross-table execution invariants remain the job's responsibility: its publish
-- transaction registers artifact/location/output rows and success together, and
-- its reuse checks select a succeeded producer with a verified output. The
-- foreign keys alone cannot establish that a producer succeeded or that a file
-- exists with the recorded bytes. Artifact records are treated as immutable by
-- the supplied application; availability changes belong to location records.
