# Lab 03 investigation report

Completed with the supplied application and checks unchanged. The separate archive
uses captured historical scene metadata; every live subset was obtained from
actual bounded HTTPS ranges, not copied from the packaged raster fixtures.

## Main archive

Scene: `S2C_34UDA_20250605_0_L2A`. Main AOI: `[19.91, 50.04, 19.94, 50.06]`.

| Band | Source shape | Subset shape | Pixel size | CRS | Raw bytes | Scale | Offset |
|---|---|---|---|---|---:|---:|---:|
| red | 10980 × 10980 | 227 × 219 | 10 × 10 m | EPSG:32634 | 99,426 | 0.0001 | -0.1 |
| nir | 10980 × 10980 | 227 × 219 | 10 × 10 m | EPSG:32634 | 99,426 | 0.0001 | -0.1 |

Red: 2,097,153 received HTTP bytes →
75,490 stored bytes. NIR:
2,097,153 → 75,702.
The repeat verified/reused both outputs with zero HTTP transfer. The oversized AOI
was rejected at planning, before remote raster reads. The alternate AOI also
succeeded: 114 × 110 pixels,
20,055 red bytes and
20,075 nir bytes. The archive now has two assets,
four requests, four artifacts and six attempts. `lab03_report.json` contains the
full IDs and main run history.

## Network interruption

Prediction before running: red succeeds, nir fails without an artifact; recovery
reuses red and retries nir while preserving the failed attempt.

Symptom: controlled range failure, exit 1. Diagnostics: `network_history` and
`request_state` in investigation_queries.sql. Before recovery:

| Run (prefix) | Band | Attempt (prefix) | Status | Stage | HTTP bytes | Artifact (prefix) |
|---|---|---|---|---|---:|---|
| lab03-54292676 | red | attempt-04d40285 | succeeded | complete | 2,097,153 | 59c9437e300a3549 |
| lab03-54292676 | nir | attempt-a485f16e | failed | read_window | 262,145 | NULL |

NIR failed at read_window with RANGE_READ_FAILED after
262,145 actual bytes; last HTTP status 206. Red was
already stored. LEFT JOIN preserves the failed row with its NULL artifact; INNER
JOIN would hide it. A discovery watermark only establishes metadata coverage.

Recovery: `python lab03_cli.py acquire --config cases/network/config.json`.
New attempts:

| Run (prefix) | Band | Attempt (prefix) | Status | Stage | HTTP bytes | Artifact (prefix) |
|---|---|---|---|---|---:|---|
| lab03-227b7ea5 | red | attempt-5056a1c6 | reused | cache_verify | 0 | 59c9437e300a3549 |
| lab03-227b7ea5 | nir | attempt-2fe99d2a | succeeded | complete | 2,097,153 | dcfea4a7d5a3e6ef |

All four history rows remain, including the original failure. Both requests are
ready, both locations available, and both actual files pass validation.

## Missing red file

Prediction before running: deleting a file cannot violate a foreign key. Original
success must remain in history; later cache verification should detect FILE_MISSING.

Symptom: after both successful transfers the isolated case deleted red, then its
verify command returned exit 1. `missing_history` joined the original artifact to
a current missing location, while a direct filesystem check confirmed absence.
Before recovery:

| Run (prefix) | Band | Attempt (prefix) | Status | Stage | HTTP bytes | Artifact (prefix) |
|---|---|---|---|---|---:|---|
| lab03-6da4bb86 | red | attempt-aff3c68f | succeeded | complete | 2,097,153 | 59c9437e300a3549 |
| lab03-6da4bb86 | nir | attempt-a634a57e | succeeded | complete | 2,097,153 | dcfea4a7d5a3e6ef |
| lab03-35d776eb | red | attempt-d3f18868 | failed | cache_verify | 0 | 59c9437e300a3549 |
| lab03-35d776eb | nir | attempt-d8dc7f71 | reused | cache_verify | 0 | dcfea4a7d5a3e6ef |

Recovery: `python lab03_cli.py acquire --config cases/missing/config.json`.
New attempts:

| Run (prefix) | Band | Attempt (prefix) | Status | Stage | HTTP bytes | Artifact (prefix) |
|---|---|---|---|---|---:|---|
| lab03-bb64ff3a | red | attempt-2d617b80 | failed | cache_verify | 0 | 59c9437e300a3549 |
| lab03-bb64ff3a | red | attempt-3d9c1745 | succeeded | complete | 2,097,153 | 59c9437e300a3549 |
| lab03-bb64ff3a | nir | attempt-c140d477 | reused | cache_verify | 0 | dcfea4a7d5a3e6ef |

Recovery rechecked the missing red, restored it and reused nir. All seven attempt
rows remain. Red's restored hash reproduced artifact `59c9437e300a3549f75913bc0b4eeace6430e4be531fe988dded691a43ee71db`, so its artifact
identity and original creator were retained while the retry got a new attempt ID.
The artifact records historical byte identity; artifact_locations records current
availability. Before/after snapshots are embedded in the executed notebook.

## Constraints versus physical evidence

Composite foreign keys prevent cross-AOI result and creator references; unique
constraints preserve source revisions, requests and per-request byte identities.
Lifecycle/timestamp checks prevent impossible row states; valid JSON and byte
bounds are enforced. PRAGMA foreign_key_check returns no violations in all three
archives. These constraints cannot establish that files exist, hashes match,
calibration is preserved or pixels outside the AOI are nodata. Actual filesystem
and Rasterio checks establish those claims.

`transfer_vs_storage` aggregates attempts separately from artifacts before joining,
so multiple paths cannot multiply network-byte totals. Four main requests have
separate outputs for two AOIs; UNIQUE(asset_id) would wrongly forbid that.

The optional NDVI view explicitly chooses the main AOI and applies scale/offset
before arithmetic. Raw ratios range from about -0.2574 to 655; 32,435 of 43,061
unmasked values lie outside [-1, 1]. Negative calibrated samples and small positive
denominators explain how such ratios arise. Outliers are masked only in the
labelled display; raw results are retained and no scientific validity is inferred.
This is an unregistered inspection image without cloud screening.
Runtime state/, data/ and cases/ stay ignored by Git. Tables above abbreviate IDs
only for readability; full IDs are retained in SQL outputs and the JSON report.
