"""Audio comparison metrics for stego evidence (cover-vs-stego difference display).

Quantifies how far a stego audio carrier has moved from its original: how many
samples changed, and the distortion in error (MSE) and signal-to-noise (SNR)
terms. Used for demo evidence and for justifying the default num_lsb.

All functions take two integer sample arrays of equal length and dtype. They do
not read files or know about carrier classes; the caller passes
`cover_carrier.array` and `stego_carrier.array` from audio_lsb.AudioCarrier
straight in.

The arrays are walked in fixed-size chunks rather than converted whole, so
memory use stays flat however long the audio is. This runs on every audio and
video encode, and a whole-array float64 copy of a 10-minute stereo track is
over 400 MB on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

# Reference power the SNR was measured against. A silent cover has no signal
# power to compare with, so the figure reported for it is not a true SNR; the
# reference travels with the value so evidence can say which one it is.
SNR_REFERENCE_SIGNAL = "signal"          # cover's own mean power: a real SNR
SNR_REFERENCE_FULL_SCALE = "full_scale"  # silent cover: full scale substituted
SNR_REFERENCE_NONE = "identical"         # no noise at all, SNR is +inf

# Samples handled per pass (see module docstring). 1M samples keeps the working
# set to roughly 17 MB while leaving the loop overhead negligible.
_CHUNK_SAMPLES = 1 << 20


def _full_scale(samples: np.ndarray) -> float:
    """Full-scale amplitude for the array's own integer dtype.

    Used as the stand-in reference for a silent cover. Derived from the dtype
    rather than assumed, so a 32-bit carrier is not measured against a 16-bit
    reference. int16 gives 32768.0, as before.
    """
    return float(np.iinfo(samples.dtype).max) + 1.0


class MetricsError(ValueError):
    """Raised when two sample arrays cannot be compared."""


@dataclass(frozen=True)
class ComparisonMetrics:
    """Distortion between a cover audio carrier and its stego version."""

    changed_samples: int
    total_samples: int
    mse: float
    snr_db: float
    snr_reference: str = SNR_REFERENCE_SIGNAL
    # Largest |stego - cover| of any single sample. LSB replacement only
    # rewrites the low num_lsb bits, so this can never exceed 2**num_lsb - 1.
    max_sample_change: int = 0

    @property
    def changed_fraction(self) -> float:
        return self.changed_samples / self.total_samples if self.total_samples else 0.0

    @property
    def snr_display(self) -> str:
        """The SNR as it should appear in evidence, qualified where it is not one.

        Use this instead of formatting `snr_db` directly, so a full-scale-
        referenced figure is never presented as a measured SNR.
        """
        if self.snr_reference == SNR_REFERENCE_NONE:
            return "inf (stego is identical to the cover)"
        if self.snr_reference == SNR_REFERENCE_FULL_SCALE:
            return (
                f"{self.snr_db:.1f} dB vs full scale "
                f"(cover is silent, so this is not a true SNR)"
            )
        return f"{self.snr_db:.1f} dB"


def _check_pair(cover: np.ndarray, stego: np.ndarray) -> None:
    if cover.shape != stego.shape:
        raise MetricsError(
            f"Sample arrays differ in shape ({cover.shape} vs {stego.shape})."
        )
    if cover.size == 0:
        raise MetricsError("Cannot compare empty sample arrays.")
    if cover.dtype != stego.dtype:
        # e.g. an int16 cover against an int32 stego: the numbers would come
        # out, but the full-scale reference would only fit one of them.
        raise MetricsError(
            f"Sample arrays differ in type ({cover.dtype} vs {stego.dtype})."
        )
    if not np.issubdtype(cover.dtype, np.integer):
        raise MetricsError(f"Expected integer PCM samples, got {cover.dtype}.")


class _Sums(NamedTuple):
    changed: int
    noise_energy: float   # sum of squared (cover - stego) differences
    signal_energy: float  # sum of squared cover samples
    max_change: int


def _sums(cover: np.ndarray, stego: np.ndarray) -> _Sums:
    """Everything the metrics need, gathered in one chunked pass.

    Only samples that differ contribute noise, so the difference is taken on
    those alone; the cover's energy still needs every sample. Values are
    squared in float64 so integer differences don't overflow first.
    """
    _check_pair(cover, stego)
    c = cover.reshape(-1)
    s = stego.reshape(-1)
    changed = 0
    noise_energy = 0.0
    signal_energy = 0.0
    max_change = 0
    for i in range(0, c.size, _CHUNK_SAMPLES):
        c_chunk = c[i:i + _CHUNK_SAMPLES]
        s_chunk = s[i:i + _CHUNK_SAMPLES]
        idx = np.flatnonzero(c_chunk != s_chunk)
        if idx.size:
            diff = c_chunk[idx].astype(np.float64) - s_chunk[idx].astype(np.float64)
            changed += int(idx.size)
            noise_energy += float(np.dot(diff, diff))
            max_change = max(max_change, int(np.abs(diff).max()))
        ref = c_chunk.astype(np.float64)
        signal_energy += float(np.dot(ref, ref))
    return _Sums(changed, noise_energy, signal_energy, max_change)


def _snr_from_sums(sums: _Sums, cover: np.ndarray) -> tuple[float, str]:
    if sums.noise_energy == 0.0:
        return float("inf"), SNR_REFERENCE_NONE

    noise_power = sums.noise_energy / cover.size
    if sums.signal_energy == 0.0:
        return (
            float(10.0 * np.log10(_full_scale(cover) ** 2 / noise_power)),
            SNR_REFERENCE_FULL_SCALE,
        )

    signal_power = sums.signal_energy / cover.size
    return float(10.0 * np.log10(signal_power / noise_power)), SNR_REFERENCE_SIGNAL


def changed_sample_count(cover: np.ndarray, stego: np.ndarray) -> int:
    """Number of samples whose value changed."""
    return _sums(cover, stego).changed


def mean_squared_error(cover: np.ndarray, stego: np.ndarray) -> float:
    """Mean squared error between the two signals."""
    return _sums(cover, stego).noise_energy / cover.size


def snr_db_with_reference(cover: np.ndarray, stego: np.ndarray) -> tuple[float, str]:
    """SNR in dB together with the reference power it was measured against.

    The reference is one of the SNR_REFERENCE_* values. A silent cover has no
    signal power, so full scale is substituted and the figure is reported as
    SNR_REFERENCE_FULL_SCALE rather than passed off as a measured SNR.
    """
    return _snr_from_sums(_sums(cover, stego), cover)


def snr_db(cover: np.ndarray, stego: np.ndarray) -> float:
    """Signal-to-noise ratio in dB, treating the embedding change as noise.

    Higher is better (less audible distortion). Returns +inf when the stego is
    identical to the cover. For a silent cover this returns a full-scale-
    referenced figure that is not a true SNR: use snr_db_with_reference, or
    ComparisonMetrics.snr_display, wherever the number is shown or recorded.
    """
    return snr_db_with_reference(cover, stego)[0]


def compare(cover: np.ndarray, stego: np.ndarray) -> ComparisonMetrics:
    """Compute all metrics in one pass and return them together."""
    sums = _sums(cover, stego)
    snr, snr_reference = _snr_from_sums(sums, cover)
    return ComparisonMetrics(
        changed_samples=sums.changed,
        total_samples=int(cover.size),
        mse=sums.noise_energy / cover.size,
        snr_db=snr,
        snr_reference=snr_reference,
        max_sample_change=sums.max_change,
    )
