CREATE TABLE batches (
 batch_id TEXT PRIMARY KEY NOT NULL,
 manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
 created_at TEXT NOT NULL
);
CREATE TABLE batch_members (
 batch_id TEXT NOT NULL REFERENCES batches(batch_id),
 member_id TEXT NOT NULL,
 planned_request_id TEXT NOT NULL,
 request_id TEXT REFERENCES processing_requests(request_id),
 spec_json TEXT NOT NULL CHECK(json_valid(spec_json)),
 PRIMARY KEY(batch_id,member_id),
 UNIQUE(batch_id,planned_request_id),
 CHECK(request_id IS NULL OR request_id=planned_request_id)
);
CREATE TABLE batch_observations (
 observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
 batch_id TEXT NOT NULL,
 member_id TEXT NOT NULL,
 observed_at TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ready','complete','blocked','unresolved','failed')),
 reason TEXT NOT NULL CHECK(length(reason)>0),
 attempt_id TEXT REFERENCES processing_attempts(attempt_id),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
 FOREIGN KEY(batch_id,member_id) REFERENCES batch_members(batch_id,member_id)
);
CREATE INDEX batch_observation_member ON batch_observations(batch_id,member_id,observation_id);
