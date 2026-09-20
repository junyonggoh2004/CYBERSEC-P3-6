"use strict";

/* ------------------------------------------------------------------ *
 * Small shared helpers
 * ------------------------------------------------------------------ */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// Briefly swaps a button to a green "done" state with confirmation text, so
// clicking a one-shot action (tamper, reset, decoy key, ...) is obviously
// registered even when the main visible change happens elsewhere on the page.
function flashButton(btn, doneText, holdMs = 1200) {
  const originalText = btn.textContent;
  const originalWidth = btn.offsetWidth;
  btn.style.minWidth = `${originalWidth}px`;
  btn.textContent = doneText;
  btn.classList.add("btn-flash");
  clearTimeout(btn._flashTimer);
  btn._flashTimer = setTimeout(() => {
    btn.textContent = originalText;
    btn.classList.remove("btn-flash");
    btn.style.minWidth = "";
  }, holdMs);
}

const QUICKFILL = {
  short:
    "Explain how steganography can be used to embed hidden verification data in image and audio cover objects.",
  large:
    "This undergraduate project requires student teams to design, implement and demonstrate a GUI-based LSB Replacement steganography program (window-based or web-based) that protects and verifies both image and audio cover objects using steganography, hashing and digital signatures. The project focuses on practical cybersecurity concepts: hiding a verification payload inside an image and an audio file, signing relevant verification data, extracting the hidden payload, checking the digital signature, and demonstrating positive and negative verification cases.",
  custom:
    "CONFIDENTIAL - Team P3-6 release note: this stego object certifies that the attached media was approved for release by the digital media verification team on this date. Do not redistribute without checking the embedded signature.",
};

