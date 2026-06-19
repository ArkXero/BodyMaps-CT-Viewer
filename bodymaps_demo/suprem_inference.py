from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import nibabel as nib

from .bundle_inference import _safe_extract_bundle, run_bundle_inference
from .storage import write_json

DEFAULT_IMAGE = "qchen99/suprem:v1"


def prepare_suprem_input(input_path: Path, inputs_dir: Path) -> tuple[str, Path]:
    staging_dir = inputs_dir.parent / "staging"
    if input_path.suffix.lower() == ".zip":
        extracted = _safe_extract_bundle(input_path, staging_dir)
        ct_candidates = [path for path in extracted if path.name == "ct.nii.gz"]
        if len(ct_candidates) != 1:
            raise ValueError(f"Expected exactly one ct.nii.gz, found {len(ct_candidates)}.")
        source_ct = ct_candidates[0]
        case_name = source_ct.parent.name
    elif input_path.name.lower().endswith((".nii", ".nii.gz")):
        source_ct = input_path
        case_name = input_path.name.removesuffix(".nii.gz").removesuffix(".nii")
    else:
        raise ValueError("SuPreM adapter requires .zip, .nii, or .nii.gz input.")

    case_dir = inputs_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    destination = case_dir / "ct.nii.gz"
    if source_ct.name.lower().endswith(".nii") and not source_ct.name.lower().endswith(".nii.gz"):
        nib.save(nib.load(source_ct), destination)
    else:
        shutil.copy2(source_ct, destination)
    return case_name, destination


def _run_docker(inputs_dir: Path, outputs_dir: Path) -> None:
    image = os.getenv("BODYMAPS_SUPREM_IMAGE", DEFAULT_IMAGE)
    command = [
        "docker",
        "container",
        "run",
        "--gpus",
        "device=0",
        "-m",
        "128G",
        "--rm",
        "-v",
        f"{inputs_dir.resolve()}:/workspace/inputs/",
        "-v",
        f"{outputs_dir.resolve()}:/workspace/outputs/",
        image,
        "/bin/bash",
        "-c",
        "sh predict.sh",
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.stdout:
        print(process.stdout, end="")
    if process.stderr:
        print(process.stderr, end="", file=sys.stderr)
    if process.returncode != 0:
        raise RuntimeError(
            f"SuPreM Docker inference exited with code {process.returncode}. "
            f"{process.stderr.strip()}"
        )


def run_suprem_inference(input_path: Path, output_dir: Path) -> dict[str, object]:
    work_dir = output_dir / "suprem"
    inputs_dir = work_dir / "inputs"
    raw_outputs_dir = work_dir / "raw_outputs"
    case_name, ct_path = prepare_suprem_input(input_path, inputs_dir)
    raw_outputs_dir.mkdir(parents=True, exist_ok=True)

    _run_docker(inputs_dir, raw_outputs_dir)

    segmentation_dir = raw_outputs_dir / case_name / "segmentations"
    mask_paths = sorted(segmentation_dir.glob("*.nii.gz"))
    if not mask_paths:
        raise ValueError(f"SuPreM wrote no segmentation masks under {segmentation_dir}.")

    prediction_bundle = work_dir / "suprem_predictions.zip"
    with zipfile.ZipFile(prediction_bundle, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(ct_path, f"{case_name}/ct.nii.gz")
        for mask_path in mask_paths:
            archive.write(mask_path, f"{case_name}/segmentations/{mask_path.name}")

    result = run_bundle_inference(prediction_bundle, output_dir)
    result["mode"] = "suprem_live_inference"
    result["summary"] = f"SuPreM inferred {len(mask_paths)} anatomical structures."
    result["disclaimer"] = "Live SuPreM prototype output. Research demo only; not for clinical use."
    result["prototype"] = {
        "source": "https://huggingface.co/qicq1c/SuPreM",
        "image": os.getenv("BODYMAPS_SUPREM_IMAGE", DEFAULT_IMAGE),
    }
    write_json(output_dir / "result.json", result)
    return result
