-- Run each query separately. Bind :batch_id to the manifest's batch_id.
-- Confirm that the batch exists before interpreting an empty result.

-- Q1. Which expected members have never reached an application attempt?
-- Columns: member ID, planned request ID, registered request ID.
-- Empty: every member has an attempt somewhere in this catalogue.
-- Next check: inspect the listed member's latest observation and input locations.
SELECT m.member_id, m.planned_request_id, m.request_id AS registered_request_id
FROM batch_members AS m
WHERE m.batch_id = :batch_id
  AND NOT EXISTS (
      SELECT 1
      FROM processing_attempts AS a
      WHERE a.request_id = m.planned_request_id
  )
ORDER BY m.member_id;

-- Q2. Which requests failed or stopped and later produced a verified result?
-- Columns: member and request IDs, incident details, retry and artifact IDs,
-- and the first recorded verification of that retry in this batch.
-- Empty: this batch recorded no such incident followed by a verified production.
-- A blocked input can appear in Q1 without having spent an application attempt.
-- Next check: compare the incident log and the observation's verification evidence.
WITH verified_outputs AS (
    SELECT o.member_id, p.attempt_id, p.artifact_id,
           MIN(o.observed_at) AS first_verified_at
    FROM batch_observations AS o
    JOIN processing_outputs AS p
      ON p.attempt_id = o.attempt_id
     AND p.artifact_id = json_extract(o.evidence_json, '$.result.artifact_id')
    WHERE o.batch_id = :batch_id
      AND o.state = 'complete'
      AND p.role = 'ndvi'
    GROUP BY o.member_id, p.attempt_id, p.artifact_id
)
SELECT m.member_id, m.planned_request_id AS request_id,
       incident.attempt_id AS incident_attempt_id,
       incident.status AS incident_status,
       incident.stage AS incident_stage,
       incident.error_code,
       incident.finished_at AS incident_finished_at,
       recovery.attempt_id AS recovery_attempt_id,
       recovery.finished_at AS recovery_finished_at,
       v.artifact_id,
       v.first_verified_at
FROM batch_members AS m
JOIN processing_attempts AS incident ON incident.request_id = m.planned_request_id
JOIN verified_outputs AS v ON v.member_id = m.member_id
JOIN processing_attempts AS recovery
  ON recovery.attempt_id = v.attempt_id
 AND recovery.request_id = m.planned_request_id
WHERE m.batch_id = :batch_id
  AND incident.status IN ('failed', 'interrupted')
  AND recovery.status = 'succeeded'
  AND recovery.started_at >= incident.finished_at
ORDER BY m.member_id, incident.started_at, recovery.started_at, recovery.attempt_id;

-- Q3. Which succeeded products have no location recorded as available?
-- Columns: member and request IDs, producer, output role, and artifact ID.
-- Empty: every published output from a succeeded attempt has at least one recorded
-- available location. Rows also include artifacts with no location records.
-- Next check: refresh the batch to check actual file presence, bytes and hashes.
-- This query reads recorded status, which may be stale.
SELECT m.member_id, a.request_id, a.attempt_id AS producing_attempt_id,
       p.role AS output_role, p.artifact_id
FROM batch_members AS m
JOIN processing_attempts AS a ON a.request_id = m.planned_request_id
JOIN processing_outputs AS p ON p.attempt_id = a.attempt_id
WHERE m.batch_id = :batch_id
  AND a.status = 'succeeded'
  AND NOT EXISTS (
      SELECT 1
      FROM processing_artifact_locations AS l
      WHERE l.artifact_id = p.artifact_id AND l.status = 'available'
  )
ORDER BY m.member_id, a.started_at, a.attempt_id, p.role;

-- Q4. Which members rely on old observations?
-- Bind :before to a UTC ISO 8601 cutoff such as 2026-11-23T09:45:00Z.
-- Columns: member and request IDs, latest observation ID, state, time and reason.
-- Select the latest appended observation by ID before applying the cutoff.
-- observed_at is when the check was recorded. The report export time and the
-- attempt's completion time do not establish the freshness of that check.
-- Empty: no observed member has a latest check older than the cutoff.
-- Unobserved members have no timestamp and are outside this result.
-- Next check: refresh stale evidence and review the newly appended observations.
SELECT m.member_id, m.planned_request_id AS request_id,
       o.observation_id, o.state, o.observed_at, o.reason
FROM batch_members AS m
JOIN batch_observations AS o
  ON o.batch_id = m.batch_id
 AND o.member_id = m.member_id
 AND o.observation_id = (
     SELECT MAX(latest.observation_id)
     FROM batch_observations AS latest
     WHERE latest.batch_id = m.batch_id AND latest.member_id = m.member_id
 )
WHERE m.batch_id = :batch_id
  AND julianday(o.observed_at) < julianday(:before)
ORDER BY o.observed_at, m.member_id;
