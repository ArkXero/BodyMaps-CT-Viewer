from __future__ import annotations

import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .doctor import diagnose
from .runner import JobRunner
from .storage import JobStore, safe_filename
from .viewer import plane_depth, render_slice

ALLOWED_SUFFIXES = (".zip", ".nii", ".nii.gz")


def _allowed_filename(filename: str) -> bool:
    return filename.lower().endswith(ALLOWED_SUFFIXES)


def _validate_saved_upload(path: Path, settings: Settings) -> None:
    if settings.adapter == "bundle" and path.suffix.lower() != ".zip":
        raise HTTPException(
            status_code=422,
            detail="Bundle adapter requires a .zip with ct.nii.gz and segmentation masks.",
        )
    if path.suffix.lower() != ".zip":
        return
    if not zipfile.is_zipfile(path):
        raise HTTPException(status_code=400, detail="Uploaded .zip is not a valid ZIP archive.")

    with zipfile.ZipFile(path) as archive:
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir() and "__MACOSX" not in info.filename
        ]
        if sum(info.file_size for info in members) > settings.max_upload_bytes * 4:
            raise HTTPException(
                status_code=413,
                detail="ZIP expands beyond configured safety limit.",
            )
        if settings.adapter == "bundle":
            has_ct = any(info.filename.endswith("/ct.nii.gz") for info in members)
            has_mask = any(
                "/segmentations/" in info.filename and info.filename.endswith(".nii.gz")
                for info in members
            )
            if not has_ct or not has_mask:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "BodyMaps bundle must contain */ct.nii.gz and */segmentations/*.nii.gz."
                    ),
                )


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds configured limit of {max_bytes // (1024 * 1024)} MB.",
                )
            output.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return total


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    store = JobStore(app_settings.artifacts_dir)
    runner = JobRunner(app_settings, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        app_settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(
        title="BodyMaps Web Inference Demo",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.store = store
    app.state.runner = runner
    app.mount("/static", StaticFiles(directory=app_settings.static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(app_settings.static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "adapter": app_settings.adapter}

    @app.get("/api/config")
    def public_config() -> dict[str, object]:
        allowed_formats = [".zip"] if app_settings.adapter == "bundle" else list(ALLOWED_SUFFIXES)
        return {
            "adapter": app_settings.adapter,
            "allowed_formats": allowed_formats,
            "max_upload_mb": app_settings.max_upload_bytes // (1024 * 1024),
            "sample_available": bool(
                app_settings.sample_path and app_settings.sample_path.is_file()
            ),
            "sample_name": app_settings.sample_path.name if app_settings.sample_path else None,
        }

    @app.get("/api/doctor")
    def doctor() -> dict[str, object]:
        return diagnose(app_settings)

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, File(...)],
    ) -> dict[str, object]:
        filename = safe_filename(file.filename or "upload.bin")
        if not _allowed_filename(filename):
            raise HTTPException(
                status_code=415,
                detail="Unsupported format. Upload .zip, .nii, or .nii.gz.",
            )
        job = store.create(filename, app_settings.adapter)
        try:
            input_path = store.input_dir(job["id"]) / filename
            size = await _save_upload(file, input_path, app_settings.max_upload_bytes)
            _validate_saved_upload(input_path, app_settings)
        except Exception:
            shutil.rmtree(store.job_dir(job["id"]), ignore_errors=True)
            raise
        store.update(job["id"], upload_size_bytes=size)
        background_tasks.add_task(runner.run, job["id"])
        return {"job_id": job["id"], "status": "queued"}

    @app.post("/api/jobs/sample", status_code=202)
    def create_sample_job(background_tasks: BackgroundTasks) -> dict[str, str]:
        sample_path = app_settings.sample_path
        if not sample_path or not sample_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Sample CT unavailable. Set BODYMAPS_SAMPLE_CT.",
            )
        if sample_path.stat().st_size > app_settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Configured sample exceeds upload limit.")
        job = store.create(sample_path.name, app_settings.adapter)
        shutil.copy2(sample_path, store.input_dir(job["id"]) / safe_filename(sample_path.name))
        store.update(job["id"], upload_size_bytes=sample_path.stat().st_size)
        background_tasks.add_task(runner.run, job["id"])
        return {"job_id": job["id"], "status": "queued"}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return store.load(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found.") from error

    @app.get("/api/jobs/{job_id}/slice")
    def get_slice(
        job_id: str,
        plane: Annotated[str, Query(pattern="^(axial|coronal|sagittal)$")],
        index: Annotated[int | None, Query(ge=0)] = None,
        overlay: bool = True,
    ) -> Response:
        try:
            job = store.load(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found.") from error
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail="Job is not completed.")
        output_dir = store.output_dir(job_id)
        try:
            import numpy as np

            volume = np.load(output_dir / "volume.npy", mmap_mode="r", allow_pickle=False)
            depth = plane_depth(volume.shape, plane)
            selected = depth // 2 if index is None else index
            image = render_slice(output_dir, plane, selected, overlay)
        except (FileNotFoundError, IndexError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return Response(
            content=image,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300"},
        )

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_path:path}")
    def get_artifact(job_id: str, artifact_path: str) -> FileResponse:
        try:
            path = store.resolve_artifact(job_id, artifact_path)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Artifact not found.") from error
        return FileResponse(path, filename=path.name)

    @app.exception_handler(Exception)
    async def unhandled_exception(_, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(error)})

    return app


app = create_app()
