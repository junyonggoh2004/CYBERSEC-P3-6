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


def load_audio_carrier(file_bytes: bytes) -> AudioCarrier:
    with wave.open(io.BytesIO(file_bytes), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth not in _DTYPE_BY_SAMPWIDTH:
        supported = ", ".join(f"{w * 8}-bit" for w in sorted(_DTYPE_BY_SAMPWIDTH))
        raise ValueError(
            f"Unsupported WAV sample width: {sampwidth * 8}-bit PCM. Supported: {supported}."
        )
    if sampwidth == 1:
        raise ValueError(
            "8-bit PCM WAV is not supported (too little headroom for reliable LSB embedding). "
            "Please use 16-bit or 32-bit PCM WAV."
        )

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
