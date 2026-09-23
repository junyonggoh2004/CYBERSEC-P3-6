"use strict";

/* ------------------------------------------------------------------ *
 * Cover vs Stego direct comparison (PNG + WAV). Separate feature from
 * Steganalysis (analysis.js): this needs both the cover and the stego
 * object and computes exact differences, rather than statistically
 * inferring anything from a single suspect file. Reuses the small shared
 * helpers ($, humanBytes, setupDropzone, setActiveTab, renderFilePreview,
 * fileFromBytes, addLog, ...) defined at top level in app.js.
 * ------------------------------------------------------------------ */
const compareState = {
  type: "image",
  coverBytes: null, coverFilename: null,
  stegoBytes: null, stegoFilename: null,
  lastResult: null,
};

const COMPARE_STAT_LABELS = {
  width: "Width (px)", height: "Height (px)", has_alpha: "Has alpha channel",
  total_rgb_channels_compared: "Total RGB channels compared", changed_rgb_channels: "Changed RGB channels",
  percent_rgb_channels_changed: "% RGB channels changed", changed_pixels: "Changed pixels",
  percent_pixels_changed: "% pixels changed", max_abs_channel_difference: "Max |difference| (channel)",
  mean_abs_channel_difference: "Mean |difference| (channel)", changed_red_channels: "Changed Red channels",
  changed_green_channels: "Changed Green channels", changed_blue_channels: "Changed Blue channels",
  changed_alpha_channels: "Changed Alpha channels", max_abs_alpha_difference: "Max |difference| (alpha)",
  mean_abs_alpha_difference: "Mean |difference| (alpha)",
  sample_rate_hz: "Sample rate (Hz)", sample_width_bits: "Sample width (bits)", channels: "Channels",
  frames: "Frames", total_samples_compared: "Total samples compared", changed_samples: "Changed samples",
  percent_samples_changed: "% samples changed", max_abs_sample_difference: "Max |difference| (sample)",
  mean_abs_sample_difference: "Mean |difference| (sample)", rms_difference: "RMS difference",
};

