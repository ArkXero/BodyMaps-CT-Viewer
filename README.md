# BodyMaps Web Inference Demo

Local-first MVP for Johns Hopkins BodyMaps developer application, Project 2: web-based AI inference and model evaluation. Browser accepts CT data, backend validates upload and runs an observable model adapter, local artifacts persist each job, and result UI reports inference trace, organ stats, slice viewer controls, and Dice/IoU segmentation metrics when ground-truth masks are available.

## Current asset situation

Workspace inspection found:

- Project sheet: `/Users/ronitsingh/Documents/Call4Developer.pdf`
- Provided sample: `/Users/ronitsingh/Downloads/BDMAP_00000338.zip`
- Sample format: NIfTI CT at `*/ct.nii.gz` plus nine precomputed NIfTI masks at `*/segmentations/*.nii.gz`
- Duplicate sample: `/Users/ronitsingh/Downloads/BDMAP_00000338 (1).zip` with matching SHA-256
- Sample SHA-256: `43d562aad64f89612f4c46a7f7738768bab2d9f25c78d8500860da6229086405`
- Project-sheet prototype link: [qicq1c/SuPreM](https://huggingface.co/qicq1c/SuPreM)
- Official SuPreM runtime: Docker image `qchen99/suprem:v1` or 10.3 GB Singularity image
- Official Docker inference command requires NVIDIA GPU and requests 128 GB RAM
- Local machine blocker: arm64 macOS, 32 GB RAM, no CUDA, Docker daemon stopped

Default `bundle` adapter imports and validates provided real CT/masks so full browser workflow and metric display are runnable on this machine. It does not claim to execute SuPreM or score model quality. Dedicated `suprem` adapter normalizes uploads, invokes official Docker prototype, converts predicted masks into the same browser result contract, and scores predictions against provided masks on a compliant NVIDIA host.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```sh
cd /Users/ronitsingh/Documents/Internship
uv sync --extra dev
uv run bodymaps doctor
```

Default configuration auto-detects `~/Downloads/BDMAP_00000338.zip`. For another path:

```sh
export BODYMAPS_SAMPLE_CT=/absolute/path/to/BDMAP_00000338.zip
```

Default upload cap is `2048 MB`. Override for larger or smaller bundles:

```sh
export BODYMAPS_MAX_UPLOAD_MB=4096
```

## Run

```sh
uv run bodymaps serve
```

Open <http://127.0.0.1:8000>. Choose a supported file or click **Run BDMAP_00000338.zip**.

One-command real-sample smoke:

```sh
uv run python scripts/smoke_sample.py
```

Smoke writes job record, logs, normalized viewer arrays, organ stats, evaluation metrics, structured result, and three preview PNGs under `artifacts/<job-id>/`.

## Model evaluation flow

For real model testing, upload a BodyMaps bundle that contains `ct.nii.gz` plus reference masks under `segmentations/*.nii.gz`, then run one of the model adapters:

- `suprem`: runs the linked SuPreM Docker prototype and scores its predicted masks.
- `external`: runs any local prototype command that writes `result.json`, `volume.npy`, `mask.npy`, and `labels.json`.
- `bundle`: uses provided masks as output; useful for verifying upload, visualization, and scoring plumbing, not model quality.

When prediction label names match reference mask names, the runner writes `output/evaluation.json` and attaches per-structure Dice, IoU, false-positive voxels, and false-negative voxels to the job result.

The result viewer supports axial/coronal/sagittal focus switching, CT window presets, custom window width/center, overlay opacity, per-label hide/show, label jump targets, shareable URL state, and local recent/saved job history. Organ stats are computed from `volume.npy`, `mask.npy`, `labels.json`, and spacing metadata; they summarize mask geometry and HU values for review only and are not clinical claims.

## Doctor

```sh
uv run bodymaps doctor
uv run bodymaps doctor --json
```

Checks Python, required packages, writable artifact directory, adapter config, sample bundle structure, model/prototype assets when external adapter is selected, and available CPU/GPU runtime.

Warnings do not fail doctor. Missing required files/config produce actionable errors and exit code `1`.

## Live prototype integration

On x86_64 Linux host with NVIDIA CUDA support, at least 128 GB RAM, and running Docker:

```sh
docker pull qchen99/suprem:v1
export BODYMAPS_ADAPTER=suprem
uv run bodymaps doctor
uv run bodymaps serve
```

`suprem` adapter:

- Extracts or copies uploaded NIfTI CT into SuPreM `inputs/<case>/ct.nii.gz` layout.
- Runs official `qchen99/suprem:v1` image with GPU and `128G` memory flags.
- Captures Docker stdout, stderr, exit code, and timing.
- Normalizes predicted NIfTI masks into viewer arrays and structured result.

Override image with `BODYMAPS_SUPREM_IMAGE`.

For another prototype, use generic external adapter:

```sh
export BODYMAPS_ADAPTER=external
export BODYMAPS_PROTOTYPE_PATH=/path/to/prototype
export BODYMAPS_WEIGHTS_PATH=/path/to/checkpoint.pth
export BODYMAPS_INFERENCE_COMMAND='python /path/to/prototype/inference.py --input {input} --output-dir {output_dir}'
```

Command contract:

- Must include `{input}` and `{output_dir}` placeholders.
- Must exit nonzero on failure.
- Must write `result.json` to output directory.
- For tri-planar viewer, write `volume.npy`, `mask.npy`, and `labels.json`.
- `volume.npy` and `mask.npy` must be same 3D shape.
- `labels.json` must contain objects with `id`, `name`, `color`, and `voxel_count`.
- `result.json` should follow default adapter output shape shown in `bodymaps_demo/bundle_inference.py`.

Backend captures rendered command, stdout, stderr, start/completion timestamps, duration, exit code, timeout status, and output directory.

If the uploaded ZIP also contains reference masks at `*/segmentations/*.nii.gz`, backend compares predicted labels against those masks by normalized label name and writes `output/evaluation.json`.

## Artifact layout

```text
artifacts/<job-id>/
├── job.json
├── input/
│   └── uploaded-scan.zip
├── logs/
│   ├── execution.json
│   ├── stderr.log
│   └── stdout.log
└── output/
    ├── result.json
    ├── evaluation.json
    ├── labels.json
    ├── mask.npy
    ├── organ_stats.json
    ├── volume.npy
    ├── previews/
    └── source/
```

## Verification

```sh
./scripts/check.sh
```

## Known limitations

- Default local sample path visualizes provided precomputed masks rather than claiming live inference.
- `bundle` evaluation scores validate metric plumbing only because prediction and reference masks come from the same provided bundle.
- SuPreM live inference cannot run on current arm64/32 GB/no-CUDA machine.
- First pass supports actual discovered format: BodyMaps ZIP/NIfTI. DICOM and NRRD are intentionally deferred.
- Jobs run locally in FastAPI background tasks; no durable queue or multi-user concurrency.
- App is research demo software, not a medical device and not for clinical use.
