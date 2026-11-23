"""Extract of the original publication bug. Fix this exercise file only."""
import os


def flush_output(path):
    """Flush an existing output before the runner publishes it."""
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
