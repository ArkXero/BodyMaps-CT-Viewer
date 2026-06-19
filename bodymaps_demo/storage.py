from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "upload.bin"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


class JobStore:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir.resolve()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create(self, source_name: str, adapter: str) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.job_dir(job_id)
        for name in ("input", "output", "logs"):
            (job_dir / name).mkdir(parents=True, exist_ok=True)
        job = {
            "id": job_id,
            "status": "queued",
            "adapter": adapter,
            "source_name": source_name,
            "created_at": utc_now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "execution": None,
        }
        self.save(job)
        return job

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", job_id):
            raise KeyError(job_id)
        return self.artifacts_dir / job_id

    def input_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "input"

    def output_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "output"

    def logs_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "logs"

    def load(self, job_id: str) -> dict[str, Any]:
        path = self.job_dir(job_id) / "job.json"
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, job: dict[str, Any]) -> None:
        write_json(self.job_dir(job["id"]) / "job.json", job)

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        job = self.load(job_id)
        job.update(changes)
        self.save(job)
        return job

    def resolve_artifact(self, job_id: str, relative_path: str) -> Path:
        job_dir = self.job_dir(job_id).resolve()
        candidate = (job_dir / relative_path).resolve()
        if candidate != job_dir and job_dir not in candidate.parents:
            raise KeyError(relative_path)
        if not candidate.is_file():
            raise KeyError(relative_path)
        return candidate
