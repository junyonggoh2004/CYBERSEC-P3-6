"""WAV carrier: validate, load, save, embed, extract.

16-bit uncompressed PCM only, mono or stereo. Every sample is a carrier unit
(interleaved for stereo). Embed/extract delegate to the shared bitstream
module, so the bit format matches the image carrier and whatever
payload.py / pipeline.py produce.

One thing to know about that format (owned by bitstream.py, not here): bits
go in MSB-first, num_lsb per sample, and the final sample's unused low bits
are zero-padded. So the modified positions are embedded_bit_slots()
= span * num_lsb, not just the payload's own bits, and the stable-media
hash has to normalise all of them.

Stdlib `wave` plus NumPy. Extra chunks (LIST, id3...) are dropped by the
stdlib writer; noted in the README.
"""

from __future__ import annotations

import os
import tempfile
import wave
from dataclasses import dataclass

import numpy as np

try:  # inside the backend package
    from . import bitstream
except ImportError:  # standalone (tests, scripts run from this folder)
    import bitstream

SUPPORTED_SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM
MIN_LSB = bitstream.MIN_LSB
MAX_LSB = bitstream.MAX_LSB


class WavCarrierError(Exception):
    """Base class for WAV carrier errors."""


class UnsupportedWavError(WavCarrierError):
    """The file is not a WAV this implementation supports."""


class WavCapacityError(WavCarrierError):
    """The requested data does not fit the eligible samples."""


@dataclass(frozen=True)
class WavInfo:
    """A loaded WAV's format parameters."""

    channels: int
    sample_rate: int
    sample_width_bytes: int
    frame_count: int

    @property
    def sample_count(self) -> int:
        """Total samples across all channels (a frame holds one per channel)."""
        return self.frame_count * self.channels


@dataclass
class WavCarrier:
    """A loaded 16-bit PCM WAV.

    `samples` is 1-D int16, interleaved for stereo (L, R, L, R, ...). Same
    layout as audio_lsb.AudioCarrier.array, so bitstream/capacity/metrics
    functions take either directly.
    """

    info: WavInfo
    samples: np.ndarray

    @property
    def eligible_units(self) -> int:
        return int(self.samples.size)


def load(path: str) -> WavCarrier:
    """Open and validate a 16-bit PCM WAV, raising UnsupportedWavError otherwise."""
    try:
        with wave.open(path, "rb") as w:
            channels = w.getnchannels()
            sample_rate = w.getframerate()
            sample_width = w.getsampwidth()
            frame_count = w.getnframes()
            comp_type = w.getcomptype()
            raw = w.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise UnsupportedWavError(f"Not a readable WAV file: {exc}") from exc

    if comp_type != "NONE":
        raise UnsupportedWavError(f"Only uncompressed PCM is supported (got '{comp_type}').")
    if sample_width != SUPPORTED_SAMPLE_WIDTH_BYTES:
        raise UnsupportedWavError(
            f"Only 16-bit PCM is supported (got {sample_width * 8}-bit)."
        )
    if channels < 1:
        raise UnsupportedWavError(f"Invalid channel count ({channels}).")
    if frame_count < 1:
        raise UnsupportedWavError("WAV has no audio samples.")

    expected_bytes = frame_count * channels * sample_width
    if len(raw) != expected_bytes:
        raise UnsupportedWavError(
            f"Truncated PCM data: header declares {expected_bytes} bytes, found {len(raw)}."
        )

    # 16-bit PCM is signed little-endian; '<i2' spells that out.
    samples = np.frombuffer(raw, dtype="<i2").astype(np.int16)

    info = WavInfo(
        channels=channels,
        sample_rate=sample_rate,
        sample_width_bytes=sample_width,
        frame_count=frame_count,
    )
    return WavCarrier(info=info, samples=samples)


