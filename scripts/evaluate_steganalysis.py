"""Reproducible blind-statistics experiment using the existing LSB embedder.

Run from the project root: python scripts/evaluate_steganalysis.py
Natural PNGs are split by source image, not by stego derivative.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from stego import analysis, bitstream, image_lsb


def metrics(rows, thresholds):
    result = {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "inconclusive": 0}
    for row in rows:
        category = analysis.combine(row["chi_score"], row["rs_score"], thresholds)["category"]
        positive = category == "High indication"
        actual = row["embedded"]
        result["TP" if positive and actual else "FP" if positive else "FN" if actual else "TN"] += 1
        result["inconclusive"] += category == "Inconclusive"
    result["false_positive_rate"] = result["FP"] / max(1, result["FP"] + result["TN"])
    result["false_negative_rate"] = result["FN"] / max(1, result["FN"] + result["TP"])
    return result


def calibrate(rows):
    # Tune only on 1-LSB calibration derivatives and clean originals.
    rows = [r for r in rows if r["split"] == "calibration" and r["lsb"] <= 1]
    best = None
    for chi in (0.5, 0.8, 0.95, 0.99):
        for rs in (0.005, 0.01, 0.025, 0.05, 0.1):
            thresholds = {"chi_square": chi, "rs": rs}
            m = metrics(rows, thresholds)
            loss = (m["false_positive_rate"] + m["false_negative_rate"]) / 2
            # Ties prefer fewer false positives, then stricter thresholds.
            candidate = (loss, m["false_positive_rate"], -chi, -rs)
            if best is None or candidate < best[0]:
                best = (candidate, thresholds)
    return best[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--covers", type=Path, default=ROOT / "samples" / "steganalysis" / "covers")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "steganalysis")
    args = parser.parse_args()
    files = sorted(args.covers.glob("*.png"))
    if len(files) < 4:
        parser.error("Provide at least four independently sourced natural PNGs; see docs/KIM_STEGANALYSIS.md.")
    args.output.mkdir(parents=True, exist_ok=True)
    demo = args.output / "demo"
    demo.mkdir(exist_ok=True)
    rows, raw = [], []
    seen = set()
    for index, path in enumerate(files):
        cover = path.read_bytes()
        original = image_lsb.load_image_carrier(cover)
        digest = hashlib.sha256(original.array.tobytes()).hexdigest()
        if digest in seen:
            raise ValueError("Duplicate decoded covers would leak between calibration and holdout.")
        seen.add(digest)
        split = "calibration" if index % 2 == 0 else "holdout"
        cases = [(0, 0.0, 0)] + [(bits, rate, offset) for bits in (1, 2, 4, 8)
                 for rate in (0.01, 0.5, 0.95) for offset in (0, 0.03)]
        for bits, rate, offset in cases:
            carrier = image_lsb.load_image_carrier(cover)
            start = int(carrier.array.size * offset)
            payload_bytes = int((carrier.array.size - start) * bits * rate) // 8 if bits else 0
            seed = 2005000 + index * 1000 + bits * 100 + round(rate * 100) + round(offset * 100)
            if bits:
                payload = np.random.default_rng(seed).integers(0, 256, payload_bytes, dtype=np.uint8).tobytes()
                bitstream.embed_bits(carrier.array, start, bits, bitstream.bytes_to_bits(payload))
            saved = image_lsb.carrier_to_png_bytes(carrier)
            result = analysis.analyse_png(saved)
            case_id = f"{path.stem}_lsb{bits}_rate{rate}_offset{offset}"
            row = {"case": case_id, "source": path.name, "split": split, "embedded": bool(bits),
                   "lsb": bits, "capacity_fraction": rate, "payload_bytes": payload_bytes,
                   "start_unit": start, "seed": seed, "cover_sha256": hashlib.sha256(cover).hexdigest(),
                   "image_sha256": result["file_sha256"], "chi_score": result["scores"]["chi_square"],
                   "rs_score": result["scores"]["rs"], "default_category": result["combined"]["category"]}
            rows.append(row)
            raw.append({"case": case_id, "report": result})
            if bits <= 1 and offset == 0:
                (demo / f"{case_id}.png").write_bytes(saved)
        print(f"Analysed {path.name}: {split}, {len(cases)} cases", flush=True)
    thresholds = calibrate(rows)
    for row in rows:
        row["calibrated_category"] = analysis.combine(row["chi_score"], row["rs_score"], thresholds)["category"]
    summaries = {}
    for split in ("calibration", "holdout"):
        for bits in (1, 2, 4, 8):
            subset = [r for r in rows if r["split"] == split and r["lsb"] in (0, bits)]
            summaries[f"{split}_{bits}lsb"] = metrics(subset, thresholds)
    report = {"version": analysis.VERSION, "thresholds": thresholds,
              "calibration": "Grid search minimizing mean FPR/FNR on calibration 1-LSB cases; holdout never used for threshold selection.",
              "binary_rule": "Only High indication is positive; inconclusive counts as negative for conservative FN reporting and is also reported separately.",
              "limitations": ["Small demonstration dataset; correlated derivatives are not independent evidence.",
                              "Raw random payloads test the existing embed_bits function, not signed container overhead.",
                              "Higher LSB settings are exploratory, outside the formal 1-LSB model.",
                              "Calibrated values are evaluation-only; GUI retains explicit provisional defaults."],
              "summary": summaries, "cases": rows}
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (args.output / "raw_results.json").write_text(json.dumps(raw, indent=2, allow_nan=False), encoding="utf-8")
    with (args.output / "evaluation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Steganalysis evaluation", "", f"Selected thresholds: `{thresholds}`.", "",
             "Split by source image. Thresholds fitted only on calibration clean/1-LSB cases.",
             "Only High indication counts as detection; inconclusive cases count as misses for stego images.", "",
             "| Split/settings | TP | FP | TN | FN | Inconclusive |", "|---|---:|---:|---:|---:|---:|"]
    for name, m in summaries.items():
        lines.append(f"| {name} | {m['TP']} | {m['FP']} | {m['TN']} | {m['FN']} | {m['inconclusive']} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    lines += ["", "See evaluation.csv for every false alarm, miss, and inconclusive case; raw_results.json retains both techniques and windows."]
    (args.output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
