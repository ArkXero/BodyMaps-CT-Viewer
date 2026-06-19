from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .config import Settings


def _check(name: str, level: str, message: str, suggestion: str | None = None) -> dict[str, str]:
    value = {"name": name, "level": level, "message": message}
    if suggestion:
        value["suggestion"] = suggestion
    return value


def _sample_bundle_check(path: Path | None) -> dict[str, str]:
    if not path:
        return _check(
            "sample CT",
            "warning",
            "No sample CT configured.",
            "Set BODYMAPS_SAMPLE_CT to a BodyMaps .zip bundle.",
        )
    if not path.is_file():
        return _check(
            "sample CT",
            "error",
            f"Configured sample does not exist: {path}",
            "Update BODYMAPS_SAMPLE_CT to an accessible file.",
        )
    if path.suffix.lower() != ".zip":
        return _check(
            "sample CT",
            "warning",
            f"Sample is not a BodyMaps .zip bundle: {path}",
            "Bundle adapter expects ct.nii.gz plus segmentations/*.nii.gz.",
        )
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return _check(
            "sample CT",
            "error",
            f"Sample is not a readable zip archive: {path}",
            "Replace file with a valid BodyMaps bundle.",
        )
    has_ct = any(name.endswith("/ct.nii.gz") for name in names)
    mask_count = sum(
        "__MACOSX" not in name and "/segmentations/" in name and name.endswith(".nii.gz")
        for name in names
    )
    if not has_ct or mask_count == 0:
        return _check(
            "sample CT",
            "error",
            f"Bundle missing expected CT or masks: {path}",
            "Expected */ct.nii.gz and */segmentations/*.nii.gz.",
        )
    return _check(
        "sample CT",
        "pass",
        f"Readable BodyMaps bundle with CT and {mask_count} masks: {path}",
    )


