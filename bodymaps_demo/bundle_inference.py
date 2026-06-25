from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from .organ_stats import attach_organ_stats
from .storage import write_json

LABEL_COLORS = [
    "#56cfe1",
    "#80ffdb",
    "#ffca3a",
    "#ff6b6b",
    "#c77dff",
    "#90be6d",
    "#f9844a",
    "#4d96ff",
    "#f15bb5",
    "#b8f2e6",
    "#ffd166",
    "#8ecae6",
]


def _safe_extract_bundle(bundle_path: Path, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path) as archive:
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and "__MACOSX" not in info.filename
            and (
                info.filename.endswith("/ct.nii.gz")
                or "/segmentations/" in info.filename
                and info.filename.endswith(".nii.gz")
            )
        ]
        if not members:
            raise ValueError("Bundle contains no ct.nii.gz or segmentations/*.nii.gz files.")
        for member in members:
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe archive member: {member.filename}")
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError(f"Unsafe archive member: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return extracted


def _load_integer_volume(path: Path) -> tuple[np.ndarray, Any]:
    image = nib.load(path)
    volume = np.asarray(image.dataobj)
    if volume.ndim != 3:
        raise ValueError(f"Expected 3D NIfTI volume, got shape {volume.shape}.")
    if not np.isfinite(volume).all():
        raise ValueError(f"Volume contains non-finite values: {path.name}")
    return np.rint(volume).astype(np.int16), image


def run_bundle_inference(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if input_path.suffix.lower() != ".zip":
        raise ValueError(
            "Bundle adapter requires a .zip containing ct.nii.gz and segmentations/*.nii.gz."
        )

    source_dir = output_dir / "source"
    extracted = _safe_extract_bundle(input_path, source_dir)
    ct_candidates = [path for path in extracted if path.name == "ct.nii.gz"]
    mask_paths = sorted(
        path
        for path in extracted
        if "segmentations" in path.parts and path.name.endswith(".nii.gz")
    )
    if len(ct_candidates) != 1:
        raise ValueError(f"Expected exactly one ct.nii.gz, found {len(ct_candidates)}.")
    if not mask_paths:
        raise ValueError("Expected at least one segmentation mask in bundle.")

    volume, image = _load_integer_volume(ct_candidates[0])
    combined_mask = np.zeros(volume.shape, dtype=np.uint16)
    labels: list[dict[str, Any]] = []

    for label_id, mask_path in enumerate(mask_paths, start=1):
        mask_image = nib.load(mask_path)
        mask = np.asarray(mask_image.dataobj) > 0
        if mask.shape != volume.shape:
            raise ValueError(
                f"Mask {mask_path.name} shape {mask.shape} does not match CT shape {volume.shape}."
            )
        overlap = mask & (combined_mask != 0)
        combined_mask[mask & ~overlap] = label_id
        labels.append(
            {
                "id": label_id,
                "name": mask_path.name.removesuffix(".nii.gz").replace("_", " "),
                "source_file": str(mask_path.relative_to(output_dir)),
                "voxel_count": int(mask.sum()),
                "overlap_voxel_count": int(overlap.sum()),
                "color": LABEL_COLORS[(label_id - 1) % len(LABEL_COLORS)],
            }
        )

    np.save(output_dir / "volume.npy", volume, allow_pickle=False)
    np.save(output_dir / "mask.npy", combined_mask, allow_pickle=False)
    write_json(output_dir / "labels.json", labels)

    spacing = [round(float(value), 4) for value in image.header.get_zooms()[:3]]
    result = {
        "mode": "precomputed_bodymaps_bundle",
        "summary": (
            f"Loaded {len(labels)} provided BodyMaps segmentation masks for browser review."
        ),
        "disclaimer": (
            "Provided bundle contains precomputed masks. No model weights or prototype "
            "were supplied, so this adapter validates web workflow and visualization, "
            "not live AI model accuracy."
        ),
        "volume": {
            "shape": list(volume.shape),
            "spacing_mm": spacing,
            "dtype": str(volume.dtype),
            "minimum_hu": int(volume.min()),
            "maximum_hu": int(volume.max()),
        },
        "labels": labels,
        "viewer": {
            "volume_path": "volume.npy",
            "mask_path": "mask.npy",
            "labels_path": "labels.json",
        },
        "downloads": [
            {"name": "Structured result", "path": "output/result.json"},
            {"name": "Labels", "path": "output/labels.json"},
            {"name": "Combined mask", "path": "output/mask.npy"},
        ],
    }
    attach_organ_stats(output_dir, result)
    write_json(output_dir / "result.json", result)
    return result
