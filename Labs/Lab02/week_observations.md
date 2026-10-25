# Lab 02 observations

Status: **in progress**. Repaired code and day-one exercises are verified; the
seven-day experiment is not complete. All timestamps below are actual UTC run
journal values. `week_report.json` is the current snapshot, not a completed week.

| Run time (UTC) | Outcome | Search interval | Sightings | Newly discovered scenes | Newest acquisition | Observation |
|---|---|---|---|---|---|---|
| 2026-10-25T16:47:32.918946Z | succeeded | 2026-09-21T00:00:00Z → 2026-10-25T16:47:32.917116Z | 40 | 40 | 2026-10-25T09:46:46.101000Z | Initial live search; one newest suitable JPEG requested. |
| 2026-10-25T16:47:36.385439Z | succeeded | 2026-10-18T16:47:32.917116Z → 2026-10-25T16:47:36.384964Z | 8 | 0 | 2026-10-25T09:46:46.101000Z | Immediate rerun; overlap revisited existing scene identities. |
| 2026-10-25T16:47:38.122303Z | succeeded | 2026-09-25T16:47:36.384964Z → 2026-10-25T16:47:38.121854Z | 36 | 0 | 2026-10-25T09:46:46.101000Z | 30-day reconciliation; no new scene identities found. |

## Interpretation

The first run associated 40 unique scenes with this stream.
The immediate rerun revisited 8 records and added none.
The 30-day reconciliation revisited 36 records and added none.
All three commands completed successfully (exit 0). The newest acquisition was
2026-10-25T09:46:46.101000Z, about 7.01 hours old at report
time. New scene membership is distinct from a newly acquired observation.

The optional preview was for S2C_34UCA_20261025_0_L2A, 12,323
bytes, SHA-256 `82ff1da2ab18e92a93da500aeaceb56e131b1fff44942433db73986e3b2c8a6c`. Its whole-tile cloud cover was
99.7338%; the clearest catalogue item had
0.004261% cloud cover (S2B_34UDA_20261023_0_L2A). The newest preview
is selected by time, not by clarity. No scientific bands were transferred.

Reports from the Lab02 and Labs working directories selected the same database
and identical run histories. The intentional missing-config invocation returned
exit 1 with FileNotFoundError, separately from the successful live experiment.
All five supplied check groups pass on Python 3.12.14.

## Required follow-up

1. Next manual discovery: **2026-10-27T16:47:40.044439Z or later**. This creates a gap of at
   least 48 hours after today's last discovery, provided there are no intervening
   discovery invocations. Report commands alone do not add discovery runs.
2. Final manual discovery: **2026-11-01T16:47:32.918946Z or later**, seven days after the
   first run. Together with the preceding step this gives at least five runs.
3. Regenerate the report and update both observation tables from actual results.
   Verify at least four real invocations, a seven-day span, the immediate rerun
   and a consecutive discovery gap of at least 48 hours before marking complete.

From the repository root, using your Python 3.10+ environment:

```bash
python Labs/Lab02/sentinel_cli.py discover --config Labs/Lab02/config/krakow_week.json --preview
python Labs/Lab02/sentinel_cli.py report --config Labs/Lab02/config/krakow_week.json > Labs/Lab02/week_report.json
```

Keep the same region, initial_start, configuration and local state database.
Do not substitute fixture runs or explicit future --until timestamps for elapsed
time. Inspect state/events.log and the run history if a request fails; retain a
short relevant excerpt and retry. Never commit the state directory or previews.

## Questions to close after the week

- Did discovery after the gap resume from the last watermark minus seven days?
  Compare actual search_start/search_until values; this has not yet been observed
  across a multi-day gap. A covered interval does not prove provider completeness.
- How old was the newest acquisition at each report, and did new membership refer
  to older acquisitions? Acquisition time is distinct from publication time.
- Did each zero-new-scenes result have successful status and an advanced watermark,
  or did the request fail? A preview failure after complete discovery can preserve
  an advanced watermark while the overall command fails.
- Did the newest preview also have the lowest whole-tile cloud cover? Even a low
  tile-wide cloud fraction does not prove the local AOI is clear.
