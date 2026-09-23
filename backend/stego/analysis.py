"""PNG LSB steganalysis (Kim). See docs/STEGANALYSIS_GUIDE.md for equations.

These statistics never participate in the cryptographic verdict pipeline.
"""
from __future__ import annotations

import hashlib
import io
import math
from datetime import datetime, timezone

import numpy as np
from PIL import Image, UnidentifiedImageError
from scipy.stats import chi2

VERSION = "kim-sa-1"
MAX_PIXELS = 8_000_000
MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_THRESHOLDS = {"chi_square": 0.95, "rs": 0.05}
LIMITATIONS = [
    "Statistical indication is not proof of hidden data, authenticity, or tampering.",
    "Small or local payloads can be missed; image processing and natural noise can cause false positives.",
    "These methods target conventional 1-LSB replacement; higher bit depths are exploratory.",
    "Default thresholds are provisional, not validated for your image source.",
    "RGB channels are analysed separately; alpha is excluded. The existing encoder also uses alpha in RGBA files.",
]


def _bytes_array(values):
    values = np.asarray(values)
    if values.dtype != np.uint8:
        raise ValueError("Analysis expects uint8 values (0-255).")
    return values


def chi_square(values: np.ndarray) -> dict:
    """Westfeld/Pfitzmann even-category PoV convention, df = k - 1.

    Sparse pairs are omitted (expected count < 5), explicitly reported.
    No p-value is returned for <2 usable pairs or a constant/empty sample.
    """
    values = _bytes_array(values).ravel()
    hist = np.bincount(values, minlength=256)
    even, odd = hist[::2], hist[1::2]
    expected = (even + odd) / 2.0
    valid = expected >= 5
    k = int(valid.sum())
    statistic = float(np.sum((even[valid] - expected[valid]) ** 2 / expected[valid]))
    usable = k >= 2 and np.count_nonzero(hist) > 1
    p = float(chi2.sf(statistic, k - 1)) if usable else None
    return {
        "sample_count": int(values.size), "statistic": statistic,
        "degrees_of_freedom": max(0, k - 1), "usable_pairs": k,
        "omitted_pairs": 128 - k, "retained_samples": int((even + odd)[valid].sum()),
        "even_counts": even.tolist(), "odd_counts": odd.tolist(),
        "expected_counts": expected.tolist(), "score": p,
        "status": "ok" if usable else "insufficient_data",
        "explanation": "Higher tail scores indicate more equal even/odd frequencies; this is not the probability that a payload exists.",
    }


def rs_counts(groups: np.ndarray, mask=(0, 1, 1, 0)) -> dict:
    """Count R/S/U with signed arithmetic, including -1 and 256 at edges."""
    groups = _bytes_array(groups)
    mask = np.asarray(mask)
    if groups.ndim != 2 or groups.shape[1] < 2 or mask.shape != (groups.shape[1],):
        raise ValueError("Groups must be an N x mask-length array (length >= 2).")
    if not np.isin(mask, (-1, 0, 1)).all():
        raise ValueError("Mask entries must be -1, 0, or 1.")
    original = groups.astype(np.int16)
    flipped = original.copy()
    for i, operation in enumerate(mask):
        if operation == 1:
            flipped[:, i] = original[:, i] ^ 1
        elif operation == -1:
            flipped[:, i] = ((original[:, i] + 1) ^ 1) - 1
    before = np.abs(np.diff(original, axis=1)).sum(axis=1)
    after = np.abs(np.diff(flipped, axis=1)).sum(axis=1)
    return {"regular": int(np.sum(after > before)),
            "singular": int(np.sum(after < before)),
            "unusable": int(np.sum(after == before))}


