"use strict";

// Independent of encode/decode state and the cryptographic verification log.
(() => {
  const byId = (id) => document.getElementById(id);
  let report = null;
  const format = (n) => n == null ? "insufficient data" : Number(n).toFixed(5);
  const counts = (c) => `${c.regular} / ${c.singular} / ${c.unusable}`;
  function clearResult() {
    report = null;
    byId("analysis-result").hidden = true;
    byId("btn-export-analysis").disabled = true;
    byId("analysis-status").textContent = "";
  }
  byId("analysis-file").addEventListener("change", clearResult);
  byId("analysis-window").addEventListener("input", clearResult);
  byId("btn-analyse").addEventListener("click", async () => {
    clearResult();
    const file = byId("analysis-file").files[0];
    const windowInput = byId("analysis-window");
    if (!file || !windowInput.reportValidity()) {
      byId("analysis-status").textContent = "Select a PNG and a valid window size.";
      return;
    }
    const controls = ["btn-analyse", "analysis-file", "analysis-window"];
    controls.forEach((id) => { byId(id).disabled = true; });
    byId("analysis-status").textContent = "Analysing PNG...";
    try {
      const form = new FormData();
      form.append("image_file", file);
      form.append("window_size", windowInput.value);
      let response = await fetch("/api/analyse?mode=async", { method: "POST", body: form });
      let data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || "Analysis request failed.");
      const jobId = data.job_id;
      const deadline = Date.now() + 120000;
      while (true) {
        if (Date.now() > deadline) throw new Error("Analysis timed out. Try a smaller image.");
        await new Promise((resolve) => setTimeout(resolve, 400));
        response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
        data = await response.json();
        if (!response.ok || data.status === "error") throw new Error(data.error || "Analysis failed.");
        if (data.status === "done") { report = data.result; break; }
      }
      byId("analysis-category").textContent = report.combined.category;
      byId("analysis-scores").textContent = `Chi-square score: ${format(report.scores.chi_square)} (threshold ${report.combined.thresholds.chi_square}); RS asymmetry: ${format(report.scores.rs)} (threshold ${report.combined.thresholds.rs}).`;
      byId("analysis-rows").replaceChildren();
      for (const [name, channel] of Object.entries(report.channels)) {
        const row = document.createElement("tr");
        for (const value of [name, `${format(channel.chi_square.statistic)} / ${channel.chi_square.degrees_of_freedom} / ${format(channel.chi_square.score)}`, counts(channel.rs.positive), counts(channel.rs.negative), format(channel.rs.score)]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.appendChild(cell);
        }
        byId("analysis-rows").appendChild(row);
      }
      byId("analysis-limitations").replaceChildren();
      for (const warning of report.limitations) {
        const item = document.createElement("li");
        item.textContent = warning;
        byId("analysis-limitations").appendChild(item);
      }
      byId("analysis-json").textContent = JSON.stringify(report, null, 2);
      byId("analysis-result").hidden = false;
      byId("btn-export-analysis").disabled = false;
      byId("analysis-status").textContent = `Finished: ${file.name}`;
    } catch (error) {
      clearResult();
      byId("analysis-status").textContent = error.message;
    } finally {
      controls.forEach((id) => { byId(id).disabled = false; });
    }
  });
  byId("btn-export-analysis").addEventListener("click", () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "steganalysis_report.json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
