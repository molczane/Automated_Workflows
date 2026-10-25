-- Run against the main archive or the named case database, as appropriate.
-- Read-only diagnostics. Before recovery, save the results: current locations
-- will change after repair, while the original attempt history is preserved.

-- query: attempt_overview
-- Supplied worked join: one row per attempt, including failures without artifacts.
SELECT r.run_id,r.command,a.item_id,a.asset_key,s.aoi_key,d.status,d.stage,
       d.network_bytes,d.http_status,d.error_code,d.error_message
FROM download_attempts d JOIN runs r ON r.run_id=d.run_id
JOIN subset_requests s ON s.subset_id=d.subset_id
JOIN assets a ON a.asset_id=s.asset_id
ORDER BY d.started_at,d.attempt_id;

-- query: network_history
-- Case A: LEFT JOIN retains the failed nir attempt with no artifact.
-- Re-run after recovery to see red reuse and a new successful nir attempt.
SELECT r.run_id, r.status AS run_status, a.asset_key, d.attempt_id,
       d.status AS attempt_status, d.stage, d.network_bytes, d.http_status,
       d.error_code, d.error_message, d.artifact_id, f.sha256, f.size_bytes
FROM download_attempts AS d
JOIN runs AS r ON r.run_id = d.run_id
JOIN subset_requests AS s ON s.subset_id = d.subset_id
JOIN assets AS a ON a.asset_id = s.asset_id
LEFT JOIN artifacts AS f
    ON f.artifact_id = d.artifact_id AND f.subset_id = d.subset_id
ORDER BY r.started_at, d.started_at, d.attempt_id;

-- query: request_state
-- Case A: red has a result while failed nir has none before recovery.
SELECT a.item_id, a.asset_key, s.subset_id, s.aoi_key,
       s.status AS request_status, s.latest_artifact_id,
       f.sha256, f.size_bytes
FROM subset_requests AS s
JOIN assets AS a ON a.asset_id = s.asset_id
LEFT JOIN artifacts AS f
    ON f.artifact_id = s.latest_artifact_id AND f.subset_id = s.subset_id
ORDER BY a.asset_key, s.aoi_key;

-- query: missing_history
-- Case B: historical acquisition success and later cache_verify failure coexist.
-- location_status is CURRENT state, not availability at the attempt timestamp.
SELECT r.run_id, r.command, r.status AS run_status, a.asset_key,
       d.attempt_id, d.status AS attempt_status, d.stage, d.error_code,
       d.artifact_id, f.sha256, f.created_by_attempt_id,
       l.local_path, l.status AS location_status, l.checked_at
FROM download_attempts AS d
JOIN runs AS r ON r.run_id = d.run_id
JOIN subset_requests AS s ON s.subset_id = d.subset_id
JOIN assets AS a ON a.asset_id = s.asset_id
LEFT JOIN artifacts AS f
    ON f.artifact_id = d.artifact_id AND f.subset_id = d.subset_id
LEFT JOIN artifact_locations AS l ON l.artifact_id = f.artifact_id
ORDER BY r.started_at, d.started_at, d.attempt_id, l.local_path;

-- query: saved_files
-- Paths, hashes and last verified availability for each request's latest result.
SELECT a.item_id, a.asset_key, s.aoi_key, s.subset_id, f.artifact_id,
       f.sha256, f.size_bytes, l.local_path, l.status AS location_status,
       l.checked_at, f.raster_json
FROM subset_requests AS s
JOIN assets AS a ON a.asset_id = s.asset_id
LEFT JOIN artifacts AS f
    ON f.artifact_id = s.latest_artifact_id AND f.subset_id = s.subset_id
LEFT JOIN artifact_locations AS l ON l.artifact_id = f.artifact_id
ORDER BY a.asset_key, s.aoi_key, l.local_path;

-- query: transfer_vs_storage
-- Aggregate attempts and distinct artifacts BEFORE joining: multiple file paths
-- must not multiply network-byte totals or registered artifact sizes.
WITH transfer AS (
    SELECT subset_id, COUNT(*) AS attempts,
           SUM(network_bytes) AS received_http_bytes,
           SUM(CASE WHEN status = 'reused' THEN 1 ELSE 0 END) AS reused_attempts
    FROM download_attempts GROUP BY subset_id
), stored AS (
    SELECT subset_id, COUNT(*) AS artifact_versions,
           SUM(size_bytes) AS registered_bytes
    FROM artifacts GROUP BY subset_id
)
SELECT a.asset_key, s.aoi_key, s.subset_id,
       COALESCE(t.attempts, 0) AS attempts,
       COALESCE(t.received_http_bytes, 0) AS received_http_bytes,
       COALESCE(t.reused_attempts, 0) AS reused_attempts,
       COALESCE(f.artifact_versions, 0) AS artifact_versions,
       COALESCE(f.registered_bytes, 0) AS registered_bytes
FROM subset_requests AS s
JOIN assets AS a ON a.asset_id = s.asset_id
LEFT JOIN transfer AS t ON t.subset_id = s.subset_id
LEFT JOIN stored AS f ON f.subset_id = s.subset_id
ORDER BY a.asset_key, s.aoi_key;

-- query: aoi_identity
-- Main archive after the alternate AOI acquisition: two requests per source band.
-- The composite references ensure each latest artifact belongs to its own request.
SELECT a.item_id, a.asset_key, a.asset_id, s.subset_id, s.aoi_key,
       s.aoi_json, s.recipe_version, s.latest_artifact_id,
       f.subset_id AS artifact_subset_id, f.sha256, f.size_bytes
FROM assets AS a
JOIN subset_requests AS s ON s.asset_id = a.asset_id
LEFT JOIN artifacts AS f
    ON f.artifact_id = s.latest_artifact_id AND f.subset_id = s.subset_id
ORDER BY a.asset_key, s.aoi_key;

-- query: foreign_key_check
-- No rows means SQLite found no invalid foreign-key references. This says
-- nothing about actual file existence, file bytes or raster metadata.
PRAGMA foreign_key_check;
