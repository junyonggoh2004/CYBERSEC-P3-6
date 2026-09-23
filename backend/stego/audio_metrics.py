"""Audio comparison metrics for stego evidence (cover-vs-stego difference display).

Quantifies how far a stego audio carrier has moved from its original: how many
samples changed, and the distortion in error (MSE) and signal-to-noise (SNR)
terms. Used for demo evidence and for justifying the default num_lsb.

All functions take two integer sample arrays of equal length. They do not read
files or know about carrier classes; the caller passes `cover_carrier.array`
and `stego_carrier.array` from audio_lsb.AudioCarrier straight in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Reference power the SNR was measured against. A silent cover has no signal
# power to compare with, so the figure reported for it is not a true SNR; the
# reference travels with the value so evidence can say which one it is.
SNR_REFERENCE_SIGNAL = "signal"          # cover's own mean power: a real SNR
SNR_REFERENCE_FULL_SCALE = "full_scale"  # silent cover: full scale substituted
SNR_REFERENCE_NONE = "identical"         # no noise at all, SNR is +inf


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


def changed_sample_count(cover: np.ndarray, stego: np.ndarray) -> int:
    """Number of samples whose value changed."""
    _check_pair(cover, stego)
    return int(np.count_nonzero(cover != stego))


def mean_squared_error(cover: np.ndarray, stego: np.ndarray) -> float:
    """Mean squared error between the two signals.

    Computed in float64 so integer differences don't overflow before squaring.
    """
    _check_pair(cover, stego)
    diff = cover.astype(np.float64) - stego.astype(np.float64)
    return float(np.mean(diff ** 2))


def snr_db_with_reference(cover: np.ndarray, stego: np.ndarray) -> tuple[float, str]:
    """SNR in dB together with the reference power it was measured against.

    The reference is one of the SNR_REFERENCE_* values. A silent cover has no
    signal power, so full scale is substituted and the figure is reported as
    SNR_REFERENCE_FULL_SCALE rather than passed off as a measured SNR.
    """
    _check_pair(cover, stego)
    ref = cover.astype(np.float64)
    noise = ref - stego.astype(np.float64)

    noise_power = float(np.mean(noise ** 2))
    if noise_power == 0.0:
        return float("inf"), SNR_REFERENCE_NONE

    signal_power = float(np.mean(ref ** 2))
    if signal_power == 0.0:
        return (
            float(10.0 * np.log10(_full_scale(cover) ** 2 / noise_power)),
            SNR_REFERENCE_FULL_SCALE,
        )

    return float(10.0 * np.log10(signal_power / noise_power)), SNR_REFERENCE_SIGNAL


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
    _check_pair(cover, stego)
    snr, snr_reference = snr_db_with_reference(cover, stego)
    return ComparisonMetrics(
        changed_samples=changed_sample_count(cover, stego),
        total_samples=int(cover.size),
        mse=mean_squared_error(cover, stego),
        snr_db=snr,
        snr_reference=snr_reference,
    )