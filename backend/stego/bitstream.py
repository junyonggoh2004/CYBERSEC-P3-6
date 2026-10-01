"""
Low-level LSB bit read/write primitives.

A "carrier" is a 1-D numpy array of integer samples that we can hide data in:
  - for images: every colour-channel byte of every pixel (uint8)
  - for audio:  every PCM sample (int16 for 16-bit WAV, int32 for 32-bit WAV)

Both cases boil down to the same operation: replace the lowest `num_lsb` bits
of each carrier unit with bits taken from the payload, starting at a chosen
`start_index` (the "start location"). This module implements that operation
once, generically, so image_lsb.py and audio_lsb.py stay tiny.
"""
from __future__ import annotations

import numpy as np

MIN_LSB = 1
MAX_LSB = 16  # PCM samples; an 8-bit image-channel value allows at most 8


def max_lsb(carrier: np.ndarray) -> int:
    """Deepest setting a carrier allows: 8 for image values, 16 for PCM samples."""
    return min(MAX_LSB, carrier.dtype.itemsize * 8)


def validate_num_lsb(num_lsb: int, carrier: np.ndarray | None = None) -> int:
    num_lsb = int(num_lsb)
    limit = MAX_LSB if carrier is None else max_lsb(carrier)
    if not (MIN_LSB <= num_lsb <= limit):
        raise ValueError(f"num_lsb must be between {MIN_LSB} and {limit} for this cover (got {num_lsb}).")
    return num_lsb


def low_bits(carrier: np.ndarray, num_lsb: int) -> tuple[np.ndarray, np.ndarray]:
    """(unsigned view of carrier, mask of its low num_lsb bits).

    Masks are built on the unsigned view because at full depth they don't fit
    the signed sample type (65,535 is not an int16); the bit patterns, and so
    the embedded samples, are identical either way.
    """
    unsigned = carrier.view(carrier.dtype.str.replace("i", "u"))
    return unsigned, np.array((1 << num_lsb) - 1, dtype=unsigned.dtype)


def bytes_to_bits(data: bytes) -> np.ndarray:
    """Big/MSB-first bit expansion of a byte string -> uint8 array of 0/1."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return np.unpackbits(arr)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return np.packbits(bits).tobytes()


def capacity_units(carrier: np.ndarray, start_index: int) -> int:
    return max(0, len(carrier) - int(start_index))


def capacity_bits(carrier: np.ndarray, start_index: int, num_lsb: int) -> int:
    return capacity_units(carrier, start_index) * validate_num_lsb(num_lsb)


def capacity_bytes(carrier: np.ndarray, start_index: int, num_lsb: int) -> int:
    return capacity_bits(carrier, start_index, num_lsb) // 8


def embed_bits(carrier: np.ndarray, start_index: int, num_lsb: int, bits: np.ndarray) -> None:
    """Embed `bits` (0/1 array) into carrier in-place, starting at start_index."""
    num_lsb = validate_num_lsb(num_lsb, carrier)
    n_bits = len(bits)
    if n_bits == 0:
        return
    n_units = (n_bits + num_lsb - 1) // num_lsb
    if start_index < 0 or start_index + n_units > len(carrier):
        raise ValueError(
            f"Not enough capacity from the selected start location: need {n_units} carrier "
            f"units, only {capacity_units(carrier, start_index)} available."
        )
    pad = n_units * num_lsb - n_bits
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    grouped = bits.reshape(n_units, num_lsb)
    weights = 1 << np.arange(num_lsb - 1, -1, -1)
    values = grouped.astype(np.int64).dot(weights)

    unsigned, keep_mask = low_bits(carrier, num_lsb)
    seg = unsigned[start_index:start_index + n_units]  # a view: writes reach the carrier
    seg &= ~keep_mask
    seg |= values.astype(seg.dtype)


def extract_bits(carrier: np.ndarray, start_index: int, num_lsb: int, n_bits: int) -> np.ndarray:
    num_lsb = validate_num_lsb(num_lsb, carrier)
    if n_bits == 0:
        return np.zeros(0, dtype=np.uint8)
    n_units = (n_bits + num_lsb - 1) // num_lsb
    if start_index < 0 or start_index + n_units > len(carrier):
        raise ValueError(
            f"Not enough data from the selected start location: need {n_units} carrier "
            f"units, only {capacity_units(carrier, start_index)} available."
        )
    unsigned, read_mask = low_bits(carrier, num_lsb)
    vals = (unsigned[start_index:start_index + n_units] & read_mask).astype(np.int64)
    weights = np.arange(num_lsb - 1, -1, -1)
    bits = ((vals[:, None] >> weights) & 1).astype(np.uint8).reshape(-1)
    return bits[:n_bits]


class StegoStream:
    """Sequential reader/writer over a carrier array at a fixed start location.

    Lets payload.py build/parse the variable-length container format one
    field at a time without every caller re-deriving bit offsets by hand.
    """

    def __init__(self, carrier: np.ndarray, start_index: int, num_lsb: int):
        self.carrier = carrier
        self.start_index = int(start_index)
        self.num_lsb = validate_num_lsb(num_lsb, carrier)
        self.pos_units = 0  # advances as we read/write, measured in carrier units

    def capacity_bytes(self) -> int:
        return capacity_bytes(self.carrier, self.start_index + self.pos_units, self.num_lsb)

    def write(self, data: bytes) -> None:
        bits = bytes_to_bits(data)
        embed_bits(self.carrier, self.start_index + self.pos_units, self.num_lsb, bits)
        self.pos_units += (len(bits) + self.num_lsb - 1) // self.num_lsb

    def read(self, n_bytes: int) -> bytes:
        n_bits = n_bytes * 8
        bits = extract_bits(self.carrier, self.start_index + self.pos_units, self.num_lsb, n_bits)
        self.pos_units += (n_bits + self.num_lsb - 1) // self.num_lsb
        return bits_to_bytes(bits)
