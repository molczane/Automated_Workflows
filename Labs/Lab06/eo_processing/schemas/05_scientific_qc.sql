CREATE TABLE IF NOT EXISTS processing_schema_migrations (
 version INTEGER PRIMARY KEY,
 applied_at TEXT NOT NULL,
 description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scientific_qc_assessments (
 assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id TEXT NOT NULL REFERENCES processing_requests(request_id),
 attempt_id TEXT NOT NULL,
 assessed_at TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 policy_json TEXT NOT NULL CHECK(json_valid(policy_json)),
 outcome TEXT NOT NULL CHECK(outcome IN ('accepted','review','rejected')),
 reason TEXT NOT NULL,
 metrics_json TEXT NOT NULL CHECK(json_valid(metrics_json)),
 FOREIGN KEY(attempt_id,request_id) REFERENCES processing_attempts(attempt_id,request_id)
);
CREATE INDEX IF NOT EXISTS scientific_qc_attempt ON scientific_qc_assessments(attempt_id,assessment_id);
CREATE VIEW IF NOT EXISTS latest_scientific_qc AS
 SELECT q.* FROM scientific_qc_assessments q
 WHERE q.assessment_id=(SELECT MAX(q2.assessment_id) FROM scientific_qc_assessments q2 WHERE q2.attempt_id=q.attempt_id);
