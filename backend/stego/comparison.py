"""
Cover-vs-stego direct comparison (PNG and WAV).

This is deliberately separate from analysis.py (Kim's steganalysis): here we
have *both* the original cover and the resulting stego object, so we can
compute exact, ground-truth differences instead of statistically inferring
whether hidden data might be present in a single suspect file. See the
README "Cover vs Stego Comparison" section for the full explanation of that
distinction.

Two entry points:
  compare_images(cover_bytes, stego_bytes) -> dict   (PNG)
  compare_audio(cover_bytes, stego_bytes, waveform_points=...) -> dict (WAV)

Both raise ValueError with a readable message if the two files are not
directly comparable (different dimensions, channel layout, sample format,
etc.) - callers (app.py) turn that into a 400 response, never a crash.

Design notes:
  - Statistics and visualisations always come from the *actual* re-decoded
    pixel/sample values, never from "which positions embedding wrote to" -
    a carrier value already equal to the bit being written stays unchanged,
    so an embedding position is not necessarily a changed position (this is
    explicitly called out in the returned alpha note and in the README).
  - Amplification/downsampling only ever affects the returned visualisation
    data; the statistics are always computed from the full, un-amplified,
    un-downsampled arrays.
"""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from . import audio_lsb, image_lsb

DEFAULT_WAVEFORM_POINTS = 2000

# Bright magenta: visually distinctive from typical natural-image colours, so
# highlighted (changed) pixels read unambiguously as "flagged by the tool"
# rather than blending into the picture's own palette.
_HIGHLIGHT_RGB = (255, 0, 160)


class ComparisonError(ValueError):
    """Cover and stego objects are not directly comparable (shape/format mismatch)."""


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def _png_b64(arr: np.ndarray, mode: str) -> str:
    img = Image.fromarray(arr, mode=mode)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# --------------------------------------------------------------------------
# PNG comparison
# --------------------------------------------------------------------------
def _validate_image_compat(cover, stego) -> None:
    if cover.shape != stego.shape:
        ch, cw, cc = cover.shape
        sh, sw, sc = stego.shape
        raise ComparisonError(
            "Cover and stego images are not directly comparable: different "
            f"dimensions/channel layout (cover {cw}x{ch}x{cc} vs stego {sw}x{sh}x{sc}). "
            "Both files must come from the same protect operation (same original image)."
        )


