"""Sample-pair analysis (SPA) shared by PNG and audio steganalysis, plus the
"likelihood of hidden data" derived from its estimate.

SPA looks at pairs of neighbouring carrier values (Dumitrescu, Wu & Wang,
2003): consecutive samples in one audio channel, or horizontally adjacent
pixels in one image row and colour plane. It is adapted here to how this
project's encoder writes: one contiguous block from the start index, rather
than bits scattered at random.

Model. For a pair (u, v) the trace m = floor(v/2) - floor(u/2) is unchanged by
any LSB change. Within trace m let b_m count (even, odd) pairs, c_m (odd, even)
pairs and T_m all pairs. Cover assumption: a pair with odd difference d = 2m+1
is equally likely to start on an even or an odd value, so b_m = c_{m+1}.
Replacing the LSBs of a share p of the values with random bits gives, in
expectation,

    b'_m - c'_{m+1} = (p / 4) * (T_m - T_{m+1})   for every trace m,

which is fitted by weighted least squares. The slope term is counted from one
half of the pairs and the residual from the other half (cross-fitting); fitting
both from the same pairs biases loud, uninformative audio towards p = 1.

These statistics never participate in the cryptographic verdict pipeline.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import expit, log_ndtr, ndtr
from scipy.stats import norm

MAX_TRACE = 4096  # |m| beyond this carries no usable evidence and only costs memory

# Likelihood assumptions (provisional, see docs/STEGANALYSIS_GUIDE.md).
PRIOR_HIDDEN = 0.5            # starting chance before looking at the file
SHARE_RANGE = (0.01, 1.0)     # if data is hidden: share of values carrying it
# Clean covers do not estimate exactly 0. Observed clean biases: images up to
# 0.05 (astronaut), audio within 0.015. This spread is added to the error.
COVER_BIAS_SD = {"image": 0.025, "audio": 0.02}


def _half_counts(u: np.ndarray, v: np.ndarray):
    """Per-trace totals T, (even,odd) counts B and (odd,even) counts C."""
    m = (v >> 1) - (u >> 1)
    keep = np.abs(m) <= MAX_TRACE + 1
    idx = m[keep] + MAX_TRACE + 1
    u_odd, v_odd = (u[keep] & 1).astype(bool), (v[keep] & 1).astype(bool)
    size = 2 * MAX_TRACE + 3
    return np.stack([np.bincount(idx, minlength=size),
                     np.bincount(idx[~u_odd & v_odd], minlength=size),
                     np.bincount(idx[u_odd & ~v_odd], minlength=size)])


def pair_counts(samples: np.ndarray) -> np.ndarray:
    """Trace counts for consecutive pairs of one audio channel, split into two
    disjoint halves (pairs starting at even / odd positions). Counts are
    additive, so segments and channels are combined by summing."""
    x = np.asarray(samples).astype(np.int64).ravel()
    u, v = x[:-1], x[1:]
    return np.stack([_half_counts(u[s::2], v[s::2]) for s in (0, 1)])


def row_pair_counts(plane: np.ndarray) -> np.ndarray:
    """Trace counts for horizontally adjacent pixels of one colour plane,
    never pairing across rows; halves split by the pair's starting column."""
    plane = np.asarray(plane)
    total = np.zeros((2, 3, 2 * MAX_TRACE + 3), dtype=np.int64)
    for top in range(0, plane.shape[0], 512):  # row blocks keep memory bounded on large photos
        x = plane[top:top + 512].astype(np.int64)
        u, v = x[:, :-1], x[:, 1:]
        total += np.stack([_half_counts(u[:, s::2].ravel(), v[:, s::2].ravel()) for s in (0, 1)])
    return total


def estimate(counts: np.ndarray) -> dict:
    """Cross-fitted weighted least-squares estimate of the share p of values
    whose LSB was replaced, with a delta-method standard error."""
    fits = []
    for T, B, C in counts.astype(float):
        fits.append((B[:-1] - C[1:], (T[:-1] - T[1:]) / 4, B[:-1] + C[1:] + 1))
    (n_a, d_a, v_a), (n_b, d_b, v_b) = fits
    numerator = np.sum(d_a * n_b / v_b) + np.sum(d_b * n_a / v_a)
    denominator = np.sum(d_a * d_b / v_b) + np.sum(d_b * d_a / v_a)
    variance = np.sum(d_a * d_a / v_b) + np.sum(d_b * d_b / v_a)
    pairs = int(counts[:, 0].sum())
    if denominator <= 0 or not math.isfinite(numerator / denominator):
        return {"estimate": None, "standard_error": None, "ci95": None, "pairs_analysed": pairs,
                "status": "insufficient_data"}
    p = float(numerator / denominator)
    se = float(math.sqrt(variance) / denominator)
    return {"estimate": p, "standard_error": se, "ci95": [p - 1.96 * se, p + 1.96 * se],
            "pairs_analysed": pairs, "status": "ok"}


def segment_estimate(counts: np.ndarray, total: np.ndarray) -> dict:
    """Time-map estimate for one segment. A segment is too short to estimate
    the slope T_m - T_{m+1} itself, so it borrows the whole file's slope,
    scaled to the segment's pair count (the segment is a small share of the
    total, so the shared noise is small)."""
    T, B, C = counts.sum(axis=0).astype(float)
    whole = total.sum(axis=0)[0].astype(float)
    scale = T.sum() / whole.sum() if whole.sum() else 0.0
    residual = B[:-1] - C[1:]
    slope = (whole[:-1] - whole[1:]) / 4 * scale
    weight = B[:-1] + C[1:] + 1
    information = float(np.sum(slope * slope / weight))
    if information <= 0:
        return {"estimate": None, "standard_error": None, "status": "insufficient_data"}
    return {"estimate": float(np.sum(slope * residual / weight) / information),
            "standard_error": float(1 / math.sqrt(information)), "status": "ok"}


def _log_normal_mass(a: float, b: float) -> float:
    """log(Phi(b) - Phi(a)) for a < b, stable in both tails."""
    if b <= 0:
        return float(log_ndtr(b) + np.log1p(-np.exp(log_ndtr(a) - log_ndtr(b))))
    if a >= 0:
        return _log_normal_mass(-b, -a)
    return float(np.log(ndtr(b) - ndtr(a)))


def hidden_data_likelihood(share_estimate, standard_error, media: str) -> dict:
    """Posterior chance that the file carries hidden data, from the SPA estimate.

    Two hypotheses: clean (true share 0) or hidden data (true share uniform over
    SHARE_RANGE), with PRIOR_HIDDEN before looking. The estimate is treated as
    normal around the true share with the statistical error widened by the
    natural cover bias for this kind of media.
    """
    lo, hi = SHARE_RANGE
    assumptions = {"prior": PRIOR_HIDDEN, "assumed_share_range": [lo, hi],
                   "cover_bias_sd": COVER_BIAS_SD[media], "basis": "sample-pair analysis"}
    if share_estimate is None or standard_error is None:
        return {"probability": None, "band": "Unknown", **assumptions}
    spread = math.hypot(standard_error, COVER_BIAS_SD[media])
    log_clean = norm.logpdf(share_estimate, 0.0, spread)
    log_hidden = _log_normal_mass((lo - share_estimate) / spread, (hi - share_estimate) / spread) - math.log(hi - lo)
    probability = float(expit(math.log(PRIOR_HIDDEN / (1 - PRIOR_HIDDEN)) + log_hidden - log_clean))
    band = "Likely" if probability >= 0.8 else "Unlikely" if probability <= 0.2 else "Uncertain"
    return {"probability": probability, "band": band, "effective_sd": spread, **assumptions}
