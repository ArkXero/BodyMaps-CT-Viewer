from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from .storage import write_json


def _canonical_label(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").replace("-", " ").split())


def _mask_label_name(filename: str) -> str:
    name = Path(filename).name
    if name.endswith(".nii.gz"):
        name = name.removesuffix(".nii.gz")
    else:
        name = name.removesuffix(Path(name).suffix)
    return name.replace("_", " ")


def _safe_extract_member(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    destination: Path,
) -> Path:
    relative = Path(member.filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe archive member: {member.filename}")
    target = (destination / relative).resolve()
    if destination.resolve() not in target.parents:
        raise ValueError(f"Unsafe archive member: {member.filename}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as source, target.open("wb") as output:
        shutil.copyfileobj(source, output)
    return target


def _ground_truth_masks(bundle_path: Path) -> dict[str, np.ndarray]:
    if bundle_path.suffix.lower() != ".zip" or not zipfile.is_zipfile(bundle_path):
        return {}

    masks: dict[str, np.ndarray] = {}
    with tempfile.TemporaryDirectory(prefix="bodymaps-eval-") as temp:
        temp_dir = Path(temp)
        with zipfile.ZipFile(bundle_path) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir()
                and "__MACOSX" not in info.filename
                and "/segmentations/" in info.filename
                and info.filename.endswith(".nii.gz")
            ]
            for member in members:
                extracted = _safe_extract_member(archive, member, temp_dir)
                label = _canonical_label(_mask_label_name(member.filename))
                mask = np.asarray(nib.load(extracted).dataobj) > 0
                if mask.ndim == 3:
                    masks[label] = mask
    return masks


def _metric_row(
    label: dict[str, Any],
    prediction: np.ndarray,
    ground_truth: np.ndarray,
) -> dict[str, Any]:
    label_id = int(label["id"])
    predicted = prediction == label_id
    if predicted.shape != ground_truth.shape:
        raise ValueError(
            f"Prediction shape {predicted.shape} does not match ground truth shape "
            f"{ground_truth.shape} for {label['name']}."
        )

    true_positive = int(np.logical_and(predicted, ground_truth).sum())
    predicted_count = int(predicted.sum())
    ground_truth_count = int(ground_truth.sum())
    false_positive = predicted_count - true_positive
    false_negative = ground_truth_count - true_positive
    union = predicted_count + ground_truth_count - true_positive
    dice_denominator = predicted_count + ground_truth_count

    return {
        "id": label_id,
        "name": label["name"],
        "dice": round((2 * true_positive / dice_denominator) if dice_denominator else 1.0, 5),
        "iou": round((true_positive / union) if union else 1.0, 5),
        "true_positive_voxels": true_positive,
        "false_positive_voxels": false_positive,
        "false_negative_voxels": false_negative,
        "predicted_voxels": predicted_count,
        "ground_truth_voxels": ground_truth_count,
    }


def evaluate_prediction(
    input_path: Path,
    output_dir: Path,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    ground_truth = _ground_truth_masks(input_path)
    if not ground_truth:
        return None

    mask_path = output_dir / "mask.npy"
    labels_path = output_dir / "labels.json"
    if not mask_path.is_file() or not labels_path.is_file():
        return None

    prediction = np.load(mask_path, mmap_mode="r", allow_pickle=False)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    matched_ground_truth: set[str] = set()
    unmatched_predictions: list[str] = []

    for label in labels:
        name = _canonical_label(str(label.get("name", "")))
        truth = ground_truth.get(name)
        if truth is None:
            unmatched_predictions.append(str(label.get("name", "")))
            continue
        rows.append(_metric_row(label, prediction, truth))
        matched_ground_truth.add(name)

    if not rows:
        return {
            "mode": "segmentation_ground_truth_comparison",
            "summary": "No prediction labels matched provided ground-truth mask names.",
            "ground_truth_source": input_path.name,
            "matched_labels": 0,
            "predicted_labels": len(labels),
            "ground_truth_labels": len(ground_truth),
            "mean_dice": None,
            "mean_iou": None,
            "labels": [],
            "missing_ground_truth_labels": sorted(set(ground_truth) - matched_ground_truth),
            "unmatched_prediction_labels": sorted(unmatched_predictions),
        }

    mean_dice = round(sum(row["dice"] for row in rows) / len(rows), 5)
    mean_iou = round(sum(row["iou"] for row in rows) / len(rows), 5)
    evaluation = {
        "mode": "segmentation_ground_truth_comparison",
        "summary": f"Compared {len(rows)} predicted structures against provided masks.",
        "ground_truth_source": input_path.name,
        "metric_definitions": {
            "dice": "2 * overlap / (prediction voxels + ground-truth voxels)",
            "iou": "overlap / union",
        },
        "matched_labels": len(rows),
        "predicted_labels": len(labels),
        "ground_truth_labels": len(ground_truth),
        "mean_dice": mean_dice,
        "mean_iou": mean_iou,
        "labels": rows,
        "missing_ground_truth_labels": sorted(set(ground_truth) - matched_ground_truth),
        "unmatched_prediction_labels": sorted(unmatched_predictions),
    }
    if result.get("mode") == "precomputed_bodymaps_bundle":
        evaluation["warning"] = (
            "Bundle adapter uses provided masks as output; these scores validate evaluation "
            "plumbing, not model quality."
        )

    write_json(output_dir / "evaluation.json", evaluation)
    return evaluation
