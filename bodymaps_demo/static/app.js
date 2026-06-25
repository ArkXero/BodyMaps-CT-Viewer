const PLANES = ["axial", "coronal", "sagittal"];
const STORAGE_KEYS = {
  recent: "bodymaps.recentJobs.v1",
  saved: "bodymaps.savedJobs.v1",
};
const WINDOW_PRESETS = {
  soft: { label: "Soft Tissue", windowWidth: 400, windowCenter: 40 },
  bone: { label: "Bone", windowWidth: 1800, windowCenter: 400 },
  lung: { label: "Lung", windowWidth: 1500, windowCenter: -600 },
  liver: { label: "Liver", windowWidth: 150, windowCenter: 30 },
};

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
    windowWidth: 400,
    windowCenter: 40,
    overlayOpacity: 0.58,
    hiddenLabels: new Set(),
    organStatsById: new Map(),
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
  windowWidthInput: document.querySelector("#window-width-input"),
  windowCenterInput: document.querySelector("#window-center-input"),
  overlayOpacityInput: document.querySelector("#overlay-opacity-input"),
  overlayOpacityOutput: document.querySelector("#overlay-opacity-output"),
  shareViewButton: document.querySelector("#share-view-button"),
  saveViewButton: document.querySelector("#save-view-button"),
  recentJobList: document.querySelector("#recent-job-list"),
  savedJobList: document.querySelector("#saved-job-list"),
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

function getMaxUploadBytes() {
  if (!state.config?.max_upload_mb) return null;
  return state.config.max_upload_mb * 1024 * 1024;
}

function canUploadSelectedFile() {
  if (!state.file) return false;
  const maxUploadBytes = getMaxUploadBytes();
  return !maxUploadBytes || state.file.size <= maxUploadBytes;
}

function setSelectedFile(file) {
  state.file = file;
  if (!file) {
    elements.fileLabel.textContent = "Drop BodyMaps bundle here or choose file";
    elements.uploadButton.disabled = true;
    return;
  }
  const maxUploadBytes = getMaxUploadBytes();
  if (maxUploadBytes && file.size > maxUploadBytes) {
    elements.fileLabel.textContent =
      `${file.name} · ${formatBytes(file.size)} · exceeds ${formatBytes(maxUploadBytes)} limit`;
    elements.uploadButton.disabled = true;
    return;
  }
  elements.fileLabel.textContent = `${file.name} · ${formatBytes(file.size)}`;
  elements.uploadButton.disabled = false;
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

function formatPlane(plane) {
  return `${plane.charAt(0).toUpperCase()}${plane.slice(1)}`;
}

function parseFiniteNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseHiddenLabels(value) {
  if (!value) return new Set();
  return new Set(
    value
      .split(",")
      .map((token) => Number(token.trim()))
      .filter((labelId) => Number.isInteger(labelId) && labelId > 0),
  );
}

function hiddenLabelsString() {
  return [...state.viewer.hiddenLabels].sort((left, right) => left - right).join(",");
}

function syncViewerInputs() {
  elements.windowWidthInput.value = String(Math.round(state.viewer.windowWidth));
  elements.windowCenterInput.value = String(Math.round(state.viewer.windowCenter));
  elements.overlayOpacityInput.value = String(Math.round(state.viewer.overlayOpacity * 100));
  elements.overlayOpacityOutput.textContent = `${Math.round(state.viewer.overlayOpacity * 100)}%`;
}

function loadStoredList(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter((item) => item?.jobId) : [];
  } catch {
    return [];
  }
}

function saveStoredList(key, entries) {
  try {
    localStorage.setItem(key, JSON.stringify(entries.slice(0, 12)));
  } catch {
    // Local history is optional; artifacts remain source of truth.
  }
}

function currentViewState() {
  const plane = state.viewer.activePlane;
  const depth = state.viewer.depths[plane] || 1;
  const progress = depth > 1 ? state.viewer.indices[plane] / (depth - 1) : state.viewer.globalProgress;
  return {
    jobId: state.job?.id || "",
    sourceName: state.job?.source_name || "completed job",
    savedAt: new Date().toISOString(),
    plane,
    progress: Number(clamp(progress, 0, 1).toFixed(4)),
    ww: Math.round(state.viewer.windowWidth),
    wc: Math.round(state.viewer.windowCenter),
    op: Number(state.viewer.overlayOpacity.toFixed(2)),
    hide: hiddenLabelsString(),
  };
}

