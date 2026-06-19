const planes = ["axial", "coronal", "sagittal"];

const state = {
  job: null,
  globalProgress: 0.5,
  indices: { axial: 0, coronal: 0, sagittal: 0 },
  depths: { axial: 0, coronal: 0, sagittal: 0 },
};

const elements = {
  status: document.querySelector("#prototype-status"),
  reload: document.querySelector("#reload-sample"),
  sync: document.querySelector("#sync-scrub"),
  syncOutput: document.querySelector("#sync-output"),
  labelPreview: document.querySelector("#label-preview"),
};

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}.`);
  }
  return payload;
}

function formatScore(value) {
  return Number.isFinite(value) ? value.toFixed(3) : "n/a";
}

function planeDepth(shape, plane) {
  return { sagittal: shape[0], coronal: shape[1], axial: shape[2] }[plane];
}

function physicalAspect(shape, spacing, plane) {
  const [sx, sy, sz] = spacing;
  if (plane === "axial") return (shape[0] * sx) / (shape[1] * sy);
  if (plane === "coronal") return (shape[0] * sx) / (shape[2] * sz);
  return (shape[1] * sy) / (shape[2] * sz);
}

function verticalScale(spacing, plane) {
  const [sx, sy, sz] = spacing;
  if (plane === "axial") return 1;
  return sz / (plane === "coronal" ? sx : sy);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function indexFromProgress(plane, progress) {
  const depth = state.depths[plane] || 1;
  return Math.round((depth - 1) * clamp(progress, 0, 1));
}

function createLocalControls() {
  document.querySelectorAll(".scan-frame[data-plane]").forEach((frame, index) => {
    const plane = frame.dataset.plane;
    const control = document.createElement("label");
    const label = document.createElement("span");
    const input = document.createElement("input");
    const output = document.createElement("output");

    control.className = "local-scrubber";
    control.setAttribute("aria-label", `${plane} local slice control`);
    label.textContent = "Local slice";
    input.type = "range";
    input.min = "0";
    input.max = "0";
    input.value = "0";
    input.dataset.planeLocalControl = plane;
    input.id = `${plane}-local-${index}`;
    output.dataset.planeLocalOutput = plane;
    output.textContent = "0 / 0";

    control.append(label, input, output);
    frame.insertAdjacentElement("afterend", control);
  });
}

function setPlaneGeometry(job) {
  const shape = job.result.volume.shape;
  const spacing = job.result.volume.spacing_mm;
  planes.forEach((plane) => {
    state.depths[plane] = planeDepth(shape, plane);
    state.indices[plane] = indexFromProgress(plane, state.globalProgress);

    document.querySelectorAll(`[data-plane="${plane}"]`).forEach((frame) => {
      frame.style.setProperty("--aspect", physicalAspect(shape, spacing, plane).toFixed(4));
      frame.style.setProperty("--scale-y", verticalScale(spacing, plane).toFixed(4));
    });
  });
}

function updateScrubberState(plane) {
  const index = state.indices[plane];
  const depth = state.depths[plane];
  const counter = `${index + 1} / ${depth}`;
  const controls = [
    ...document.querySelectorAll(`[data-plane-control="${plane}"]`),
    ...document.querySelectorAll(`[data-plane-local-control="${plane}"]`),
  ];
  controls.forEach((slider) => {
    slider.max = String(depth - 1);
    slider.value = String(index);
  });
  document.querySelector(`[data-plane-output="${plane}"]`).textContent = counter;
  document.querySelectorAll(`[data-plane-local-output="${plane}"]`).forEach((output) => {
    output.textContent = counter;
  });
}

function updatePlane(plane) {
  const index = state.indices[plane];
  const depth = state.depths[plane];
  const counter = `${index + 1} / ${depth}`;
  document.querySelectorAll(`[data-plane-counter="${plane}"]`).forEach((item) => {
    item.textContent = counter;
  });
  updateScrubberState(plane);

  document.querySelectorAll(`[data-plane="${plane}"]`).forEach((frame) => {
    frame.classList.remove("is-ready");
  });

  document.querySelectorAll(`[data-plane-image="${plane}"]`).forEach((image) => {
    image.addEventListener(
      "load",
      () => image.closest(".scan-frame")?.classList.add("is-ready"),
      { once: true },
    );
    image.src = `/api/jobs/${state.job.id}/slice?plane=${plane}&index=${index}&overlay=true&t=${Date.now()}`;
  });
}

function setPlaneIndex(plane, index) {
  state.indices[plane] = clamp(index, 0, Math.max(0, state.depths[plane] - 1));
  if (state.job) updatePlane(plane);
}

function setGlobalProgress(progress) {
  state.globalProgress = clamp(progress, 0, 1);
  elements.sync.value = String(Math.round(state.globalProgress * 1000));
  elements.syncOutput.textContent = `${Math.round(state.globalProgress * 100)}%`;
  if (!state.job) return;
  planes.forEach((plane) => {
    state.indices[plane] = indexFromProgress(plane, state.globalProgress);
    updatePlane(plane);
  });
}

function updateScores(job) {
  const evaluation = job.result.evaluation || {};
  document.querySelector('[data-score="dice"]').textContent = formatScore(evaluation.mean_dice);
  document.querySelector('[data-score="iou"]').textContent = formatScore(evaluation.mean_iou);
  document.querySelector('[data-score="matched"]').textContent =
    `${evaluation.matched_labels || 0} / ${evaluation.ground_truth_labels || 0}`;
}

function updateLabels(job) {
  const labels = [...(job.result.labels || [])]
    .sort((left, right) => right.voxel_count - left.voxel_count)
    .slice(0, 6);
  elements.labelPreview.replaceChildren();
  labels.forEach((label) => {
    const row = document.createElement("div");
    row.className = "label-chip";
    const swatch = document.createElement("i");
    swatch.style.background = label.color;
    const name = document.createElement("span");
    name.textContent = label.name;
    const count = document.createElement("small");
    count.textContent = Number(label.voxel_count).toLocaleString();
    row.append(swatch, name, count);
    elements.labelPreview.append(row);
  });
}

function renderJob(job) {
  state.job = job;
  setPlaneGeometry(job);
  setGlobalProgress(state.globalProgress);
  updateScores(job);
  updateLabels(job);
  elements.status.textContent = `Job ${job.id} loaded`;
}

async function pollJob(jobId) {
  const job = await request(`/api/jobs/${jobId}`);
  elements.status.textContent = `Job ${jobId}: ${job.status}`;
  if (job.status === "completed") {
    renderJob(job);
    return;
  }
  if (job.status === "failed") {
    throw new Error(job.error || "Sample job failed.");
  }
  setTimeout(() => pollJob(jobId).catch(showError), 800);
}

function showError(error) {
  elements.status.textContent = error.message;
}

async function loadSample() {
  elements.reload.disabled = true;
  elements.status.textContent = "Starting sample job";
  try {
    const created = await request("/api/jobs/sample", { method: "POST" });
    await pollJob(created.job_id);
  } catch (error) {
    showError(error);
  } finally {
    elements.reload.disabled = false;
  }
}

async function initialize() {
  createLocalControls();
  elements.sync.addEventListener("input", (event) => {
    setGlobalProgress(Number(event.target.value) / 1000);
  });

  planes.forEach((plane) => {
    document.querySelector(`[data-plane-control="${plane}"]`).addEventListener("input", (event) => {
      setPlaneIndex(plane, Number(event.target.value));
    });
  });

  document.querySelectorAll("[data-plane-local-control]").forEach((slider) => {
    slider.addEventListener("input", (event) => {
      setPlaneIndex(event.target.dataset.planeLocalControl, Number(event.target.value));
    });
  });

  elements.reload.addEventListener("click", loadSample);

  const params = new URLSearchParams(window.location.search);
  const jobId = params.get("job");
  if (jobId) {
    try {
      renderJob(await request(`/api/jobs/${jobId}`));
    } catch (error) {
      showError(error);
    }
    return;
  }
  loadSample();
}

initialize();
