"use strict";

// Encoding context describes the file; it never feeds the blind classifier.
(() => {
  const byId = (id) => document.getElementById(id);
  let report = null;
  let selectedFile = null;
  let encodingContext = null;
  let busy = false;

  function format(n, tail = false) {
    if (n == null || !Number.isFinite(n)) return "insufficient data";
    if (tail && n === 0) return "below numerical precision (returned 0)";
    if (n > 0 && n < 0.0001) return n.toExponential(4);
    return Number(n).toFixed(5);
  }
  const counts = (c) => `${c.regular} / ${c.singular} / ${c.unusable}`;
  function addRow(body, values) {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
  function clearResult() {
    report = null;
    byId("analysis-result").hidden = true;
    byId("btn-export-analysis").disabled = true;
    byId("analysis-status").textContent = "";
  }
  function updateSource() {
    byId("analysis-source").textContent = selectedFile
      ? `${encodingContext ? "Encoder output" : "Manual upload"}: ${selectedFile.name}`
      : "Select a PNG, or use 'Analyse this stego PNG' after encoding.";
  }
  function setBusy(value) {
    busy = value;
    for (const id of ["btn-analyse", "analysis-file", "analysis-window"]) byId(id).disabled = value;
    byId("btn-send-to-analysis").disabled = value || byId("btn-send-to-analysis").dataset.pngOutput !== "true";
  }
  byId("analysis-file").addEventListener("change", () => {
    selectedFile = byId("analysis-file").files[0] || null;
    encodingContext = null;
    clearResult();
    updateSource();
  });
  byId("analysis-window").addEventListener("input", clearResult);

  function render(result) {
    byId("analysis-details").open = false;
    byId("analysis-raw-details").open = false;
    byId("analysis-file-details").textContent = `${result.input.filename} - ${result.input.byte_length.toLocaleString()} bytes; ${result.image.width} x ${result.image.height}, ${result.image.mode}.`;
    byId("analysis-file-hash").textContent = `SHA-256 of analysed PNG: ${result.file_sha256}`;
    byId("analysis-encoding").hidden = !result.input.encoding_context;
    if (result.input.encoding_context) {
      const c = result.input.encoding_context;
      const usage = c.capacity_bytes > 0 ? (100 * c.container_bytes / c.capacity_bytes).toFixed(2) + "%" : "unavailable";
      byId("analysis-encoding-details").textContent = `LSB depth: ${c.num_lsb}; start: ${c.start_unit} carrier units; signed container: ${c.container_bytes.toLocaleString()} bytes; available capacity from start: ${c.capacity_bytes.toLocaleString()} bytes; capacity used: ${usage}.`;
    }
    byId("analysis-category").textContent = result.combined.category;
    byId("analysis-scores").textContent = `Chi-square tail score: ${format(result.scores.chi_square, true)}  |  RS score: ${format(result.scores.rs)}`;
    byId("analysis-interpretation").textContent = result.scores.chi_square == null
      ? "Insufficient data for the whole-image chi-square score."
      : result.scores.chi_square < result.combined.thresholds.chi_square
        ? "Weak whole-image evidence of pair equalisation. Hidden data may still be present, even when extraction succeeds."
        : "Whole-image value pairs show equalisation compatible with LSB replacement; other causes are possible.";
    byId("analysis-rows").replaceChildren();
    byId("analysis-window-rows").replaceChildren();
    const summaries = [];
    for (const name of ["L", "R", "G", "B"]) {
      const channel = result.channels[name];
      if (!channel) continue;
      addRow(byId("analysis-rows"), [name, `${format(channel.chi_square.statistic)} / ${channel.chi_square.degrees_of_freedom} / ${format(channel.chi_square.score, true)}`, counts(channel.rs.positive), counts(channel.rs.negative), format(channel.rs.score)]);
      const valid = channel.windows.filter((w) => w.score != null);
      const high = valid.filter((w) => w.score >= result.combined.thresholds.chi_square).length;
      const peak = valid.length ? Math.max(...valid.map((w) => w.score)) : null;
      summaries.push(`${name}: ${channel.windows.length} windows, effective size ${channel.effective_window_size}, ${valid.length} usable, ${high} at/above the reference threshold, peak ${format(peak, true)}`);
      channel.windows.forEach((w, index) => {
        const observation = w.score == null ? "Insufficient data" : w.score >= result.combined.thresholds.chi_square ? "At/above reference threshold" : "Below reference threshold";
        addRow(byId("analysis-window-rows"), [name, index + 1, `${w.start}-${w.stop}`, w.sample_count, `${format(w.statistic)} / ${w.degrees_of_freedom}`, format(w.score, true), observation]);
      });
    }
    byId("analysis-window-summary").textContent = `Requested window size: ${result.configuration.requested_window_size}. ${summaries.join(". ")}. Effective size may increase to limit each channel to 128 windows.`;
    byId("analysis-limitations").replaceChildren();
    for (const warning of result.limitations) {
      const item = document.createElement("li");
      item.textContent = warning;
      byId("analysis-limitations").appendChild(item);
    }
    byId("analysis-json").textContent = JSON.stringify(result, null, 2);
    byId("analysis-result").hidden = false;
    byId("btn-export-analysis").disabled = false;
  }

  async function runAnalysis() {
    if (busy) return;
    clearResult();
    const windowInput = byId("analysis-window");
    if (!selectedFile || !windowInput.reportValidity()) {
      byId("analysis-status").textContent = "Select a PNG and a valid window size.";
      return;
    }
    const file = selectedFile;
    const context = encodingContext ? { ...encodingContext } : null;
    if (file.size > 32 * 1024 * 1024) {
      byId("analysis-status").textContent = "Analysis supports PNG files up to 32 MiB.";
      return;
    }
    setBusy(true);
    byId("analysis-status").textContent = "Analysing exact PNG bytes...";
    try {
      const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
      const expectedHash = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
      const form = new FormData();
      form.append("image_file", file);
      form.append("window_size", windowInput.value);
      let response = await fetch("/api/analyse?mode=async", { method: "POST", body: form });
      let data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || "Analysis request failed.");
      const jobId = data.job_id;
      const deadline = Date.now() + 120000;
      let result;
      while (true) {
        if (Date.now() > deadline) throw new Error("Analysis timed out. Try a smaller image.");
        await new Promise((resolve) => setTimeout(resolve, 400));
        response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
        data = await response.json();
        if (!response.ok || data.error || data.status === "error") throw new Error(data.error || "Analysis failed.");
        if (data.status === "done") { result = data.result; break; }
      }
      if (result.file_sha256 !== expectedHash) throw new Error("Analysed file hash did not match the selected PNG. No result displayed.");
      result.input = { filename: file.name, byte_length: file.size,
        source: context ? "encoder_output" : "manual_upload", sha256_matches_selected_file: true,
        encoding_context: context, context_origin: context ? "Browser snapshot of encoder response; not inferred or independently verified" : null };
      result.display_version = "steganalysis-ui-3";
      render(result);
      report = result;
      byId("analysis-status").textContent = "Analysis complete. File match verified.";
    } catch (error) {
      clearResult();
      byId("analysis-status").textContent = error.message;
    } finally {
      setBusy(false);
    }
  }
  byId("btn-analyse").addEventListener("click", runAnalysis);
  window.StegoAnalysis = Object.freeze({
    isBusy: () => busy,
    analyseEncoded(file, context) {
      if (busy) return;
      selectedFile = file;
      // Allowlist non-secret explanatory settings; no payloads, keys or passwords.
      encodingContext = { num_lsb: context.num_lsb, start_unit: context.start_unit,
        container_bytes: context.container_bytes, capacity_bytes: context.capacity_bytes };
      byId("analysis-file").value = "";
      updateSource();
      byId("analysis-card").scrollIntoView({ behavior: "smooth", block: "start" });
      return runAnalysis();
    },
  });
  byId("btn-export-analysis").addEventListener("click", () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "steganalysis_report.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
