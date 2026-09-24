"""
Audio cover-object support (WAV/PCM, FR2/FR5/FR6/FR8).

Supports 16-, 24- and 32-bit PCM WAV. The header determines sample width;
packed 24-bit values are sign-extended to int32 in memory and written back
as three bytes per sample. Each sample remains one carrier unit. Other
input encodings are converted by media_input before embedding.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np

_DTYPE_BY_SAMPWIDTH = {
    1: np.uint8,   # 8-bit PCM is unsigned in WAV
    2: np.int16,   # 16-bit PCM
    3: np.int32,   # Packed 24-bit PCM is expanded to signed int32 in memory
    4: np.int32,   # 32-bit PCM
}


@dataclass
class AudioCarrier:
    array: np.ndarray  # 1-D, dtype depends on sample width, mutable
    nchannels: int
    sampwidth: int  # bytes per sample: 2, 3 or 4
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

    if len(raw) != nframes * nchannels * sampwidth:
        raise ValueError("WAV audio data is truncated. Choose a complete audio file.")
    if sampwidth == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
        arr = (values ^ 0x800000) - 0x800000
    else:
        dtype = np.dtype(_DTYPE_BY_SAMPWIDTH[sampwidth]).newbyteorder("<")
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
        if carrier.sampwidth == 3:
            packed = np.column_stack([(carrier.array >> shift) & 255 for shift in (0, 8, 16)])
            wf.writeframes(packed.astype(np.uint8).tobytes())
        else:
            wf.writeframes(carrier.array.astype(carrier.array.dtype.newbyteorder("<")).tobytes())
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
