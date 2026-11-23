# Release validation

Validated 15 November 2026 on Linux with Python 3.12, NumPy 2.3.5 and Rasterio 1.5.2. The supplied dependency ranges also target the existing Python 3.12 course environment. Windows-specific locking and Gaia execution were not run here.

The eleven automated behavior checks passed. They cover checksums and native metadata for thirty real subset rasters; scale/offset and denominator edge cases; six complete MNDWI requests and eighteen outputs; reuse without new attempts; missing output recovery; scientific assessment history; scientific identity versus runtime paths; abrupt child-process interruption and explicit reconciliation; missing inputs without attempts; NDVI agreement with the earlier arithmetic on all six real red/NIR pairs; independent MNDWI arithmetic for real pixels; an all-masked real scene; and a separately loaded scientific extension with a source revision.

The count is eleven test functions; several exercise more than one related behavior. Tiny numeric arrays are used only for mathematical edge cases. All scientific processing maps use the delivered real observations.

An actual completed Lab 05 reference catalogue was migrated. Every row in every original table was compared with the source and remained identical. Foreign key and database integrity checks passed.

The live search route returned the pinned Sentinel-2 Collection 1 scene. A different small AOI was then acquired from actual bounded HTTP range reads, registered, planned, processed and assessed successfully. It transferred 3,670,019 bytes for green/SWIR/SCL. Live service availability can change independently of this captured-data exercise.

The default captured MNDWI run completed all six requests and wrote all declared roles. Repeating it started zero attempts. Four results passed the default scientific policy and two were rejected for insufficient useful coverage. An independent NDMI reference extension used the same runner.

The HTML/JSON report was generated and its embedded scientific charts were visually inspected. Browser rendering could not be verified in this execution environment. The report is a saved local artifact with embedded PNGs and no external assets.

To repeat the supplied behavior checks:

```bash
python -m pytest tests -q
```

An unrelated preinstalled pytest plugin emitted a deprecation warning during the validation run; the processing checks passed. Tests do not contact the live catalogue or require another lab archive.

## Windows correction, 16 November 2026

The original read-only file-flush failure was reproduced with the Windows writable-handle requirement enforced during actual raster processing. The corrected code passed all thirteen checks with NumPy 1.26.4 and Rasterio 1.4.4, including the new file-handle and CLI error-reporting regressions. The incident is described in `docs/FILE_FLUSH_INCIDENT.md`. Native Windows execution still requires confirmation on that platform.

## Clean Git package and debugging clinic, 16 November 2026

All thirteen processing checks passed again for this package. Its shared Python and SQL core is byte for byte identical to the corrected class release. The optional notebook contains no saved cell outputs or execution counts.

The standalone clinic reproduced the expected `Bad file descriptor` error with the original mode on Linux under the supplied Windows requirement. The corrected mode passed both reproduction and verification, including a repeated flush with unchanged real raster bytes. A truncating mode and removal of the flush each failed verification. The distributed exercise file was restored to its deliberately faulty starting state after these checks.

A disposable Git repository staged 89 source, data and teaching files. A checkout with `core.autocrlf=true` preserved every tracked byte because of the supplied attributes, and `check-core` in that checkout reported an exact match. Ignore checks covered generated outputs, SQLite data, Python caches, installation metadata, notebook checkpoints, patch backups and environment credentials. The final archive contains the tracked files, with no Git history, work directory, installation metadata, instructor directory or caches.