def rs_analysis(channel: np.ndarray) -> dict:
    """Nonoverlapping horizontal groups of four, never across row boundaries.

    Score is a documented mask-asymmetry indicator, NOT a payload-rate estimate.
    """
    channel = _bytes_array(channel)
    if channel.ndim != 2:
        raise ValueError("RS expects a two-dimensional colour channel.")
    height, width = channel.shape
    groups = channel[:, :width // 4 * 4].reshape(-1, 4)
    positive = rs_counts(groups)
    negative = rs_counts(groups, (0, -1, -1, 0))
    n = len(groups)
    asymmetry = (abs(positive["regular"] - negative["regular"])
                 + abs(positive["singular"] - negative["singular"])) / (2 * n) if n else None
    usable = n >= 64 and np.unique(channel).size > 1 and (
        positive["regular"] + positive["singular"] > 0)
    return {"groups": n, "discarded_values": height * (width % 4),
            "mask": [0, 1, 1, 0], "inverse_mask": [0, -1, -1, 0],
            "positive": positive, "negative": negative,
            "raw_asymmetry": asymmetry, "score": asymmetry if usable else None,
            "status": "ok" if usable else "insufficient_data",
            "explanation": "Higher positive/inverse-mask asymmetry is a heuristic indication of LSB replacement, not an estimated payload size."}


def combine(chi_score, rs_score, thresholds=None):
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS) or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
        for v in thresholds.values()
    ):
        raise ValueError("Both analysis thresholds must be finite values from 0 to 1.")
    if chi_score is None or rs_score is None:
        category = "Inconclusive"
    else:
        votes = (chi_score >= thresholds["chi_square"], rs_score >= thresholds["rs"])
        category = "High indication" if all(votes) else "Low indication" if not any(votes) else "Inconclusive"
    return {"category": category, "thresholds": thresholds,
            "rule": "Both scores cross thresholds: high; neither: low; disagreement or insufficient data: inconclusive."}


def analyse_png(file_bytes: bytes, window_size: int = 65536, thresholds=None) -> dict:
    if not isinstance(window_size, int) or not 256 <= window_size <= 1_000_000:
        raise ValueError("Window size must be 256-1000000 channel values.")
    if not file_bytes or len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError("Upload a nonempty PNG of at most 32 MiB.")
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            if img.format != "PNG" or img.mode not in ("RGB", "RGBA", "L"):
                raise ValueError("Use an 8-bit RGB, RGBA, or grayscale PNG.")
            if img.width * img.height > MAX_PIXELS:
                raise ValueError("Analysis supports images up to 8 million pixels.")
            if getattr(img, "n_frames", 1) != 1:
                raise ValueError("Animated PNG is not supported for analysis.")
            mode = img.mode
            arr = np.array(img)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot read a valid supported PNG.") from exc
    names = ["L"] if arr.ndim == 2 else ["R", "G", "B"]
    channels = {}
    for i, name in enumerate(names):
        channel = arr if arr.ndim == 2 else arr[:, :, i]
        flat = channel.ravel()
        # At most 128 adjacent windows, covering the whole channel without sampling.
        effective_window = max(window_size, math.ceil(flat.size / 128))
        windows = []
        for start in range(0, flat.size, effective_window):
            result = chi_square(flat[start:start + effective_window])
            windows.append({k: result[k] for k in (
                "sample_count", "statistic", "degrees_of_freedom", "score", "status")}
                           | {"start": start, "stop": min(start + effective_window, flat.size)})
        channels[name] = {"chi_square": chi_square(flat), "rs": rs_analysis(channel),
                          "windows": windows, "effective_window_size": effective_window}
    scores = {}
    for method in ("chi_square", "rs"):
        values = [c[method]["score"] for c in channels.values()]
        scores[method] = float(np.median(values)) if all(v is not None for v in values) else None
    return {"analysis_version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "image": {"width": int(arr.shape[1]), "height": int(arr.shape[0]), "mode": mode},
            "configuration": {"requested_window_size": window_size, "aggregation": "median of all channel scores; any insufficient channel makes that method inconclusive", "alpha": "excluded"},
            "scores": scores, "channels": channels,
            "combined": combine(scores["chi_square"], scores["rs"], thresholds),
            "limitations": list(LIMITATIONS)}
