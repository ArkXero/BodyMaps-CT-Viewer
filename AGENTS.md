# Contributor Guide

## Scope

Keep this MVP local-first and narrow. Do not add auth, cloud queues, databases, deployment config, or heavy 3D rendering unless requested.

## Architecture

- `bodymaps_demo/app.py`: thin HTTP API and static UI serving
- `bodymaps_demo/runner.py`: subprocess lifecycle and execution trace
- `bodymaps_demo/bundle_inference.py`: provided BodyMaps bundle adapter
- `bodymaps_demo/suprem_inference.py`: linked SuPreM Docker adapter
- `bodymaps_demo/doctor.py`: non-executing preflight checks
- `bodymaps_demo/storage.py`: local job persistence
- `bodymaps_demo/viewer.py`: server-rendered slice previews
- `bodymaps_demo/static/`: dependency-free browser UI

Keep model-specific behavior behind adapter/subprocess boundary. Never introduce fake inference into default demo path.

## Checks

```sh
./scripts/check.sh
```
