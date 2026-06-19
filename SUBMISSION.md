# BodyMaps Project 2 Demo

## What this demonstrates

This local web application accepts a BodyMaps CT bundle in the browser, validates it, runs an isolated inference adapter, persists a reproducible job trace, scores predicted masks against provided reference masks, and renders segmentation results across axial, coronal, and sagittal planes.

The included demo uses the provided `BDMAP_00000338.zip` CT and its nine provided masks. The linked SuPreM prototype has a dedicated Docker adapter for a compliant NVIDIA host.

## Run the demo

```sh
cd /Users/ronitsingh/Documents/Internship
uv sync --extra dev
./scripts/check.sh
uv run bodymaps serve
```

Open <http://127.0.0.1:8000>, run doctor, then select **Run BDMAP_00000338.zip**.

## Review points

- Browser upload and sample-run paths
- Model evaluation report with Dice, IoU, false-positive voxels, and false-negative voxels
- Async job polling and clear failure states
- Axial, coronal, and sagittal slice review
- Segmentation overlay toggle and label legend
- Downloadable structured result, logs, command, exit code, and timing
- `bodymaps doctor` preflight for local demo and SuPreM runtime requirements

## Live SuPreM status

Project sheet links `qicq1c/SuPreM`. Its official Docker command requires an NVIDIA GPU and requests 128 GB RAM. Current development machine is arm64 macOS with 32 GB RAM and no CUDA, so live SuPreM execution is blocked by hardware. On a compatible host:

```sh
docker pull qchen99/suprem:v1
export BODYMAPS_ADAPTER=suprem
uv run bodymaps doctor
uv run bodymaps serve
```

No mock inference is presented as model output. The local bundle mode is a reference-mask path for proving the browser, artifact, visualization, and metric pipeline. Live model quality testing happens through `BODYMAPS_ADAPTER=suprem` on compatible hardware or `BODYMAPS_ADAPTER=external` for another prototype command.