function viewStateFromParams() {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get("job") || "";
  if (!jobId && !params.has("plane") && !params.has("progress")) return null;
  return {
    jobId,
    plane: PLANES.includes(params.get("plane")) ? params.get("plane") : state.viewer.activePlane,
    progress: clamp(parseFiniteNumber(params.get("progress"), state.viewer.globalProgress), 0, 1),
    ww: clamp(parseFiniteNumber(params.get("ww"), state.viewer.windowWidth), 1, 6000),
    wc: clamp(parseFiniteNumber(params.get("wc"), state.viewer.windowCenter), -2000, 2000),
    op: clamp(parseFiniteNumber(params.get("op"), state.viewer.overlayOpacity), 0, 1),
    hide: params.get("hide") || "",
  };
}

function applyViewState(viewState) {
  if (!viewState) return;
  if (PLANES.includes(viewState.plane)) {
    state.viewer.activePlane = viewState.plane;
  }
  state.viewer.globalProgress = clamp(parseFiniteNumber(viewState.progress, state.viewer.globalProgress), 0, 1);
  state.viewer.windowWidth = clamp(parseFiniteNumber(viewState.ww, state.viewer.windowWidth), 1, 6000);
  state.viewer.windowCenter = clamp(parseFiniteNumber(viewState.wc, state.viewer.windowCenter), -2000, 2000);
  state.viewer.overlayOpacity = clamp(parseFiniteNumber(viewState.op, state.viewer.overlayOpacity), 0, 1);
  state.viewer.hiddenLabels = parseHiddenLabels(viewState.hide);
  syncViewerInputs();
}

function updateShareUrl() {
  if (!state.job?.id) return "";
  const view = currentViewState();
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("job", view.jobId);
  url.searchParams.set("plane", view.plane);
  url.searchParams.set("progress", String(view.progress));
  url.searchParams.set("ww", String(view.ww));
  url.searchParams.set("wc", String(view.wc));
  url.searchParams.set("op", String(view.op));
  if (view.hide) url.searchParams.set("hide", view.hide);
  window.history.replaceState(null, "", url);
  return url.toString();
}

function rememberCompletedJob(job) {
  if (job.status !== "completed") return;
  const entry = currentViewState();
  entry.jobId = job.id;
  entry.sourceName = job.source_name || entry.sourceName;
  const recent = loadStoredList(STORAGE_KEYS.recent).filter((item) => item.jobId !== job.id);
  saveStoredList(STORAGE_KEYS.recent, [entry, ...recent].slice(0, 8));
}

function renderStoredJobs(container, key, emptyText) {
  const entries = loadStoredList(key);
  container.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("small");
    empty.className = "history-empty";
    empty.textContent = emptyText;
    container.append(empty);
    return;
  }

  entries.slice(0, 5).forEach((entry) => {
    const button = document.createElement("button");
    button.className = "history-item";
    button.type = "button";
    const name = document.createElement("span");
    name.textContent = entry.sourceName || entry.jobId;
    const meta = document.createElement("small");
    meta.textContent = `${formatPlane(entry.plane || "sagittal")} · ${entry.jobId}`;
    button.append(name, meta);
    button.addEventListener("click", () => restoreStoredJob(entry));
    container.append(button);
  });
}