function nowStr() {
  return new Date().toLocaleTimeString();
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

function bytesToB64(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function fileFromBytes(bytes, filename, mime) {
  return new File([bytes], filename, { type: mime });
}

function humanBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

/* Shared preview ownership: replaced files must not leave object URLs alive. */
const previewUrls = new Map();
function releasePreviewUrl(slot) {
  if (previewUrls.has(slot)) URL.revokeObjectURL(previewUrls.get(slot));
  previewUrls.delete(slot);
}
function previewUrl(slot, bytes, mime = "") {
  releasePreviewUrl(slot);
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  previewUrls.set(slot, url);
  return url;
}
window.addEventListener("pagehide", () => {
  for (const slot of previewUrls.keys()) releasePreviewUrl(slot);
});

const comparisons = new Map();
const fileReadTokens = {};
let encodeRevision = 0;
let encodeBusy = false;
let decodeRevision = 0;
let decodeBusy = false;
function mediaDescriptor(bytes, name, kind, mime = "") {
  return bytes ? { bytes, name: name || "Selected file", kind, mime } : null;
}
function fitComparisonImages(view) {
  const loaded = view.images.filter(img => img.naturalWidth && img.naturalHeight);
  if (!loaded.length) return;
  // Use one pixels-to-CSS-pixels ratio for both images, including unlike dimensions.
  const scale = Math.min(1, ...loaded.flatMap(img => [
    (img.parentElement.clientWidth - 24) / img.naturalWidth,
    (img.parentElement.clientHeight - 24) / img.naturalHeight,
  ]));
  loaded.forEach(img => {
    img.style.width = `${Math.max(0, img.naturalWidth * scale)}px`;
    img.style.height = `${Math.max(0, img.naturalHeight * scale)}px`;
  });
}
function renderComparison(prefix, left, right) {
  const previous = comparisons.get(prefix);
  previous?.observer?.disconnect();
  const grid = $(`#${prefix}-comparison-grid`);
  const notice = $(`#${prefix}-comparison-note`);
  grid.replaceChildren(); notice.textContent = "";
  const view = { images: [], dimensions: [], failures: new Set(), observer: null };
  comparisons.set(prefix, view);
  const labels = prefix === "encode" ? ["Original cover", "Encoded stego object"] : ["Original reference", "Received stego object"];
  function updateNotice() {
    if (comparisons.get(prefix) !== view) return;
    const notes = [];
    if (left && right && left.kind !== right.kind) notes.push("The selected objects have different media types; choose a matching reference for comparison.");
    if (view.dimensions[0] && view.dimensions[1] && view.dimensions[0] !== view.dimensions[1]) notes.push("Image dimensions differ. Both are shown at the same scale; the reference is for comparison only.");
    notes.push(...view.failures);
    notice.textContent = notes.join(" ");
    fitComparisonImages(view);
  }
  [left, right].forEach((file, index) => {
    const slot = `${prefix}-comparison-${index}`;
    releasePreviewUrl(slot);
    const figure = document.createElement("figure"); figure.className = "comparison-card";
    const caption = document.createElement("figcaption"); caption.textContent = labels[index];
    const stage = document.createElement("div"); stage.className = "comparison-stage";
    const filename = document.createElement("p"); filename.className = "comparison-file";
    const meta = document.createElement("p"); meta.className = "comparison-meta";
    figure.append(caption, stage, filename, meta); grid.append(figure);
    if (!file) {
      const empty = document.createElement("p"); empty.className = "comparison-placeholder";
      empty.textContent = prefix === "encode"
        ? (index === 0 ? "Choose a cover to preview the original." : "Encode your payload to see the stego object here.")
        : (index === 0 ? "Add an optional original reference. You can verify without it." : "Choose a received stego file to compare.");
      stage.append(empty); filename.textContent = "No file selected"; meta.textContent = "—";
      return;
    }
    filename.textContent = file.name;
    meta.textContent = `${humanBytes(file.bytes.length)} · ${file.bytes.length.toLocaleString()} bytes`;
    const kind = file.kind || "image";
    const media = document.createElement(kind === "image" ? "img" : kind === "audio" ? "audio" : "video");
    if (kind === "image") {
      media.alt = `${labels[index]}: ${file.name}`; view.images.push(media);
      media.onload = () => {
        if (comparisons.get(prefix) !== view) return;
        view.dimensions[index] = `${media.naturalWidth} × ${media.naturalHeight}`;
        meta.textContent += ` · ${view.dimensions[index]} px`;
        updateNotice();
      };
    } else {
      media.controls = true; media.preload = "metadata";
      media.setAttribute("aria-label", `${labels[index]} playback: ${file.name}`);
      media.onloadedmetadata = () => {
        if (comparisons.get(prefix) !== view) return;
        if (Number.isFinite(media.duration)) meta.textContent += ` · ${media.duration.toFixed(2)} seconds`;
      };
    }
    media.onerror = () => {
      if (comparisons.get(prefix) !== view) return;
      const error = document.createElement("p"); error.className = "comparison-placeholder";
      error.textContent = "Preview unavailable. The file may be damaged or unsupported by this browser.";
      stage.replaceChildren(error); view.images = view.images.filter(img => img !== media);
      view.failures.add(`${labels[index]} cannot be previewed. Verification remains a separate check.`); updateNotice();
    };
    stage.append(media); media.src = previewUrl(slot, file.bytes, file.mime);
  });
  view.observer = new ResizeObserver(() => fitComparisonImages(view));
  view.observer.observe(grid); updateNotice();
}
function currentCover() {
  return mediaDescriptor(state.encode.coverBytes, state.encode.coverFilename, state.encode.coverType);
}
function refreshEncodeComparison() {
  renderComparison("encode", currentCover(), null);
  $("#encode-comparison-settings").textContent = state.encode.coverBytes
    ? `${$("#encode-num-lsb").value} LSB(s) selected · payload ${humanBytes(estimatePayloadSize())}. Encode to compare the saved output.`
    : "Choose a cover file to begin. The encoded object will appear alongside it.";
}
function invalidateEncodeResult() {
  encodeRevision++;
  lastStego = null;
  $("#encode-result").hidden = true;
  $("#encode-download-link").removeAttribute("href");
  releasePreviewUrl("encode-download");
  refreshEncodeComparison();
}
function refreshDecodeComparison() {
  renderComparison("decode", state.decode.reference,
    mediaDescriptor(state.decode.stegoBytes, state.decode.stegoFilename, state.decode.coverType));
}
function invalidateDecodeResult() {
  decodeRevision++;
  $("#demo-outcome").textContent = "";
  $("#decode-result").hidden = true;
  ["payload-media", "payload-download"].forEach(releasePreviewUrl);
  refreshDecodeComparison();
}

/* ------------------------------------------------------------------ *
 * Verification log (evidence trail)
 * ------------------------------------------------------------------ */
const logEntries = [];

function addLog(action, coverType, verdict, ok, details) {
  const entry = { time: new Date().toISOString(), action, coverType, verdict, ok: !!ok, details };
  logEntries.push(entry);
  const tbody = $("#log-body");
  const tr = document.createElement("tr");
  [nowStr(), action, coverType, verdict, details || ""].forEach((value, index) => {
    const cell = document.createElement("td");
    if (index === 3) {
      const badge = document.createElement("span");
      badge.className = `log-badge ${ok ? "ok" : "bad"}`;
      badge.textContent = value;
      cell.appendChild(badge);
    } else cell.textContent = value;
    tr.appendChild(cell);
  });
  tbody.prepend(tr);
}

$("#btn-clear-log").addEventListener("click", () => {
  logEntries.length = 0;
  $("#log-body").innerHTML = "";
});

$("#btn-export-log").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(logEntries, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "verification_log.json";
  a.click();
  URL.revokeObjectURL(url);
});

/* ------------------------------------------------------------------ *
 * Key panel
 * ------------------------------------------------------------------ */
async function loadPublicKey() {
  try {
    const res = await fetch("/api/keys/public");
    const data = await res.json();
    if (data.public_key_pem) {
      $("#decode-public-key").value = data.public_key_pem;
    invalidateDecodeResult();
      $("#key-status").textContent = "Key pair ready.";
    }
  } catch (e) {
    $("#key-status").textContent = "Could not reach backend - is app.py running?";
  }
}

$("#btn-gen-keys").addEventListener("click", async (e) => {
  const btn = e.currentTarget; // capture before the first await - the event object's
  // currentTarget is reset to null once the handler yields control (classic DOM gotcha)
  $("#key-status").textContent = "Generating…";
  try {
    const res = await fetch("/api/keys/generate", { method: "POST" });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    $("#decode-public-key").value = data.public_key_pem;
    invalidateDecodeResult();
    $("#key-status").textContent = "New key pair generated.";
    addLog("Generate keys", "-", "OK", true, "New RSA-2048 key pair generated.");
    flashButton(btn, "✅ Generated");
  } catch (e2) {
    $("#key-status").textContent = "Key generation failed.";
  }
});

$("#btn-show-key").addEventListener("click", async () => {
  const res = await fetch("/api/keys/public");
  const data = await res.json();
  $("#key-modal-content").textContent = data.public_key_pem || data.error;
  $("#key-modal").hidden = false;
});
$("#key-modal-close").addEventListener("click", () => ($("#key-modal").hidden = true));

/* ------------------------------------------------------------------ *
 * Cover-type detection - lets the dropzones accept any supported file and
 * figure out image/audio/video for themselves, instead of requiring the
 * user to click the right tab first. Tabs still work for manually forcing
 * a type, and stay in sync with whatever was auto-detected.
 * ------------------------------------------------------------------ */
const EXT_TO_COVER_TYPE = {
  png: "image", bmp: "image", jpg: "image", jpeg: "image",
  wav: "audio",
  mp4: "video", m4v: "video", mkv: "video", mov: "video", avi: "video", webm: "video",
};
const COVER_HINTS = {
  image: "PNG image required for lossless embedding",
  audio: "WAV/PCM (16-bit or 32-bit) required",
  video: "Hides the payload in the video's audio track - needs an audio track; output is produced as .mkv",
};

// Extension first (fast, and what a user would expect from a file's name);
// falls back to the browser-reported MIME type for extensionless/renamed
// files. Returns null if neither gives a confident answer.
function detectCoverType(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (EXT_TO_COVER_TYPE[ext]) return EXT_TO_COVER_TYPE[ext];
  const mime = file.type || "";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("video/")) return "video";
  return null;
}

/* ------------------------------------------------------------------ *
 * Tab bars (cover type selection) - both clickable and settable from code
 * ------------------------------------------------------------------ */
function setActiveTab(groupName, value) {
  document
    .querySelectorAll(`.tabbar[data-group="${groupName}"] .tab`)
    .forEach((t) => t.classList.toggle("active", t.dataset.value === value));
}

function setupTabbar(groupName, onChange) {
  const bar = document.querySelector(`.tabbar[data-group="${groupName}"]`);
  const btns = Array.from(bar.querySelectorAll(".tab"));
  btns.forEach((btn) => {
    btn.addEventListener("click", () => {
      setActiveTab(groupName, btn.dataset.value);
      onChange(btn.dataset.value);
    });
  });
}

