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

/* ------------------------------------------------------------------ *
 * Verification log (evidence trail)
 * ------------------------------------------------------------------ */
const logEntries = [];

function addLog(action, coverType, verdict, ok, details) {
  const entry = { time: new Date().toISOString(), action, coverType, verdict, ok: !!ok, details };
  logEntries.push(entry);
  const tbody = $("#log-body");
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>${nowStr()}</td>
    <td>${action}</td>
    <td>${coverType}</td>
    <td><span class="log-badge ${ok ? "ok" : "bad"}">${verdict}</span></td>
    <td>${details || ""}</td>`;
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
  decode: { coverType: "image", stegoBytes: null, stegoBytesOriginal: null, stegoFilename: null },
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
    if (e.target.closest(".dz-preview")) return;
    input.click();
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
  const blobUrl = URL.createObjectURL(new Blob([bytes]));
  if (mime.startsWith("image/") || /\.(png|jpe?g|bmp)$/i.test(file.name)) {
    const img = document.createElement("img");
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
}

/* ---- Encode: cover dropzone (accepts any supported file, auto-detects type) ---- */
setupDropzone("encode-cover-drop", "encode-cover-input", async (file) => {
  const detected = detectCoverType(file);
  if (detected) {
    setActiveTab("encode-cover-type", detected);
    applyEncodeCoverType(detected);
  } // else: unrecognised file - keep whatever tab is currently selected, let the server explain if it's wrong

  const buf = new Uint8Array(await file.arrayBuffer());
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
  const buf = new Uint8Array(await file.arrayBuffer());
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
  updateDecodeButtonState();
}

// Accepts any supported stego file and auto-detects image/audio/video.
setupDropzone("decode-stego-drop", "decode-stego-input", async (file) => {
  const detected = detectCoverType(file);
  if (detected) {
    setActiveTab("decode-cover-type", detected);
    applyDecodeCoverType(detected);
  }

  const buf = new Uint8Array(await file.arrayBuffer());
  state.decode.stegoBytes = buf;
  state.decode.stegoBytesOriginal = buf.slice();
  state.decode.stegoFilename = file.name;
  renderFilePreview("decode-stego", file, buf, clearDecodeStego);
  updateDecodeButtonState();
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
    bar.textContent = "Could not check capacity (backend unreachable?).";
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
  $("#btn-encode").disabled = !(hasCover && hasPayload);
}

function updateDecodeButtonState() {
  const has = !!state.decode.stegoBytes;
  $("#btn-decode-sync").disabled = !has;
  $("#btn-decode-async").disabled = !has;
}

/* ------------------------------------------------------------------ *
 * Encode action
 * ------------------------------------------------------------------ */
$("#btn-encode").addEventListener("click", async () => {
  const btn = $("#btn-encode");
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

    renderEncodeResult(data);
    addLog(
      "Encode",
      state.encode.coverType,
      "OK",
      true,
      `LSBs=${data.num_lsb}, start=${data.start_index}, container=${data.container_size_bytes}B, capacity=${data.capacity_bytes}B`
    );
    // Compare (defined in compare.js) runs cover-vs-stego automatically so
    // the difference views are already waiting below, without an extra click.
    sendCoverAndStegoToCompare({ auto: true });
  } catch (e) {
    addLog("Encode", state.encode.coverType, "FAILED", false, e.message);
    alert(`Encoding failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "🔏 Sign & Embed Payload";
  }
});

let lastStego = null; // { bytes, filename, mime }

function renderEncodeResult(data) {
  const bytes = b64ToBytes(data.stego_base64);
  lastStego = { bytes, filename: data.stego_filename, mime: data.mime };

  const panel = $("#encode-result");
  panel.hidden = false;

  const preview = $("#encode-stego-preview");
  preview.innerHTML = "";
  const blobUrl = URL.createObjectURL(new Blob([bytes], { type: data.mime }));
  if (data.mime.startsWith("image/")) {
    const img = document.createElement("img");
    img.src = blobUrl;
    preview.appendChild(img);
  } else if (data.mime.startsWith("video/")) {
    const video = document.createElement("video");
    video.controls = true;
    video.style.maxHeight = "220px";
    video.src = blobUrl;
    preview.appendChild(video);
  } else {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = blobUrl;
    preview.appendChild(audio);
  }

  const kv = $("#encode-result-kv");
  kv.innerHTML = "";
  const payloadLabel =
    state.encode.payloadType === "text"
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
  state.decode.stegoBytes = lastStego.bytes.slice();
  state.decode.stegoBytesOriginal = lastStego.bytes.slice();
  state.decode.stegoFilename = lastStego.filename;
  state.decode.coverType = state.encode.coverType;

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
  addLog("Send to Party B", state.encode.coverType, "OK", true, "Stego file handed to Decode panel.");
});

