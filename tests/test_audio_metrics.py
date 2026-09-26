"""Tests for audio comparison metrics (AUD-003).

Values are checked against hand-calculable cases so a reviewer can verify the
maths independently, not just trust the code.
"""

import io
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from stego import audio_lsb, audio_metrics as m
from stego.bitstream import StegoStream
from app import _audio_metrics_json, app


def test_identical_signals_have_no_distortion():
    x = np.array([100, -200, 300, -400], dtype=np.int16)
    result = m.compare(x, x.copy())
    assert result.changed_samples == 0
    assert result.mse == 0.0
    assert result.snr_db == float("inf")


def test_changed_sample_count():
    cover = np.array([0, 0, 0, 0], dtype=np.int16)
    stego = np.array([1, 0, 1, 0], dtype=np.int16)  # two samples changed
    assert m.changed_sample_count(cover, stego) == 2


def test_mse_known_value():
    # diffs = [1, 2], squared = [1, 4], mean = 2.5
    cover = np.array([10, 20], dtype=np.int16)
    stego = np.array([11, 22], dtype=np.int16)
    assert m.mean_squared_error(cover, stego) == pytest.approx(2.5)


def test_mse_does_not_overflow_int16():
    # Difference of 65535 would overflow int16 if not promoted to float first.
    cover = np.array([32767], dtype=np.int16)
    stego = np.array([-32768], dtype=np.int16)
    expected = (32767.0 - (-32768.0)) ** 2
    assert m.mean_squared_error(cover, stego) == pytest.approx(expected)


def test_snr_known_value():
    # signal power = mean([100^2, 100^2]) = 10000
    # noise power  = mean([1^2, 1^2]) = 1
    # SNR = 10*log10(10000/1) = 40 dB
    cover = np.array([100, -100], dtype=np.int16)
    stego = np.array([101, -99], dtype=np.int16)
    assert m.snr_db(cover, stego) == pytest.approx(40.0, abs=1e-6)
    # a cover with real signal power is measured against itself, so this is a
    # true SNR and is shown without a qualifier
    result = m.compare(cover, stego)
    assert result.snr_reference == m.SNR_REFERENCE_SIGNAL
    assert result.snr_display == "40.0 dB"


def test_snr_infinite_when_identical():
    x = np.array([1, 2, 3], dtype=np.int16)
    assert m.snr_db(x, x.copy()) == float("inf")


def test_snr_silent_original_stays_finite():
    cover = np.zeros(4, dtype=np.int16)
    stego = np.array([1, 0, 0, 0], dtype=np.int16)
    # Should not raise or return inf; uses full-scale reference.
    value = m.snr_db(cover, stego)
    assert np.isfinite(value)


# --- the SNR reference must be reported, not silently substituted -----------


def test_silent_cover_is_labelled_as_not_a_true_snr():
    cover = np.zeros(4, dtype=np.int16)
    stego = np.array([1, 0, 0, 0], dtype=np.int16)
    value, reference = m.snr_db_with_reference(cover, stego)
    assert reference == m.SNR_REFERENCE_FULL_SCALE
    assert np.isfinite(value)

    display = m.compare(cover, stego).snr_display
    assert "full scale" in display
    assert "not a true SNR" in display


def test_silent_cover_reference_follows_the_sample_dtype():
    # The stand-in reference is full scale for the carrier's own dtype, so a
    # 32-bit cover is not measured against a 16-bit reference. Same noise, wider
    # dtype, so the int32 figure must be the larger of the two.
    noise = [1, 0, 0, 0]
    snr16 = m.snr_db(np.zeros(4, dtype=np.int16), np.array(noise, dtype=np.int16))
    snr32 = m.snr_db(np.zeros(4, dtype=np.int32), np.array(noise, dtype=np.int32))

    # int16 result is unchanged: full scale 32768, noise power 0.25.
    assert snr16 == pytest.approx(10.0 * np.log10(32768.0 ** 2 / 0.25), abs=1e-9)
    assert snr32 == pytest.approx(10.0 * np.log10(2147483648.0 ** 2 / 0.25), abs=1e-9)
    assert snr32 > snr16


def test_identical_signals_are_labelled_rather_than_printed_as_a_number():
    x = np.array([1, 2, 3], dtype=np.int16)
    result = m.compare(x, x.copy())
    assert result.snr_reference == m.SNR_REFERENCE_NONE
    assert result.snr_db == float("inf")
    assert "identical" in result.snr_display


def test_higher_bit_depth_lowers_snr():
    # More bits changed -> more noise -> lower SNR. Verified with the real carrier.
    rng = np.random.default_rng(2)
    samples = rng.integers(-3000, 3000, size=2000, dtype=np.int16)
    carrier = audio_lsb.AudioCarrier(
        array=samples, nchannels=1, sampwidth=2, framerate=44100, nframes=2000
    )
    payload = b"x" * 100

    def embed(num_lsb):
        stego = carrier.array.copy()
        StegoStream(stego, 0, num_lsb).write(payload)
        return stego

    snr_1bit = m.snr_db(carrier.array, embed(1))
    snr_8bit = m.snr_db(carrier.array, embed(8))
    assert snr_1bit > snr_8bit


def test_mismatched_shapes_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.array([1, 2], dtype=np.int16), np.array([1], dtype=np.int16))