def save(carrier: WavCarrier, path: str) -> None:
    """Write the carrier out as a standard PCM WAV, keeping its format.

    Writes to a temp file then moves it into place, so an interrupted write
    can't leave a half-written file where a valid one was.
    """
    info = carrier.info
    if info.channels < 1:
        raise ValueError(f"Invalid channel count ({info.channels}).")
    if carrier.samples.size % info.channels:
        # writeframes would quietly drop a leftover sample; refuse instead so a
        # payload bit can't vanish with it.
        raise ValueError(
            f"Sample count ({carrier.samples.size}) is not a whole number of "
            f"{info.channels}-channel frames."
        )
    if info.sample_count != carrier.samples.size:
        # Header comes from `info`, audio from `samples`; if they disagree
        # the saved file lies about its own format.
        raise ValueError(
            f"info describes {info.frame_count} frames x {info.channels} channels "
            f"({info.sample_count} samples) but the carrier holds "
            f"{carrier.samples.size}."
        )

    data = carrier.samples.astype("<i2").tobytes()
    directory = os.path.dirname(os.path.abspath(path))
    handle, temp_path = tempfile.mkstemp(suffix=".wav.tmp", dir=directory)
    os.close(handle)
    try:
        with wave.open(temp_path, "wb") as w:
            w.setnchannels(info.channels)
            w.setsampwidth(info.sample_width_bytes)
            w.setframerate(info.sample_rate)
            w.writeframes(data)
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


# --- embed / extract (delegating to the shared bitstream module) -------------


def embedded_sample_span(byte_count: int, num_lsb: int) -> int:
    """Number of samples `embed`/`extract` span for `byte_count` bytes."""
    if byte_count < 0:
        raise ValueError(f"byte_count must not be negative (got {byte_count}).")
    num_lsb = bitstream.validate_num_lsb(num_lsb)
    return -(-(byte_count * 8) // num_lsb)  # ceil division


def embedded_bit_slots(byte_count: int, num_lsb: int) -> int:
    """Bit positions `embed` writes for `byte_count` bytes.

    bitstream.embed_bits zero-pads the final sample, so every low bit of
    every spanned sample gets written: span * num_lsb, not byte_count * 8.
    The stable hash must normalise exactly these positions.
    """
    num_lsb = bitstream.validate_num_lsb(num_lsb)
    return embedded_sample_span(byte_count, num_lsb) * num_lsb


def embed(carrier: WavCarrier, data: bytes, num_lsb: int, start_index: int = 0) -> WavCarrier:
    """Embed `data` in the lowest `num_lsb` bits from `start_index`.

    Returns a new carrier; the input is untouched (embed_bits mutates in
    place, so it gets a copy). Raises WavCapacityError if it won't fit.
    """
    num_lsb = bitstream.validate_num_lsb(num_lsb)
    if start_index < 0 or start_index >= carrier.samples.size:
        raise ValueError(
            f"start_index out of range (got {start_index}, samples={carrier.samples.size})."
        )

    bits = bitstream.bytes_to_bits(data)
    if bits.size > bitstream.capacity_bits(carrier.samples, start_index, num_lsb):
        raise WavCapacityError(
            f"Need {bits.size} bits but only "
            f"{bitstream.capacity_bits(carrier.samples, start_index, num_lsb)} "
            f"available from start_index={start_index}."
        )

    out = carrier.samples.copy()
    bitstream.embed_bits(out, start_index, num_lsb, bits)
    return WavCarrier(info=carrier.info, samples=out)


def extract(carrier: WavCarrier, byte_count: int, num_lsb: int, start_index: int = 0) -> bytes:
    """Read `byte_count` bytes back from the lowest `num_lsb` bits at `start_index`."""
    num_lsb = bitstream.validate_num_lsb(num_lsb)
    if byte_count < 0:
        raise ValueError(f"byte_count must not be negative (got {byte_count}).")
    if start_index < 0 or start_index >= carrier.samples.size:
        raise ValueError(
            f"start_index out of range (got {start_index}, samples={carrier.samples.size})."
        )

    span = embedded_sample_span(byte_count, num_lsb)
    if start_index + span > carrier.samples.size:
        raise WavCapacityError(
            f"Requested {byte_count} bytes but not enough samples from start_index={start_index}."
        )

    bits = bitstream.extract_bits(carrier.samples, start_index, num_lsb, byte_count * 8)
    return bitstream.bits_to_bytes(bits)