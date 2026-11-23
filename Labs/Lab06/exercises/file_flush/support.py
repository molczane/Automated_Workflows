"""Supplied exercise harness. No changes are needed in this file.

The wrapper enforces the Windows writable-handle requirement on every OS.
It is a controlled reproduction of that one requirement, not Windows emulation.
"""
import errno
import os
from pathlib import Path
import shutil
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "eo_processing" / "data" / "fixtures" / "S2C_T34UDA_20250605T095638_L2A-river-green.tif"
OUTPUT = ROOT / "work" / "file_flush" / "copied_output.tif"


def prepare_copy():
    """Recreate only the exercise's disposable copy of a real observation."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, OUTPUT)
    return OUTPUT


def checked_flush(path, flush_function):
    """Require a writable handle and preserve the entire input byte sequence."""
    before = path.read_bytes()
    native_open = Path.open
    native_fsync = os.fsync
    streams = {}
    flushed = []

    def tracked_open(target, *args, **kwargs):
        stream = native_open(target, *args, **kwargs)
        if target == path:
            streams[stream.fileno()] = stream
        return stream

    def windows_fsync(descriptor):
        stream = streams.get(descriptor)
        if stream is None or stream.closed:
            raise OSError(errno.EBADF, "Bad file descriptor")
        if not stream.writable():
            raise OSError(errno.EBADF, "Bad file descriptor")
        native_fsync(descriptor)
        flushed.append(descriptor)

    with patch.object(Path, "open", tracked_open), patch.object(os, "fsync", windows_fsync):
        flush_function(path)

    if len(flushed) != 1:
        raise AssertionError("The fix must perform one successful fsync; removing it is not a fix.")
    if path.read_bytes() != before:
        raise AssertionError("The file contents changed. Choose a mode that preserves existing bytes.")
    return len(before)
