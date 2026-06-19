from __future__ import annotations

import json
import shutil
import sys

from bodymaps_demo.config import Settings
from bodymaps_demo.runner import JobRunner
from bodymaps_demo.storage import JobStore, safe_filename
from bodymaps_demo.viewer import render_slice


def main() -> None:
    settings = Settings.from_env()
    sample = settings.sample_path
    if not sample or not sample.is_file():
        raise SystemExit("Sample unavailable. Set BODYMAPS_SAMPLE_CT to a BodyMaps bundle.")
    if settings.adapter != "bundle":
        raise SystemExit("Sample smoke currently requires BODYMAPS_ADAPTER=bundle.")

    store = JobStore(settings.artifacts_dir)
    job = store.create(sample.name, settings.adapter)
    destination = store.input_dir(job["id"]) / safe_filename(sample.name)
    shutil.copy2(sample, destination)
    store.update(job["id"], upload_size_bytes=sample.stat().st_size)

    JobRunner(settings, store).run(job["id"])
    completed = store.load(job["id"])
    if completed["status"] != "completed":
        print(json.dumps(completed, indent=2), file=sys.stderr)
        raise SystemExit("Sample smoke failed.")

    output_dir = store.output_dir(job["id"])
    previews = output_dir / "previews"
    previews.mkdir(exist_ok=True)
    shape = completed["result"]["volume"]["shape"]
    for plane, depth in zip(("sagittal", "coronal", "axial"), shape, strict=True):
        (previews / f"{plane}.png").write_bytes(
            render_slice(output_dir, plane, depth // 2, overlay=True)
        )

    print("BodyMaps sample smoke passed")
    print(f"Job: {job['id']}")
    print(f"Artifacts: {store.job_dir(job['id'])}")
    print(f"Structures: {len(completed['result']['labels'])}")
    evaluation = completed["result"].get("evaluation") or {}
    if evaluation:
        print(f"Mean Dice: {evaluation['mean_dice']}")
        print(f"Mean IoU: {evaluation['mean_iou']}")
    print(f"Shape: {' x '.join(str(value) for value in shape)}")


if __name__ == "__main__":
    main()