const state = {
  encode: { coverType: "image", coverBytes: null, coverFilename: null, payloadType: "text", payloadBytes: null, payloadFilename: null, payloadMime: null },
  decode: { coverType: "image", stegoBytes: null, stegoBytesOriginal: null, stegoFilename: null, reference: null, modified: false },
};

// Applying a cover type never touches an already-loaded file by itself -
// callers decide whether to also clear/reset it (manual tab click: yes,
// since the old file no longer matches; auto-detect-on-drop: no, since the
// file *is* what set this type).
function applyEncodeCoverType(v) {
  state.encode.coverType = v;
  $("#encode-cover-hint").textContent = COVER_HINTS[v];
}
function applyDecodeCoverType(v) {
  state.decode.coverType = v;
}

setupTabbar("encode-cover-type", (v) => {
  applyEncodeCoverType(v);
  state.encode.coverBytes = null;
  state.encode.coverFilename = null;
  resetDropzonePreview("encode-cover");
  updateCapacity();
  updateEncodeButtonState();
});

setupTabbar("decode-cover-type", (v) => {
  applyDecodeCoverType(v);
  clearDecodeStego();
  resetDropzonePreview("decode-stego");
});

/* ------------------------------------------------------------------ *
 * Generic drag-and-drop wiring
 * ------------------------------------------------------------------ */
function setupDropzone(dzId, inputId, onFile) {
  const dz = document.getElementById(dzId);
  const input = document.getElementById(inputId);

  dz.addEventListener("click", (e) => {
    if (e.target === input || e.target.closest(".dz-preview")) return;
    input.click();
  });
  dz.tabIndex = 0;
  dz.setAttribute("role", "button");
  dz.setAttribute("aria-label", inputId === "decode-reference-input" ? "Choose optional original reference" : inputId === "decode-stego-input" ? "Choose received stego file" : inputId === "encode-cover-input" ? "Choose cover file" : "Choose payload file");
  dz.addEventListener("keydown", (e) => {
    if (e.target === dz && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => {
    if (input.files[0]) onFile(input.files[0]);
  });
  ["dragenter", "dragover"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.classList.remove("dragover");
    })
  );
  dz.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  });
}

function resetDropzonePreview(prefix) {
  fileReadTokens[prefix] = (fileReadTokens[prefix] || 0) + 1;
  releasePreviewUrl(`dropzone-${prefix}`);
  document.getElementById(`${prefix}-input`).value = "";
  document.getElementById(`${prefix}-preview`).hidden = true;
  document.getElementById(`${prefix}-preview`).innerHTML = "";
  document.querySelector(`#${prefix}-drop .dz-placeholder`).hidden = false;
}

// prefix must match: `${prefix}-drop` (dropzone), `${prefix}-preview`, `${prefix}-input` (file input)
// `onRemove` is called when the user clicks "Remove" - it should clear whatever
// app state held this file. Clicking "Change" always just reopens the file
// picker for the same input, so a new drop/pick fires onFile() again.
function renderFilePreview(prefix, file, bytes, onRemove) {
  const placeholder = document.querySelector(`#${prefix}-drop .dz-placeholder`);
  const preview = document.getElementById(`${prefix}-preview`);
  const input = document.getElementById(`${prefix}-input`);
  preview.innerHTML = "";
  placeholder.hidden = true;
  preview.hidden = false;

  const mime = file.type || "";
  const blobUrl = previewUrl(`dropzone-${prefix}`, bytes, mime);
  if (mime.startsWith("image/") || /\.(png|jpe?g|bmp)$/i.test(file.name)) {
    const img = document.createElement("img");
    img.alt = file.name;
    img.src = blobUrl;
    preview.appendChild(img);
  } else if (mime.startsWith("video/") || /\.(mp4|m4v|mkv|mov|avi|webm)$/i.test(file.name)) {
    const video = document.createElement("video");
    video.controls = true;
    video.style.maxHeight = "160px";
    video.style.maxWidth = "100%";
    video.src = blobUrl;
    preview.appendChild(video);
  } else if (mime.startsWith("audio/") || /\.(wav|mp3)$/i.test(file.name)) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = blobUrl;
    preview.appendChild(audio);
  }
  const label = document.createElement("div");
  label.className = "dz-filename";
  label.textContent = `📄 ${file.name} (${humanBytes(bytes.length)})`;
  preview.appendChild(label);

  const toolbar = document.createElement("div");
  toolbar.className = "dz-toolbar";
  const changeBtn = document.createElement("button");
  changeBtn.type = "button";
  changeBtn.className = "btn btn-small";
  changeBtn.textContent = "🔄 Change file";
  changeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (input) input.click();
  });
  toolbar.appendChild(changeBtn);

  if (onRemove) {
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-small btn-warn";
    removeBtn.textContent = "✕ Remove";
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      resetDropzonePreview(prefix);
      onRemove();
    });
    toolbar.appendChild(removeBtn);
  }
  preview.appendChild(toolbar);
  if (prefix === "decode-stego") invalidateDecodeResult();
}

/* ---- Encode: cover dropzone (accepts any supported file, auto-detects type) ---- */
setupDropzone("encode-cover-drop", "encode-cover-input", async (file) => {
  const selection = fileReadTokens["encode-cover"] = (fileReadTokens["encode-cover"] || 0) + 1;
  state.encode.coverBytes = null; updateCapacity(); updateEncodeButtonState();
  const detected = detectCoverType(file);
  if (detected) {
    setActiveTab("encode-cover-type", detected);
    applyEncodeCoverType(detected);
  } // else: unrecognised file - keep whatever tab is currently selected, let the server explain if it's wrong

  const buf = new Uint8Array(await file.arrayBuffer());
  if (selection !== fileReadTokens["encode-cover"]) return;
  state.encode.coverBytes = buf;
  state.encode.coverFilename = file.name;
  renderFilePreview("encode-cover", file, buf, () => {
    state.encode.coverBytes = null;
    state.encode.coverFilename = null;
    updateCapacity();
    updateEncodeButtonState();
  });
  updateCapacity();
  updateEncodeButtonState();
});

