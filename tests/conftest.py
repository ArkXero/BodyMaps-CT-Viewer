from __future__ import annotations

import zipfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest


@pytest.fixture
def tiny_bodymaps_bundle(tmp_path: Path) -> Path:
    source = tmp_path / "source" / "BDMAP_TEST"
    segmentations = source / "segmentations"
    segmentations.mkdir(parents=True)

    grid = np.indices((18, 20, 22))
    volume = (-900 + grid[0] * 30 + grid[1] * 18 + grid[2] * 12).astype(np.int16)
    liver = (grid[0] - 9) ** 2 + (grid[1] - 10) ** 2 + (grid[2] - 11) ** 2 < 36
    kidney = (grid[0] - 5) ** 2 + (grid[1] - 8) ** 2 + (grid[2] - 13) ** 2 < 12

    affine = np.diag([1.25, 1.25, 2.5, 1])
    nib.save(nib.Nifti1Image(volume, affine), source / "ct.nii.gz")
    nib.save(nib.Nifti1Image(liver.astype(np.uint8), affine), segmentations / "liver.nii.gz")
    nib.save(
        nib.Nifti1Image(kidney.astype(np.uint8), affine),
        segmentations / "kidney_left.nii.gz",
    )

    bundle = tmp_path / "BDMAP_TEST.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(tmp_path / "source"))
    return bundle
