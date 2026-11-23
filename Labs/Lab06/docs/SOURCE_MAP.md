# From earlier labs to one package

The earlier released archives remain unchanged. Version 1 supplies completed implementations of earlier repair exercises and consolidates their responsibilities. New masking and MNDWI behavior is explicit scientific development beyond the earlier NDVI job.

| Earlier responsibility | Version 1 location |
|---|---|
| Separate Lab 04/05 command scripts | `eo_processing/cli.py`, `__main__.py`, and installed entry point |
| `processing_store.py`, `batch_store.py`, fixture registration | `database.py` and supplied schema resources |
| Request fingerprint repairs and `batch_plan.py` | `planning.py` |
| NDVI arithmetic in repair functions | `products.NDVI` plus shared `normalized_difference` |
| NDVI-specific input checks and raster operations | `preparation.py` and runner output verification |
| Batch classification, adapter and serial coordinator | `runner.py` |
| Report building | `reporting.py` |
| Acquisition fixture scripts and native geometry helpers | `acquisition.py`, retaining the bounded range reader |
| Scientific suitability discussed in Lecture 5 | Independent, append-only assessments in `qc.py` |

Earlier features retained include expected membership before attempts, one writer per catalogue, persistent retry counts, explicit unresolved-attempt reconciliation, exact code/runtime request identity, current checksum/grid/provenance verification, separate artifacts and file locations, and preserved attempt history.

The old NDVI compatibility configuration deliberately uses a native 10 m grid and nodata-only preparation. It provides a numeric regression comparison with the recorded Lab 05 red/NIR data. It is not the preferred scientific masking policy for new vegetation analysis.

The generic runner is a new implementation of the shared contracts, rather than nested command wrappers around earlier lab directories. It publishes a set of declared outputs atomically and requires all of them for reuse. Course updates now change this shared package once, while personal science lives outside it.