/* ---- Encode: payload file dropzone (for file/audio payload types) ---- */
setupDropzone("encode-payload-file-drop", "encode-payload-file-input", async (file) => {
  const selection = fileReadTokens["encode-payload-file"] = (fileReadTokens["encode-payload-file"] || 0) + 1;
  state.encode.payloadBytes = null; updateCapacity(); updateEncodeButtonState();
  const buf = new Uint8Array(await file.arrayBuffer());
  if (selection !== fileReadTokens["encode-payload-file"]) return;
  state.encode.payloadBytes = buf;
  state.encode.payloadFilename = file.name;
  state.encode.payloadMime = file.type || "application/octet-stream";
  renderFilePreview("encode-payload-file", file, buf, () => {
    state.encode.payloadBytes = null;
    state.encode.payloadFilename = null;
    state.encode.payloadMime = null;
    updateCapacity();
    updateEncodeButtonState();
  });
  updateCapacity();
  updateEncodeButtonState();
});

/* ---- Decode: stego dropzone ---- */
function clearDecodeStego() {
  state.decode.stegoBytes = null;
  state.decode.stegoBytesOriginal = null;
  state.decode.stegoFilename = null;
  invalidateDecodeResult();
  updateDecodeButtonState();
}

// Accepts any supported stego file and auto-detects image/audio/video.
setupDropzone("decode-stego-drop", "decode-stego-input", async (file) => {
  const selection = fileReadTokens["decode-stego"] = (fileReadTokens["decode-stego"] || 0) + 1;
  state.decode.stegoBytes = null; invalidateDecodeResult(); updateDecodeButtonState();
  const detected = detectCoverType(file);
  if (detected) {
    setActiveTab("decode-cover-type", detected);
    applyDecodeCoverType(detected);
  }

  const buf = new Uint8Array(await file.arrayBuffer());
  if (selection !== fileReadTokens["decode-stego"]) return;
  state.decode.stegoBytes = buf;
  state.decode.stegoBytesOriginal = buf.slice();
  state.decode.modified = false;
  state.decode.stegoFilename = file.name;
  renderFilePreview("decode-stego", file, buf, clearDecodeStego);
  updateDecodeButtonState();
});

setupDropzone("decode-reference-drop", "decode-reference-input", async (file) => {
  const selection = fileReadTokens["decode-reference"] = (fileReadTokens["decode-reference"] || 0) + 1;
  state.decode.reference = null;
  refreshDecodeComparison();
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (selection !== fileReadTokens["decode-reference"]) return;
  state.decode.reference = mediaDescriptor(bytes, file.name, detectCoverType(file), file.type);
  renderFilePreview("decode-reference", file, bytes, () => {
    state.decode.reference = null;
    refreshDecodeComparison();
  });
  refreshDecodeComparison();
});

/* ------------------------------------------------------------------ *
 * Payload type switching
 * ------------------------------------------------------------------ */
$("#encode-payload-type").addEventListener("change", (e) => {
  state.encode.payloadType = e.target.value;
  const isText = e.target.value === "text";
  $("#payload-text-block").hidden = !isText;
  $("#encode-payload-file-drop").hidden = isText;
  $("#encode-payload-file-input").accept = e.target.value === "audio" ? ".mp3,.wav,audio/*" : "";
  updateCapacity();
  updateEncodeButtonState();
});

$$('[data-fill]').forEach((btn) =>
  btn.addEventListener("click", () => {
    $("#encode-payload-text").value = QUICKFILL[btn.dataset.fill];
    updateCapacity();
    updateEncodeButtonState();
  })
);
$("#encode-payload-text").addEventListener("input", () => {
  updateCapacity();
  updateEncodeButtonState();
});

/* ------------------------------------------------------------------ *
 * LSB sliders + start-location mode toggles
 * ------------------------------------------------------------------ */
function wireSlider(sliderId, outId, onChange) {
  const slider = document.getElementById(sliderId);
  const out = document.getElementById(outId);
  slider.addEventListener("input", () => {
    out.textContent = slider.value;
    onChange();
  });
}
wireSlider("encode-num-lsb", "encode-num-lsb-out", updateCapacity);
wireSlider("decode-num-lsb", "decode-num-lsb-out", () => {});

function wireStartMode(prefix, onChange) {
  const select = document.getElementById(`${prefix}-start-mode`);
  select.addEventListener("change", () => {
    const isManual = select.value === "manual";
    document.getElementById(`${prefix}-offset-field`).hidden = !isManual;
    document.getElementById(`${prefix}-passphrase-field`).hidden = isManual;
    onChange();
  });
}
wireStartMode("encode", updateCapacity);
wireStartMode("decode", () => {});
$("#encode-offset").addEventListener("input", updateCapacity);
$("#encode-passphrase").addEventListener("input", updateCapacity);

/* ------------------------------------------------------------------ *
 * Live capacity check (encode side)
 * ------------------------------------------------------------------ */
let capacityTimer = null;
function updateCapacity() {
  invalidateEncodeResult();
  clearTimeout(capacityTimer);
  capacityTimer = setTimeout(doCapacityCheck, 250);
}

async function doCapacityCheck() {
  const bar = $("#encode-capacity-text");
  const fill = $("#encode-capacity-fill");
  if (!state.encode.coverBytes) {
    bar.textContent = "Load a cover file to see capacity…";
    fill.style.width = "0%";
    return;
  }
  const revision = encodeRevision;
  const fd = new FormData();
  fd.append("cover_type", state.encode.coverType);
  fd.append("num_lsb", $("#encode-num-lsb").value);
  fd.append("start_mode", $("#encode-start-mode").value);
  fd.append("manual_offset", $("#encode-offset").value || 0);
  fd.append("passphrase", $("#encode-passphrase").value || "");
  fd.append("cover_file", fileFromBytes(state.encode.coverBytes, state.encode.coverFilename || "cover", ""));

  try {
    const res = await fetch("/api/capacity", { method: "POST", body: fd });
    const data = await res.json();
    if (revision !== encodeRevision) return;
    if (data.error) {
      bar.textContent = `⚠️ ${data.error}`;
      fill.style.width = "100%";
      fill.classList.add("over");
      updateEncodeButtonState(false);
      return;
    }
    const payloadSize = estimatePayloadSize();
    const overheadEstimate = 64 + payloadSize; // rough container header overhead for the live bar
    const fits = overheadEstimate <= data.capacity_bytes;
    bar.textContent =
      `Capacity from start location: ${humanBytes(data.capacity_bytes)} · ` +
      `Payload (+header): ~${humanBytes(overheadEstimate)} · ` +
      (fits ? "✅ fits" : "❌ too large for this cover/start-location/LSB combination");
    const pct = Math.min(100, (overheadEstimate / Math.max(1, data.capacity_bytes)) * 100);
    fill.style.width = `${pct}%`;
    fill.classList.toggle("over", !fits);
    updateEncodeButtonState(fits);
  } catch (e) {
    if (revision === encodeRevision) bar.textContent = "Could not check capacity (backend unreachable?).";
  }
}

