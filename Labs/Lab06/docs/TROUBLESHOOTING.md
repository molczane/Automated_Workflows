# Investigating a problem

Start with the error message, the request's recorded inputs/settings, and its processing history. Preserve the failed attempt. Fix the actual cause before retrying.

| Observation | Next useful check |
|---|---|
| Module or dependency missing | Run from the extracted release directory; install with `python -m pip install -e . --no-deps --no-build-isolation`; check the active interpreter and `environment.yml` |
| No registered input for a band | Match the product's required bands, scene ID and exact bbox with the registered bundle; list input IDs |
| Several input candidates | Supply exact artifact IDs through the job's `inputs` map, including `scl` |
| Core/runtime or product source changed | Preserve the earlier manifest; create a new one from the editable configuration |
| Outputs exist but request is incomplete | Check all declared output roles, their checksums, grid and provenance; primary image presence alone is insufficient |
| Succeeded attempt has rejected QC | Read the coverage/mask evidence and policy; execution succeeded, but this use may lack enough observations |
| A snow result contains no snow | Check whether class 11 was excluded by the default SCL policy |
| Implausible or extreme index values | Check calibration, band selection, denominator behavior and masks; the package records unusual values instead of clipping them away |
| AOI outside tile or pixel limit exceeded | Choose a covering item or smaller bbox; mosaicking and large scenes are outside Version 1 |
| Network acquisition fails | Inspect the specific HTTP/range or metadata failure; retain the incomplete bundle and retry into a new destination |
| Workspace already exists | Use its existing manifest with `run`, or choose a distinct workspace; do not repeat setup to reset history |

## Failed execution

Each attempt records `log_path`, `error_code`, `error_message` and the stage it reached. Logs are JSON lines in the workspace's `logs/` directory. A completed product's receipt is also inside its output directory. A software error is different from rejected scientific QC.

After investigating a failure, an explicit retry can be requested, within the persistent attempt budget:

```bash
python -m eo_processing run --manifest work/personal/batch.json --retry-failed --reason "Restored the verified input file after investigating the failure"
```

If fixing the error changes scientific code, masks, parameters or runtime, plan a new manifest instead. Changing a file's location while retaining the exact verified bytes does not itself change the scientific request.

## Unresolved execution

Do not decide a worker is dead from the age of a database row. Establish whether the old process stopped. Version 1 holds an OS writer lock throughout processing, and reconciliation must acquire that lock. This is a local serial design, not a distributed scheduler.

Use this controlled drill only in a new practice workspace:

```bash
python -m eo_processing demo --workspace work/recovery_practice
```

```bash
python -m eo_processing run --manifest work/recovery_practice/batch.json --simulate crash-before-publish
```

The child intentionally exits with status 87 after real rasters were written and validated, before publication. Inspect `status` and the catalogue. Confirm the command process ended, identify the running attempt, and use that exact ID:

```bash
python -m eo_processing status --manifest work/recovery_practice/batch.json --out work/recovery_practice/status.json
```

```bash
python -m eo_processing reconcile --manifest work/recovery_practice/batch.json --attempt REPLACE_WITH_THE_ACTUAL_ATTEMPT_ID --reason "Controlled command exited with status 87; its process ended"
```

```bash
python -m eo_processing run --manifest work/recovery_practice/batch.json
```

The earlier attempt becomes interrupted and remains in history. An unpublished partial directory remains for investigation. A new attempt gets its own directory. Files left by a failed publication are not accepted as completed output without the producing catalogue records.

The supplied tests exercise the abrupt exit in a subprocess. Do not run this simulation against your main project just to see what happens.
