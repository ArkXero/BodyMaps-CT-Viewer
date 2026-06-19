#!/bin/sh
set -eu

uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run bodymaps doctor
uv run python scripts/smoke_sample.py

printf '\nBodyMaps full check passed\n'
