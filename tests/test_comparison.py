"""Cover-vs-stego direct comparison tests (PNG + WAV) - separate from Kim's
steganalysis (tests/test_steganalysis.py), which infers from one suspect
file instead of comparing two known files."""
import base64
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from stego import audio_lsb, comparison, crypto_utils, pipeline  # noqa: E402
from app import app  # noqa: E402


@pytest.fixture
def stable_keys(monkeypatch):
    """pipeline.encode() signs with the real on-disk key by default; keep
    tests hermetic (and avoid touching the developer's actual keys/) by
    signing/verifying with an in-memory key for the duration of the test."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(crypto_utils, "load_private_key", lambda: key)
    monkeypatch.setattr(crypto_utils, "load_public_key", lambda *_: key.public_key())
    return key


def png_bytes(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def wav_bytes(samples: np.ndarray, nchannels=1, sampwidth=2, framerate=8000) -> bytes:
    carrier = audio_lsb.AudioCarrier(
        array=samples, nchannels=nchannels, sampwidth=sampwidth,
        framerate=framerate, nframes=len(samples) // nchannels,
    )
    return audio_lsb.carrier_to_wav_bytes(carrier)


def encode_png(cover_bytes: bytes, num_lsb: int, data: bytes = b"hello world", offset: int = 16) -> bytes:
    return pipeline.encode(
        cover_type="image", cover_bytes=cover_bytes, payload_type="text", data=data,
        filename=None, mime="text/plain", num_lsb=num_lsb, start_mode="manual",
        manual_offset=offset, passphrase=None, media_id="cmp-test", team_metadata={},
        stego_out_name="test.png",
    ).stego_bytes


def encode_wav(cover_bytes: bytes, num_lsb: int, data: bytes = b"hello audio", offset: int = 16) -> bytes:
    return pipeline.encode(
        cover_type="audio", cover_bytes=cover_bytes, payload_type="text", data=data,
        filename=None, mime="text/plain", num_lsb=num_lsb, start_mode="manual",
        manual_offset=offset, passphrase=None, media_id="cmp-test", team_metadata={},
        stego_out_name="test.wav",
    ).stego_bytes


def tone(n, dtype=np.int16, amplitude=10000):
    t = np.linspace(0, 1, n, endpoint=False)
    return (np.sin(2 * np.pi * 5 * t) * amplitude).astype(dtype)


# --------------------------------------------------------------------------
# PNG comparison
# --------------------------------------------------------------------------
def test_png_identical_gives_zero_changes():
    cover_arr = np.random.default_rng(1).integers(0, 256, (40, 50, 3), dtype=np.uint8)
    cover = png_bytes(cover_arr)
    result = comparison.compare_images(cover, cover)
    stats = result["stats"]
    assert stats["changed_rgb_channels"] == 0
    assert stats["changed_pixels"] == 0
    assert stats["max_abs_channel_difference"] == 0
    assert stats["mean_abs_channel_difference"] == 0.0
    assert stats["percent_pixels_changed"] == 0.0
    # No changes -> the "over cover" highlight overlay must render as exactly
    # the plain cover image (zero highlight blend everywhere), never a false
    # highlight.
    over_cover = np.array(Image.open(io.BytesIO(base64.b64decode(result["amplified_difference_over_cover_png_base64"]))))
    np.testing.assert_array_equal(over_cover, cover_arr)


def test_png_1lsb_stego_has_small_bounded_diff(stable_keys):
    cover_arr = np.random.default_rng(2).integers(0, 256, (60, 60, 3), dtype=np.uint8)
    cover = png_bytes(cover_arr)
    stego = encode_png(cover, num_lsb=1, data=b"x" * 200, offset=10)
    result = comparison.compare_images(cover, stego)
    stats = result["stats"]
    assert stats["changed_rgb_channels"] > 0
    assert stats["max_abs_channel_difference"] <= 1
    assert result["amplification_factor"] >= 1.0
    assert result["change_mask_png_base64"]
    assert result["amplified_difference_png_base64"]
    assert result["amplified_difference_over_cover_png_base64"]
    # The "over cover" composite must be the same size as the cover and must
    # differ from the plain cover exactly where pixels actually changed.
    over_cover = np.array(Image.open(io.BytesIO(base64.b64decode(result["amplified_difference_over_cover_png_base64"]))))
    assert over_cover.shape == cover_arr.shape
    highlighted = np.any(over_cover != cover_arr, axis=2)
    assert highlighted.sum() == stats["changed_pixels"]


def test_png_multi_lsb_comparison_bounded_by_depth(stable_keys):
    cover_arr = np.random.default_rng(3).integers(0, 256, (60, 60, 3), dtype=np.uint8)
    cover = png_bytes(cover_arr)
    stego = encode_png(cover, num_lsb=4, data=b"y" * 500, offset=10)
    result = comparison.compare_images(cover, stego)
    stats = result["stats"]
    assert stats["changed_rgb_channels"] > 0
    assert stats["max_abs_channel_difference"] <= (2 ** 4 - 1)


def test_png_dimension_mismatch_rejected_cleanly():
    a = png_bytes(np.zeros((20, 20, 3), dtype=np.uint8))
    b = png_bytes(np.zeros((20, 21, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        comparison.compare_images(a, b)


def test_png_compare_api_rejects_mismatch_cleanly():
    client = app.test_client()
    a = png_bytes(np.zeros((10, 10, 3), dtype=np.uint8))
    b = png_bytes(np.zeros((12, 10, 3), dtype=np.uint8))
    res = client.post(
        "/api/compare/image",
        data={"cover_file": (io.BytesIO(a), "cover.png"), "stego_file": (io.BytesIO(b), "stego.png")},
    )
    assert res.status_code == 400
    assert "error" in res.json


def test_png_compare_api_round_trip(stable_keys):
    cover_arr = np.random.default_rng(4).integers(0, 256, (32, 32, 3), dtype=np.uint8)
    cover = png_bytes(cover_arr)
    stego = encode_png(cover, num_lsb=2, data=b"api test", offset=5)
    client = app.test_client()
    res = client.post(
        "/api/compare/image",
        data={"cover_file": (io.BytesIO(cover), "cover.png"), "stego_file": (io.BytesIO(stego), "stego.png")},
    )
    assert res.status_code == 200
    assert res.json["stats"]["changed_rgb_channels"] > 0


# --------------------------------------------------------------------------
# WAV comparison
# --------------------------------------------------------------------------
def test_wav_identical_gives_zero_changes():
    samples = tone(4000)
    cover = wav_bytes(samples, nchannels=1, sampwidth=2, framerate=8000)
    result = comparison.compare_audio(cover, cover)
    stats = result["stats"]
    assert stats["changed_samples"] == 0
    assert stats["max_abs_sample_difference"] == 0
    assert stats["rms_difference"] == 0.0


def test_wav_1lsb_stego_small_diff(stable_keys):
    samples = tone(8000)
    cover = wav_bytes(samples, nchannels=1, sampwidth=2, framerate=8000)
    stego = encode_wav(cover, num_lsb=1, data=b"z" * 200, offset=10)
    result = comparison.compare_audio(cover, stego)
    stats = result["stats"]
    assert stats["changed_samples"] > 0
    assert stats["max_abs_sample_difference"] <= 1
    assert len(result["waveform"]["channels"]) == 1


def test_wav_stereo_per_channel_comparison(stable_keys):
    left = tone(4000, amplitude=8000)
    right = tone(4000, amplitude=4000)
    interleaved = np.empty(8000, dtype=np.int16)
    interleaved[0::2] = left
    interleaved[1::2] = right
    cover = wav_bytes(interleaved, nchannels=2, sampwidth=2, framerate=8000)
    stego = encode_wav(cover, num_lsb=2, data=b"stereo test payload", offset=20)
    result = comparison.compare_audio(cover, stego)
    assert result["stats"]["channels"] == 2
    assert len(result["stats"]["per_channel"]) == 2
    assert len(result["waveform"]["channels"]) == 2
    assert result["stats"]["changed_samples"] > 0
    # Every per-channel changed count must be <= that channel's total samples.
    for ch_stats in result["stats"]["per_channel"]:
        assert 0 <= ch_stats["changed_samples"] <= ch_stats["total_samples_compared"]


def test_wav_incompatible_parameters_rejected_cleanly():
    a = wav_bytes(tone(2000), nchannels=1, sampwidth=2, framerate=8000)
    b = wav_bytes(tone(2000), nchannels=1, sampwidth=2, framerate=16000)
    with pytest.raises(ValueError):
        comparison.compare_audio(a, b)


def test_wav_compare_api_rejects_mismatch_cleanly():
    client = app.test_client()
    a = wav_bytes(tone(1000), nchannels=1, sampwidth=2, framerate=8000)
    b = wav_bytes(tone(1000), nchannels=2, sampwidth=2, framerate=8000)
    res = client.post(
        "/api/compare/audio",
        data={"cover_file": (io.BytesIO(a), "cover.wav"), "stego_file": (io.BytesIO(b), "stego.wav")},
    )
    assert res.status_code == 400
    assert "error" in res.json


def test_wav_compare_api_round_trip(stable_keys):
    samples = tone(6000)
    cover = wav_bytes(samples, nchannels=1, sampwidth=2, framerate=8000)
    stego = encode_wav(cover, num_lsb=2, data=b"api wav test", offset=8)
    client = app.test_client()
    res = client.post(
        "/api/compare/audio",
        data={"cover_file": (io.BytesIO(cover), "cover.wav"), "stego_file": (io.BytesIO(stego), "stego.wav")},
    )
    assert res.status_code == 200
    assert res.json["stats"]["changed_samples"] > 0