def test_empty_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.array([], dtype=np.int16), np.array([], dtype=np.int16))


def test_changed_fraction():
    cover = np.zeros(10, dtype=np.int16)
    stego = cover.copy()
    stego[:3] = 1
    result = m.compare(cover, stego)
    assert result.changed_fraction == pytest.approx(0.3)


def test_mismatched_dtypes_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.array([1, 2], dtype=np.int16), np.array([1, 2], dtype=np.int32))


def test_float_samples_rejected():
    with pytest.raises(m.MetricsError):
        m.compare(np.zeros(3, dtype=np.float32), np.array([0.1, 0, 0], dtype=np.float32))


# --- largest single-sample change ----------------------------------------


def test_max_sample_change_known_value():
    # |diffs| = [1, 3, 0] -> 3
    cover = np.array([10, 20, -5], dtype=np.int16)
    stego = np.array([11, 17, -5], dtype=np.int16)
    assert m.compare(cover, stego).max_sample_change == 3


@pytest.mark.parametrize("dtype, lim", [(np.int16, 2**15), (np.int32, 2**31)])
def test_max_sample_change_within_lsb_limit(dtype, lim):
    # LSB replacement only rewrites the low num_lsb bits, so no sample can move
    # by more than 2**num_lsb - 1, negative samples included.
    rng = np.random.default_rng(5)
    cover = rng.integers(-lim, lim, size=16000, dtype=dtype)
    payload = rng.integers(0, 256, size=1500, dtype=np.uint8).tobytes()  # 12000 samples at 1 LSB
    for num_lsb in range(1, 9):
        stego = cover.copy()
        StegoStream(stego, 0, num_lsb).write(payload)
        assert 0 < m.compare(cover, stego).max_sample_change <= (1 << num_lsb) - 1


# --- chunked pass must agree with the whole-array formulas ------------------


@pytest.mark.parametrize("dtype, lim", [(np.int16, 2**15), (np.int32, 2**31)])
def test_chunked_pass_matches_whole_array_formulas(monkeypatch, dtype, lim):
    # A tiny chunk forces many chunk boundaries, including a short last chunk.
    monkeypatch.setattr(m, "_CHUNK_SAMPLES", 7)
    rng = np.random.default_rng(11)
    cover = rng.integers(-lim, lim, size=1001, dtype=dtype)
    stego = cover.copy()
    stego[::3] ^= 5

    diff = cover.astype(np.float64) - stego.astype(np.float64)
    mse = np.mean(diff ** 2)
    snr = 10.0 * np.log10(np.mean(cover.astype(np.float64) ** 2) / mse)

    result = m.compare(cover, stego)
    assert result.changed_samples == np.count_nonzero(diff)
    assert result.mse == pytest.approx(mse, rel=1e-12)
    assert result.snr_db == pytest.approx(snr, abs=1e-9)
    assert result.max_sample_change == np.abs(diff).max()


# --- wiring: the Compare page's /api/compare response -----------------------


def _wav_bytes(samples, width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(44100)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def _png_bytes(pixels):
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format="PNG")
    return buf.getvalue()


def _post_compare(cover_type, original, stego, name):
    response = app.test_client().post(
        "/api/compare",
        data={
            "cover_type": cover_type,
            "original_file": (io.BytesIO(original), f"original.{name}"),
            "stego_file": (io.BytesIO(stego), f"stego.{name}"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    # parsed the way the browser's res.json() does: NaN/Infinity would fail
    return json.loads(
        response.get_data(as_text=True),
        parse_constant=lambda name: pytest.fail(f"non-standard JSON constant {name}"),
    )


def test_compare_api_adds_audio_metrics():
    samples = np.random.default_rng(3).integers(-8000, 8000, size=20000, dtype=np.int16)
    stego = samples.copy()
    StegoStream(stego, 0, 2).write(b"hello metrics" * 20)

    result = _post_compare("audio", _wav_bytes(samples), _wav_bytes(stego), "wav")

    expected = _audio_metrics_json(m.compare(samples, stego))
    assert result["audio_metrics"] == expected
    assert expected["changed_sample_count"] > 0
    assert expected["snr_reference"] == m.SNR_REFERENCE_SIGNAL
    assert 0 < expected["max_sample_change"] <= 3  # 2 LSBs
    # agrees with the paired measurements comparison.py already reports
    assert result["changed_values"] == expected["changed_sample_count"]
    assert result["max_absolute_difference"] == expected["max_sample_change"]


def test_compare_api_identical_pair_sends_null_snr_not_infinity():
    samples = np.random.default_rng(6).integers(-8000, 8000, size=2000, dtype=np.int16)
    wav_bytes = _wav_bytes(samples)

    metrics = _post_compare("audio", wav_bytes, wav_bytes, "wav")["audio_metrics"]

    assert metrics["snr_db"] is None
    assert metrics["snr_reference"] == m.SNR_REFERENCE_NONE
    assert "identical" in metrics["snr_display"]
    assert _audio_metrics_json(None) is None


def test_compare_api_image_has_no_audio_metrics():
    pixels = np.random.default_rng(4).integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    changed = pixels.copy()
    changed[0, 0, 0] ^= 1

    result = _post_compare("image", _png_bytes(pixels), _png_bytes(changed), "png")

    assert "audio_metrics" not in result
