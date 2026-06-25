from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .storage import write_json

PLANE_AXES = {"sagittal": 0, "coronal": 1, "axial": 2}


def _spacing_mm(result: dict[str, Any] | None) -> list[float]:
    spacing = (result or {}).get("volume", {}).get("spacing_mm", [1, 1, 1])
    if not isinstance(spacing, list | tuple) or len(spacing) != 3:
        return [1.0, 1.0, 1.0]
    try:
        return [float(value) for value in spacing]
    except (TypeError, ValueError):
        return [1.0, 1.0, 1.0]


def _slice_counts(mask: np.ndarray, axis: int) -> np.ndarray:
    other_axes = tuple(index for index in range(mask.ndim) if index != axis)
    return np.count_nonzero(mask, axis=other_axes)


def _best_slices(mask: np.ndarray) -> tuple[dict[str, int | None], str | None]:
    best_slice_index: dict[str, int | None] = {}
    best_plane: str | None = None
    best_count = -1

    for plane, axis in PLANE_AXES.items():
        counts = _slice_counts(mask, axis)
        if counts.size == 0 or int(counts.max()) == 0:
            best_slice_index[plane] = None
            continue
        slice_index = int(counts.argmax())
        count = int(counts[slice_index])
        best_slice_index[plane] = slice_index
        if count > best_count:
            best_plane = plane
            best_count = count

    return best_slice_index, best_plane


def compute_organ_stats(output_dir: Path, result: dict[str, Any] | None = None) -> dict[str, Any]:
    volume_path = output_dir / "volume.npy"
    mask_path = output_dir / "mask.npy"
    labels_path = output_dir / "labels.json"
    if not volume_path.is_file():
        raise FileNotFoundError("Viewer volume missing: output/volume.npy")
    if not mask_path.is_file():
        raise FileNotFoundError("Viewer mask missing: output/mask.npy")
    if not labels_path.is_file():
        raise FileNotFoundError("Viewer labels missing: output/labels.json")

    volume = np.load(volume_path, mmap_mode="r", allow_pickle=False)
    mask = np.load(mask_path, mmap_mode="r", allow_pickle=False)
    if volume.shape != mask.shape:
        raise ValueError(f"Volume shape {volume.shape} does not match mask shape {mask.shape}.")

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    spacing = _spacing_mm(result)
    voxel_volume_cm3 = float(np.prod(spacing)) / 1000
    rows: list[dict[str, Any]] = []

    for label in labels:
        label_id = int(label["id"])
        selected = mask == label_id
        coords = np.argwhere(selected)
        voxel_count = int(coords.shape[0])
        best_slice_index, best_plane = _best_slices(selected)

        if voxel_count:
            centroid = [
                int(round(float(coords[:, axis].mean()))) for axis in range(coords.shape[1])
            ]
            edge_touch = any(
                bool((coords[:, axis] == 0).any())
                or bool((coords[:, axis] == volume.shape[axis] - 1).any())
                for axis in range(coords.shape[1])
            )
            mean_hu = round(float(volume[selected].mean()), 3)
        else:
            centroid = None
            edge_touch = False
            mean_hu = None

        rows.append(
            {
                "id": label_id,
                "name": str(label.get("name", f"Label {label_id}")),
                "voxel_count": voxel_count,
                "volume_cm3": round(voxel_count * voxel_volume_cm3, 5),
                "mean_hu": mean_hu,
                "edge_touch_warning": edge_touch,
                "centroid_index": centroid,
                "best_slice_index": best_slice_index,
                "best_plane": best_plane,
            }
        )

    return {
        "source": "output/volume.npy + output/mask.npy",
        "spacing_mm": spacing,
        "voxel_volume_cm3": round(voxel_volume_cm3, 8),
        "labels": rows,
    }


def attach_organ_stats(output_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    stats = compute_organ_stats(output_dir, result)
    write_json(output_dir / "organ_stats.json", stats)
    result["organ_stats"] = stats

    downloads = result.setdefault("downloads", [])
    if isinstance(downloads, list) and not any(
        item.get("path") == "output/organ_stats.json"
        for item in downloads
        if isinstance(item, dict)
    ):
        downloads.append({"name": "Organ stats", "path": "output/organ_stats.json"})
    return stats