def compare_images(cover_bytes: bytes, stego_bytes: bytes) -> dict:
    cover = image_lsb.load_image_carrier(cover_bytes)
    stego = image_lsb.load_image_carrier(stego_bytes)
    _validate_image_compat(cover, stego)

    height, width, channels = cover.shape
    cover_px = cover.array.reshape(cover.shape).astype(np.int16)
    stego_px = stego.array.reshape(stego.shape).astype(np.int16)

    # Visualisations and the headline statistics are RGB-only, matching what
    # a viewer actually sees as "the picture". The 4th (alpha) channel - which
    # the current encoder also embeds into for RGBA covers, see image_lsb.py -
    # is tracked separately below rather than silently folded in or ignored.
    rgb_cover = cover_px[:, :, :3]
    rgb_stego = stego_px[:, :, :3]
    rgb_diff = np.abs(rgb_stego - rgb_cover)  # (H, W, 3)
    channel_changed = rgb_diff != 0
    changed_pixel_mask = channel_changed.any(axis=2)  # (H, W)

    total_rgb_channels = int(rgb_diff.size)
    changed_rgb_channels = int(channel_changed.sum())
    total_pixels = height * width
    changed_pixels = int(changed_pixel_mask.sum())
    max_abs_diff = int(rgb_diff.max()) if rgb_diff.size else 0
    mean_abs_diff = float(rgb_diff.mean()) if rgb_diff.size else 0.0

    stats = {
        "width": int(width),
        "height": int(height),
        "has_alpha": channels == 4,
        "total_rgb_channels_compared": total_rgb_channels,
        "changed_rgb_channels": changed_rgb_channels,
        "percent_rgb_channels_changed": _pct(changed_rgb_channels, total_rgb_channels),
        "changed_pixels": changed_pixels,
        "percent_pixels_changed": _pct(changed_pixels, total_pixels),
        "max_abs_channel_difference": max_abs_diff,
        "mean_abs_channel_difference": mean_abs_diff,
        "changed_red_channels": int(channel_changed[:, :, 0].sum()),
        "changed_green_channels": int(channel_changed[:, :, 1].sum()),
        "changed_blue_channels": int(channel_changed[:, :, 2].sum()),
    }

    if channels == 4:
        alpha_diff = np.abs(stego_px[:, :, 3] - cover_px[:, :, 3])
        stats.update(
            changed_alpha_channels=int((alpha_diff != 0).sum()),
            max_abs_alpha_difference=int(alpha_diff.max()) if alpha_diff.size else 0,
            mean_abs_alpha_difference=float(alpha_diff.mean()) if alpha_diff.size else 0.0,
            alpha_note=(
                "This cover has an alpha channel, and the current encoder also embeds into it "
                "(see image_lsb.py). Alpha differences are reported here but are not included in "
                "the RGB statistics above or in the change-mask/amplified-difference images below, "
                "which only ever compare R/G/B."
            ),
        )

    # Change mask: bright/white where >=1 RGB channel differs, dark/black otherwise.
    mask_arr = (changed_pixel_mask.astype(np.uint8) * 255)
    change_mask_png_b64 = _png_b64(mask_arr, mode="L")

    # Amplified difference: scale |stego-cover| so the single largest observed
    # difference maps to 255, making 1-LSB-scale changes visible. This never
    # touches the source images - it is computed into a brand-new array.
    amplification_factor = 1.0 if max_abs_diff == 0 else 255.0 / max_abs_diff
    amplified = np.clip(rgb_diff.astype(np.float64) * amplification_factor, 0, 255).astype(np.uint8)
    amplified_diff_png_b64 = _png_b64(amplified, mode="RGB")

    # Amplified difference *over the cover image*: the same amplified signal,
    # but blended on top of the actual cover picture (instead of a black
    # background) so changed spots can be seen in context - "this is where in
    # the photo the change happened" rather than an abstract diff-only image.
    # Per pixel, the strongest of its (amplified) R/G/B differences becomes a
    # blend weight toward a fixed, visually distinctive highlight colour;
    # untouched pixels (weight 0) render as the plain, unmodified cover.
    alpha = (amplified.max(axis=2).astype(np.float64) / 255.0)[:, :, None]
    highlight = np.array(_HIGHLIGHT_RGB, dtype=np.float64)
    over_cover = rgb_cover.astype(np.float64) * (1 - alpha) + highlight * alpha
    amplified_over_cover_png_b64 = _png_b64(np.clip(over_cover, 0, 255).astype(np.uint8), mode="RGB")

    return {
        "cover_info": image_lsb.describe(cover),
        "stego_info": image_lsb.describe(stego),
        "stats": stats,
        "change_mask_png_base64": change_mask_png_b64,
        "amplified_difference_png_base64": amplified_diff_png_b64,
        "amplified_difference_over_cover_png_base64": amplified_over_cover_png_b64,
        "amplification_factor": round(amplification_factor, 3),
    }


# --------------------------------------------------------------------------
# WAV comparison
# --------------------------------------------------------------------------
def _validate_audio_compat(cover, stego) -> None:
    mismatches = []
    if cover.nchannels != stego.nchannels:
        mismatches.append(f"channel count ({cover.nchannels} vs {stego.nchannels})")
    if cover.sampwidth != stego.sampwidth:
        mismatches.append(f"sample width ({cover.sampwidth * 8}-bit vs {stego.sampwidth * 8}-bit)")
    if cover.framerate != stego.framerate:
        mismatches.append(f"sample rate ({cover.framerate} vs {stego.framerate} Hz)")
    if cover.array.size != stego.array.size:
        mismatches.append(f"sample count ({cover.nframes} vs {stego.nframes} frames)")
    if mismatches:
        raise ComparisonError(
            "Cover and stego WAV files are not directly comparable: different "
            + "; different ".join(mismatches)
            + ". Both files must come from the same protect operation (same original audio)."
        )