function estimatePayloadSize() {
  if (state.encode.payloadType === "text") {
    return new Blob([$("#encode-payload-text").value]).size;
  }
  return state.encode.payloadBytes ? state.encode.payloadBytes.length : 0;
}

function updateEncodeButtonState(fitsOverride) {
  const hasCover = !!state.encode.coverBytes;
  const hasPayload =
    state.encode.payloadType === "text"
      ? $("#encode-payload-text").value.trim().length > 0
      : !!state.encode.payloadBytes;
  $("#btn-encode").disabled = encodeBusy || !(hasCover && hasPayload);
}

function updateTamperControls() {
  const loaded = !!state.decode.stegoBytes;
  const changed = loaded && state.decode.modified;
  $("#btn-tamper-payload").disabled = !loaded || decodeBusy || changed;
  $("#btn-clear-tamper").disabled = !changed || decodeBusy;
  $("#tamper-state").textContent = !loaded ? "No file loaded" : changed ? "Modified copy" : "Unmodified copy";
  $("#tamper-state").classList.toggle("is-modified", !!changed);
  $("#tamper-help").textContent = !loaded
    ? "Load a received stego file to enable this test."
    : changed
      ? "One bit has changed. Run Decode to see the actual verdict, or reset to the file you loaded."
      : "Ready to test. A bit flip can damage PNG structure; the result may be Cannot Verify instead of Tampered. Use the guided WAV case for a controlled Tampered result.";
}
function updateDecodeButtonState() {
  updateTamperControls();
  const has = !!state.decode.stegoBytes;
  $("#btn-decode-sync").disabled = decodeBusy || !has;
  $("#btn-decode-async").disabled = decodeBusy || !has;
}

/* ------------------------------------------------------------------ *
 * Encode action
 * ------------------------------------------------------------------ */
