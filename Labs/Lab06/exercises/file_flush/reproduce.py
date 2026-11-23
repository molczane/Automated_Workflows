"""Run from the package root: python exercises/file_flush/reproduce.py"""
from publication import flush_output
from support import checked_flush, prepare_copy


if __name__ == "__main__":
    output = prepare_copy()
    print("Prepared a disposable copy of a real Sentinel-2 GeoTIFF.", flush=True)
    print("Enforcing the Windows writable-handle rule on this operating system.", flush=True)
    print("An OSError is expected until you fix publication.py.", flush=True)
    size = checked_flush(output, flush_output)
    print(f"Flush completed; all {size} original bytes were preserved.")
