from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bodymaps_demo.app import create_app
from bodymaps_demo.config import REPO_ROOT, Settings


def settings_for(tmp_path: Path, sample_path: Path, **overrides) -> Settings:
    values = {
        "repo_root": REPO_ROOT,
        "artifacts_dir": tmp_path / "artifacts",
        "static_dir": REPO_ROOT / "bodymaps_demo" / "static",
        "adapter": "bundle",
        "max_upload_bytes": 5 * 1024 * 1024,
        "inference_timeout_seconds": 60,
        "sample_path": sample_path,
        "inference_command": None,
        "prototype_path": None,
        "weights_path": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_sample_job_runs_and_renders_slice(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle))

    with TestClient(app) as client:
        response = client.post("/api/jobs/sample")
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["execution"]["exit_code"] == 0
        assert job["result"]["mode"] == "precomputed_bodymaps_bundle"
        assert len(job["result"]["labels"]) == 2
        assert job["result"]["evaluation"]["matched_labels"] == 2
        assert 0 < job["result"]["evaluation"]["mean_dice"] <= 1
        stats = job["result"]["organ_stats"]
        kidney = next(row for row in stats["labels"] if row["name"] == "kidney left")
        assert kidney["voxel_count"] > 0
        assert kidney["volume_cm3"] == pytest.approx(
            kidney["voxel_count"] * 1.25 * 1.25 * 2.5 / 1000,
            rel=1e-5,
        )
        assert isinstance(kidney["mean_hu"], float)
        assert set(kidney["best_slice_index"]) == {"axial", "coronal", "sagittal"}

        image = client.get(
            f"/api/jobs/{job_id}/slice",
            params={"plane": "axial", "index": 10, "overlay": "true"},
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG")

        trace = client.get(f"/api/jobs/{job_id}/artifacts/logs/execution.json")
        assert trace.status_code == 200
        assert b'"exit_code": 0' in trace.content
        evaluation = client.get(f"/api/jobs/{job_id}/artifacts/output/evaluation.json")
        assert evaluation.status_code == 200
        assert b'"mean_dice"' in evaluation.content
        organ_stats = client.get(f"/api/jobs/{job_id}/artifacts/output/organ_stats.json")
        assert organ_stats.status_code == 200
        assert b'"mean_hu"' in organ_stats.content


def test_slice_viewer_controls_affect_render(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle))

    with TestClient(app) as client:
        response = client.post("/api/jobs/sample")
        job_id = response.json()["job_id"]

        default = client.get(
            f"/api/jobs/{job_id}/slice",
            params={"plane": "axial", "index": 10, "overlay": "true"},
        )
        windowed = client.get(
            f"/api/jobs/{job_id}/slice",
            params={
                "plane": "axial",
                "index": 10,
                "overlay": "true",
                "window_center": -500,
                "window_width": 80,
            },
        )
        no_overlay = client.get(
            f"/api/jobs/{job_id}/slice",
            params={"plane": "axial", "index": 10, "overlay": "false"},
        )
        transparent_overlay = client.get(
            f"/api/jobs/{job_id}/slice",
            params={
                "plane": "axial",
                "index": 10,
                "overlay": "true",
                "overlay_opacity": 0,
            },
        )
        hidden_overlay = client.get(
            f"/api/jobs/{job_id}/slice",
            params={
                "plane": "axial",
                "index": 10,
                "overlay": "true",
                "hidden_labels": "1,2",
            },
        )
        invalid_hidden = client.get(
            f"/api/jobs/{job_id}/slice",
            params={"plane": "axial", "index": 10, "hidden_labels": "1,bad"},
        )

    assert default.status_code == 200
    assert default.content != windowed.content
    assert transparent_overlay.content == no_overlay.content
    assert hidden_overlay.content == no_overlay.content
    assert invalid_hidden.status_code == 422


def test_upload_rejects_unsupported_format(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle))

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("notes.txt", b"not a scan", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported format. Upload .zip, .nii, or .nii.gz."


def test_upload_limit_is_enforced(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle, max_upload_bytes=8))

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("scan.nii", b"0123456789", "application/octet-stream")},
        )

    assert response.status_code == 413
    assert list((tmp_path / "artifacts").glob("*")) == []


def test_bundle_adapter_rejects_invalid_zip(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle))

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("scan.zip", b"not a zip", "application/zip")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded .zip is not a valid ZIP archive."
    assert list((tmp_path / "artifacts").glob("*")) == []


def test_bundle_adapter_rejects_single_nifti(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(settings_for(tmp_path, tiny_bodymaps_bundle))

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("scan.nii.gz", b"nifti-placeholder", "application/gzip")},
        )

    assert response.status_code == 422
    assert "Bundle adapter requires a .zip" in response.json()["detail"]
    assert list((tmp_path / "artifacts").glob("*")) == []


def test_external_adapter_failure_is_persisted(tmp_path: Path, tiny_bodymaps_bundle: Path) -> None:
    app = create_app(
        settings_for(
            tmp_path,
            tiny_bodymaps_bundle,
            adapter="external",
            inference_command=(
                'python -c \'import sys; print("model crash", file=sys.stderr); '
                "sys.exit(7)' {input} {output_dir}"
            ),
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("scan.nii", b"valid-enough-for-external-adapter")},
        )
        job = client.get(f"/api/jobs/{response.json()['job_id']}").json()

    assert job["status"] == "failed"
    assert job["execution"]["exit_code"] == 7
    assert "model crash" in job["error"]
