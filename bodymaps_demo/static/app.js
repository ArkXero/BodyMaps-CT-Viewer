const PLANES = ["axial", "coronal", "sagittal"];

const state = {
  config: null,
  file: null,
  job: null,
  pollTimer: null,
  viewer: {
    globalProgress: 0.5,
    activePlane: "sagittal",
    depths: { axial: 0, coronal: 0, sagittal: 0 },
    indices: { axial: 0, coronal: 0, sagittal: 0 },
    renderTimers: { axial: null, coronal: null, sagittal: null },
    lastRenderAt: { axial: 0, coronal: 0, sagittal: 0 },
    sliceControllers: { axial: null, coronal: null, sagittal: null },
    sliceUrls: { axial: null, coronal: null, sagittal: null },
  },
};

const elements = {
  adapterName: document.querySelector("#adapter-name"),
  uploadLimit: document.querySelector("#upload-limit"),
  uploadForm: document.querySelector("#upload-form"),
  fileInput: document.querySelector("#file-input"),
  fileLabel: document.querySelector("#file-label"),
  formatNote: document.querySelector("#format-note"),
  uploadButton: document.querySelector("#upload-button"),
  sampleButton: document.querySelector("#sample-button"),
  jobPanel: document.querySelector("#job-panel"),
  jobTitle: document.querySelector("#job-title"),
  statusPill: document.querySelector("#status-pill"),
  progressBar: document.querySelector("#progress-bar"),
  jobMessage: document.querySelector("#job-message"),
  results: document.querySelector("#results-section"),
  overlayToggle: document.querySelector("#overlay-toggle"),
  syncSliceSlider: document.querySelector("#sync-slice-slider"),
  syncSliceOutput: document.querySelector("#sync-slice-output"),
  focusPlaneLabel: document.querySelector("#focus-plane-label"),
  focusSliceValue: document.querySelector("#focus-slice-value"),
  focusFrame: document.querySelector("#focus-image-frame"),
  focusImage: document.querySelector("#focus-image"),
  focusSliceSlider: document.querySelector("#focus-slice-slider"),
  focusSliceOutput: document.querySelector("#focus-slice-output"),
  resultSummary: document.querySelector("#result-summary"),
  resultDisclaimer: document.querySelector("#result-disclaimer"),
  metrics: document.querySelector("#metrics"),
  evaluationCard: document.querySelector("#evaluation-card"),
  evaluationSummary: document.querySelector("#evaluation-summary"),
  evaluationWarning: document.querySelector("#evaluation-warning"),
  scoreStrip: document.querySelector("#score-strip"),
  evaluationRows: document.querySelector("#evaluation-rows"),
  viewerStructureList: document.querySelector("#viewer-structure-list"),
  labelList: document.querySelector("#label-list"),
  traceList: document.querySelector("#trace-list"),
  downloadList: document.querySelector("#download-list"),
  doctorDialog: document.querySelector("#doctor-dialog"),
  doctorSummary: document.querySelector("#doctor-summary"),
  doctorChecks: document.querySelector("#doctor-checks"),
};

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}.`);
  }
  return payload;
}

function setSelectedFile(file) {
  state.file = file;
  elements.fileLabel.textContent = file ? `${file.name} · ${formatBytes(file.size)}` : "Drop BodyMaps bundle here or choose file";
  elements.uploadButton.disabled = !file;
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "unknown";
  const units = ["B", "KB", "MB", "GB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function createDefinition(term, description, helper = "") {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = description;
  wrapper.append(dt, dd);
  if (helper) {
    const small = document.createElement("small");
    small.className = "metric-help";
    small.textContent = helper;
    wrapper.append(small);
  }
  return wrapper;
}

function formatScore(value) {
  return Number.isFinite(value) ? value.toFixed(3) : "n/a";
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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

function applyFrameGeometry(frame, job, plane) {
  const shape = job.result.volume.shape;
  const spacing = job.result.volume.spacing_mm || [1, 1, 1];
  frame.style.setProperty("--aspect", physicalAspect(shape, spacing, plane).toFixed(4));
  frame.style.setProperty("--scale-y", verticalScale(spacing, plane).toFixed(4));
}

function indexFromProgress(plane, progress) {
  const depth = state.viewer.depths[plane] || 1;
  return Math.round((depth - 1) * clamp(progress, 0, 1));
}

function showJob(jobId) {
  state.job = { id: jobId, status: "queued" };
  state.viewer.globalProgress = 0.5;
  state.viewer.activePlane = "sagittal";
  elements.jobPanel.classList.remove("hidden");
  elements.results.classList.add("hidden");
  elements.jobTitle.textContent = `Job ${jobId}`;
  elements.statusPill.textContent = "Queued";
  elements.progressBar.style.width = "18%";
  elements.jobMessage.textContent = "Upload persisted. Waiting for inference runner.";
  elements.jobPanel.scrollIntoView({ behavior: "smooth", block: "center" });
  pollJob();
}

async function pollJob() {
  clearTimeout(state.pollTimer);
  try {
    const job = await request(`/api/jobs/${state.job.id}`);
    state.job = job;
    elements.statusPill.textContent = job.status;
    if (job.status === "queued") {
      elements.progressBar.style.width = "18%";
      elements.jobMessage.textContent = "Upload persisted. Waiting for inference runner.";
    } else if (job.status === "running") {
      elements.progressBar.style.width = "62%";
      elements.jobMessage.textContent = "Inference subprocess active. Capturing output and timing.";
    } else if (job.status === "completed") {
      elements.progressBar.style.width = "100%";
      elements.jobMessage.textContent = "Structured result and viewer artifacts ready.";
      renderResult(job);
      return;
    } else if (job.status === "failed") {
      elements.progressBar.style.width = "100%";
      elements.progressBar.style.background = "var(--danger)";
      elements.jobMessage.textContent = job.error || "Inference failed.";
      return;
    }
    state.pollTimer = setTimeout(pollJob, 900);
  } catch (error) {
    elements.jobMessage.textContent = error.message;
    state.pollTimer = setTimeout(pollJob, 1800);
  }
}

function configureViewer(job) {
  const shape = job.result.volume.shape;
  document.querySelectorAll(".viewer-card").forEach((card) => {
    const plane = card.dataset.plane;
    if (!plane) return;
    state.viewer.depths[plane] = planeDepth(shape, plane);
    applyFrameGeometry(card.querySelector(".image-frame"), job, plane);
  });
  setFocusPlane(state.viewer.activePlane, false);
  setGlobalProgress(state.viewer.globalProgress);
}

function updatePlane(plane) {
  if (!state.job?.id) return;
  const card = document.querySelector(`.viewer-card[data-plane="${plane}"]`);
  const slider = card.querySelector(".slice-slider");
  const depth = state.viewer.depths[plane] || 1;
  const value = clamp(state.viewer.indices[plane], 0, depth - 1);
  const counter = `${value + 1} / ${depth}`;
  state.viewer.indices[plane] = value;
  slider.max = String(depth - 1);
  slider.value = String(value);
  card.querySelector(".slice-value").textContent = counter;
  card.querySelector(".slice-output").textContent = counter;
  if (state.viewer.activePlane === plane) updateFocusControls();
  scheduleSliceLoad(plane);
}

function updateFocusControls() {
  const plane = state.viewer.activePlane;
  const depth = state.viewer.depths[plane] || 1;
  const value = clamp(state.viewer.indices[plane], 0, depth - 1);
  const counter = `${value + 1} / ${depth}`;
  elements.focusPlaneLabel.textContent = `${plane} inspection`;
  elements.focusSliceValue.textContent = counter;
  elements.focusSliceSlider.max = String(depth - 1);
  elements.focusSliceSlider.value = String(value);
  elements.focusSliceOutput.textContent = counter;
  document.querySelectorAll(".viewer-thumb").forEach((card) => {
    card.classList.toggle("is-focused", card.dataset.plane === plane);
  });
  if (state.job?.result) applyFrameGeometry(elements.focusFrame, state.job, plane);
  if (state.viewer.sliceUrls[plane]) {
    elements.focusImage.src = state.viewer.sliceUrls[plane];
  }
}

function setFocusPlane(plane, shouldRender = true) {
  state.viewer.activePlane = plane;
  updateFocusControls();
  if (shouldRender) scheduleSliceLoad(plane);
}

function setPlaneImages(plane, url) {
  document.querySelectorAll(`[data-plane-image="${plane}"]`).forEach((image) => {
    image.src = url;
  });
  if (state.viewer.activePlane === plane) {
    elements.focusImage.src = url;
  }
}

async function loadPlaneImage(plane) {
  if (!state.job?.id) return;
  state.viewer.lastRenderAt[plane] = Date.now();
  state.viewer.sliceControllers[plane]?.abort();
  const controller = new AbortController();
  state.viewer.sliceControllers[plane] = controller;
  const index = state.viewer.indices[plane];
  const overlay = elements.overlayToggle.checked;
  try {
    const response = await fetch(
      `/api/jobs/${state.job.id}/slice?plane=${plane}&index=${index}&overlay=${overlay}`,
      { signal: controller.signal },
    );
    if (!response.ok) return;
    const blob = await response.blob();
    if (controller.signal.aborted) return;
    const nextUrl = URL.createObjectURL(blob);
    if (state.viewer.sliceUrls[plane]) {
      URL.revokeObjectURL(state.viewer.sliceUrls[plane]);
    }
    state.viewer.sliceUrls[plane] = nextUrl;
    setPlaneImages(plane, nextUrl);
  } catch (error) {
    if (error.name !== "AbortError") {
      console.error(error);
    }
  }
}

function scheduleSliceLoad(plane) {
  const interval = plane === "axial" ? 120 : 80;
  const elapsed = Date.now() - state.viewer.lastRenderAt[plane];
  if (elapsed >= interval) {
    clearTimeout(state.viewer.renderTimers[plane]);
    state.viewer.renderTimers[plane] = null;
    loadPlaneImage(plane);
    return;
  }
  if (state.viewer.renderTimers[plane]) return;
  state.viewer.renderTimers[plane] = setTimeout(() => {
    state.viewer.renderTimers[plane] = null;
    loadPlaneImage(plane);
  }, interval - elapsed);
}

function setPlaneIndex(plane, index) {
  state.viewer.indices[plane] = clamp(index, 0, Math.max(0, state.viewer.depths[plane] - 1));
  updatePlane(plane);
}

function setGlobalProgress(progress) {
  state.viewer.globalProgress = clamp(progress, 0, 1);
  elements.syncSliceSlider.value = String(Math.round(state.viewer.globalProgress * 1000));
  elements.syncSliceOutput.textContent = `${Math.round(state.viewer.globalProgress * 100)}%`;
  if (!state.job?.id) return;
  PLANES.forEach((plane) => {
    state.viewer.indices[plane] = indexFromProgress(plane, state.viewer.globalProgress);
    updatePlane(plane);
  });
}

function renderViewerStructures(labels) {
  const topLabels = [...(labels || [])]
    .sort((left, right) => right.voxel_count - left.voxel_count)
    .slice(0, 6);
  elements.viewerStructureList.replaceChildren();
  topLabels.forEach((label) => {
    const row = document.createElement("div");
    row.className = "viewer-structure-row";
    const swatch = document.createElement("i");
    swatch.style.background = label.color;
    const name = document.createElement("span");
    name.textContent = label.name;
    const count = document.createElement("small");
    count.textContent = Number(label.voxel_count).toLocaleString();
    row.append(swatch, name, count);
    elements.viewerStructureList.append(row);
  });
}

function renderResult(job) {
  const result = job.result;
  elements.results.classList.remove("hidden");
  elements.resultSummary.textContent = result.summary || "Inference completed.";
  elements.resultDisclaimer.textContent = result.disclaimer || "";

  const volume = result.volume || {};
  elements.metrics.replaceChildren(
    createDefinition("Shape", (volume.shape || []).join(" × ")),
    createDefinition("Spacing", `${(volume.spacing_mm || []).join(" × ")} mm`),
    createDefinition("HU range", `${volume.minimum_hu} to ${volume.maximum_hu}`),
    createDefinition("Upload", formatBytes(job.upload_size_bytes)),
  );

  const evaluation = result.evaluation;
  if (evaluation) {
    elements.evaluationCard.classList.remove("hidden");
    elements.evaluationSummary.textContent = evaluation.summary || "Evaluation complete.";
    elements.evaluationWarning.textContent = evaluation.warning || evaluation.error || "";
    elements.scoreStrip.replaceChildren(
      createDefinition("Mean Dice", formatScore(evaluation.mean_dice), "Average overlap score; 1.0 is perfect."),
      createDefinition("Mean IoU", formatScore(evaluation.mean_iou), "Average overlap divided by union; stricter than Dice."),
      createDefinition("Matched", `${evaluation.matched_labels || 0} / ${evaluation.ground_truth_labels || 0}`, "Predicted labels compared with reference masks."),
      createDefinition("Predicted", String(evaluation.predicted_labels || 0), "Structures returned by the model adapter."),
    );
    elements.evaluationRows.replaceChildren();
    (evaluation.labels || []).forEach((row) => {
      const tr = document.createElement("tr");
      [row.name, formatScore(row.dice), formatScore(row.iou), row.false_positive_voxels, row.false_negative_voxels].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = Number.isFinite(value) ? Number(value).toLocaleString() : String(value);
        tr.append(cell);
      });
      elements.evaluationRows.append(tr);
    });
  } else {
    elements.evaluationCard.classList.add("hidden");
    elements.scoreStrip.replaceChildren();
    elements.evaluationRows.replaceChildren();
  }

  elements.labelList.replaceChildren();
  (result.labels || []).forEach((label) => {
    const row = document.createElement("div");
    row.className = "label-row";
    const swatch = document.createElement("i");
    swatch.style.background = label.color;
    const name = document.createElement("span");
    name.textContent = label.name;
    const count = document.createElement("small");
    count.textContent = `${Number(label.voxel_count).toLocaleString()} vox`;
    row.append(swatch, name, count);
    elements.labelList.append(row);
  });
  renderViewerStructures(result.labels || []);

  const execution = job.execution || {};
  elements.traceList.replaceChildren(
    createDefinition("Adapter", job.adapter),
    createDefinition("Exit code", String(execution.exit_code)),
    createDefinition("Duration", `${execution.duration_ms} ms`),
    createDefinition("Command", execution.command),
  );

  const downloads = [
    ...(result.downloads || []),
    { name: "stdout log", path: "logs/stdout.log" },
    { name: "stderr log", path: "logs/stderr.log" },
    { name: "execution trace", path: "logs/execution.json" },
    { name: "job record", path: "job.json" },
  ];
  elements.downloadList.replaceChildren();
  downloads.forEach((download) => {
    const link = document.createElement("a");
    link.href = `/api/jobs/${job.id}/artifacts/${download.path}`;
    link.textContent = `Download ${download.name}`;
    elements.downloadList.append(link);
  });

  configureViewer(job);
  elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submitUpload(event) {
  event.preventDefault();
  if (!state.file) return;
  elements.uploadButton.disabled = true;
  const body = new FormData();
  body.append("file", state.file);
  try {
    const job = await request("/api/jobs", { method: "POST", body });
    showJob(job.job_id);
  } catch (error) {
    elements.fileLabel.textContent = error.message;
  } finally {
    elements.uploadButton.disabled = !state.file;
  }
}

async function submitSample() {
  elements.sampleButton.disabled = true;
  try {
    const job = await request("/api/jobs/sample", { method: "POST" });
    showJob(job.job_id);
  } catch (error) {
    elements.fileLabel.textContent = error.message;
  } finally {
    elements.sampleButton.disabled = !state.config?.sample_available;
  }
}

async function showDoctor() {
  elements.doctorSummary.textContent = "Running checks…";
  elements.doctorChecks.replaceChildren();
  elements.doctorDialog.showModal();
  try {
    const report = await request("/api/doctor");
    elements.doctorSummary.textContent = `${report.passed ? "Ready" : "Blocked"} · ${report.errors} errors · ${report.warnings} warnings`;
    report.checks.forEach((check) => {
      const row = document.createElement("div");
      row.className = "doctor-check";
      const status = document.createElement("strong");
      status.className = check.level;
      status.textContent = check.level;
      const content = document.createElement("div");
      const message = document.createElement("p");
      message.textContent = `${check.name}: ${check.message}`;
      content.append(message);
      if (check.suggestion) {
        const suggestion = document.createElement("small");
        suggestion.textContent = `Action: ${check.suggestion}`;
        content.append(suggestion);
      }
      row.append(status, content);
      elements.doctorChecks.append(row);
    });
  } catch (error) {
    elements.doctorSummary.textContent = error.message;
  }
}

async function initialize() {
  try {
    state.config = await request("/api/config");
    elements.adapterName.textContent = `${state.config.adapter} adapter`;
    elements.uploadLimit.textContent = `${state.config.max_upload_mb} MB limit`;
    elements.fileInput.accept = state.config.allowed_formats.join(",");
    elements.formatNote.textContent = `Accepted: ${state.config.allowed_formats.join(", ")}`;
    elements.sampleButton.disabled = !state.config.sample_available;
    if (state.config.sample_available) {
      elements.sampleButton.textContent = `Run ${state.config.sample_name}`;
    }
  } catch (error) {
    elements.adapterName.textContent = `Runtime unavailable: ${error.message}`;
    elements.sampleButton.disabled = true;
  }
}

elements.fileInput.addEventListener("change", () => setSelectedFile(elements.fileInput.files[0] || null));
elements.uploadForm.addEventListener("submit", submitUpload);
elements.sampleButton.addEventListener("click", submitSample);
document.querySelector("#doctor-button").addEventListener("click", showDoctor);
document.querySelector("#doctor-close").addEventListener("click", () => elements.doctorDialog.close());
elements.overlayToggle.addEventListener("change", () => {
  PLANES.forEach(updatePlane);
});
elements.syncSliceSlider.addEventListener("input", (event) => {
  setGlobalProgress(Number(event.target.value) / 1000);
});
document.querySelectorAll(".viewer-card").forEach((card) => {
  if (!card.dataset.plane) return;
  card.querySelector(".slice-slider").addEventListener("input", (event) => {
    setPlaneIndex(card.dataset.plane, Number(event.target.value));
  });
});
elements.focusSliceSlider.addEventListener("input", (event) => {
  setPlaneIndex(state.viewer.activePlane, Number(event.target.value));
});
document.querySelectorAll("[data-select-plane]").forEach((button) => {
  button.addEventListener("click", () => setFocusPlane(button.dataset.selectPlane));
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.uploadForm.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.uploadForm.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  elements.uploadForm.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.uploadForm.classList.remove("dragging");
  });
});
elements.uploadForm.addEventListener("drop", (event) => setSelectedFile(event.dataTransfer.files[0] || null));

initialize();
