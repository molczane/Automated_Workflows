"""Regression checks for writable file flushing and visible application errors."""
import errno
import json
from pathlib import Path

import pytest

from eo_processing.cli import demo, main
from eo_processing.common import read_json, write_json
from eo_processing.planning import freeze
from eo_processing import runner


@pytest.fixture
def single_request(tmp_path):
    root = tmp_path / "workspace"
    demo(root)
    config = read_json(root / "batch_config.json")
    config["jobs"] = config["jobs"][:1]
    write_json(root / "one_config.json", config)
    freeze(root / "one_config.json", root / "one_batch.json")
    return root / "one_batch.json"


def test_flush_uses_writable_file_handles(single_request, monkeypatch):
    """Apply Windows' writable-handle requirement while processing real data."""
    original_open = Path.open
    original_fsync = runner.os.fsync
    open_files = {}
    flushed = []

    def tracked_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.suffix == ".tif":
            open_files[stream.fileno()] = stream
        return stream

    def windows_fsync(fd):
        stream = open_files[fd]
        if not stream.writable():
            raise OSError(errno.EBADF, "Bad file descriptor")
        flushed.append(stream.name)
        return original_fsync(fd)

    monkeypatch.setattr(Path, "open", tracked_open)
    monkeypatch.setattr(runner.os, "fsync", windows_fsync)
    result = runner.run(single_request)
    assert result["complete"], result["members"][0]["attempts"]
    assert len(flushed) == 3
    assert {Path(name).name for name in flushed} == {"index.tif", "water.tif", "valid_mask.tif"}


def test_failed_cli_exposes_exception_and_log(single_request, monkeypatch, capsys):
    def failed_flush(fd):
        raise OSError(errno.EBADF, "Bad file descriptor")

    monkeypatch.setattr(runner.os, "fsync", failed_flush)
    with pytest.raises(SystemExit) as exc:
        main(["run", "--manifest", str(single_request)])
    assert exc.value.code == 2
    output = json.loads(capsys.readouterr().out)
    attempt = output["members"][0]["last_attempt"]
    assert attempt["error_code"] == "OSError"
    assert "Bad file descriptor" in attempt["error_message"]
    assert Path(attempt["log_path"]).is_file()
