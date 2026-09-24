"""Tests for the WAV/PCM audio carrier (audio_lsb.py).

Covers what the carrier itself promises: it loads 16- and 32-bit PCM WAVs as
interleaved signed samples, writes them back with the same format, carries
hidden bits through a save/reload at every LSB depth, and rejects anything
else with a message the GUI can show as-is (not a server error).
"""

import io
import struct
import sys
import uuid
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from stego import audio_lsb
from stego.bitstream import StegoStream
from app import app


def _wav_bytes(samples, width=2, channels=1, rate=44100):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples).tobytes())
    return buf.getvalue()


def _riff(fmt_chunk, data):
    """A minimal RIFF/WAVE file with a hand-written fmt chunk, for formats the
    stdlib writer refuses to produce (float, mu-law, extensible)."""
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
            + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _fmt(tag, channels, rate, bits):
    block = channels * bits // 8
    return struct.pack("<HHIIHH", tag, channels, rate, rate * block, block, bits)


def _random_samples(dtype, count, seed=0):
    info = np.iinfo(dtype)
    return np.random.default_rng(seed).integers(info.min, info.max, size=count, dtype=dtype, endpoint=True)


# --- loading -----------------------------------------------------------------


def test_load_16bit_mono():
    samples = np.array([0, 1, -1, 32767, -32768], dtype=np.int16)
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(samples))
    assert carrier.array.dtype == np.int16
    assert carrier.array.tolist() == samples.tolist()
    assert (carrier.nchannels, carrier.sampwidth, carrier.framerate, carrier.nframes) == (1, 2, 44100, 5)


def test_load_stereo_keeps_samples_interleaved():
    # frames: (L=1, R=-1), (L=2, R=-2) -> carrier units L, R, L, R
    samples = np.array([1, -1, 2, -2], dtype=np.int16)
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(samples, channels=2))
    assert carrier.array.tolist() == [1, -1, 2, -2]
    assert (carrier.nchannels, carrier.nframes) == (2, 2)


def test_samples_read_as_signed_little_endian():
    raw = struct.pack("<hhh", -1, 256, -32768)
    carrier = audio_lsb.load_audio_carrier(_riff(_fmt(1, 1, 8000, 16), raw))
    assert carrier.array.tolist() == [-1, 256, -32768]


def test_load_32bit_uses_int32():
    samples = np.array([-2**31, -1, 0, 2**31 - 1], dtype=np.int32)
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(samples, width=4))
    assert carrier.array.dtype == np.int32
    assert carrier.array.tolist() == samples.tolist()


def test_describe_reports_the_format():
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(np.zeros(8820, dtype=np.int16), channels=2, rate=22050))
    assert audio_lsb.describe(carrier) == {
        "channels": 2,
        "sample_width_bits": 16,
        "sample_rate_hz": 22050,
        "frames": 4410,
        "total_units": 8820,
        "duration_seconds": 0.2,
    }


# --- saving ------------------------------------------------------------------


@pytest.mark.parametrize("width, dtype", [(2, np.int16), (4, np.int32)])
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("rate", [8000, 44100, 48000])
def test_save_round_trip_keeps_format_and_samples(width, dtype, channels, rate):
    samples = _random_samples(dtype, 600 * channels)
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(samples, width, channels, rate))

    reloaded = audio_lsb.load_audio_carrier(audio_lsb.carrier_to_wav_bytes(carrier))

    assert (reloaded.nchannels, reloaded.sampwidth, reloaded.framerate, reloaded.nframes) == (channels, width, rate, 600)
    assert np.array_equal(reloaded.array, samples)


# --- hiding data in the carrier --------------------------------------------


@pytest.mark.parametrize("width, dtype", [(2, np.int16), (4, np.int32)])
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("num_lsb", range(1, 9))
def test_hidden_bytes_survive_save_and_reload(width, dtype, channels, num_lsb):
    payload = b"P3-6 hidden payload \x00\xff" * 4
    start = 37
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(_random_samples(dtype, 2000, seed=num_lsb), width, channels))

    StegoStream(carrier.array, start, num_lsb).write(payload)
    reloaded = audio_lsb.load_audio_carrier(audio_lsb.carrier_to_wav_bytes(carrier))

    assert StegoStream(reloaded.array, start, num_lsb).read(len(payload)) == payload


