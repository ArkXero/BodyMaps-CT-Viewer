from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: Path | None = None) -> Path | None:
    raw = os.getenv(name)
    if raw:
        return Path(raw).expanduser().resolve()
    return default.resolve() if default else None


def _default_sample_path() -> Path | None:
    candidate = Path.home() / "Downloads" / "BDMAP_00000338.zip"
    return candidate.resolve() if candidate.is_file() else None


def _default_artifacts_dir() -> Path:
    if os.getenv("VERCEL"):
        return Path("/tmp/bodymaps-artifacts")
    return REPO_ROOT / "artifacts"


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    artifacts_dir: Path
    static_dir: Path
    adapter: str
    max_upload_bytes: int
    inference_timeout_seconds: int
    sample_path: Path | None
    inference_command: str | None
    prototype_path: Path | None
    weights_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        max_upload_mb = int(os.getenv("BODYMAPS_MAX_UPLOAD_MB", "2048"))
        return cls(
            repo_root=REPO_ROOT,
            artifacts_dir=_path_from_env("BODYMAPS_ARTIFACTS_DIR", _default_artifacts_dir()),
            static_dir=REPO_ROOT / "bodymaps_demo" / "static",
            adapter=os.getenv("BODYMAPS_ADAPTER", "bundle").strip().lower(),
            max_upload_bytes=max_upload_mb * 1024 * 1024,
            inference_timeout_seconds=int(os.getenv("BODYMAPS_INFERENCE_TIMEOUT_SECONDS", "3600")),
            sample_path=_path_from_env("BODYMAPS_SAMPLE_CT", _default_sample_path()),
            inference_command=os.getenv("BODYMAPS_INFERENCE_COMMAND"),
            prototype_path=_path_from_env("BODYMAPS_PROTOTYPE_PATH"),
            weights_path=_path_from_env("BODYMAPS_WEIGHTS_PATH"),
        )
