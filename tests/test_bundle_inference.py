from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from bodymaps_demo.bundle_inference import run_bundle_inference
from bodymaps_demo.doctor import diagnose
from bodymaps_demo.evaluation import evaluate_prediction

from .test_app import settings_for


def test_bundle_inference_writes_structured_artifacts(
    tmp_path: Path, tiny_bodymaps_bundle: Path
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = run_bundle_inference(tiny_bodymaps_bundle, output_dir)

    assert result["volume"]["shape"] == [18, 20, 22]
    assert [label["name"] for label in result["labels"]] == ["kidney left", "liver"]
    assert np.load(output_dir / "volume.npy", allow_pickle=False).dtype == np.int16
    assert np.load(output_dir / "mask.npy", allow_pickle=False).max() == 2
    assert json.loads((output_dir / "result.json").read_text())["mode"] == (
        "precomputed_bodymaps_bundle"
    )


def test_evaluation_scores_predictions_against_ground_truth(
    tmp_path: Path, tiny_bodymaps_bundle: Path
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    result = run_bundle_inference(tiny_bodymaps_bundle, output_dir)

    evaluation = evaluate_prediction(tiny_bodymaps_bundle, output_dir, result)

    assert evaluation is not None
    assert evaluation["matched_labels"] == 2
    assert 0 < evaluation["mean_dice"] <= 1
    assert 0 < evaluation["mean_iou"] <= 1
    assert (output_dir / "evaluation.json").is_file()


def test_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../ct.nii.gz", b"unsafe")
        archive.writestr("../segmentations/liver.nii.gz", b"unsafe")

    with pytest.raises(ValueError, match="Unsafe archive member"):
        run_bundle_inference(bundle, tmp_path / "output")


def test_doctor_reports_bundle_mode_without_errors(
    tmp_path: Path, tiny_bodymaps_bundle: Path
) -> None:
    report = diagnose(settings_for(tmp_path, tiny_bodymaps_bundle))

    assert report["passed"] is True
    assert report["errors"] == 0
    adapter_check = next(item for item in report["checks"] if item["name"] == "inference adapter")
    assert adapter_check["level"] == "warning"
    assert "linked SuPreM prototype is not running" in adapter_check["message"]
