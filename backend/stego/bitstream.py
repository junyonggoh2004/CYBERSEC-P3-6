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
MAX_LSB = 8


def validate_num_lsb(num_lsb: int) -> int:
    num_lsb = int(num_lsb)
    if not (MIN_LSB <= num_lsb <= MAX_LSB):
        raise ValueError(f"num_lsb must be between {MIN_LSB} and {MAX_LSB} (got {num_lsb}).")
    return num_lsb


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
    num_lsb = validate_num_lsb(num_lsb)
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

    seg = carrier[start_index:start_index + n_units]
    dtype = seg.dtype
    # Build the "clear low num_lsb bits" mask by inverting a small positive,
    # already-typed value rather than casting a negative Python int into an
    # unsigned dtype (numpy >= 2 raises OverflowError on the latter).
    keep_mask = np.array((1 << num_lsb) - 1, dtype=dtype)
    clear_mask = ~keep_mask
    set_values = values.astype(dtype)
    seg &= clear_mask
    seg |= set_values


def extract_bits(carrier: np.ndarray, start_index: int, num_lsb: int, n_bits: int) -> np.ndarray:
    num_lsb = validate_num_lsb(num_lsb)
    if n_bits == 0:
        return np.zeros(0, dtype=np.uint8)
    n_units = (n_bits + num_lsb - 1) // num_lsb
    if start_index < 0 or start_index + n_units > len(carrier):
        raise ValueError(
            f"Not enough data from the selected start location: need {n_units} carrier "
            f"units, only {capacity_units(carrier, start_index)} available."
        )
    seg = carrier[start_index:start_index + n_units]
    read_mask = np.array((1 << num_lsb) - 1, dtype=seg.dtype)
    vals = (seg & read_mask).astype(np.int64)
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
        self.num_lsb = validate_num_lsb(num_lsb)
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
