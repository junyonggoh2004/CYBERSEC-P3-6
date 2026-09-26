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

from . import spa

VERSION = "kim-sa-2"
# Large enough for photos Protect can produce; RS and SPA count in row blocks
# so memory stays bounded.
MAX_PIXELS = 50_000_000
MAX_FILE_BYTES = 200 * 1024 * 1024
ROW_BLOCK = 512
DEFAULT_THRESHOLDS = {"chi_square": 0.95, "rs": 0.05}
LIMITATIONS = [
    "Statistical indication is not proof of hidden data, authenticity, or tampering.",
    "Small or local payloads can be missed; image processing and natural noise can cause false positives.",
    "Chi-square and RS here target conventional 1-LSB replacement; higher bit depths are outside their formal model.",
    "Chi-square relies on approximately balanced embedded LSBs; strongly structured payload bits can evade it.",
    "RS payload estimates assume approximately random message bits and broadly distributed replacement; localized or non-random embedding can reduce accuracy.",
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


def _rs_message_fraction(positive: dict, negative: dict,
                         flipped_positive: dict, flipped_negative: dict):
    """Return the Fridrich/Goljan/Du RS message-length estimate and diagnostics.

    The quadratic uses the paper's rescaled x axis.  The physically meaningful
    message fraction is p = x / (x - 1/2), using the root with smaller |x|.
    If the fitted quadratic has no real root, use the straight-line fallback
    employed by established RS implementations.
    """
    r, s = positive["regular"], positive["singular"]
    r_minus, s_minus = negative["regular"], negative["singular"]
    r1, s1 = flipped_positive["regular"], flipped_positive["singular"]
    r_minus1, s_minus1 = flipped_negative["regular"], flipped_negative["singular"]

    d0 = r - s
    d1 = r1 - s1
    d_minus0 = r_minus - s_minus
    d_minus1 = r_minus1 - s_minus1
    a = 2.0 * (d1 + d0)
    b = d_minus0 - d_minus1 - d1 - 3.0 * d0
    c = d0 - d_minus0
    eps = 1e-12
    roots = []
    discriminant = None
    method = "quadratic"

    if abs(a) <= eps:
        method = "linear"
        if abs(b) > eps:
            roots = [-c / b]
    else:
        discriminant = b * b - 4.0 * a * c
        # Small negative values can arise from floating point cancellation.
        if discriminant >= -eps:
            discriminant = max(0.0, discriminant)
            root_term = math.sqrt(discriminant)
            roots = [(-b + root_term) / (2.0 * a), (-b - root_term) / (2.0 * a)]
        else:
            # When the idealized parabolas do not produce a real crossing,
            # approximate the R and S crossings with straight lines.
            denominator_r = r1 - r + r_minus - r_minus1
            denominator_s = s1 - s + s_minus - s_minus1
            if abs(denominator_r) > eps and abs(denominator_s) > eps:
                crossing_r = (r_minus - r) / denominator_r
                crossing_s = (s_minus - s) / denominator_s
                roots = [(crossing_r + crossing_s) / 2.0]
                method = "straight_line_fallback"

    roots = [float(root) for root in roots if math.isfinite(root)]
    if not roots:
        return None, {
            "a": a, "b": b, "c": c, "discriminant": discriminant,
            "roots": [], "method": method,
        }, {"d0": d0, "d1": d1, "d_minus0": d_minus0, "d_minus1": d_minus1}

    x = min(roots, key=abs)
    if abs(x - 0.5) <= eps:
        estimate = None
    else:
        estimate = x / (x - 0.5)
        if not math.isfinite(estimate):
            estimate = None

    return estimate, {
        "a": a, "b": b, "c": c, "discriminant": discriminant,
        "roots": roots, "selected_root": x, "method": method,
    }, {"d0": d0, "d1": d1, "d_minus0": d_minus0, "d_minus1": d_minus1}


def rs_analysis(channel: np.ndarray) -> dict:
    """Fridrich/Goljan/Du RS analysis using horizontal groups of four.

    Measurements are taken on the supplied image and again after flipping every
    LSB.  The four R-S differences are inserted into the paper's quadratic to
    estimate the fraction of samples carrying 1-LSB replacement.
    """
    channel = _bytes_array(channel)
    if channel.ndim != 2:
        raise ValueError("RS expects a two-dimensional colour channel.")
    height, width = channel.shape
    usable_width = width // 4 * 4
    n = height * (width // 4)

    # The RS estimator also requires the measurements at 1 - p/2, obtained by
    # flipping every LSB in the observed stego image before repeating R/S counts.
    # Counts add up across rows, so count a block of rows at a time.
    totals = [{"regular": 0, "singular": 0, "unusable": 0} for _ in range(4)]
    for top in range(0, height, ROW_BLOCK):
        block = channel[top:top + ROW_BLOCK, :usable_width]
        if not block.size:
            continue
        groups = block.reshape(-1, 4)
        flipped_groups = (block ^ np.uint8(1)).reshape(-1, 4)
        for total, (source, mask) in zip(totals, ((groups, (0, 1, 1, 0)), (groups, (0, -1, -1, 0)),
                                                  (flipped_groups, (0, 1, 1, 0)), (flipped_groups, (0, -1, -1, 0)))):
            for key, value in rs_counts(source, mask).items():
                total[key] += value
    positive, negative, flipped_positive, flipped_negative = totals

    raw_estimate, quadratic, differences = _rs_message_fraction(
        positive, negative, flipped_positive, flipped_negative
    )

    usable = n >= 64 and np.unique(channel).size > 1 and (
        positive["regular"] + positive["singular"] > 0
    ) and raw_estimate is not None

    # Natural-image bias can make the signed estimate slightly negative; RS
    # message length is interpreted by magnitude. Severe model mismatch can make
    # it exceed one, so the detector score is bounded while the raw result remains.
    score = min(1.0, abs(float(raw_estimate))) if usable else None

    return {
        "groups": n,
        "discarded_values": height * (width % 4),
        "mask": [0, 1, 1, 0],
        "inverse_mask": [0, -1, -1, 0],
        "positive": positive,
        "negative": negative,
        "flipped_positive": flipped_positive,
        "flipped_negative": flipped_negative,
        "differences": differences,
        "quadratic": quadratic,
        "estimated_payload_fraction_raw": float(raw_estimate) if raw_estimate is not None else None,
        "score": score,
        "status": "ok" if usable else "insufficient_data",
        "explanation": "RS score is the bounded Fridrich/Goljan/Du estimate of the fraction of samples affected by conventional 1-LSB replacement; it is not a probability.",
    }


def combine(chi_score, rs_score, thresholds=None):
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS) or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
        for v in thresholds.values()
    ):
        raise ValueError("Both analysis thresholds must be finite values from 0 to 1.")

    available = {
        "chi_square": chi_score,
        "rs": rs_score,
    }
    positives = [
        name for name, score in available.items()
        if score is not None and score >= thresholds[name]
    ]

    if positives:
        category = "High indication"
    elif all(score is not None for score in available.values()):
        category = "Low indication"
    else:
        category = "Inconclusive"

    return {
        "category": category,
        "thresholds": thresholds,
        "rule": "Either detector crossing its threshold gives high indication; both available and below threshold gives low; otherwise inconclusive.",
    }


