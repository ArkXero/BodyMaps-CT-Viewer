from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .evaluation import evaluate_prediction
from .storage import JobStore, utc_now, write_json


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class JobRunner:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store

    def _command(self, input_path: Path, output_dir: Path) -> tuple[str | list[str], bool, str]:
        if self.settings.adapter == "bundle":
            args = [
                sys.executable,
                "-m",
                "bodymaps_demo.cli",
                "infer-bundle",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ]
            return args, False, shlex.join(args)

        if self.settings.adapter == "suprem":
            args = [
                sys.executable,
                "-m",
                "bodymaps_demo.cli",
                "infer-suprem",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ]
            return args, False, shlex.join(args)

        if self.settings.adapter == "external":
            template = self.settings.inference_command
            if not template:
                raise ValueError(
                    "BODYMAPS_INFERENCE_COMMAND is required when BODYMAPS_ADAPTER=external."
                )
            if "{input}" not in template or "{output_dir}" not in template:
                raise ValueError(
                    "BODYMAPS_INFERENCE_COMMAND must include {input} and {output_dir} placeholders."
                )
            command = template.replace("{input}", shlex.quote(str(input_path))).replace(
                "{output_dir}", shlex.quote(str(output_dir))
            )
            return command, True, command

        raise ValueError(
            f"Unknown BODYMAPS_ADAPTER={self.settings.adapter!r}; "
            "expected bundle, suprem, or external."
        )

    def run(self, job_id: str) -> None:
        self.store.update(job_id, status="running", started_at=utc_now(), error=None)
        input_files = [path for path in self.store.input_dir(job_id).iterdir() if path.is_file()]
        if len(input_files) != 1:
            self.store.update(
                job_id,
                status="failed",
                completed_at=utc_now(),
                error=f"Expected one input file, found {len(input_files)}.",
            )
            return

        output_dir = self.store.output_dir(job_id)
        logs_dir = self.store.logs_dir(job_id)
        started_at = _iso_now()
        start = time.perf_counter()

        try:
            command, shell, display_command = self._command(input_files[0], output_dir)
            process = subprocess.run(
                command,
                cwd=self.settings.repo_root,
                capture_output=True,
                text=True,
                timeout=self.settings.inference_timeout_seconds,
                shell=shell,
                check=False,
            )
            exit_code = process.returncode
            stdout = process.stdout
            stderr = process.stderr
            timed_out = False
        except subprocess.TimeoutExpired as error:
            display_command = (
                error.cmd if isinstance(error.cmd, str) else shlex.join(error.cmd or [])
            )
            exit_code = 124
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            stderr += f"\nInference timed out after {self.settings.inference_timeout_seconds}s."
            timed_out = True
        except Exception as error:
            display_command = "not started"
            exit_code = 1
            stdout = ""
            stderr = str(error)
            timed_out = False

        completed_at = _iso_now()
        execution = {
            "command": display_command,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": round((time.perf_counter() - start) * 1000),
            "stdout_path": "logs/stdout.log",
            "stderr_path": "logs/stderr.log",
            "output_dir": "output",
        }
        (logs_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (logs_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        write_json(logs_dir / "execution.json", execution)

        result_path = output_dir / "result.json"
        if exit_code != 0:
            self.store.update(
                job_id,
                status="failed",
                completed_at=utc_now(),
                error=stderr.strip() or f"Inference exited with code {exit_code}.",
                execution=execution,
            )
            return
        if not result_path.is_file():
            self.store.update(
                job_id,
                status="failed",
                completed_at=utc_now(),
                error="Inference exited successfully but did not write output/result.json.",
                execution=execution,
            )
            return

        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            self.store.update(
                job_id,
                status="failed",
                completed_at=utc_now(),
                error=f"Could not read output/result.json: {error}",
                execution=execution,
            )
            return

        try:
            evaluation = evaluate_prediction(input_files[0], output_dir, result)
        except Exception as error:
            evaluation = {
                "mode": "segmentation_ground_truth_comparison",
                "summary": "Evaluation failed after inference completed.",
                "error": str(error),
            }
            write_json(output_dir / "evaluation.json", evaluation)
        if evaluation:
            result["evaluation"] = evaluation
            downloads = result.setdefault("downloads", [])
            if isinstance(downloads, list):
                downloads.append({"name": "Evaluation metrics", "path": "output/evaluation.json"})
            write_json(result_path, result)

        self.store.update(
            job_id,
            status="completed",
            completed_at=utc_now(),
            result=result,
            execution=execution,
        )
