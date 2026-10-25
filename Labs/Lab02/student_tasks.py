"""Repair these three functions. The service and command parser are supplied."""
from datetime import datetime, timezone
from pathlib import Path
from lab01_service import utc_parse, utc_text

def resolve_paths(config, config_path):
    """Exercise 1: this works only when the terminal is in the expected folder.
    Make the configuration file's parent the anchor for all three paths.
    Preserve absolute paths. Do not create files here or change the working directory.
    """
    base = Path(config_path).resolve().parent
    paths = {}
    for key in ('database', 'preview_directory', 'log_file'):
        path = Path(config[key])
        paths[key] = path if path.is_absolute() else (base / path).resolve()
    return paths

def choose_until(explicit_until=None, clock=None):
    """Exercise 2: this copied demonstration end never discovers fresh scenes.
    Preserve an explicit --until (normalizing it to UTC); otherwise capture the
    current aware UTC clock once. clock is supplied only by the checks.
    Reject timestamps without a timezone instead of assuming local time.
    """
    if explicit_until is not None:
        return utc_text(utc_parse(explicit_until))
    instant = clock() if clock is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Use a timezone in every timestamp')
    return utc_text(instant)

def execute_job(job, logger):
    """Exercise 3: the terminal currently claims success after a failed job.
    On success return (0, the job result). On failure log the exception and return
    (1, a dictionary with status='failed' and an informative error string).
    Keep the exception handler, but report its actual outcome.
    """
    try:
        return 0, job()
    except Exception as exc:
        logger.exception('Job failed')
        return 1, {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
