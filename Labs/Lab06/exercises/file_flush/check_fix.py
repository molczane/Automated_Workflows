"""Run from the package root: python exercises/file_flush/check_fix.py"""
from publication import flush_output
from support import checked_flush, prepare_copy


if __name__ == "__main__":
    output = prepare_copy()
    size = checked_flush(output, flush_output)
    checked_flush(output, flush_output)
    print(f"PASS: two successful writable-handle flushes; all {size} bytes are unchanged.")
    print("Only the exercise copy was used. The shared processor and catalogue were not changed.")
