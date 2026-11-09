-- Run against one Lab 04 catalogue at a time. The queries do not change data.
-- Q2 accepts :ndvi_artifact_id; use NULL to trace all produced NDVI artifacts.
PRAGMA foreign_keys = ON;

-- Q1. List requests with their number of attempts, grouped by outcome.
-- COUNT(attempt_id) preserves requests with zero attempts without counting the LEFT JOIN row.
SELECT request.request_id,
       request.stage AS request_stage,
       attempt.status AS outcome,
       COUNT(attempt.attempt_id) AS attempt_count
FROM processing_requests AS request
LEFT JOIN processing_attempts AS attempt ON attempt.request_id = request.request_id
GROUP BY request.request_id, request.stage, attempt.status
ORDER BY request.request_id, attempt.status;

-- Q2. Trace an NDVI artifact through its actual producer and both acquired inputs.
-- A reuse attempt links to the same output but did not produce it.
SELECT output.artifact_id AS ndvi_artifact_id,
       producer.attempt_id AS producing_attempt_id,
       request.request_id,
       request.normalized_json,
       input.role AS input_role,
       input.artifact_id AS input_artifact_id,
       input_artifact.sha256 AS input_sha256,
       acquired.artifact_id AS lab3_artifact_id,
       subset.subset_id,
       asset.asset_id,
       scene.collection,
       scene.item_id,
       asset.asset_key AS band,
       subset.aoi_key,
       subset.aoi_json,
       subset.recipe_version
FROM processing_outputs AS output
JOIN processing_attempts AS producer ON producer.attempt_id = output.attempt_id
JOIN processing_requests AS request ON request.request_id = producer.request_id
JOIN processing_inputs AS input ON input.request_id = request.request_id
JOIN processing_artifacts AS input_artifact ON input_artifact.artifact_id = input.artifact_id
LEFT JOIN artifacts AS acquired ON acquired.artifact_id = input_artifact.source_artifact_id
LEFT JOIN subset_requests AS subset ON subset.subset_id = acquired.subset_id
LEFT JOIN assets AS asset ON asset.asset_id = subset.asset_id
LEFT JOIN scenes AS scene ON scene.collection = asset.collection AND scene.item_id = asset.item_id
WHERE output.role = 'ndvi'
  AND producer.status = 'succeeded'
  AND (:ndvi_artifact_id IS NULL OR output.artifact_id = :ndvi_artifact_id)
ORDER BY output.artifact_id, producer.attempt_id, CASE input.role WHEN 'red' THEN 0 ELSE 1 END, input.role;

-- Q3. Return the full attempt history for requests with a failure or interruption.
-- Filter requests, rather than individual attempts, so successful retries stay visible.
SELECT attempt.request_id,
       attempt.attempt_id,
       attempt.status,
       attempt.stage,
       attempt.started_at,
       attempt.finished_at,
       attempt.error_code,
       attempt.error_message,
       attempt.reused_from_attempt_id,
       attempt.log_path
FROM processing_attempts AS attempt
WHERE EXISTS (
    SELECT 1
    FROM processing_attempts AS incident
    WHERE incident.request_id = attempt.request_id
      AND incident.status IN ('failed', 'interrupted')
)
ORDER BY attempt.request_id, attempt.started_at, attempt.attempt_id;

-- Q4. Find successful outputs with no location recorded as available.
-- This includes artifacts with no location rows. An "available" row is a past
-- observation: confirming current availability requires checking the file and its hash.
SELECT attempt.request_id,
       attempt.attempt_id,
       output.role AS output_role,
       output.artifact_id,
       artifact.sha256
FROM processing_attempts AS attempt
JOIN processing_outputs AS output ON output.attempt_id = attempt.attempt_id
JOIN processing_artifacts AS artifact ON artifact.artifact_id = output.artifact_id
WHERE attempt.status = 'succeeded'
  AND NOT EXISTS (
      SELECT 1
      FROM processing_artifact_locations AS location
      WHERE location.artifact_id = output.artifact_id
        AND location.status = 'available'
  )
ORDER BY attempt.request_id, attempt.attempt_id, output.role;

-- Q5. Inspect unresolved attempts even when no output has been registered.
-- A running row alone does not establish that the process is still alive.
SELECT attempt.request_id,
       attempt.attempt_id,
       attempt.status,
       attempt.stage,
       attempt.started_at,
       attempt.temp_path,
       attempt.final_path,
       attempt.log_path,
       attempt.receipt_json,
       output.role AS output_role,
       output.artifact_id AS output_artifact_id
FROM processing_attempts AS attempt
LEFT JOIN processing_outputs AS output ON output.attempt_id = attempt.attempt_id
WHERE attempt.status = 'running'
ORDER BY attempt.started_at, attempt.attempt_id, output.role;

-- Q6. Compare registered input calibration and provider metadata with the review
-- saved in the normalized request. A reviewed calibration is bound to one input hash.
WITH calibration AS (
    SELECT request.request_id,
           input.role AS input_role,
           input.artifact_id AS input_artifact_id,
           input_artifact.sha256 AS input_sha256,
           json_extract(request.normalized_json, '$.settings.scaling') AS scaling_policy,
           json_extract(asset.metadata_json, '$."raster:bands"[0].scale') AS provider_scale,
           json_extract(asset.metadata_json, '$."raster:bands"[0].offset') AS provider_offset,
           json_extract(input_artifact.raster_json, '$.scale') AS original_scale,
           json_extract(input_artifact.raster_json, '$.offset') AS original_offset,
           json_extract(review.value, '$.scale') AS reviewed_scale,
           json_extract(review.value, '$.offset') AS reviewed_offset,
           json_extract(review.value, '$.sha256') AS reviewed_sha256,
           json_extract(review.value, '$.evidence') AS review_evidence
    FROM processing_requests AS request
    JOIN processing_inputs AS input ON input.request_id = request.request_id
    JOIN processing_artifacts AS input_artifact ON input_artifact.artifact_id = input.artifact_id
    LEFT JOIN artifacts AS acquired ON acquired.artifact_id = input_artifact.source_artifact_id
    LEFT JOIN subset_requests AS subset ON subset.subset_id = acquired.subset_id
    LEFT JOIN assets AS asset ON asset.asset_id = subset.asset_id
    LEFT JOIN json_each(request.normalized_json, '$.settings.calibration') AS review
           ON review.key = input.role
)
SELECT calibration.*,
       CASE WHEN scaling_policy = 'reviewed_calibration'
            THEN COALESCE(reviewed_sha256 = input_sha256, 0)
       END AS review_hash_matches_input,
       CASE
           WHEN scaling_policy = 'asset_metadata' THEN original_scale
           WHEN scaling_policy = 'reviewed_calibration' AND reviewed_sha256 = input_sha256 THEN reviewed_scale
       END AS configured_scale,
       CASE
           WHEN scaling_policy = 'asset_metadata' THEN original_offset
           WHEN scaling_policy = 'reviewed_calibration' AND reviewed_sha256 = input_sha256 THEN reviewed_offset
       END AS configured_offset
FROM calibration
ORDER BY request_id, CASE input_role WHEN 'red' THEN 0 ELSE 1 END, input_role;
