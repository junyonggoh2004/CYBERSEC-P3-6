"""Paired media measurements. These describe changes, not authenticity."""
import base64
import io

import numpy as np
from PIL import Image

from . import audio_lsb, image_lsb

_HIGHLIGHT_RGB = (255, 0, 160)  # magenta: distinct from any natural image colour


def _png_b64(array, mode):
    out = io.BytesIO()
    Image.fromarray(array, mode=mode).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


def compare(cover_type, before_bytes, after_bytes):
    loader = image_lsb.load_image_carrier if cover_type == "image" else audio_lsb.load_audio_carrier
    before, after = loader(before_bytes), loader(after_bytes)
    describe = image_lsb.describe if cover_type == "image" else audio_lsb.describe
    if describe(before) != describe(after):
        raise ValueError("Objects must have matching dimensions/channels or audio format/duration.")
    a, b = before.array.astype(np.float64), after.array.astype(np.float64)
    if not len(a):
        raise ValueError("Objects must contain at least one carrier value.")
    difference = b - a
    mse = float(np.mean(difference ** 2))
    peak = 255 if cover_type == "image" else float(2 ** (before.sampwidth * 8) - 1)
    result = {"cover_info": describe(before), "original_size_bytes": len(before_bytes),
              "stego_size_bytes": len(after_bytes), "changed_values": int(np.count_nonzero(difference)),
              "total_values": len(a), "changed_percent": round(100 * np.count_nonzero(difference) / len(a), 4),
              "mse": mse, "psnr_db": float(10 * np.log10(peak ** 2 / mse)) if mse else None,
              "max_absolute_difference": float(np.max(np.abs(difference))),
              "note": "Paired measurements describe changes; they do not prove hidden data or authenticity."}
    result.update(_compare_image(before, after) if cover_type == "image" else _compare_audio(before, a, b))
    return result


def _compare_image(before, after):
    original = before.array.reshape(before.shape)
    changed = after.array.reshape(after.shape)
    channels = before.shape[2]
    histograms = {name: {"before": np.bincount(original[:, :, i].ravel(), minlength=256).tolist(),
                          "after": np.bincount(changed[:, :, i].ravel(), minlength=256).tolist()}
                  for i, name in enumerate("RGBA"[:channels])}

    # RGB-only from here on: alpha is measured separately below, since it is
    # not part of a picture's visible appearance the way R/G/B are.
    rgb_before = original[:, :, :3].astype(np.int16)
    rgb_after = changed[:, :, :3].astype(np.int16)
    rgb_diff = np.abs(rgb_after - rgb_before)
    channel_changed = rgb_diff != 0
    changed_pixel_mask = channel_changed.any(axis=2)
    maximum = int(rgb_diff.max()) if rgb_diff.size else 0
    gain = 255 / maximum if maximum else 1.0
    amplified = (rgb_diff.astype(float) * gain).astype(np.uint8)

    # Same amplified signal blended onto the actual cover (magenta highlight)
    # instead of a black background, so changed areas can be seen in context.
    weight = (amplified.max(axis=2).astype(np.float64) / 255.0)[:, :, None]
    highlighted = np.clip(rgb_before.astype(np.float64) * (1 - weight) + np.array(_HIGHLIGHT_RGB) * weight, 0, 255)

    out = {"histograms": histograms, "difference_png_base64": _png_b64(amplified, "RGB"), "difference_gain": gain,
           "change_mask_png_base64": _png_b64(changed_pixel_mask.astype(np.uint8) * 255, "L"),
           "highlighted_difference_png_base64": _png_b64(highlighted.astype(np.uint8), "RGB"),
           "changed_pixels": int(changed_pixel_mask.sum()), "total_pixels": int(changed_pixel_mask.size),
           "changed_red": int(channel_changed[:, :, 0].sum()), "changed_green": int(channel_changed[:, :, 1].sum()),
           "changed_blue": int(channel_changed[:, :, 2].sum())}
    if channels == 4:
        alpha_diff = np.abs(changed[:, :, 3].astype(np.int16) - original[:, :, 3].astype(np.int16))
        out["changed_alpha"] = int(np.count_nonzero(alpha_diff))
        out["alpha_note"] = ("This cover has an alpha channel, and the encoder also embeds into it. Alpha "
                              "differences are counted here but excluded from the RGB figures and images above.")
    return out


def _compare_audio(before, a, b):
    # Same time buckets and full-scale amplitude for both tracks; use channel 1.
    nchannels = before.nchannels
    av, bv = a.reshape(-1, nchannels), b.reshape(-1, nchannels)
    diff = bv - av
    scale = float(2 ** (before.sampwidth * 8 - 1))
    step = max(1, (len(av) + 799) // 800)

    def envelope(values):
        return [[float(values[i:i + step].min() / scale), float(values[i:i + step].max() / scale)]
                for i in range(0, len(values), step)]

    per_channel = [{"channel": ch + 1, "changed_samples": int(np.count_nonzero(diff[:, ch])),
                    "total_samples": int(len(diff)), "max_absolute_difference": float(np.max(np.abs(diff[:, ch]))),
                    "rms_difference": float(np.sqrt(np.mean(diff[:, ch] ** 2)))} for ch in range(nchannels)]
    return {"waveforms": {"before": envelope(av[:, 0]), "after": envelope(bv[:, 0]),
                          "difference": envelope(diff[:, 0]), "seconds_per_bucket": step / before.framerate,
                          "channel": 1, "amplitude_scale": "Full-scale PCM amplitude (-1 to 1)"},
            "per_channel": per_channel}