@pytest.mark.parametrize("width, dtype", [(2, np.int16), (4, np.int32)])
@pytest.mark.parametrize("num_lsb", range(1, 9))
def test_embedding_changes_only_the_chosen_low_bits(width, dtype, num_lsb):
    cover = _random_samples(dtype, 3000, seed=7)
    carrier = audio_lsb.load_audio_carrier(_wav_bytes(cover, width))
    payload = np.random.default_rng(num_lsb).integers(0, 256, size=200, dtype=np.uint8).tobytes()
    start = 100

    stream = StegoStream(carrier.array, start, num_lsb)
    stream.write(payload)
    end = start + stream.pos_units
    stego = carrier.array

    high_bits = ~np.array((1 << num_lsb) - 1, dtype=dtype)
    assert not np.any((stego ^ cover) & high_bits)          # nothing above the chosen LSBs
    assert np.array_equal(stego[:start], cover[:start])     # nothing before the start location
    assert np.array_equal(stego[end:], cover[end:])         # nothing after the payload
    assert np.any(stego[start:end] != cover[start:end])     # and the payload really went in


# --- unsupported or damaged files: clear messages, not crashes --------------


def _extensible_float_wav():
    float_guid = uuid.UUID("00000003-0000-0010-8000-00aa00389b71").bytes_le
    fmt = struct.pack("<HHIIHHHHI", 0xFFFE, 1, 44100, 44100 * 4, 4, 32, 22, 32, 0) + float_guid
    return _riff(fmt, np.zeros(10, dtype=np.float32).tobytes())


# Python < 3.12 cannot read any extensible header, so it gets that message instead.
_EXTENSIBLE_FLOAT_MESSAGE = "float WAV isn't supported" if sys.version_info >= (3, 12) else "extensible header"

BAD_WAVS = {
    "not a WAV": (b"this is not audio" * 10, "not a WAV file"),
    "empty file": (b"", "empty or cut off"),
    "32-bit float": (_riff(_fmt(3, 1, 44100, 32), np.zeros(10, dtype=np.float32).tobytes()), "float WAV isn't supported"),
    "extensible float": (_extensible_float_wav(), _EXTENSIBLE_FLOAT_MESSAGE),
    "mu-law": (_riff(_fmt(7, 1, 8000, 8), b"\x7f" * 10), "compressed or non-PCM"),
    "24-bit PCM": (_wav_bytes(np.zeros(30, dtype=np.uint8), width=3), "24-bit PCM. Supported: 16-bit and 32-bit PCM"),
    "8-bit PCM": (_wav_bytes(np.zeros(10, dtype=np.uint8), width=1), "8-bit PCM WAV is not supported"),
    "cut mid-sample": (_wav_bytes(np.arange(100, dtype=np.int16))[:-1], "truncated or damaged"),
    "no samples": (_wav_bytes(np.zeros(0, dtype=np.int16)), "no audio samples"),
}


@pytest.mark.parametrize("name", BAD_WAVS)
def test_bad_wav_is_rejected_with_a_clear_message(name):
    data, message = BAD_WAVS[name]
    with pytest.raises(ValueError, match=message):
        audio_lsb.load_audio_carrier(data)


def test_header_overstating_its_length_counts_the_real_frames():
    # A download cut at a frame boundary: the header still claims 1000 frames.
    data = _wav_bytes(np.arange(1000, dtype=np.int16))[:-2]
    carrier = audio_lsb.load_audio_carrier(data)
    assert carrier.nframes == 999
    assert audio_lsb.describe(carrier)["frames"] == carrier.array.size == 999


@pytest.mark.parametrize("name", ["not a WAV", "32-bit float"])
def test_bad_wav_in_the_app_is_a_clear_400_not_a_server_error(name):
    data, message = BAD_WAVS[name]
    response = app.test_client().post(
        "/api/prepare",
        data={
            "cover_type": "audio", "num_lsb": "1", "start_mode": "manual", "manual_offset": "0",
            "payload_type": "text", "payload_text": "hi",
            "cover_file": (io.BytesIO(data), "cover.wav"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    assert "Unexpected server error" not in response.get_json()["error"]