$("#btn-encode").addEventListener("click", async () => {
  const btn = $("#btn-encode");
  const revision = encodeRevision;
  const snapshot = { cover: currentCover(), coverType: state.encode.coverType, payloadType: state.encode.payloadType, payloadSize: estimatePayloadSize() };
  if (!snapshot.cover || encodeBusy) return;
  snapshot.cover = { ...snapshot.cover, bytes: snapshot.cover.bytes.slice() };
  encodeBusy = true;
  $("#encode-feedback").textContent = "Encoding the selected cover…";
  btn.disabled = true;
  btn.textContent = "Encoding…";
  try {
    const fd = new FormData();
    fd.append("cover_type", state.encode.coverType);
    fd.append("num_lsb", $("#encode-num-lsb").value);
    fd.append("start_mode", $("#encode-start-mode").value);
    fd.append("manual_offset", $("#encode-offset").value || 0);
    fd.append("passphrase", $("#encode-passphrase").value || "");
    fd.append("media_id", $("#encode-media-id").value || "");
    fd.append("team_metadata", JSON.stringify({ team: "P3-6", tool: "Stego Integrity Verifier" }));
    fd.append("payload_type", state.encode.payloadType);
    fd.append(
      "cover_file",
      fileFromBytes(state.encode.coverBytes, state.encode.coverFilename || "cover", "")
    );

    if (state.encode.payloadType === "text") {
      fd.append("payload_text", $("#encode-payload-text").value);
    } else {
      if (!state.encode.payloadBytes) throw new Error("Please choose a payload file first.");
      fd.append(
        "payload_file",
        fileFromBytes(state.encode.payloadBytes, state.encode.payloadFilename || "payload.bin", state.encode.payloadMime || "")
      );
    }

    const res = await fetch("/api/encode", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    if (revision !== encodeRevision) {
      $("#encode-feedback").textContent = "Inputs changed while encoding. Encode again to compare the current selection.";
      return;
    }
    renderEncodeResult(data, snapshot);
    $("#encode-feedback").textContent = "Encoding complete. Compare the original and stego object below.";
    addLog(
      "Encode",
      state.encode.coverType,
      "OK",
      true,
      `LSBs=${data.num_lsb}, start=${data.start_index}, container=${data.container_size_bytes}B, capacity=${data.capacity_bytes}B`
    );
  } catch (e) {
    addLog("Encode", state.encode.coverType, "FAILED", false, e.message);
    $("#encode-feedback").textContent = `Encoding failed: ${e.message}`;
  } finally {
    encodeBusy = false;
    updateEncodeButtonState();
    btn.textContent = "🔏 Sign & Embed Payload";
  }
});

let lastStego = null; // { bytes, filename, mime }

function renderEncodeResult(data, snapshot) {
  const bytes = b64ToBytes(data.stego_base64);
  lastStego = { bytes, filename: data.stego_filename, mime: data.mime, original: snapshot.cover, coverType: snapshot.coverType };

  const panel = $("#encode-result");
  panel.hidden = false;

  const blobUrl = previewUrl("encode-download", bytes, data.mime);
  renderComparison("encode", snapshot.cover, mediaDescriptor(bytes, data.stego_filename, snapshot.coverType, data.mime));
  $("#encode-comparison-settings").textContent = `${data.num_lsb} LSB(s) · payload ${humanBytes(snapshot.payloadSize)} · complete package ${humanBytes(data.container_size_bytes)} · start ${data.start_index}`;

  const kv = $("#encode-result-kv");
  kv.innerHTML = "";
  const payloadLabel =
    snapshot.payloadType === "text"
      ? "(typed text message)"
      : data.metadata.filename || "(unnamed file)";
  const rows = [
    ["Payload file", payloadLabel],
    ["Start location (carrier units)", data.start_index],
    ["LSBs used", data.num_lsb],
    ["Container size", humanBytes(data.container_size_bytes)],
    ["Capacity from start", humanBytes(data.capacity_bytes)],
    ["Payload hash (SHA-256)", data.payload_hash_hex],
    ["Signature (RSA-2048, hex, truncated)", data.signature_hex.slice(0, 64) + "…"],
    ["Media ID", data.metadata.media_id],
  ];
  for (const [k, v] of rows) {
    const d1 = document.createElement("div");
    d1.className = "kv-key";
    d1.textContent = k;
    const d2 = document.createElement("div");
    d2.className = "kv-val";
    d2.textContent = v;
    kv.appendChild(d1);
    kv.appendChild(d2);
  }

  $("#encode-metadata-json").textContent = JSON.stringify(data.metadata, null, 2);

  const link = $("#encode-download-link");
  link.href = blobUrl;
  link.download = data.stego_filename;
}

$("#btn-send-to-decode").addEventListener("click", () => {
  if (!lastStego) return;
  for (const prefix of ["decode-stego", "decode-reference"]) {
    fileReadTokens[prefix] = (fileReadTokens[prefix] || 0) + 1;
  }
  state.decode.stegoBytes = lastStego.bytes.slice();
  state.decode.stegoBytesOriginal = lastStego.bytes.slice();
  state.decode.modified = false;
  state.decode.stegoFilename = lastStego.filename;
  state.decode.coverType = lastStego.coverType;
  state.decode.reference = { ...lastStego.original, bytes: lastStego.original.bytes.slice() };
  renderFilePreview("decode-reference", fileFromBytes(state.decode.reference.bytes, state.decode.reference.name, state.decode.reference.mime), state.decode.reference.bytes, () => {
    state.decode.reference = null; refreshDecodeComparison();
  });

  // Switch the decode tab to match, mirror settings a legitimate Party B
  // would have agreed on out-of-band, and load the file into the dropzone.
  setActiveTab("decode-cover-type", state.encode.coverType);
  $("#decode-num-lsb").value = $("#encode-num-lsb").value;
  $("#decode-num-lsb-out").textContent = $("#encode-num-lsb").value;
  $("#decode-start-mode").value = $("#encode-start-mode").value;
  $("#decode-offset-field").hidden = $("#encode-start-mode").value !== "manual";
  $("#decode-passphrase-field").hidden = $("#encode-start-mode").value === "manual";
  $("#decode-offset").value = $("#encode-offset").value;
  $("#decode-passphrase").value = $("#encode-passphrase").value;

  const fakeFile = fileFromBytes(lastStego.bytes, lastStego.filename, lastStego.mime);
  renderFilePreview("decode-stego", fakeFile, lastStego.bytes, clearDecodeStego);
  updateDecodeButtonState();
  addLog("Demo shortcut", state.encode.coverType, "OK", true, "Local copy and original reference loaded into Verify; this is not an actual transfer.");
  $("#decode-card").scrollIntoView({ behavior: "smooth", block: "start" });
});

/* ------------------------------------------------------------------ *
 * Negative-case tools
 * ------------------------------------------------------------------ */
$("#btn-tamper-payload").addEventListener("click", (e) => {
  if (!state.decode.stegoBytes || decodeBusy || state.decode.modified) return;
  const bytes = state.decode.stegoBytes.slice();
  const offset = Math.max(64, Math.min(bytes.length - 8, Math.floor(bytes.length * 0.55)));
  bytes[offset] ^= 0x80; // flip a high (non-LSB) bit so this reads as visible-content tampering
  state.decode.stegoBytes = bytes;
  state.decode.modified = true;
  updateTamperControls();
  const fakeFile = fileFromBytes(bytes, state.decode.stegoFilename || "tampered", "");
  renderFilePreview("decode-stego", fakeFile, bytes, clearDecodeStego);
  addLog("Tamper tool", state.decode.coverType, "Applied", true, `Flipped bit at byte offset ${offset}`);
  flashButton(e.currentTarget, "✅ Bit flipped");
});

$("#btn-clear-tamper").addEventListener("click", (e) => {
  if (!state.decode.stegoBytesOriginal || decodeBusy) return;
  state.decode.stegoBytes = state.decode.stegoBytesOriginal.slice();
  state.decode.modified = false;
  updateTamperControls();
  const fakeFile = fileFromBytes(state.decode.stegoBytes, state.decode.stegoFilename || "stego", "");
  renderFilePreview("decode-stego", fakeFile, state.decode.stegoBytes, clearDecodeStego);
  addLog("Tamper tool", state.decode.coverType, "Reset", true, "Restored original stego bytes.");
  flashButton(e.currentTarget, "✅ Restored");
});

$("#btn-use-server-key").addEventListener("click", async (e) => {
  const btn = e.currentTarget; // capture before the first await - see note on btn-gen-keys above
  const res = await fetch("/api/keys/public");
  const data = await res.json();
  if (data.public_key_pem) {
    $("#decode-public-key").value = data.public_key_pem;
    invalidateDecodeResult();
    flashButton(btn, "✅ Loaded");
  }
});

$("#btn-mangle-key").addEventListener("click", async (e) => {
  const btn = e.currentTarget; // capture before the first await - see note on btn-gen-keys above
  const res = await fetch("/api/keys/decoy", { method: "POST" });
  const data = await res.json();
  if (data.public_key_pem) {
    $("#decode-public-key").value = data.public_key_pem;
    invalidateDecodeResult();
    addLog("Negative case", state.decode.coverType, "Decoy key loaded", true, "Loaded an unrelated public key to demo Signature Invalid.");
    flashButton(btn, "✅ Decoy loaded");
  }
});

/* Guided cases change only the local receiver inputs; never the saved file or keys. */
const DEMO_CASES = {
  "positive-image": { kind: "image", expected: "Authentic", steps: [
    "Encode a PNG with the Short (Learning Outcome) quick-fill message. Check capacity first.",
    "Download and transfer the stego PNG to Party B. Load the downloaded file here.",
    "Use the sender's trusted public key and matching LSB/start settings, then decode. Record the extracted message and all three verification checks." ] },
  "positive-audio": { kind: "audio", expected: "Authentic", steps: [
    "Encode a WAV with the Large (Project Overview) quick-fill message. Check that the complete package fits.",
    "Transfer and download the stego WAV. Play both objects, then verify with matching settings and the trusted public key.",
    "Repeat with your team's custom payload to demonstrate a third message size." ] },
  "wrong-key": { kind: "image", expected: "Signature Invalid", action: "Load a decoy public key", steps: [
    "Load a valid stego PNG and first verify it as Authentic with matching settings.",
    "Prepare this case to load an unrelated public key, then decode again. The saved key pair is unchanged.",
    "Capture Signature Invalid. Afterwards click Use current server key (for files signed by this server), or reload the sender's trusted key." ] },
  "tampered-audio": { kind: "audio", expected: "Tampered", action: "Alter the loaded WAV copy", steps: [
    "Encode WAV at 1 LSB with Manual offset 700. Load the stego WAV and first verify it as Authentic.",
    "Keep the correct public key and matching manual settings. Prepare this case to flip a bit in the loaded audio copy, then decode.",
    "Capture Tampered and the failed cover-integrity check. Reset to original and verify again to show recovery." ] },
  "missing": { kind: "image", expected: "Payload Missing", action: "Use original reference as received PNG", steps: [
    "Choose an unencoded PNG in the optional Original reference selector. Use the correct public key.",
    "Prepare this case to copy that PNG into the received-file input and set 1 LSB, Manual offset 0. Then decode.",
    "Capture Payload Missing. Reload the actual stego PNG afterwards. The reference must really be an unencoded original." ] },
  "wrong-start": { expected: "Wrong Start Location", action: "Change the receiver passphrase", steps: [
    "Encode PNG or WAV using passphrase-derived start mode, then verify once with the correct passphrase.",
    "Prepare this case to change only the receiver passphrase, then decode. Keep the same LSB depth and trusted public key.",
    "Restore the agreed passphrase afterwards. A missing payload and a wrong start can be indistinguishable; this verdict uses the selected start mode." ] },
  "oversized": { expected: "Encoding rejected (capacity error)", steps: [
    "In Protect, choose a small cover and 1 LSB. Note usable embedding capacity.",
    "Choose a payload file larger than that capacity and attempt encoding. Capture the capacity warning and rejection; no new stego output should be produced.",
    "This is an encoding case, not a decode verdict. Compare package bytes (payload + metadata + signature) against capacity, not cover file size." ] },
  "invalid-key": { expected: "Cannot Verify", action: "Insert invalid public-key text", steps: [
    "Load a valid stego PNG or WAV with matching decoding settings.",
    "Prepare this case to replace the receiver key field with invalid text, then decode.",
    "Capture Cannot Verify, then restore the trusted public key." ] },
};
$("#demo-case").addEventListener("change", () => {
  const demo = DEMO_CASES[$("#demo-case").value];
  $("#demo-expected").textContent = demo ? `Expected result: ${demo.expected}` : "";
  $("#demo-steps").replaceChildren();
  for (const step of demo?.steps || []) {
    const li = document.createElement("li"); li.textContent = step; $("#demo-steps").append(li);
  }
  $("#btn-demo-prepare").hidden = !demo?.action;
  $("#btn-demo-prepare").textContent = demo?.action || "Prepare case";
  $("#demo-feedback").textContent = "";
  $("#demo-outcome").textContent = "";
});
$("#btn-demo-prepare").addEventListener("click", async () => {
  const button = $("#btn-demo-prepare");
  const id = $("#demo-case").value;
  const demo = DEMO_CASES[id];
  const feedback = $("#demo-feedback");
  if (decodeBusy) { feedback.textContent = "Wait for the current verification to finish."; return; }
  button.disabled = true;
  try {
    if (id === "missing") {
      const original = state.decode.reference;
      if (!original || original.kind !== "image" || !/\.png$/i.test(original.name)) throw new Error("Select an unencoded PNG as the Original reference first.");
      fileReadTokens["decode-stego"] = (fileReadTokens["decode-stego"] || 0) + 1;
      state.decode.stegoBytes = original.bytes.slice();
      state.decode.stegoBytesOriginal = original.bytes.slice();
      state.decode.modified = false;
      state.decode.stegoFilename = original.name;
      applyDecodeCoverType("image"); setActiveTab("decode-cover-type", "image");
      $("#decode-num-lsb").value = "1"; $("#decode-num-lsb-out").textContent = "1";
      $("#decode-start-mode").value = "manual"; $("#decode-offset").value = "0";
      $("#decode-offset-field").hidden = false; $("#decode-passphrase-field").hidden = true;
      renderFilePreview("decode-stego", fileFromBytes(original.bytes, original.name, "image/png"), original.bytes, clearDecodeStego);
      updateDecodeButtonState();
    } else {
      if (!state.decode.stegoBytes || (demo.kind && state.decode.coverType !== demo.kind)) throw new Error(`Load a valid ${demo.kind === "image" ? "PNG" : demo.kind === "audio" ? "WAV" : "PNG or WAV"} stego file first.`);
      if (id === "wrong-key") {
        const response = await fetch("/api/keys/decoy", { method: "POST" });
        const data = await response.json();
        if (!response.ok || !data.public_key_pem) throw new Error(data.error || "Could not load a decoy key.");
        if ($("#demo-case").value !== id) return;
        $("#decode-public-key").value = data.public_key_pem;
      } else if (id === "tampered-audio") {
        if ($("#decode-start-mode").value !== "manual" || $("#decode-num-lsb").value !== "1") throw new Error("Use a WAV encoded with 1 LSB and manual start mode. Keep the original matching offset.");
        $("#btn-tamper-payload").click();
      } else if (id === "wrong-start") {
        if ($("#decode-start-mode").value !== "passphrase") throw new Error("Use a file encoded in passphrase-derived mode first.");
        $("#decode-passphrase").value += "-wrong-demo";
      } else if (id === "invalid-key") {
        $("#decode-public-key").value = "INVALID PUBLIC KEY - ACW1 negative case";
      }
    }
    invalidateDecodeResult();
    feedback.textContent = "Case prepared. Run Decode to obtain the actual verdict; an expected result is not evidence until verified.";
    addLog("Demo setup", state.decode.coverType, "Prepared", true, `${id}: expected ${demo.expected}`);
  } catch (error) { feedback.textContent = error.message; }
  finally { button.disabled = false; }
});

/* ------------------------------------------------------------------ *
 * Decode action (sync + async)
 * ------------------------------------------------------------------ */
function buildDecodeFormData() {
  const fd = new FormData();
  fd.append("cover_type", state.decode.coverType);
  fd.append("num_lsb", $("#decode-num-lsb").value);
  fd.append("start_mode", $("#decode-start-mode").value);
  fd.append("manual_offset", $("#decode-offset").value || 0);
  fd.append("passphrase", $("#decode-passphrase").value || "");
  fd.append("public_key_pem", $("#decode-public-key").value || "");
  fd.append(
    "stego_file",
    fileFromBytes(state.decode.stegoBytes, state.decode.stegoFilename || "stego", "")
  );
  return fd;
}

async function runDecode(mode) {
  if (decodeBusy || !state.decode.stegoBytes) return;
  decodeBusy = true;
  const revision = decodeRevision;
  const kind = state.decode.coverType;
  const demoId = $("#demo-case").value;
  const status = $("#async-status");
  status.hidden = false;
  status.textContent = "Extracting and verifying the received file…";
  updateDecodeButtonState();
  try {
    const response = await fetch(`/api/decode?mode=${mode}`, { method: "POST", body: buildDecodeFormData() });
    let data = await response.json();
    if (data.error) throw new Error(data.error);
    if (mode === "async") {
      const jobId = data.job_id;
      const deadline = Date.now() + 120000;
      while (true) {
        if (Date.now() > deadline) throw new Error("Verification timed out. Try again with a smaller file.");
        await new Promise(resolve => setTimeout(resolve, 400));
        const result = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
        data = await result.json();
        if (!result.ok || data.status === "error") throw new Error(data.error || "Verification failed.");
        if (data.status === "done") { data = data.result; break; }
      }
    }
    if (revision !== decodeRevision) {
      status.textContent = "Received file or settings changed. Run verification again for the current selection.";
      return;
    }
    renderDecodeResult(data);
    const demo = DEMO_CASES[demoId];
    if (demo && demoId !== "oversized") {
      const matches = data.verdict === demo.expected && (!demo.kind || demo.kind === kind);
      const evidence = `Expected ${demo.expected}${demo.kind ? ` (${demo.kind})` : ""}; observed ${data.verdict} (${kind}). ${matches ? "Matches expected case result." : "Does not match this case; check the setup."}`;
      if ($("#demo-case").value === demoId) $("#demo-outcome").textContent = evidence;
      addLog("Demo result", kind, data.verdict, matches, `${demoId}: ${evidence}`);
    }
    status.textContent = "Verification complete. The reference and received object remain above for comparison.";
  } catch (error) {
    addLog(`Decode (${mode})`, kind, "FAILED", false, error.message);
    status.textContent = `Verification failed: ${error.message}`;
  } finally {
    decodeBusy = false;
    updateDecodeButtonState();
  }
}
$("#btn-decode-sync").addEventListener("click", () => runDecode("sync"));
$("#btn-decode-async").addEventListener("click", () => runDecode("async"));

function renderDecodeResult(data) {
  ["payload-media", "payload-download"].forEach(releasePreviewUrl);
  const panel = $("#decode-result");
  panel.hidden = false;

  const badge = $("#verdict-badge");
  badge.textContent = data.verdict;
  badge.className = `verdict-badge verdict-${data.verdict.replace(/\s+/g, "")}`;
  $("#verdict-detail").textContent = data.detail;

  const kv = $("#decode-result-kv");
  kv.innerHTML = "";
  const boolCell = (label, val) => {
    const d1 = document.createElement("div");
    d1.className = "kv-key";
    d1.textContent = label;
    const d2 = document.createElement("div");
    d2.className = `kv-val ${val === true ? "ok" : val === false ? "bad" : ""}`;
    d2.textContent = val === null || val === undefined ? "n/a" : val ? "✅ match / valid" : "❌ mismatch / invalid";
    kv.appendChild(d1);
    kv.appendChild(d2);
  };
  boolCell("Payload hash match", data.payload_hash_match);
  boolCell("Signature valid", data.signature_valid);
  boolCell("Cover (visible content) unchanged", data.cover_hash_match);
  const startRow = document.createElement("div");
  startRow.className = "kv-key";
  startRow.textContent = "Start location used";
  kv.appendChild(startRow);
  const startVal = document.createElement("div");
  startVal.className = "kv-val";
  startVal.textContent = data.start_index ?? "n/a";
  kv.appendChild(startVal);

  const extracted = $("#extracted-payload");
  extracted.innerHTML = "";
  if (data.data_base64) {
    const bytes = b64ToBytes(data.data_base64);
    const mime = data.data_mime || "application/octet-stream";

    const label = document.createElement("div");
    label.className = "dz-filename";
    label.textContent = data.data_filename ? `📄 ${data.data_filename} · ${mime}` : `📝 typed text · ${mime}`;
    extracted.appendChild(label);

    if (mime.startsWith("text/")) {
      const pre = document.createElement("pre");
      pre.textContent = new TextDecoder().decode(bytes);
      extracted.appendChild(pre);
    } else if (mime.startsWith("audio/")) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = previewUrl("payload-media", bytes, mime);
      extracted.appendChild(audio);
    } else if (mime.startsWith("image/")) {
      const img = document.createElement("img");
      img.style.maxHeight = "160px";
      img.src = previewUrl("payload-media", bytes, mime);
      extracted.appendChild(img);
    } else if (mime.startsWith("video/")) {
      const video = document.createElement("video");
      video.controls = true;
      video.style.maxHeight = "200px";
      video.src = previewUrl("payload-media", bytes, mime);
      extracted.appendChild(video);
    }
    const link = document.createElement("a");
    link.className = "btn btn-secondary";
    link.textContent = `⬇️ Download extracted payload (${humanBytes(bytes.length)})`;
    link.href = previewUrl("payload-download", bytes, mime);
    link.download = data.data_filename || "extracted_payload.bin";
    extracted.appendChild(document.createElement("br"));
    extracted.appendChild(link);
  } else {
    extracted.textContent = "No payload could be extracted.";
  }

  $("#decode-metadata-json").textContent = data.metadata ? JSON.stringify(data.metadata, null, 2) : "(none)";

  const ok = data.verdict === "Authentic";
  addLog(
    "Decode",
    state.decode.coverType,
    data.verdict,
    ok,
    `hash=${data.payload_hash_match}, sig=${data.signature_valid}, cover=${data.cover_hash_match}`
  );
}

/* ------------------------------------------------------------------ *
 * Init
 * ------------------------------------------------------------------ */
loadPublicKey();

// Comparison state follows inputs, independently of cryptographic verification.
$("#encode-media-id").addEventListener("input", updateCapacity);
["decode-num-lsb", "decode-start-mode", "decode-offset", "decode-passphrase", "decode-public-key"].forEach(id => {
  document.getElementById(id).addEventListener("input", invalidateDecodeResult);
});
const themeButton = $("#btn-theme");
function renderThemeButton() {
  const dark = document.documentElement.dataset.theme === "dark";
  themeButton.textContent = dark ? "Light theme" : "Dark theme";
  themeButton.setAttribute("aria-pressed", String(dark));
}
themeButton.addEventListener("click", () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("stego-theme", theme); } catch (_) {}
  renderThemeButton();
});
renderThemeButton();
refreshEncodeComparison();
refreshDecodeComparison();