def _downsample_mean(values: np.ndarray, n_points: int) -> list:
    """Representative waveform for display: bucket-average. Never used for stats."""
    if len(values) <= n_points:
        return values.tolist()
    buckets = np.array_split(values, n_points)
    return [float(b.mean()) for b in buckets]


def _downsample_peak(values: np.ndarray, n_points: int) -> list:
    """Representative *difference* waveform for display: keep each bucket's
    largest-magnitude (signed) sample so small, sparse LSB differences don't
    get averaged away into invisibility. Never used for stats."""
    if len(values) <= n_points:
        return values.tolist()
    buckets = np.array_split(values, n_points)
    out = []
    for b in buckets:
        idx = int(np.argmax(np.abs(b)))
        out.append(float(b[idx]))
    return out


def compare_audio(cover_bytes: bytes, stego_bytes: bytes, waveform_points: int = DEFAULT_WAVEFORM_POINTS) -> dict:
    if not 64 <= waveform_points <= 20000:
        raise ValueError("waveform_points must be between 64 and 20000.")

    cover = audio_lsb.load_audio_carrier(cover_bytes)
    stego = audio_lsb.load_audio_carrier(stego_bytes)
    _validate_audio_compat(cover, stego)

    nchannels = cover.nchannels
    # Per-frame view (nframes, nchannels) so multichannel files compare
    # corresponding samples of the same channel, not interleaved raw indices.
    cover_samples = cover.array.reshape(-1, nchannels).astype(np.int64)
    stego_samples = stego.array.reshape(-1, nchannels).astype(np.int64)
    diff = stego_samples - cover_samples
    abs_diff = np.abs(diff)
    changed_mask = diff != 0

    total_samples = int(cover_samples.size)
    changed_samples = int(changed_mask.sum())

    def _channel_stats(ch: int) -> dict:
        ch_abs = abs_diff[:, ch]
        ch_diff = diff[:, ch]
        ch_total = int(ch_abs.size)
        ch_changed = int(changed_mask[:, ch].sum())
        return {
            "channel": ch,
            "total_samples_compared": ch_total,
            "changed_samples": ch_changed,
            "percent_samples_changed": _pct(ch_changed, ch_total),
            "max_abs_sample_difference": int(ch_abs.max()) if ch_abs.size else 0,
            "mean_abs_sample_difference": float(ch_abs.mean()) if ch_abs.size else 0.0,
            "rms_difference": float(np.sqrt(np.mean(ch_diff.astype(np.float64) ** 2))) if ch_diff.size else 0.0,
        }

    stats = {
        "sample_rate_hz": cover.framerate,
        "sample_width_bits": cover.sampwidth * 8,
        "channels": nchannels,
        "frames": cover.nframes,
        "total_samples_compared": total_samples,
        "changed_samples": changed_samples,
        "percent_samples_changed": _pct(changed_samples, total_samples),
        "max_abs_sample_difference": int(abs_diff.max()) if abs_diff.size else 0,
        "mean_abs_sample_difference": float(abs_diff.mean()) if abs_diff.size else 0.0,
        "rms_difference": float(np.sqrt(np.mean(diff.astype(np.float64) ** 2))) if diff.size else 0.0,
        "per_channel": [_channel_stats(ch) for ch in range(nchannels)],
    }

    waveform_channels = []
    for ch in range(nchannels):
        waveform_channels.append(
            {
                "channel": ch,
                "cover": _downsample_mean(cover_samples[:, ch], waveform_points),
                "stego": _downsample_mean(stego_samples[:, ch], waveform_points),
                "difference": _downsample_peak(diff[:, ch], waveform_points),
            }
        )
    point_count = min(waveform_points, cover.nframes) if cover.nframes else 0

    return {
        "cover_info": audio_lsb.describe(cover),
        "stego_info": audio_lsb.describe(stego),
        "stats": stats,
        "waveform": {"point_count": point_count, "channels": waveform_channels},
    }