def _memory_bytes() -> int | None:
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            return int(result.stdout.strip())
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _suprem_checks() -> list[dict[str, str]]:
    checks = [
        _check(
            "SuPreM prototype",
            "pass",
            "Configured official BodyMaps-linked prototype: qchen99/suprem:v1.",
        )
    ]
    docker = shutil.which("docker")
    if not docker:
        checks.append(
            _check(
                "Docker",
                "error",
                "Docker executable not found.",
                "Install Docker on NVIDIA Linux host.",
            )
        )
    else:
        checks.append(_check("Docker", "pass", f"Executable available: {docker}"))
        try:
            result = subprocess.run(
                [docker, "info"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if result.returncode == 0:
                checks.append(_check("Docker daemon", "pass", "Docker daemon is reachable."))
            else:
                message = result.stderr.strip().splitlines()[-1] if result.stderr else "unreachable"
                checks.append(
                    _check(
                        "Docker daemon",
                        "error",
                        message,
                        "Start Docker daemon before running SuPreM.",
                    )
                )
        except subprocess.SubprocessError as error:
            checks.append(
                _check(
                    "Docker daemon",
                    "error",
                    f"Docker diagnostic failed: {error}",
                    "Start Docker daemon before running SuPreM.",
                )
            )

    architecture = platform.machine()
    checks.append(
        _check(
            "host architecture",
            "pass" if architecture in {"x86_64", "amd64"} else "error",
            f"Detected {architecture}.",
            (
                None
                if architecture in {"x86_64", "amd64"}
                else "Use x86_64 Linux host compatible with official CUDA image."
            ),
        )
    )

    memory = _memory_bytes()
    required = 128 * 1024**3
    checks.append(
        _check(
            "host memory",
            "pass" if memory and memory >= required else "error",
            (
                f"Detected {memory / 1024**3:.0f} GB; SuPreM command requests 128 GB."
                if memory
                else "Could not determine host memory; SuPreM command requests 128 GB."
            ),
            None if memory and memory >= required else "Use host with at least 128 GB RAM.",
        )
    )

    nvidia_smi = shutil.which("nvidia-smi")
    checks.append(
        _check(
            "NVIDIA GPU",
            "pass" if nvidia_smi else "error",
            f"nvidia-smi available: {nvidia_smi}" if nvidia_smi else "nvidia-smi not found.",
            None if nvidia_smi else "Run SuPreM on NVIDIA CUDA host.",
        )
    )
    return checks


def diagnose(settings: Settings) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    checks.append(
        _check(
            "Python",
            "pass" if sys.version_info >= (3, 10) else "error",
            f"Python {sys.version.split()[0]} at {sys.executable}",
            None if sys.version_info >= (3, 10) else "Install Python 3.10 or newer.",
        )
    )

    for package in ("fastapi", "nibabel", "numpy", "PIL", "uvicorn"):
        available = importlib.util.find_spec(package) is not None
        checks.append(
            _check(
                f"package {package}",
                "pass" if available else "error",
                "Installed." if available else "Missing.",
                None if available else "Run `uv sync --extra dev`.",
            )
        )

    try:
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.artifacts_dir, delete=True):
            pass
        checks.append(_check("artifact directory", "pass", f"Writable: {settings.artifacts_dir}"))
    except OSError as error:
        checks.append(
            _check(
                "artifact directory",
                "error",
                f"Not writable: {settings.artifacts_dir} ({error})",
                "Set BODYMAPS_ARTIFACTS_DIR to a writable directory.",
            )
        )

    if settings.adapter == "bundle":
        checks.append(
            _check(
                "inference adapter",
                "warning",
                "Using provided-mask bundle adapter; linked SuPreM prototype is not running.",
                "On compliant NVIDIA host, set BODYMAPS_ADAPTER=suprem.",
            )
        )
        checks.append(_sample_bundle_check(settings.sample_path))
    elif settings.adapter == "suprem":
        checks.extend(_suprem_checks())
        checks.append(_sample_bundle_check(settings.sample_path))
    elif settings.adapter == "external":
        if settings.inference_command and all(
            placeholder in settings.inference_command for placeholder in ("{input}", "{output_dir}")
        ):
            executable = settings.inference_command.split()[0]
            available = Path(executable).is_file() or shutil.which(executable)
            checks.append(
                _check(
                    "inference command",
                    "pass" if available else "error",
                    (
                        f"Configured with required placeholders: {settings.inference_command}"
                        if available
                        else f"Executable not found: {executable}"
                    ),
                    None if available else "Install executable or fix BODYMAPS_INFERENCE_COMMAND.",
                )
            )
        else:
            checks.append(
                _check(
                    "inference command",
                    "error",
                    "BODYMAPS_INFERENCE_COMMAND missing or lacks {input}/{output_dir}.",
                    "Set command using both required placeholders.",
                )
            )
        for name, path in (
            ("prototype path", settings.prototype_path),
            ("weights path", settings.weights_path),
        ):
            environment_name = (
                "BODYMAPS_PROTOTYPE_PATH"
                if name.startswith("prototype")
                else "BODYMAPS_WEIGHTS_PATH"
            )
            checks.append(
                _check(
                    name,
                    "pass" if path and path.exists() else "error",
                    f"Accessible: {path}" if path and path.exists() else f"Missing: {path}",
                    f"Set {environment_name}.",
                )
            )
        checks.append(_sample_bundle_check(settings.sample_path))
    else:
        checks.append(
            _check(
                "inference adapter",
                "error",
                f"Unknown adapter: {settings.adapter}",
                "Set BODYMAPS_ADAPTER=bundle, suprem, or external.",
            )
        )

    if settings.adapter != "suprem":
        try:
            import torch

            gpu_message = (
                f"CUDA available ({torch.cuda.get_device_name(0)})."
                if torch.cuda.is_available()
                else "PyTorch installed; CUDA unavailable. CPU execution only."
            )
            checks.append(
                _check(
                    "compute",
                    "pass" if torch.cuda.is_available() else "warning",
                    gpu_message,
                )
            )
        except ImportError:
            checks.append(
                _check(
                    "compute",
                    "warning",
                    (
                        f"CPU available ({os.cpu_count() or 'unknown'} logical cores); "
                        "PyTorch not installed."
                    ),
                    "Prototype-specific environment may install PyTorch and expose GPU support.",
                )
            )

    errors = sum(item["level"] == "error" for item in checks)
    warnings = sum(item["level"] == "warning" for item in checks)
    return {
        "passed": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = ["BodyMaps doctor", ""]
    for item in report["checks"]:
        lines.append(f"{item['level'].upper()} {item['name']}: {item['message']}")
        if item.get("suggestion"):
            lines.append(f"  Suggestion: {item['suggestion']}")
    passed = len(report["checks"]) - report["errors"] - report["warnings"]
    lines.extend(
        [
            "",
            f"Summary: {passed} passed, {report['warnings']} warnings, {report['errors']} errors",
        ]
    )
    return "\n".join(lines)
