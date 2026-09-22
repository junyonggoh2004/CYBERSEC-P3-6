"""Paired media measurements. These describe changes, not authenticity."""
import base64
import io

import numpy as np
from PIL import Image

from . import audio_lsb, image_lsb


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
    if cover_type == "image":
        original = before.array.reshape(before.shape)
        changed = after.array.reshape(after.shape)
        result["histograms"] = {name: {"before": np.bincount(original[:, :, i].ravel(), minlength=256).tolist(),
                                      "after": np.bincount(changed[:, :, i].ravel(), minlength=256).tolist()}
                                for i, name in enumerate("RGBA"[:before.shape[2]])}
        diff = np.abs(changed.astype(np.int16) - original.astype(np.int16))[:, :, :3]
        maximum = int(diff.max())
        amplified = (diff.astype(float) * (255 / maximum if maximum else 1)).astype(np.uint8)
        out = io.BytesIO()
        Image.fromarray(amplified).save(out, format="PNG")
        result["difference_png_base64"] = base64.b64encode(out.getvalue()).decode()
        result["difference_gain"] = 255 / maximum if maximum else 1
    else:
        # Same time buckets and full-scale amplitude for both tracks; use channel 1.
        av = a.reshape(-1, before.nchannels)[:, 0]
        bv = b.reshape(-1, after.nchannels)[:, 0]
        scale = float(2 ** (before.sampwidth * 8 - 1))
        step = max(1, (len(av) + 799) // 800)
        def envelope(values):
            return [[float(values[i:i+step].min() / scale), float(values[i:i+step].max() / scale)]
                    for i in range(0, len(values), step)]
        result["waveforms"] = {"before": envelope(av), "after": envelope(bv),
            "difference": envelope(bv - av), "seconds_per_bucket": step / before.framerate,
            "channel": 1, "amplitude_scale": "Full-scale PCM amplitude (-1 to 1)"}
    return result