/* ------------------------------------------------------------------ *
 * Negative-case tools
 * ------------------------------------------------------------------ */
$("#btn-tamper-payload").addEventListener("click", (e) => {
  if (!state.decode.stegoBytes) return;
  const bytes = state.decode.stegoBytes.slice();
  const offset = Math.max(64, Math.min(bytes.length - 8, Math.floor(bytes.length * 0.55)));
  bytes[offset] ^= 0x80; // flip a high (non-LSB) bit so this reads as visible-content tampering
  state.decode.stegoBytes = bytes;
  const fakeFile = fileFromBytes(bytes, state.decode.stegoFilename || "tampered", "");
  renderFilePreview("decode-stego", fakeFile, bytes, clearDecodeStego);
  addLog("Tamper tool", state.decode.coverType, "Applied", true, `Flipped bit at byte offset ${offset}`);
  flashButton(e.currentTarget, "✅ Bit flipped");
});

$("#btn-clear-tamper").addEventListener("click", (e) => {
  if (!state.decode.stegoBytesOriginal) return;
  state.decode.stegoBytes = state.decode.stegoBytesOriginal.slice();
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
    flashButton(btn, "✅ Loaded");
  }
});

$("#btn-mangle-key").addEventListener("click", async (e) => {
  const btn = e.currentTarget; // capture before the first await - see note on btn-gen-keys above
  const res = await fetch("/api/keys/decoy", { method: "POST" });
  const data = await res.json();
  if (data.public_key_pem) {
    $("#decode-public-key").value = data.public_key_pem;
    addLog("Negative case", state.decode.coverType, "Decoy key loaded", true, "Loaded an unrelated public key to demo Signature Invalid.");
    flashButton(btn, "✅ Decoy loaded");
  }
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

$("#btn-decode-sync").addEventListener("click", async () => {
  const btn = $("#btn-decode-sync");
  btn.disabled = true;
  btn.textContent = "Decoding…";
  try {
    const res = await fetch("/api/decode?mode=sync", { method: "POST", body: buildDecodeFormData() });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderDecodeResult(data);
  } catch (e) {
    addLog("Decode (sync)", state.decode.coverType, "FAILED", false, e.message);
    alert(`Decoding failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "🔎 Decode (Synchronous)";
    updateDecodeButtonState();
  }
});

$("#btn-decode-async").addEventListener("click", async () => {
  const btn = $("#btn-decode-async");
  const statusEl = $("#async-status");
  btn.disabled = true;
  statusEl.hidden = false;
  statusEl.textContent = "Submitted to background worker thread…";
  try {
    const res = await fetch("/api/decode?mode=async", { method: "POST", body: buildDecodeFormData() });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    const jobId = data.job_id;
    let attempts = 0;
    const poll = async () => {
      attempts++;
      const jr = await fetch(`/api/jobs/${jobId}`);
      const jdata = await jr.json();
      if (jdata.status === "pending") {
        statusEl.textContent = `Still running asynchronously… (poll #${attempts})`;
        setTimeout(poll, 400);
        return;
      }
      if (jdata.status === "error") throw new Error(jdata.error);
      statusEl.textContent = "Async job complete.";
      renderDecodeResult(jdata.result);
      btn.disabled = false;
      updateDecodeButtonState();
    };
    poll();
  } catch (e) {
    addLog("Decode (async)", state.decode.coverType, "FAILED", false, e.message);
    alert(`Async decoding failed: ${e.message}`);
    btn.disabled = false;
    updateDecodeButtonState();
  }
});

function renderDecodeResult(data) {
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
      audio.src = URL.createObjectURL(new Blob([bytes], { type: mime }));
      extracted.appendChild(audio);
    } else if (mime.startsWith("image/")) {
      const img = document.createElement("img");
      img.style.maxHeight = "160px";
      img.src = URL.createObjectURL(new Blob([bytes], { type: mime }));
      extracted.appendChild(img);
    } else if (mime.startsWith("video/")) {
      const video = document.createElement("video");
      video.controls = true;
      video.style.maxHeight = "200px";
      video.src = URL.createObjectURL(new Blob([bytes], { type: mime }));
      extracted.appendChild(video);
    }
    const link = document.createElement("a");
    link.className = "btn btn-secondary";
    link.textContent = `⬇️ Download extracted payload (${humanBytes(bytes.length)})`;
    link.href = URL.createObjectURL(new Blob([bytes], { type: mime }));
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
