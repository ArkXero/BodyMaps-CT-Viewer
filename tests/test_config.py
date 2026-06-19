from __future__ import annotations

from pathlib import Path

from bodymaps_demo.config import Settings


def test_vercel_uses_tmp_artifacts(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("BODYMAPS_ARTIFACTS_DIR", raising=False)

    settings = Settings.from_env()

    assert settings.artifacts_dir == Path("/tmp/bodymaps-artifacts").resolve()


def test_artifacts_env_overrides_vercel_default(monkeypatch, tmp_path: Path) -> None:
    custom_artifacts = tmp_path / "custom-artifacts"
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("BODYMAPS_ARTIFACTS_DIR", str(custom_artifacts))

    settings = Settings.from_env()

    assert settings.artifacts_dir == custom_artifacts.resolve()
