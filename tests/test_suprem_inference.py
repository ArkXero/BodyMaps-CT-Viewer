from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from bodymaps_demo.suprem_inference import prepare_suprem_input


def test_prepare_suprem_input_normalizes_bodymaps_bundle(
    tmp_path: Path, tiny_bodymaps_bundle: Path
) -> None:
    case_name, ct_path = prepare_suprem_input(tiny_bodymaps_bundle, tmp_path / "suprem" / "inputs")

    assert case_name == "BDMAP_TEST"
    assert ct_path == tmp_path / "suprem" / "inputs" / "BDMAP_TEST" / "ct.nii.gz"
    assert ct_path.is_file()


def test_prepare_suprem_input_compresses_uncompressed_nifti(tmp_path: Path) -> None:
    source = tmp_path / "case.nii"
    nib.save(nib.Nifti1Image(np.zeros((4, 5, 6), dtype=np.int16), np.eye(4)), source)

    case_name, ct_path = prepare_suprem_input(source, tmp_path / "suprem" / "inputs")

    assert case_name == "case"
    assert ct_path.name == "ct.nii.gz"
    assert ct_path.read_bytes().startswith(b"\x1f\x8b")
    assert nib.load(ct_path).shape == (4, 5, 6)
