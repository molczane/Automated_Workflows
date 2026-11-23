-- Run each statement separately in your SQLite GUI. These are current-catalogue
-- investigations; comments are part of the evidence you should retain.

-- Execution succeeded but the latest scientific assessment rejected its use.
SELECT a.attempt_id, a.status AS execution_status, q.outcome,
       q.assessed_at, q.reason,
       json_extract(q.metrics_json,'$.valid_fraction') AS valid_fraction
FROM processing_attempts AS a
JOIN latest_scientific_qc AS q USING(attempt_id)
WHERE a.status='succeeded' AND q.outcome='rejected'
ORDER BY q.assessment_id;

-- Named outputs from each producing attempt; no column per optical index.
SELECT a.request_id, a.attempt_id,
       json_extract(r.normalized_json,'$.product.name') AS product,
       o.role, o.artifact_id
FROM processing_attempts AS a
JOIN processing_requests AS r USING(request_id)
JOIN processing_outputs AS o USING(attempt_id)
ORDER BY a.started_at, o.role;

-- Earlier and later scientific conclusions remain available.
SELECT attempt_id, assessment_id, assessed_at, policy_version, outcome,
       json_extract(policy_json,'$.minimum_valid_fraction') AS minimum_valid_fraction,
       json_extract(metrics_json,'$.valid_fraction') AS observed_valid_fraction
FROM scientific_qc_assessments
ORDER BY attempt_id, assessment_id;

-- Current stored location checks. Compare checked_at with the time you need.
-- Running the Version 1 coordinator refreshes the locations it inspects.
SELECT artifact_id, local_path, status, checked_at
FROM processing_artifact_locations
WHERE status<>'available'
ORDER BY checked_at DESC;

-- Expected work with no execution attempt, including unattached planned requests.
SELECT m.batch_id, m.member_id, m.planned_request_id
FROM batch_members AS m
WHERE NOT EXISTS (
 SELECT 1 FROM processing_attempts AS a WHERE a.request_id=m.planned_request_id
)
ORDER BY m.batch_id,m.member_id;

-- Unresolved executions: timestamps alone do not establish whether a process ended.
SELECT attempt_id, request_id, stage, started_at, log_path
FROM processing_attempts
WHERE status='running';

-- MNDWI area is explicitly restricted to observed pixels.
SELECT attempt_id,
       json_extract(receipt_json,'$.metrics.product_metrics.candidate_water_area_m2') AS candidate_water_area_m2,
       json_extract(receipt_json,'$.metrics.product_metrics.observed_area_m2') AS observed_area_m2,
       json_extract(receipt_json,'$.metrics.valid_fraction') AS valid_fraction
FROM processing_attempts
WHERE status='succeeded' AND json_extract(receipt_json,'$.contract')='optical-product-v1';

-- Add your own question, SQL and interpretation below.
