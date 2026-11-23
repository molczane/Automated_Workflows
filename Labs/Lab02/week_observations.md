# Lab 02 observations

Status: **four successful runs recorded across two dates**. This includes the
immediate rerun and a gap of more than 48 hours. Only three runs fell within
the original seven-day window, so the weekly cadence requirement remains open.
All timestamps below come from the UTC run journal.

| Run time (UTC) | Outcome | Search interval | Sightings | Newly discovered scenes | Newest acquisition | Observation |
|---|---|---|---|---|---|---|
| 2026-10-25T16:47:32.918946Z | succeeded | 2026-09-21T00:00:00Z → 2026-10-25T16:47:32.917116Z | 40 | 40 | 2026-10-25T09:46:46.101000Z | Initial live search; one newest suitable JPEG requested. |
| 2026-10-25T16:47:36.385439Z | succeeded | 2026-10-18T16:47:32.917116Z → 2026-10-25T16:47:36.384964Z | 8 | 0 | 2026-10-25T09:46:46.101000Z | Immediate rerun; overlap revisited existing scene identities. |
| 2026-10-25T16:47:38.122303Z | succeeded | 2026-09-25T16:47:36.384964Z → 2026-10-25T16:47:38.121854Z | 36 | 0 | 2026-10-25T09:46:46.101000Z | 30-day reconciliation; no new scene identities found. |
| 2026-11-23T09:32:33.016449Z | succeeded | 2026-10-18T16:47:38.121854Z → 2026-11-23T09:32:33.013684Z | 38 | 30 | 2026-11-22T09:56:46.924000Z | Resumed from the saved watermark minus seven days after a 28-day gap. |

## Interpretation

The first run associated 40 unique scenes with this stream.
The immediate rerun revisited 8 records and added none.
The 30-day reconciliation revisited 36 records and added none.
The newest acquisition at the 25 October report was 7.01 hours old.
The 23 November run found 30 new scenes and revisited 8 already catalogued
scenes, bringing the stream to 70 unique scenes. The new entries were acquired
between 27 October and 22 November. The newest was 23.61 hours old at the updated
report time. A scene can be newly catalogued well after its acquisition.

The fourth run started at the previous watermark minus seven days and advanced
the watermark to its search end. Its window covered the gap between runs.
That confirms resumption and overlap. Provider completeness was not measured.
The two zero-new-scene runs succeeded and advanced their watermarks.

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

Use the existing configuration and database to record at least four manual
discoveries within a single seven-day window. Include an immediate rerun and
a gap of at least 48 hours. Regenerate the report and update the observation
table with the recorded results.

From the repository root, using your Python 3.10+ environment:

```bash
python Labs/Lab02/sentinel_cli.py discover --config Labs/Lab02/config/krakow_week.json --preview
python Labs/Lab02/sentinel_cli.py report --config Labs/Lab02/config/krakow_week.json > Labs/Lab02/week_report.json
```

Keep the same region, initial_start, configuration and local state database.
Do not substitute fixture runs or explicit future --until timestamps for elapsed
time. Inspect state/events.log and the run history if a request fails; retain a
short relevant excerpt and retry. Never commit the state directory or previews.

When interpreting later results, compare acquisition age and watermark movement.
Acquisition time differs from publication time. A preview failure can leave an
advanced discovery watermark even when the overall command fails. Whole-tile
cloud cover does not establish whether the area of interest is clear.
