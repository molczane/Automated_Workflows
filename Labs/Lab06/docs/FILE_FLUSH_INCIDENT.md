# File flush incident · 16 November 2026

The original release calculated and validated temporary GeoTIFFs, then failed during the flush before publication on Windows. The reported traceback ended in `os.fsync(stream.fileno())` with `OSError: [Errno 9] Bad file descriptor`.

The installed code matched the classroom release. All six MNDWI requests and the NDMI reference failed in the same shared step. This was a compatibility bug in the supplied runner.

## Cause and correction

The original runner reopened each completed output with `"rb"`, which provided a descriptor for reading only. Windows requires write access for the file-buffer flush. Python exposes `os.fsync` through the underlying operating system; the descriptor requirements must be respected.

```python
# Original
with path.open("rb") as stream:
    os.fsync(stream.fileno())

# Corrected
with path.open("r+b") as stream:
    os.fsync(stream.fileno())
```

`"r+b"` opens an existing binary file for reading and writing without truncating it. `"w+b"` would truncate the existing file. Removing the flush would also remove part of the intended publication procedure.

The correction is already included in this package. The `run` summary also exposes the latest attempt's stage, exception and log path, so a future failure is easier to investigate. The shared-code checksum record includes these corrections. This clean package needs no patch installer.

## Recovery and reproducibility

For the actual incident, changing the runner changed the processing environment recorded in each request. New manifests were frozen from the existing batch configurations. The failed attempts and their logs were retained in the catalogue; the corrected requests created new attempts and outputs. Repeating the corrected requests reused their verified outputs.

The separate [exercise](../exercises/file_flush/README.md) changes only an extracted function. It does not change the installed core, so completing that exercise needs no new processing manifest.

The regression check in `tests/test_windows_publication.py` enforces the writable-handle rule while processing real rasters. It would reject the original code on Linux as well. This is evidence about that requirement, not a substitute for testing the whole package on native Windows.

## References

- [Microsoft: FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers) specifies write access for the handle.
- [Python: os.fsync](https://docs.python.org/3.11/library/os.html#os.fsync) describes the flush and its platform implementations.
- [Python: open](https://docs.python.org/3.11/library/functions.html#open) defines the file modes and truncation behavior.
