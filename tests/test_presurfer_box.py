"""Regression tests for workflow paths and container execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from presurfer import spm_workflows as presurfer_box


def test_nii_stem_rejects_non_nifti(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Expected a .nii"):
        presurfer_box.nii_stem(tmp_path / "scan.txt")


def test_utc_run_directory_adds_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, timezone: object = None) -> FixedDatetime:
            return cls(2026, 9, 8, 12, 34, 56, tzinfo=UTC)

    monkeypatch.setattr(presurfer_box, "datetime", FixedDatetime)
    first = presurfer_box.utc_run_directory(tmp_path)
    second = presurfer_box.utc_run_directory(tmp_path)
    temporary = presurfer_box.utc_run_directory(tmp_path, temporary=True)
    assert first.name == "260908T12:34:56_presurfer"
    assert second.name == "260908T12:34:56_presurfer-2"
    assert temporary.name == "tmp_260908T12:34:56_presurfer"


def test_run_spm_batch_captures_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = tmp_path / "job.m"
    job.touch()
    log = tmp_path / "spm.log"
    monkeypatch.setattr(presurfer_box, "container_command", lambda *_: ["spm"])
    monkeypatch.setattr(
        presurfer_box.subprocess,
        "run",
        lambda *args, **kwargs: presurfer_box.subprocess.CompletedProcess(
            args[0], 0, "normal output", "normal error"
        ),
    )
    presurfer_box.run_spm_batch(tmp_path, job, "image", "docker", log)
    assert "normal output" in log.read_text()
    assert "normal error" in log.read_text()


def test_run_spm_batch_failure_points_to_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = tmp_path / "job.m"
    job.touch()
    log = tmp_path / "spm.log"
    monkeypatch.setattr(presurfer_box, "container_command", lambda *_: ["spm"])
    monkeypatch.setattr(
        presurfer_box.subprocess,
        "run",
        lambda *args, **kwargs: presurfer_box.subprocess.CompletedProcess(
            args[0], 7, "", "failure"
        ),
    )
    with pytest.raises(RuntimeError, match="singularity exit status 7"):
        presurfer_box.run_spm_batch(tmp_path, job, "image", "singularity", log)
    assert "failure" in log.read_text()