def _chi_channel_summary(full_result: dict, windows: list[dict]):
    """Combine whole-channel and sustained regional PoV evidence.

    A single high window is deliberately not enough because scanning many
    regions creates chance peaks.  The median usable-window tail score captures
    sustained sequential embedding, while the whole-channel value remains useful
    for broadly scattered replacement.  The stronger of those two is used.
    """
    usable_windows = [window["score"] for window in windows if window["score"] is not None]
    regional_median = float(np.median(usable_windows)) if usable_windows else None
    candidates = [score for score in (full_result["score"], regional_median) if score is not None]
    return (max(candidates) if candidates else None), regional_median


def analyse_png(file_bytes: bytes, window_size: int = 65536, thresholds=None) -> dict:
    if not isinstance(window_size, int) or not 256 <= window_size <= 1_000_000:
        raise ValueError("Window size must be 256-1000000 channel values.")
    if not file_bytes or len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError(f"Upload a nonempty PNG of at most {MAX_FILE_BYTES // (1024 * 1024)} MiB.")
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            if img.format != "PNG" or img.mode not in ("RGB", "RGBA", "L"):
                raise ValueError("Use an 8-bit RGB, RGBA, or grayscale PNG.")
            if img.width * img.height > MAX_PIXELS:
                raise ValueError(f"Analysis supports images up to {MAX_PIXELS // 1_000_000} million pixels.")
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

        full_chi = chi_square(flat)
        chi_summary, regional_median = _chi_channel_summary(full_chi, windows)
        counts = spa.row_pair_counts(channel)
        spa_counts = counts if not channels else spa_counts + counts
        channels[name] = {
            "chi_square": full_chi,
            "chi_square_summary_score": chi_summary,
            "chi_square_regional_median_score": regional_median,
            "rs": rs_analysis(channel),
            "spa": spa.estimate(counts),
            "windows": windows,
            "effective_window_size": effective_window,
        }

    chi_values = [
        channel["chi_square_summary_score"] for channel in channels.values()
        if channel["chi_square_summary_score"] is not None
    ]
    rs_values = [
        channel["rs"]["score"] for channel in channels.values()
        if channel["rs"]["score"] is not None
    ]
    scores = {
        "chi_square": float(np.median(chi_values)) if chi_values else None,
        "rs": float(np.median(rs_values)) if rs_values else None,
    }
    # Sample-pair analysis over all colour planes: an estimated share of values
    # carrying hidden bits, which also gives the likelihood of hidden data.
    # It is reported alongside, and does not change, the chi-square/RS verdict.
    overall = spa.estimate(spa_counts)
    values = len(names) * arr.shape[0] * arr.shape[1]
    hidden_bytes = None if overall["estimate"] is None else int(max(0.0, min(1.0, overall["estimate"])) * values / 8)

    return {
        "analysis_version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "image": {"width": int(arr.shape[1]), "height": int(arr.shape[0]), "mode": mode},
        "configuration": {
            "requested_window_size": window_size,
            "aggregation": "Per channel: chi-square uses the stronger of the whole-channel tail score and median usable-window tail score; RS uses the paper's bounded payload-fraction estimate. Overall method scores are medians of available RGB/L channel scores.",
            "alpha": "excluded",
        },
        "scores": scores,
        "channels": channels,
        "combined": combine(scores["chi_square"], scores["rs"], thresholds),
        "spa": overall,
        "estimated_hidden_bytes_at_1_lsb": hidden_bytes,
        "likelihood": spa.hidden_data_likelihood(overall["estimate"], overall["standard_error"], "image"),
        "limitations": list(LIMITATIONS),
    }
