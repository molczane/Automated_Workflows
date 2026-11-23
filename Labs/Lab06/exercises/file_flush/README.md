# A real bug: the calculation finished, but the attempt failed

Allow 10–15 minutes. You need only Python's standard library for this exercise. Run the commands from the package root, beside `pyproject.toml`.

During preparation of this lab, the same processing package worked on Linux but failed on Windows. Both the supplied MNDWI requests and the instructor's NDMI example failed. Reinstalling the package did not solve it. The useful evidence was the saved traceback:

```text
File "eo_processing/runner.py", in execute
    os.fsync(stream.fileno())
OSError: [Errno 9] Bad file descriptor
```

The real runner had already calculated the product, written a temporary GeoTIFF, closed the Rasterio writer and validated the raster. It then reopened that file to flush it before publication. That final step used a handle opened for reading only. The attempt failed before the output was published or recorded as a successful product.

The shared runner in this package already includes the correction. You will repair a small copy of the original faulty function in `publication.py`. The harness copies a real supplied Sentinel-2 raster into `work/file_flush/` and enforces the relevant Windows rule on Windows, Linux and macOS. It simulates that specific requirement; it does not emulate the whole Windows filesystem. Each run recreates its own disposable sample. Your main demo outputs and catalogue are untouched.

## 1. Read the failure

```bash
python exercises/file_flush/reproduce.py
```

The initial command should fail with `OSError: [Errno 9] Bad file descriptor`. Read the traceback from the bottom upward and find the line in `publication.py` that called `os.fsync`. The last frame is in the supplied harness because it is enforcing the Windows requirement.

Explain why the existence of a `.tif` file was insufficient evidence of a successful processing attempt. Would changing the MNDWI equation address this error?

## 2. Explain the file mode and apply the correction

Open `exercises/file_flush/publication.py`. The function deliberately contains the original `"rb"` mode. Find the appropriate mode in the [Python open documentation](https://docs.python.org/3.11/library/functions.html#open): you need an existing binary file, permission to write, and preservation of its existing contents. Change just the mode string.

Before running it again, explain what `r`, `b` and `+` mean. Explain why a mode starting with `w` would be dangerous here, even if the flush stopped raising an exception.

You do not need to change `support.py`, install a package, or remove the flush. The harness is supplied so you can concentrate on the diagnosis and correction.

## 3. Verify the correction

```bash
python exercises/file_flush/reproduce.py
```

```bash
python exercises/file_flush/check_fix.py
```

The check requires a successful flush through a writable handle, unchanged file contents and a successful repeat. Removing `fsync`, hiding the exception, or truncating the file does not pass. Compare your corrected function with the file-flush block in the shared `eo_processing/runner.py`.

```bash
python -m eo_processing check-core
```

The shared core should still match the class release. Only your exercise file changed. Your source diff should show a small correction and you should be able to explain its effect.

## 4. Connect this to the real pipeline

Discuss these points in two or three sentences, or add them to the optional debugging section in `submission/report.md`:

1. Why did testing only on Linux miss this failure, and what requirement does the supplied regression check add?
2. In the original incident, correcting `runner.py` changed the processing code hash. Why did that require a new frozen manifest rather than editing the old manifest or deleting failed attempts?
3. Why does the exercise correction require no new processing manifest? Which file did you actually change?

The real incident and correction are recorded in [docs/FILE_FLUSH_INCIDENT.md](../../docs/FILE_FLUSH_INCIDENT.md). This exercise is a short debugging clinic; it adds no extra marks or scientific product requirement.
