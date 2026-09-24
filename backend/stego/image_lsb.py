"""
Image cover-object support (PNG, FR1/FR5/FR6/FR8).

An image is turned into a "carrier" by flattening every colour-channel byte
of every pixel (R,G,B[,A]) into one big uint8 array, in row-major order.
Carrier unit #0 is the top-left pixel's first channel; the spec explicitly
asks for a start location *other than* the top-left corner, which is exactly
what start_location.py provides.

PNG is required because it is lossless - any lossy format would destroy the
LSBs we just wrote. If a user drops a JPEG in, we still load it (Pillow
decodes it) but always *save* the stego result as PNG and say so, since
re-compressing to JPEG would erase the hidden payload.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class ImageCarrier:
    array: np.ndarray  # 1-D uint8, mutable
    shape: tuple  # (height, width, channels)
    mode: str  # PIL mode used for saving, e.g. "RGB" / "RGBA"


def load_image_carrier(file_bytes: bytes) -> ImageCarrier:
    img = Image.open(io.BytesIO(file_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode in ("P", "LA") else "RGB")
    arr = np.array(img)  # (H, W, C) uint8
    flat = arr.reshape(-1).copy()
    return ImageCarrier(array=flat, shape=arr.shape, mode=img.mode)


def carrier_to_png_bytes(carrier: ImageCarrier) -> bytes:
    arr = carrier.array.reshape(carrier.shape)
    img = Image.fromarray(arr, mode=carrier.mode)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def describe(carrier: ImageCarrier) -> dict:
    h, w, c = carrier.shape
    return {
        "width": w,
        "height": h,
        "channels": c,
        "total_units": int(carrier.array.size),
    }
