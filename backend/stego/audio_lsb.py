"""
Audio cover-object support (WAV/PCM, FR2/FR5/FR6/FR8).

Supports 16-bit and 32-bit PCM WAV specifically (the "16bit and 32bit"
requirement): the sample width is auto-detected from the WAV header (never
hard-coded), each PCM sample becomes one carrier unit (int16 or int32), and
LSB embedding/extraction reuses the exact same bitstream.py primitives as
images. 8-bit PCM (unsigned) and other widths (e.g. 24-bit, float) are
rejected with a clear error rather than silently corrupting the file.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np

_DTYPE_BY_SAMPWIDTH = {
    1: np.uint8,   # 8-bit PCM is unsigned in WAV
    2: np.int16,   # 16-bit PCM
    4: np.int32,   # 32-bit PCM
}


@dataclass
class AudioCarrier:
    array: np.ndarray  # 1-D, dtype depends on sample width, mutable
    nchannels: int
    sampwidth: int  # bytes per sample: 1, 2 or 4
    framerate: int
    nframes: int


# The SubFormat GUID Python's `wave` reports for an extensible-header float WAV.
_FLOAT_SUBFORMAT = "00000003-0000-0010-8000-00aa00389b71"
_WAVE_FORMAT_FLOAT = 3
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def _unreadable_wav_message(exc: Exception) -> str:
    """Turns a stdlib `wave` error into a message the GUI can show as-is.

    `wave` raises wave.Error / EOFError with low-level text such as
    "unknown format: 3"; those are not ValueErrors, so the API routes would
    otherwise report them as an unexpected server error."""
    text = str(exc)
    if isinstance(exc, EOFError):
        return "This WAV file is empty or cut off before its audio data. Please use a complete WAV file."
    if "RIFF" in text or "not a WAVE file" in text:
        return "This file is not a WAV file. Please choose a 16-bit or 32-bit PCM WAV."
    if text == f"unknown format: {_WAVE_FORMAT_FLOAT}" or _FLOAT_SUBFORMAT in text:
        return (
            "32-bit float WAV is not supported (LSB embedding needs integer samples). "
            "Please export it as 16-bit or 32-bit PCM WAV."
        )
    if text == f"unknown format: {_WAVE_FORMAT_EXTENSIBLE}":
        # Only Python < 3.12: newer versions read extensible PCM headers.
        return (
            "This WAV uses the extensible header format, which this Python version cannot read "
            "(Python 3.12 or newer can). Please re-export it as a standard 16-bit PCM WAV."
        )
    if text.startswith(("unknown format", "unknown extended format")):
        return "This WAV uses a compressed or non-PCM encoding. Please export it as 16-bit or 32-bit PCM WAV."
    return f"Could not read this WAV file ({text}). Please use a 16-bit or 32-bit PCM WAV."


def load_audio_carrier(file_bytes: bytes) -> AudioCarrier:
    try:
        with wave.open(io.BytesIO(file_bytes), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except (wave.Error, EOFError) as exc:
        raise ValueError(_unreadable_wav_message(exc)) from exc

    if sampwidth not in _DTYPE_BY_SAMPWIDTH:
        # 8-bit is in the table (for its dtype) but rejected just below.
        supported = " and ".join(f"{w * 8}-bit" for w in sorted(_DTYPE_BY_SAMPWIDTH) if w != 1)
        raise ValueError(
            f"Unsupported WAV sample width: {sampwidth * 8}-bit PCM. Supported: {supported} PCM."
        )
    if sampwidth == 1:
        raise ValueError(
            "8-bit PCM WAV is not supported (too little headroom for reliable LSB embedding). "
            "Please use 16-bit or 32-bit PCM WAV."
        )

    frame_bytes = sampwidth * nchannels
    if len(raw) % frame_bytes:
        raise ValueError(
            "This WAV file is truncated or damaged: its audio data stops part-way through a sample. "
            "Please use a complete WAV file."
        )
    # A cut-off file's header can declare more frames than it holds; count what
    # is really there so describe() matches the stego file written back out.
    nframes = len(raw) // frame_bytes
    if nframes == 0:
        raise ValueError("This WAV file contains no audio samples.")

    dtype = _DTYPE_BY_SAMPWIDTH[sampwidth]
    arr = np.frombuffer(raw, dtype=dtype).copy()
    return AudioCarrier(
        array=arr,
        nchannels=nchannels,
        sampwidth=sampwidth,
        framerate=framerate,
        nframes=nframes,
    )


def carrier_to_wav_bytes(carrier: AudioCarrier) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(carrier.nchannels)
        wf.setsampwidth(carrier.sampwidth)
        wf.setframerate(carrier.framerate)
        wf.writeframes(carrier.array.tobytes())
    return buf.getvalue()


def describe(carrier: AudioCarrier) -> dict:
    return {
        "channels": carrier.nchannels,
        "sample_width_bits": carrier.sampwidth * 8,
        "sample_rate_hz": carrier.framerate,
        "frames": carrier.nframes,
        "total_units": int(carrier.array.size),
        "duration_seconds": round(carrier.nframes / carrier.framerate, 3) if carrier.framerate else 0,
    }
