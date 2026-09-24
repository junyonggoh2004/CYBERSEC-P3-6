"""Sample-pair analysis (SPA) for PCM audio: WAV files and video audio tracks.

Chi-square is unreliable on audio: a 16-bit recording's value histogram is
already smooth at the LSB scale, so clean audio looks "embedded". SPA instead
looks at consecutive sample pairs; the model and estimator live in spa.py and
are shared with PNG analysis.

These statistics never participate in the cryptographic verdict pipeline.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

import numpy as np

from . import audio_lsb
from .spa import MAX_TRACE, estimate, hidden_data_likelihood, pair_counts, segment_estimate

VERSION = "spa-audio-1"
SEGMENTS = 16
DEFAULT_THRESHOLDS = {"min_rate": 0.03, "max_standard_error": 0.1}
LIMITATIONS = [
    "Statistical indication is not proof of hidden data, authenticity, or tampering.",
    "The estimate needs consecutive samples that are close in value (quiet passages, speech pauses). "
    "Loud, noisy or 32-bit audio usually gives too little evidence and is reported as inconclusive.",
    "The model targets 1-LSB replacement written as one contiguous block; partial 2+ LSB payloads are underestimated.",
    "Default thresholds and likelihood assumptions are provisional, not validated for your audio source.",
    "For video, only the audio track is analysed: this project never modifies the video frames.",
]


def combine(result: dict, thresholds=None) -> dict:
    thresholds = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_THRESHOLDS) or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
        for v in thresholds.values()
    ):
        raise ValueError("Both audio analysis thresholds must be finite values from 0 to 1.")
    se = result["standard_error"]
    if result["estimate"] is None or se > thresholds["max_standard_error"]:
        category = "Inconclusive"
    elif result["ci95"][0] > thresholds["min_rate"]:
        category = "High indication"
    else:
        category = "Low indication"
    return {"category": category, "thresholds": thresholds,
            "rule": "Too little evidence (standard error above the limit): inconclusive. Otherwise high when "
                    "the lower end of the 95% interval exceeds the minimum share; low when it does not."}


def analyse_audio(wav_bytes: bytes, source_bytes: bytes | None = None, video_info: dict | None = None,
                  thresholds=None) -> dict:
    """SPA report for a PCM WAV. For a video, pass the demuxed audio track as
    wav_bytes, the original file as source_bytes and the probe info."""
    try:
        carrier = audio_lsb.load_audio_carrier(wav_bytes)
    except (ValueError, EOFError, OSError) as exc:
        raise ValueError(f"Cannot read the audio: {exc}") from exc
    frames = carrier.array.reshape(-1, carrier.nchannels)
    if len(frames) < 2:
        raise ValueError("The audio is too short to analyse.")
    bounds = np.linspace(0, len(frames), min(SEGMENTS, len(frames) // 2) + 1).astype(int)
    total = np.zeros((2, 3, 2 * MAX_TRACE + 3), dtype=np.int64)
    channels, segments = [], []
    for ch in range(carrier.nchannels):
        # Count each segment separately (bounded memory, and a time map); the
        # few pairs straddling a segment boundary are dropped.
        per_segment = [pair_counts(frames[start:stop, ch]) for start, stop in zip(bounds[:-1], bounds[1:])]
        channel_total = sum(per_segment)
        total += channel_total
        channels.append({"channel": ch + 1, **estimate(channel_total)})
        for i, counts in enumerate(per_segment):
            if ch == 0:
                segments.append(counts)
            else:
                segments[i] = segments[i] + counts
    overall = estimate(total)
    rate = carrier.framerate or 1
    segment_results = [{"start_seconds": round(start / rate, 3), "stop_seconds": round(stop / rate, 3),
                        **segment_estimate(counts, total)}
                       for (start, stop), counts in zip(zip(bounds[:-1], bounds[1:]), segments)]
    units = int(carrier.array.size)
    hidden_bytes = None if overall["estimate"] is None else int(max(0.0, min(1.0, overall["estimate"])) * units / 8)
    media = {"kind": "video" if video_info is not None else "audio", "channels": carrier.nchannels,
             "sample_rate_hz": carrier.framerate, "sample_width_bits": carrier.sampwidth * 8,
             "frames": int(len(frames)), "duration_seconds": round(len(frames) / rate, 3)}
    if video_info is not None:
        media["video"] = video_info
    return {"analysis_version": VERSION, "method": "sample_pair_analysis",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_sha256": hashlib.sha256(source_bytes if source_bytes is not None else wav_bytes).hexdigest(),
            "media": media, "scores": {"spa": overall["estimate"]}, "spa": overall,
            "estimated_hidden_bytes_at_1_lsb": hidden_bytes, "channels": channels,
            "segments": segment_results,
            "configuration": {"pairs": "consecutive samples within each channel", "max_trace": MAX_TRACE,
                              "segments": len(segment_results), "model": "1-LSB replacement written as one contiguous block"},
            "combined": combine(overall, thresholds),
            "likelihood": hidden_data_likelihood(overall["estimate"], overall["standard_error"], "audio"),
            "limitations": list(LIMITATIONS)}
