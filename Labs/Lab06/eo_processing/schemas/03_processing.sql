CREATE TABLE processing_artifacts (
 artifact_id TEXT PRIMARY KEY NOT NULL,
 source_artifact_id TEXT UNIQUE REFERENCES artifacts(artifact_id),
 sha256 TEXT NOT NULL CHECK(length(sha256)=64),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
 raster_json TEXT NOT NULL CHECK(json_valid(raster_json)),
 lineage_json TEXT NOT NULL CHECK(json_valid(lineage_json)),
 created_at TEXT NOT NULL
);
CREATE TABLE processing_artifact_locations (
 location_id TEXT PRIMARY KEY NOT NULL,
 artifact_id TEXT NOT NULL REFERENCES processing_artifacts(artifact_id),
 local_path TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('available','missing','corrupt')),
 checked_at TEXT NOT NULL
);
CREATE TABLE processing_requests (
 request_id TEXT PRIMARY KEY NOT NULL,
 fingerprint TEXT NOT NULL UNIQUE CHECK(length(fingerprint)=64),
 stage TEXT NOT NULL,
 normalized_json TEXT NOT NULL CHECK(json_valid(normalized_json)),
 created_at TEXT NOT NULL
);
CREATE TABLE processing_inputs (
 request_id TEXT NOT NULL REFERENCES processing_requests(request_id),
 role TEXT NOT NULL CHECK(length(role)>0),
 artifact_id TEXT NOT NULL REFERENCES processing_artifacts(artifact_id),
 PRIMARY KEY(request_id,role)
);
CREATE TABLE processing_attempts (
 attempt_id TEXT PRIMARY KEY NOT NULL,
 request_id TEXT NOT NULL REFERENCES processing_requests(request_id),
 status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','interrupted','reused')),
 stage TEXT NOT NULL,
 started_at TEXT NOT NULL,
 finished_at TEXT,
 environment_json TEXT NOT NULL CHECK(json_valid(environment_json)),
 original_config TEXT NOT NULL,
 resolved_config_json TEXT NOT NULL CHECK(json_valid(resolved_config_json)),
 temp_path TEXT NOT NULL UNIQUE,
 final_path TEXT NOT NULL UNIQUE,
 log_path TEXT NOT NULL UNIQUE,
 receipt_json TEXT CHECK(receipt_json IS NULL OR json_valid(receipt_json)),
 error_code TEXT,
 error_message TEXT,
 reused_from_attempt_id TEXT,
 UNIQUE(attempt_id,request_id),
 FOREIGN KEY(reused_from_attempt_id,request_id) REFERENCES processing_attempts(attempt_id,request_id),
 CHECK((status='running' AND finished_at IS NULL) OR (status<>'running' AND finished_at IS NOT NULL)),
 CHECK((status='reused' AND reused_from_attempt_id IS NOT NULL) OR (status<>'reused' AND reused_from_attempt_id IS NULL)),
 CHECK(status<>'succeeded' OR receipt_json IS NOT NULL),
 CHECK(status NOT IN ('failed','interrupted') OR error_code IS NOT NULL)
);
CREATE TABLE processing_outputs (
 attempt_id TEXT NOT NULL REFERENCES processing_attempts(attempt_id),
 role TEXT NOT NULL CHECK(length(role)>0),
 artifact_id TEXT NOT NULL REFERENCES processing_artifacts(artifact_id),
 PRIMARY KEY(attempt_id,role)
);
CREATE INDEX processing_attempt_request ON processing_attempts(request_id,started_at);
CREATE INDEX processing_input_artifact ON processing_inputs(artifact_id);
CREATE INDEX processing_output_artifact ON processing_outputs(artifact_id);