function compareStatLabel(key) {
  return COMPARE_STAT_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtStatValue(key, value) {
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number" && key.startsWith("percent_")) return `${value.toFixed(2)}%`;
  if (typeof value === "number" && !Number.isInteger(value)) return value.toFixed(4);
  return String(value);
}

function clearCompareResult() {
  compareState.lastResult = null;
  document.getElementById("compare-result").hidden = true;
  document.getElementById("compare-status").textContent = "";
}

function updateCompareButtonState() {
  document.getElementById("btn-compare").disabled = !(compareState.coverBytes && compareState.stegoBytes);
}

function updateCompareAccept() {
  const accept = compareState.type === "audio" ? ".wav" : ".png";
  document.getElementById("compare-cover-input").accept = accept;
  document.getElementById("compare-stego-input").accept = accept;
}

function applyCompareType(v) {
  compareState.type = v;
  updateCompareAccept();
  document.getElementById("compare-image-view").hidden = v !== "image";
  document.getElementById("compare-audio-view").hidden = v !== "audio";
  clearCompareResult();
}

// A manual tab click means the user is switching media type - any
// already-loaded file no longer matches the new accept filter, so drop it
// (mirrors app.js's encode/decode cover-type tab behaviour).
setupTabbar("compare-type", (v) => {
  applyCompareType(v);
  compareState.coverBytes = null;
  compareState.coverFilename = null;
  compareState.stegoBytes = null;
  compareState.stegoFilename = null;
  resetDropzonePreview("compare-cover");
  resetDropzonePreview("compare-stego");
  updateCompareButtonState();
});

// Both return a Promise that resolves once the file is loaded and previewed,
// so callers (the auto-compare flow below) can await both files being ready
// before immediately running the comparison.
function handleCompareCoverFile(file) {
  return file.arrayBuffer().then((buf) => {
    const bytes = new Uint8Array(buf);
    compareState.coverBytes = bytes;
    compareState.coverFilename = file.name;
    renderFilePreview("compare-cover", file, bytes, () => {
      compareState.coverBytes = null;
      compareState.coverFilename = null;
      updateCompareButtonState();
    });
    clearCompareResult();
    updateCompareButtonState();
  });
}

function handleCompareStegoFile(file) {
  return file.arrayBuffer().then((buf) => {
    const bytes = new Uint8Array(buf);
    compareState.stegoBytes = bytes;
    compareState.stegoFilename = file.name;
    renderFilePreview("compare-stego", file, bytes, () => {
      compareState.stegoBytes = null;
      compareState.stegoFilename = null;
      updateCompareButtonState();
    });
    clearCompareResult();
    updateCompareButtonState();
  });
}

setupDropzone("compare-cover-drop", "compare-cover-input", handleCompareCoverFile);
setupDropzone("compare-stego-drop", "compare-stego-input", handleCompareStegoFile);

/* ------------------------------------------------------------------ *
 * Run comparison against whatever is currently loaded in compareState.
 * Shared by the manual "Compare cover vs stego" button and the automatic
 * post-encode flow below.
 * ------------------------------------------------------------------ */
async function runCompare() {
  const btn = document.getElementById("btn-compare");
  const statusEl = document.getElementById("compare-status");
  btn.disabled = true;
  statusEl.textContent = "Comparing…";
  clearCompareResult();
  try {
    const fd = new FormData();
    fd.append("cover_file", fileFromBytes(compareState.coverBytes, compareState.coverFilename || "cover", ""));
    fd.append("stego_file", fileFromBytes(compareState.stegoBytes, compareState.stegoFilename || "stego", ""));
    const endpoint = compareState.type === "audio" ? "/api/compare/audio" : "/api/compare/image";
    const res = await fetch(endpoint, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "Comparison failed.");
    compareState.lastResult = data;
    if (compareState.type === "audio") renderAudioComparison(data);
    else renderImageComparison(data);
    renderCompareStats(data.stats);
    document.getElementById("compare-json").textContent = JSON.stringify(data, null, 2);
    document.getElementById("compare-result").hidden = false;
    statusEl.textContent = "Comparison complete.";
    return true;
  } catch (e) {
    statusEl.textContent = `⚠️ ${e.message}`;
    return false;
  } finally {
    btn.disabled = false;
    updateCompareButtonState();
  }
}

document.getElementById("btn-compare").addEventListener("click", runCompare);

/* ------------------------------------------------------------------ *
 * Send cover + stego to Compare and run it immediately - no extra click
 * needed. Used both by the manual "Send cover + stego to Compare" button
 * and automatically right after a successful encode (see app.js's
 * #btn-encode handler). `auto=true` suppresses the video-cover alert since
 * the automatic post-encode call shouldn't interrupt the user with a popup.
 * ------------------------------------------------------------------ */
async function sendCoverAndStegoToCompare({ auto = false } = {}) {
  if (!lastStego || !state.encode.coverBytes) return;
  if (state.encode.coverType === "video") {
    if (!auto) {
      alert(
        "Direct comparison currently supports PNG and WAV covers only " +
        "(a video's payload lives in its audio track - extract that audio and compare it as WAV if needed)."
      );
    }
    return;
  }
  setActiveTab("compare-type", state.encode.coverType);
  applyCompareType(state.encode.coverType);

  const coverFile = fileFromBytes(state.encode.coverBytes, state.encode.coverFilename || "cover", "");
  const stegoFile = fileFromBytes(lastStego.bytes, lastStego.filename, lastStego.mime);
  await Promise.all([handleCompareCoverFile(coverFile), handleCompareStegoFile(stegoFile)]);

  const ok = await runCompare();

  // The difference is the whole point of arriving here straight from an
  // encode - default straight to the amplified-difference view instead of
  // making the user click past the (usually indistinguishable) overlay.
  if (ok && state.encode.coverType === "image") {
    setActiveTab("compare-image-mode", "amplified");
    document.getElementById("compare-overlay-panel").hidden = true;
    document.getElementById("compare-mask-panel").hidden = true;
    document.getElementById("compare-amp-panel").hidden = false;
  }

  addLog("Send to Compare", state.encode.coverType, ok ? "OK" : "FAILED", ok, "Cover + stego compared automatically.");
  // A manual click means the user wants to go look at it now; the automatic
  // post-encode call just gets it ready in the background so it's waiting
  // whenever the user scrolls down, without yanking them away from the
  // encode result (download link, etc.) they just produced.
  if (!auto) document.getElementById("compare-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("btn-send-to-compare").addEventListener("click", () => sendCoverAndStegoToCompare({ auto: false }));

function renderCompareStats(stats) {
  const kv = document.getElementById("compare-stats-kv");
  kv.innerHTML = "";
  for (const [key, value] of Object.entries(stats)) {
    if (key === "per_channel" || key === "alpha_note") continue;
    const d1 = document.createElement("div");
    d1.className = "kv-key";
    d1.textContent = compareStatLabel(key);
    const d2 = document.createElement("div");
    d2.className = "kv-val";
    d2.textContent = fmtStatValue(key, value);
    kv.appendChild(d1);
    kv.appendChild(d2);
  }
  if (stats.alpha_note) {
    const note = document.createElement("div");
    note.className = "kv-val";
    note.style.gridColumn = "1 / -1";
    note.textContent = `ℹ️ ${stats.alpha_note}`;
    kv.appendChild(note);
  }
  if (Array.isArray(stats.per_channel) && stats.per_channel.length > 1) {
    for (const ch of stats.per_channel) {
      const label = document.createElement("div");
      label.className = "kv-key";
      label.textContent = `Channel ${ch.channel} changed samples`;
      const val = document.createElement("div");
      val.className = "kv-val";
      val.textContent = `${ch.changed_samples} / ${ch.total_samples_compared} (${ch.percent_samples_changed.toFixed(2)}%), max |diff| ${ch.max_abs_sample_difference}, RMS ${ch.rms_difference.toFixed(4)}`;
      kv.appendChild(label);
      kv.appendChild(val);
    }
  }
}

/* ------------------------------------------------------------------ *
 * PNG comparison rendering: overlay (client-side, from the uploaded
 * files themselves) + change mask / amplified difference (server PNGs).
 * ------------------------------------------------------------------ */
function renderImageComparison(data) {
  const coverUrl = URL.createObjectURL(new Blob([compareState.coverBytes], { type: "image/png" }));
  const stegoUrl = URL.createObjectURL(new Blob([compareState.stegoBytes], { type: "image/png" }));
  document.getElementById("compare-overlay-cover").src = coverUrl;
  document.getElementById("compare-overlay-stego").src = stegoUrl;
  document.getElementById("compare-mask-img").src = `data:image/png;base64,${data.change_mask_png_base64}`;
  document.getElementById("compare-amp-img").src = `data:image/png;base64,${data.amplified_difference_over_cover_png_base64}`;
  document.getElementById("compare-amp-raw-img").src = `data:image/png;base64,${data.amplified_difference_png_base64}`;
  document.getElementById("compare-amp-factor").textContent = `×${data.amplification_factor} amplified`;
}

const opacitySlider = document.getElementById("compare-opacity-slider");
opacitySlider.addEventListener("input", () => {
  document.getElementById("compare-overlay-stego").style.opacity = opacitySlider.value / 100;
  document.getElementById("compare-opacity-out").textContent = `${opacitySlider.value}%`;
});

setupTabbar("compare-image-mode", (mode) => {
  document.getElementById("compare-overlay-panel").hidden = mode !== "overlay";
  document.getElementById("compare-mask-panel").hidden = mode !== "mask";
  document.getElementById("compare-amp-panel").hidden = mode !== "amplified";
});

/* ------------------------------------------------------------------ *
 * WAV comparison rendering: playback + waveform overlay + difference
 * waveform (drawn from the downsampled display arrays the backend
 * returns; full-precision arrays are never sent to the frontend).
 * ------------------------------------------------------------------ */
function renderAudioComparison(data) {
  const coverUrl = URL.createObjectURL(new Blob([compareState.coverBytes], { type: "audio/wav" }));
  const stegoUrl = URL.createObjectURL(new Blob([compareState.stegoBytes], { type: "audio/wav" }));
  document.getElementById("compare-audio-cover-player").src = coverUrl;
  document.getElementById("compare-audio-stego-player").src = stegoUrl;

  // Multichannel: overlay/difference canvases show channel 0; the full
  // per-channel breakdown is always available in the statistics table.
  const ch = data.waveform.channels[0];
  drawWaveformOverlay(document.getElementById("compare-waveform-canvas"), ch.cover, ch.stego);
  drawDifferenceWaveform(document.getElementById("compare-diff-canvas"), ch.difference);
}

function drawWaveformOverlay(canvas, coverArr, stegoArr) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height, mid = h / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "rgba(255,255,255,0.03)";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.15)";
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();

  const maxAmp = Math.max(1, ...coverArr.map(Math.abs), ...stegoArr.map(Math.abs));
  const plot = (arr, color, alpha) => {
    ctx.strokeStyle = color;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    arr.forEach((v, i) => {
      const x = (i / Math.max(1, arr.length - 1)) * w;
      const y = mid - (v / maxAmp) * mid * 0.95;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;
  };
  plot(coverArr, "#5b8cff", 1);
  plot(stegoArr, "#38d0b0", 0.75);
}

function drawDifferenceWaveform(canvas, diffArr) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height, mid = h / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "rgba(255,255,255,0.03)";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.15)";
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();

  const maxAbs = Math.max(1, ...diffArr.map(Math.abs));
  ctx.strokeStyle = "#f2a33c";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  diffArr.forEach((v, i) => {
    const x = (i / Math.max(1, diffArr.length - 1)) * w;
    const y = mid - (v / maxAbs) * mid * 0.95;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#9aa5c0";
  ctx.font = "11px sans-serif";
  ctx.fillText(`visually magnified - full scale = ±${maxAbs} raw sample units`, 6, 14);
}

/* ------------------------------------------------------------------ *
 * Init
 * ------------------------------------------------------------------ */
updateCompareAccept();
updateCompareButtonState();
