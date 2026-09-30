"""Boosted listening copies for the Compare page.

LSB changes to audio are far too quiet to hear at normal volume: even at the
maximum depth of 8 LSBs a 16-bit sample moves by at most 255 out of 32,767
(under 1% of full scale). This module makes three short WAVs so a person can
*hear* where the hidden data is:

  - original, turned up by some gain G
  - stego,    turned up by the SAME gain G (fair A/B: only the change differs)
  - the change on its own (stego - original), amplified to a clearly audible level

These are listening aids only. They are generated in memory for the Compare
page and never replace or modify the stego file, which still verifies.
"""
from __future__ import annotations

import base64
import io
import wave

import numpy as np

MAX_SECONDS = 30          # keeps the JSON response small for long files
TARGET_PEAK = 0.9         # boosted original/stego peak, as a fraction of full scale
DIFF_TARGET_PEAK = 0.5    # amplified difference peak (about -6 dBFS)
MAX_GAIN = 1000.0         # never boost the pair by more than 60 dB


def _to_float(carrier) -> np.ndarray:
    """Interleaved integer samples -> (frames, channels) floats in [-1, 1]."""
    full_scale = float(1 << (8 * carrier.sampwidth - 1))
    samples = carrier.array.astype(np.float64) / full_scale
    return samples.reshape(-1, carrier.nchannels)


def _wav_base64(samples: np.ndarray, framerate: int) -> str:
    """(frames, channels) floats in [-1, 1] -> base64 16-bit PCM WAV."""
    pcm = np.clip(np.round(samples * 32767), -32767, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(samples.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(pcm.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _db(gain: float) -> float:
    return round(20.0 * float(np.log10(gain)), 1)


def build(before, after) -> dict | None:
    """Listening copies for a cover/stego pair of AudioCarriers.

    Returns None when the pair can't be compared sample-for-sample (different
    layout) so the page simply hides the panel.
    """
    if (before.nchannels, before.framerate) != (after.nchannels, after.framerate):
        return None
    a, b = _to_float(before), _to_float(after)
    frames = min(len(a), len(b), MAX_SECONDS * before.framerate)
    if frames == 0:
        return None
    a, b = a[:frames], b[:frames]
    diff = b - a

    peak = max(float(np.abs(a).max()), float(np.abs(b).max()))
    gain = min(MAX_GAIN, TARGET_PEAK / peak) if peak > 0 else 1.0
    gain = max(gain, 1.0)  # a cover that is already loud is left as it is

    result = {
        "seconds": round(frames / before.framerate, 2),
        "truncated": frames < min(len(before.array), len(after.array)) // before.nchannels,
        "gain": round(gain, 1),
        "gain_db": _db(gain),
        "original_wav_base64": _wav_base64(a * gain, before.framerate),
        "stego_wav_base64": _wav_base64(b * gain, before.framerate),
        "difference_wav_base64": None,
        "difference_gain": None,
        "difference_gain_db": None,
    }
    diff_peak = float(np.abs(diff).max())
    if diff_peak > 0:
        diff_gain = DIFF_TARGET_PEAK / diff_peak
        result.update(
            difference_wav_base64=_wav_base64(diff * diff_gain, before.framerate),
            difference_gain=round(diff_gain, 1),
            difference_gain_db=_db(diff_gain),
        )
    return result
