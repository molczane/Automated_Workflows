# Lab 04 database contract

Write all six new table definitions in `student_processing_schema.sql`. Choose and
write the keys, references, checks and indexes yourself. The Python interface uses
the names below. `check_lab04.py --part schema` checks behavior in memory and never
changes your working catalogue.

Keep the existing Lab 3 tables. Its `artifacts.subset_id` is required, so every row
there means an acquired subset. An NDVI output has no acquisition subset request.
This lab therefore adds `processing_artifacts`, a general registry, and links an
imported input back through `source_artifact_id`. Derived outputs use the same
registry with that reference absent. No dummy subset or acquisition attempt is
created for an NDVI output. `support/` contains the already completed Lab 2/3 schema
only, so the real captured inputs can be opened without repeating those exercises.

| Table | What one row means | Key |
| --- | --- | --- |
| processing_artifacts | One identified input or output byte sequence with interpretation metadata | artifact_id |
| processing_artifact_locations | One current known path for an artifact | location_id |
| processing_requests | One specified calculation under the declared equivalence policy | request_id |
| processing_inputs | An artifact filling one named role in a request | request_id, role |
| processing_attempts | One invocation trying to satisfy a request | attempt_id |
| processing_outputs | An artifact returned by one attempt under one output role | attempt_id, role |

All IDs and UTC timestamps are TEXT and are supplied by Python. Every column is
NOT NULL except those explicitly marked optional below. Make TEXT primary keys
explicitly NOT NULL in SQLite. JSON columns contain valid JSON text. Do not make
request_id individually unique in either relationship or attempt tables: a request
has several inputs and can have several attempts.

## processing_artifacts

| Column | Type | Meaning |
| --- | --- | --- |
| artifact_id | TEXT | Primary key |
| source_artifact_id | TEXT, optional | Unique reference to Lab 3 artifacts.artifact_id for an acquired input |
| sha256 | TEXT | File checksum; exactly 64 characters |
| size_bytes | INTEGER | Positive byte count |
| raster_json | TEXT | Original input plan, or derived raster validation record |
| lineage_json | TEXT | Input scene/asset/AOI lineage; derived rows use {} and follow output links |
| created_at | TEXT | Registration time |

Different artifacts may share a checksum. Interpretation and source lineage also
matter. An artifact ID refers to immutable records; changing a file requires a new
artifact, rather than changing its registered checksum.

## processing_artifact_locations

| Column | Type | Meaning |
| --- | --- | --- |
| location_id | TEXT | Primary key |
| artifact_id | TEXT | Reference to processing_artifacts |
| local_path | TEXT | Unique path |
| status | TEXT | available, missing or corrupt |
| checked_at | TEXT | Most recent actual check |

A path is not proof of availability. Python checks size and SHA-256 before use.
An artifact can have more than one location. Changing availability never rewrites
the historical status of its producing attempt.

## processing_requests

| Column | Type | Meaning |
| --- | --- | --- |
| request_id | TEXT | Primary key |
| fingerprint | TEXT | Unique 64-character SHA-256 of canonical normalized JSON |
| stage | TEXT | Algorithm identity, initially ndvi_v1 |
| normalized_json | TEXT | The complete explanation of the fingerprint |
| created_at | TEXT | First registration |

Request identity includes ordered input roles, exact input identities/checksums,
lineage and raster interpretation, scientific settings, and the recorded environment.
Runtime output/log paths are excluded. The strict policy in this lab deliberately
creates a new request when code, Python, relevant library versions or platform
change. Later you can define and test a less restrictive equivalence policy.

## processing_inputs

| Column | Type | Meaning |
| --- | --- | --- |
| request_id | TEXT | Reference to processing_requests |
| role | TEXT | Nonempty input role, initially red or nir |
| artifact_id | TEXT | Reference to processing_artifacts |

Use a composite primary key of request_id and role. Roles are names, not list
positions inferred from file order. The application verifies the two NDVI roles;
the table can support other named roles in future stages.

## processing_attempts

| Column | Type | Meaning |
| --- | --- | --- |
| attempt_id | TEXT | Primary key |
| request_id | TEXT | Reference to processing_requests |
| status | TEXT | running, succeeded, failed, interrupted or reused |
| stage | TEXT | Last reached stage |
| started_at | TEXT | UTC start time |
| finished_at | TEXT, optional | Absent while running; present for every terminal status |
| environment_json | TEXT | Code hashes and execution versions |
| original_config | TEXT | Original YAML text, including runtime choices |
| resolved_config_json | TEXT | Parsed config, resolved paths and input metadata |
| temp_path | TEXT | Unique reserved temporary output path |
| final_path | TEXT | Unique reserved final output path |
| log_path | TEXT | Unique JSONL log path |
| receipt_json | TEXT, optional | Validated raster metadata, checksum and expected grid before rename |
| error_code | TEXT, optional | Required for failed/interrupted status |
| error_message | TEXT, optional | Detailed explanation when available |
| reused_from_attempt_id | TEXT, optional | Producing attempt, required only for reused status |

Running rows have no finished_at. Every other status has one. Succeeded rows
require a receipt. Reused rows require reused_from_attempt_id; other statuses must
leave it NULL. Enforce that a reused attempt belongs to the same request through
a composite reference `(reused_from_attempt_id, request_id)` to
`(attempt_id, request_id)` in this table. Supply a matching UNIQUE parent key.

An interruption may leave a row at running because the process cannot report its
own death. Reconciliation updates that row only after establishing that it stopped.
Stages used by the wrapper are validate_inputs, calculate, write_temporary,
validate_temporary, before_rename, register_output and complete. Keep stage as
nonempty explanatory text rather than creating a lifecycle status for every cause.

## processing_outputs

| Column | Type | Meaning |
| --- | --- | --- |
| attempt_id | TEXT | Reference to processing_attempts |
| role | TEXT | Nonempty output role, initially ndvi |
| artifact_id | TEXT | Reference to processing_artifacts |

Use attempt_id and role as the composite primary key. A reused attempt returns an
existing artifact and points to its producing attempt. To find actual production,
follow the output link to an attempt with status succeeded.

The wrapper inserts the artifact, location, output link and succeeded status in one
short database transaction. Ordinary CHECK constraints cannot enforce all rules
that depend on several tables. Explain which constraints your SQL enforces and
which invariants require the supplied transaction and job checks.

Enable foreign keys on every SQLite connection, including DB Browser sessions.
Useful indexes include processing_attempts.request_id and the artifact references
in processing_inputs and processing_outputs. Keep discovery/acquisition `runs`
separate from processing_attempts.
