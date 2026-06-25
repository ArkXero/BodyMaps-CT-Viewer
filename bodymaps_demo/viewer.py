from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image


def plane_depth(shape: tuple[int, ...], plane: str) -> int:
    axis = {"sagittal": 0, "coronal": 1, "axial": 2}.get(plane)
    if axis is None:
        raise ValueError("Plane must be axial, coronal, or sagittal.")
    return shape[axis]


def _slice(volume: np.ndarray, plane: str, index: int) -> np.ndarray:
    if plane == "axial":
        value = volume[:, :, index]
    elif plane == "coronal":
        value = volume[:, index, :]
    elif plane == "sagittal":
        value = volume[index, :, :]
    else:
        raise ValueError("Plane must be axial, coronal, or sagittal.")
    return np.rot90(value)


def render_slice(
    output_dir: Path,
    plane: str,
    index: int,
    overlay: bool,
    window_center: float = 40,
    window_width: float = 400,
    overlay_opacity: float = 0.58,
    hidden_labels: set[int] | None = None,
) -> bytes:
    volume_path = output_dir / "volume.npy"
    mask_path = output_dir / "mask.npy"
    labels_path = output_dir / "labels.json"
    if not volume_path.is_file():
        raise FileNotFoundError("Viewer volume missing: output/volume.npy")

    volume = np.load(volume_path, mmap_mode="r", allow_pickle=False)
    depth = plane_depth(volume.shape, plane)
    if index < 0 or index >= depth:
        raise IndexError(f"Slice index {index} outside 0..{depth - 1}.")
    if window_width <= 0:
        raise ValueError("window_width must be greater than 0.")
    source = _slice(volume, plane, index).astype(np.float32)
    low = window_center - window_width / 2
    gray = np.clip((source - low) / window_width, 0, 1)
    gray = np.rint(gray * 255).astype(np.uint8)
    rgb = np.repeat(gray[:, :, None], 3, axis=2).astype(np.float32)

    if overlay and mask_path.is_file() and labels_path.is_file():
        opacity = float(np.clip(overlay_opacity, 0, 1))
        hidden = hidden_labels or set()
        mask = np.load(mask_path, mmap_mode="r", allow_pickle=False)
        mask_slice = _slice(mask, plane, index)
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        for label in labels:
            label_id = int(label["id"])
            if label_id in hidden:
                continue
            selected = mask_slice == label_id
            if not selected.any():
                continue
            color = label["color"].lstrip("#")
            color_rgb = np.array(
                [int(color[offset : offset + 2], 16) for offset in (0, 2, 4)],
                dtype=np.float32,
            )
            rgb[selected] = rgb[selected] * (1 - opacity) + color_rgb * opacity

    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=1)
    return buffer.getvalue()