function renderHistoryLists() {
  renderStoredJobs(elements.recentJobList, STORAGE_KEYS.recent, "No recent jobs");
  renderStoredJobs(elements.savedJobList, STORAGE_KEYS.saved, "No saved views");
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

function statsForLabel(labelId) {
  return state.viewer.organStatsById.get(Number(labelId)) || null;
}

function renderAllPlanes() {
  if (!state.job?.id) return;
  PLANES.forEach((plane) => scheduleSliceLoad(plane));
  updateShareUrl();
}

function syncLabelVisibilityControls() {
  document.querySelectorAll("[data-label-row]").forEach((row) => {
    const labelId = Number(row.dataset.labelRow);
    const hidden = state.viewer.hiddenLabels.has(labelId);
    row.classList.toggle("is-hidden", hidden);
    const checkbox = row.querySelector("input[type='checkbox']");
    if (checkbox) checkbox.checked = !hidden;
  });
}

function setLabelHidden(labelId, hidden) {
  if (hidden) {
    state.viewer.hiddenLabels.add(labelId);
  } else {
    state.viewer.hiddenLabels.delete(labelId);
  }
  syncLabelVisibilityControls();
  renderAllPlanes();
}

function setWindowSettings(changes) {
  state.viewer.windowWidth = clamp(
    parseFiniteNumber(changes.windowWidth, state.viewer.windowWidth),
    1,
    6000,
  );
  state.viewer.windowCenter = clamp(
    parseFiniteNumber(changes.windowCenter, state.viewer.windowCenter),
    -2000,
    2000,
  );
  state.viewer.overlayOpacity = clamp(
    parseFiniteNumber(changes.overlayOpacity, state.viewer.overlayOpacity),
    0,
    1,
  );
  syncViewerInputs();
  renderAllPlanes();
}

function sliceForStatPlane(stat, plane) {
  if (!stat) return null;
  const bestSlice = stat.best_slice_index?.[plane];
  if (Number.isInteger(bestSlice)) return bestSlice;
  const axis = { sagittal: 0, coronal: 1, axial: 2 }[plane];
  const centroid = stat.centroid_index?.[axis];
  return Number.isInteger(centroid) ? centroid : null;
}

function jumpToStructure(labelId) {
  const stat = statsForLabel(labelId);
  const plane = PLANES.includes(stat?.best_plane) ? stat.best_plane : state.viewer.activePlane;
  const slice = sliceForStatPlane(stat, plane);
  state.viewer.hiddenLabels.delete(labelId);
  syncLabelVisibilityControls();
  setFocusPlane(plane, false);
  if (Number.isInteger(slice)) {
    setPlaneIndex(plane, slice);
  } else {
    updateFocusControls();
    renderAllPlanes();
  }
}

function indexFromProgress(plane, progress) {
  const depth = state.viewer.depths[plane] || 1;
  return Math.round((depth - 1) * clamp(progress, 0, 1));
}

function showJob(jobId) {
  state.job = { id: jobId, status: "queued" };
  state.viewer.globalProgress = 0.5;
  state.viewer.activePlane = "sagittal";
  state.viewer.hiddenLabels = new Set();
  state.viewer.organStatsById = new Map();
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
  syncViewerInputs();
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
  elements.focusPlaneLabel.textContent = `${formatPlane(plane)} inspection`;
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
  if (!PLANES.includes(plane)) return;
  state.viewer.activePlane = plane;
  updateFocusControls();
  if (shouldRender) scheduleSliceLoad(plane);
  updateShareUrl();
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
  const params = new URLSearchParams({
    plane,
    index: String(index),
    overlay: String(overlay),
    window_center: String(state.viewer.windowCenter),
    window_width: String(state.viewer.windowWidth),
    overlay_opacity: String(state.viewer.overlayOpacity),
  });
  const hidden = hiddenLabelsString();
  if (hidden) params.set("hidden_labels", hidden);
  try {
    const response = await fetch(
      `/api/jobs/${state.job.id}/slice?${params.toString()}`,
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
  if (state.viewer.activePlane === plane) updateShareUrl();
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
  updateShareUrl();
}

function renderViewerStructures(labels) {
  const topLabels = [...(labels || [])]
    .sort((left, right) => right.voxel_count - left.voxel_count)
    .slice(0, 6);
  elements.viewerStructureList.replaceChildren();
  topLabels.forEach((label) => {
    const stat = statsForLabel(label.id);
    const row = document.createElement("div");
    row.className = "viewer-structure-row";
    row.dataset.labelRow = String(label.id);
    const swatch = document.createElement("i");
    swatch.style.background = label.color;
    const name = document.createElement("span");
    name.textContent = label.name;
    const count = document.createElement("small");
    count.textContent = stat?.volume_cm3
      ? `${stat.volume_cm3.toLocaleString()} cm3`
      : Number(label.voxel_count).toLocaleString();
    const jump = document.createElement("button");
    jump.className = "structure-jump-button";
    jump.type = "button";
    jump.textContent = "Target";
    jump.addEventListener("click", () => jumpToStructure(Number(label.id)));
    row.append(swatch, name, count, jump);
    elements.viewerStructureList.append(row);
  });
  syncLabelVisibilityControls();
}

function renderResult(job, options = {}) {
  const result = job.result;
  const shouldScroll = options.scroll !== false;
  state.viewer.organStatsById = new Map(
    (result.organ_stats?.labels || []).map((row) => [Number(row.id), row]),
  );
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
    const stat = statsForLabel(label.id);
    const row = document.createElement("div");
    row.className = "label-row";
    row.dataset.labelRow = String(label.id);
    const swatch = document.createElement("i");
    swatch.style.background = label.color;
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = !state.viewer.hiddenLabels.has(Number(label.id));
    toggle.setAttribute("aria-label", `Show ${label.name}`);
    toggle.addEventListener("change", () => {
      setLabelHidden(Number(label.id), !toggle.checked);
    });
    const name = document.createElement("span");
    name.textContent = label.name;
    const count = document.createElement("small");
    const mean = Number.isFinite(stat?.mean_hu) ? ` · ${stat.mean_hu} HU` : "";
    count.textContent = stat
      ? `${stat.volume_cm3.toLocaleString()} cm3${mean}`
      : `${Number(label.voxel_count).toLocaleString()} vox`;
    const jump = document.createElement("button");
    jump.className = "structure-jump-button";
    jump.type = "button";
    jump.textContent = "Target";
    jump.addEventListener("click", () => jumpToStructure(Number(label.id)));
    row.append(toggle, swatch, name, count, jump);
    elements.labelList.append(row);
  });
  syncLabelVisibilityControls();
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
  rememberCompletedJob(job);
  renderHistoryLists();
  updateShareUrl();
  if (shouldScroll) elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadCompletedJob(jobId, viewState = null, options = {}) {
  if (!jobId) return false;
  try {
    const job = await request(`/api/jobs/${jobId}`);
    if (job.status !== "completed") return false;
    if (viewState) applyViewState(viewState);
    state.job = job;
    elements.jobPanel.classList.remove("hidden");
    elements.jobTitle.textContent = `Job ${job.id}`;
    elements.statusPill.textContent = "Completed";
    elements.progressBar.style.width = "100%";
    elements.jobMessage.textContent = "Restored completed local job.";
    renderResult(job, { scroll: options.scroll });
    return true;
  } catch {
    return false;
  }
}

async function restoreStoredJob(entry) {
  applyViewState(entry);
  await loadCompletedJob(entry.jobId, entry, { scroll: true });
}

async function restoreInitialJob() {
  const shared = viewStateFromParams();
  if (shared) applyViewState(shared);
  if (shared?.jobId && (await loadCompletedJob(shared.jobId, shared, { scroll: false }))) {
    return;
  }
  const [recent] = loadStoredList(STORAGE_KEYS.recent);
  if (recent) {
    await loadCompletedJob(recent.jobId, recent, { scroll: false });
  }
}

async function shareCurrentView() {
  const url = updateShareUrl();
  if (!url) return;
  try {
    if (!navigator.clipboard) throw new Error("Clipboard unavailable.");
    await navigator.clipboard.writeText(url);
    elements.shareViewButton.textContent = "Copied";
  } catch {
    elements.shareViewButton.textContent = "URL ready";
  }
  setTimeout(() => {
    elements.shareViewButton.textContent = "Share view";
  }, 1400);
}

function saveCurrentView() {
  if (!state.job?.id) return;
  const entry = currentViewState();
  const saved = loadStoredList(STORAGE_KEYS.saved).filter((item) => item.jobId !== entry.jobId);
  saveStoredList(STORAGE_KEYS.saved, [entry, ...saved].slice(0, 8));
  renderHistoryLists();
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
    elements.uploadButton.disabled = !canUploadSelectedFile();
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
  syncViewerInputs();
  renderHistoryLists();
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
  await restoreInitialJob();
}

elements.fileInput.addEventListener("change", () => setSelectedFile(elements.fileInput.files[0] || null));
elements.uploadForm.addEventListener("submit", submitUpload);
elements.sampleButton.addEventListener("click", submitSample);
document.querySelector("#doctor-button").addEventListener("click", showDoctor);
document.querySelector("#doctor-close").addEventListener("click", () => elements.doctorDialog.close());
elements.overlayToggle.addEventListener("change", () => {
  renderAllPlanes();
});
elements.windowWidthInput.addEventListener("change", (event) => {
  setWindowSettings({ windowWidth: Number(event.target.value) });
});
elements.windowCenterInput.addEventListener("change", (event) => {
  setWindowSettings({ windowCenter: Number(event.target.value) });
});
elements.overlayOpacityInput.addEventListener("input", (event) => {
  setWindowSettings({ overlayOpacity: Number(event.target.value) / 100 });
});
elements.shareViewButton.addEventListener("click", shareCurrentView);
elements.saveViewButton.addEventListener("click", saveCurrentView);
document.querySelectorAll("[data-window-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const preset = WINDOW_PRESETS[button.dataset.windowPreset];
    if (preset) setWindowSettings(preset);
  });
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
document.querySelectorAll(".viewer-thumb").forEach((card) => {
  const selectPlane = () => setFocusPlane(card.dataset.plane);
  card.addEventListener("click", (event) => {
    if (event.target.closest("button, input, label, a")) return;
    selectPlane();
  });
  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    selectPlane();
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
