"""
Audio cover-object support (WAV/PCM, FR2/FR5/FR6/FR8).

Supports 16-, 24- and 32-bit PCM WAV. The header determines sample width;
packed 24-bit values are sign-extended to int32 in memory and written back
as three bytes per sample. Each sample remains one carrier unit. Other
input encodings are converted by media_input before embedding.
"""
from __future__ import annotations

import io
import struct
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
        return "This file is not a WAV file. Please choose a 16-, 24- or 32-bit PCM WAV."
    if text == f"unknown format: {_WAVE_FORMAT_FLOAT}" or _FLOAT_SUBFORMAT in text:
        return (
            "32-bit float WAV isn't supported: this tool hides data in whole-number (PCM) samples. "
            "Please export it as 16-, 24- or 32-bit PCM WAV."
        )
    if text == f"unknown format: {_WAVE_FORMAT_EXTENSIBLE}":
        # Only Python < 3.12: newer versions read extensible PCM headers.
        return (
            "This WAV uses the extensible header format, which this Python version cannot read "
            "(Python 3.12 or newer can). Please re-export it as a standard 16-bit PCM WAV."
        )
    if text.startswith(("unknown format", "unknown extended format")):
        return "This WAV uses a compressed or non-PCM encoding. Please export it as 16-, 24- or 32-bit PCM WAV."
    return f"Could not read this WAV file ({text}). Please use a 16-, 24- or 32-bit PCM WAV."


# SubFormat GUID of an extensible-header WAV whose samples are plain integer PCM.
_PCM_SUBFORMAT = bytes.fromhex("0100000000001000800000aa00389b71")


def _extensible_pcm_as_plain(file_bytes: bytes) -> bytes:
    """Relabel an extensible-header integer PCM WAV as a standard PCM WAV.

    Python < 3.12 cannot read WAVE_FORMAT_EXTENSIBLE, which ffmpeg writes for
    PCM wider than 16 bits (for example when media_input converts MP3 or float
    WAV). The sample data is identical, so only the format tag changes. Other
    files are returned unchanged."""
    if file_bytes[:4] != b"RIFF" or file_bytes[8:12] != b"WAVE":
        return file_bytes
    pos = 12
    while pos + 8 <= len(file_bytes):
        chunk_id, size = file_bytes[pos:pos + 4], struct.unpack("<I", file_bytes[pos + 4:pos + 8])[0]
        if chunk_id == b"fmt ":
            body = file_bytes[pos + 8:pos + 8 + size]
            if (size >= 40 and struct.unpack("<H", body[:2])[0] == _WAVE_FORMAT_EXTENSIBLE
                    and body[24:40] == _PCM_SUBFORMAT):
                return file_bytes[:pos + 8] + struct.pack("<H", 1) + file_bytes[pos + 10:]
            return file_bytes
        pos += 8 + size + (size & 1)
    return file_bytes


def load_audio_carrier(file_bytes: bytes) -> AudioCarrier:
    file_bytes = _extensible_pcm_as_plain(file_bytes)
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
            "Please use 16-, 24- or 32-bit PCM WAV."
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
